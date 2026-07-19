"""Tests for media ingestion (change video-ingestion).

Authored in the `api_gateway` package layout (CI/container). No network, no ffmpeg, no Whisper: every
external seam (`extract_audio`, `extract_frames`, `_transcribe_file`, `_ytdlp_subtitles`, `_ytdlp_audio`,
vision, embeddings) is monkeypatched. Covers tasks.md §4.2/§4.3/§4.4.
"""
import io
import os

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("FASTAPI_GM_API_KEY", "test-key-123")
os.environ.setdefault("FASTAPI_API_KEY", "test-key-123")
os.environ.setdefault("OPENAI_API_KEY", "test-openai")

import pytest
from sqlalchemy import create_engine, text

from api_gateway.routers import _media
from api_gateway.routers import _extract as ex
from api_gateway.routers import rag as rag_mod
from api_gateway.routers import strategy as st

H = {"X-API-Key": "test-key-123"}

_DDL_CHUNKS = """
CREATE TABLE document_chunks (
  id INTEGER PRIMARY KEY AUTOINCREMENT, source_type TEXT NOT NULL, source_id TEXT,
  source_name TEXT NOT NULL, chunk_index INTEGER NOT NULL, chunk_text TEXT NOT NULL,
  embedding TEXT, metadata TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)
"""
_DDL_SUGG = ("CREATE TABLE daily_suggestions (id INTEGER PRIMARY KEY AUTOINCREMENT, "
             "fecha TEXT, tag TEXT, titulo TEXT, cuerpo TEXT, estado TEXT, ref TEXT)")
_DDL_INBOX = ("CREATE TABLE inbox_items (id INTEGER PRIMARY KEY AUTOINCREMENT, "
              "tipo TEXT, texto TEXT, origen TEXT, procesado BOOLEAN)")


def _fake_embed(text_in):
    t = (text_in or "").lower()
    return [float(t.count("alfa") + 1), float(t.count("beta") + 1), float(len(t) % 7)]


class _FakeAnalysisClient:
    class _Comp:
        def create(self, **kw):
            class R:  # noqa
                pass
            r = R(); ch = R(); msg = R()
            msg.content = "Resumen de prueba."; ch.message = msg; r.choices = [ch]
            return r

    def __init__(self):
        class Chat:  # noqa
            pass
        self.chat = Chat(); self.chat.completions = _FakeAnalysisClient._Comp()


# ── pure helpers ────────────────────────────────────────────────────────────────
def test_is_video_url():
    assert _media.is_video_url("https://www.youtube.com/watch?v=abc")
    assert _media.is_video_url("https://youtu.be/abc")
    assert _media.is_video_url("https://vimeo.com/123")
    assert not _media.is_video_url("https://lafalla.co/politica.html")
    assert not _media.is_video_url("")


def test_is_media_file():
    assert _media.is_media_file("clip.mp4", "")
    assert _media.is_media_file("nota.ogg", "audio/ogg")
    assert _media.is_media_file("x", "video/mp4")
    assert not _media.is_media_file("doc.pdf", "application/pdf")


def test_vtt_to_text_strips_timestamps():
    vtt = "WEBVTT\n\n1\n00:00:01.000 --> 00:00:03.000\nHola equipo\n\n2\n00:00:03.000 --> 00:00:05.000\nHola equipo\nNuevo punto"
    out = _media._vtt_to_text(vtt)
    assert "Hola equipo" in out and "-->" not in out and "WEBVTT" not in out
    assert out.count("Hola equipo") == 1  # consecutive dupes collapsed


# ── transcribe_bytes ────────────────────────────────────────────────────────────
def test_transcribe_audio_passthrough_no_ffmpeg(monkeypatch):
    called = {"extract_audio": False}
    monkeypatch.setattr(_media, "extract_audio", lambda s: called.__setitem__("extract_audio", True) or s)
    monkeypatch.setattr(_media, "_transcribe_file", lambda p: "hola desde el audio")
    out = _media.transcribe_bytes(b"small audio bytes", "nota.ogg", "audio/ogg")
    assert out == "hola desde el audio"
    assert called["extract_audio"] is False  # small audio went straight to Whisper


def test_transcribe_video_uses_ffmpeg(monkeypatch):
    monkeypatch.setattr(_media, "extract_audio", lambda s: s + ".16k.m4a")
    monkeypatch.setattr(_media, "_transcribe_file", lambda p: "audio del video")
    out = _media.transcribe_bytes(b"video bytes", "clip.mp4", "video/mp4")
    assert out == "audio del video"


def test_transcribe_no_audio_is_honest(monkeypatch):
    monkeypatch.setattr(_media, "extract_audio", lambda s: None)
    assert _media.transcribe_bytes(b"video without audio", "silent.mp4", "video/mp4") == ""


def test_transcribe_oversize_is_honest(monkeypatch):
    monkeypatch.setattr(_media, "VIDEO_MAX_BYTES", 5)
    assert _media.transcribe_bytes(b"way too big", "big.mp4", "video/mp4") == ""


def test_transcribe_file_openai_fallback_when_no_groq(monkeypatch, tmp_path):
    """No GROQ key -> OpenAI whisper-1 with the OPENAI_API_KEY already present in prod."""
    monkeypatch.setattr(_media, "GROQ_API_KEY", "")
    monkeypatch.setattr(_media, "TRANSCRIBE_PROVIDER", "")
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    seen = {}

    class _Tr:
        def create(self, **kw):
            seen["model"] = kw.get("model")
            class R:  # noqa
                text = "transcripcion via openai"
            return R()

    class _Client:
        def __init__(self, *a, **k):
            class Audio:  # noqa
                pass
            self.audio = Audio(); self.audio.transcriptions = _Tr()

    import openai
    monkeypatch.setattr(openai, "OpenAI", _Client)
    f = tmp_path / "a.m4a"; f.write_bytes(b"audio bytes")
    out = _media._transcribe_file(str(f))
    assert out == "transcripcion via openai"
    assert seen["model"] == "whisper-1"


# ── video_to_text (transcript + frames) ─────────────────────────────────────────
def test_video_to_text_transcript_and_frames(monkeypatch, tmp_path):
    monkeypatch.setattr(_media, "extract_audio", lambda s: s)
    monkeypatch.setattr(_media, "_transcribe_file", lambda p: "esto dice el audio")
    monkeypatch.setattr(_media, "VIDEO_FRAMES", True)

    def fake_frames(src, n):
        paths = []
        for i in range(2):
            p = tmp_path / f"frame{i}.jpg"
            p.write_bytes(b"fakejpgbytes")
            paths.append(str(p))
        return paths

    monkeypatch.setattr(_media, "extract_frames", fake_frames)
    monkeypatch.setattr(ex, "extract_image", lambda data, content_type="": "TEXTO EN PANTALLA")

    out = _media.video_to_text(b"video bytes", "clip.mp4", "video/mp4")
    assert "TRANSCRIPCIÓN" in out and "esto dice el audio" in out
    assert "TEXTO EN PANTALLA" in out and "Fotograma 1" in out


def test_video_to_text_frames_off(monkeypatch):
    monkeypatch.setattr(_media, "extract_audio", lambda s: s)
    monkeypatch.setattr(_media, "_transcribe_file", lambda p: "solo audio")
    monkeypatch.setattr(_media, "VIDEO_FRAMES", False)
    out = _media.video_to_text(b"v", "c.mp4", "video/mp4")
    assert "solo audio" in out and "Fotograma" not in out


def test_video_to_text_unreadable_is_empty(monkeypatch):
    monkeypatch.setattr(_media, "extract_audio", lambda s: None)
    monkeypatch.setattr(_media, "VIDEO_FRAMES", False)
    assert _media.video_to_text(b"v", "c.mp4", "video/mp4") == ""


# ── media_url_to_text (yt-dlp) ──────────────────────────────────────────────────
def test_url_subtitles_preferred(monkeypatch):
    monkeypatch.setattr(_media, "_ytdlp_subtitles", lambda u: "subtitulos reales del video")
    monkeypatch.setattr(_media, "_ytdlp_audio", lambda u: pytest.fail("should not download audio"))
    assert _media.media_url_to_text("https://youtu.be/x") == "subtitulos reales del video"


def test_url_audio_fallback(monkeypatch, tmp_path):
    monkeypatch.setattr(_media, "_ytdlp_subtitles", lambda u: None)
    audio = tmp_path / "a.m4a"; audio.write_bytes(b"audio bytes")
    monkeypatch.setattr(_media, "_ytdlp_audio", lambda u: str(audio))
    monkeypatch.setattr(_media, "transcribe_bytes", lambda data, filename="", content_type="": "transcrito del audio")
    assert _media.media_url_to_text("https://youtu.be/x") == "transcrito del audio"


def test_url_failure_is_honest(monkeypatch):
    monkeypatch.setattr(_media, "_ytdlp_subtitles", lambda u: None)
    monkeypatch.setattr(_media, "_ytdlp_audio", lambda u: None)
    assert _media.media_url_to_text("https://youtu.be/x") == ""
    assert _media.media_url_to_text("") == ""


# ── endpoint + DB ───────────────────────────────────────────────────────────────
def _setup_db(tmp_path, monkeypatch):
    db = tmp_path / "ing.db"
    url = f"sqlite:///{db.as_posix()}"
    eng = create_engine(url)
    with eng.begin() as c:
        c.execute(text(_DDL_CHUNKS)); c.execute(text(_DDL_SUGG)); c.execute(text(_DDL_INBOX))
    monkeypatch.setattr(st, "DATABASE_URL", url)
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setattr(rag_mod, "get_embedding", _fake_embed)
    monkeypatch.setattr(st, "_analysis_client_model", lambda: (_FakeAnalysisClient(), "gpt-4o-mini"))
    return url, eng


def _client():
    from fastapi.testclient import TestClient
    from api_gateway.main import app
    return TestClient(app)


def test_ingest_video_file_indexes(tmp_path, monkeypatch):
    url, eng = _setup_db(tmp_path, monkeypatch)
    monkeypatch.setattr(_media, "media_to_text", lambda data, filename="", content_type="": "TRANSCRIPCIÓN:\nreunion sobre el rodaje en el eje cafetero")
    r = _client().post("/api/strategy/ingest-resource", headers=H, data={"intent": "obs"},
                       files={"file": ("reunion.mp4", b"fakevideobytes", "video/mp4")})
    assert r.status_code == 200, r.text
    assert r.json()["chunks_indexed"] >= 1
    with eng.connect() as c:
        n = c.execute(text("SELECT COUNT(*) FROM document_chunks WHERE source_name='reunion.mp4'")).scalar()
    assert n >= 1


def test_ingest_video_url_indexes(tmp_path, monkeypatch):
    url, eng = _setup_db(tmp_path, monkeypatch)
    monkeypatch.setattr(_media, "media_url_to_text", lambda u: "subtitulos: presentacion de La Falla")
    r = _client().post("/api/strategy/ingest-resource", headers=H,
                       data={"intent": "obs", "url": "https://www.youtube.com/watch?v=abc"})
    assert r.status_code == 200, r.text
    assert r.json()["chunks_indexed"] >= 1


def test_ingest_media_requires_key():
    r = _client().post("/api/strategy/ingest-resource",
                       data={"intent": "obs", "url": "https://youtu.be/x"})
    assert r.status_code in (401, 403)

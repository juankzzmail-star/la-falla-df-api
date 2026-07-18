"""Media extractor: video/audio files and video links -> indexable text (change video-ingestion).

Pipeline (all external calls are isolated in small functions so tests can mock them):
- transcribe_bytes(): audio track -> Groq Whisper (whisper-large-v3, the only sanctioned Groq use).
- video_to_text(): transcript + optionally a few key frames described by the vision model (reused from
  _extract.extract_image).
- media_url_to_text(): yt-dlp -> existing captions if any, else download audio -> transcribe.

ffmpeg comes from the imageio-ffmpeg pip wheel (design D1) — keeps the deploy pip-only; falls back to a
PATH ffmpeg. Honesty rule (inherited): unreadable media returns "" so the caller reports it instead of
fabricating a transcript. Temp files are always cleaned up.
"""
import glob
import os
import re
import tempfile

GROQ_API_KEY  = os.environ.get("GROQ_API_KEY", "")
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "whisper-large-v3")

# Transcription provider (design D2). Auto = Groq if GROQ_API_KEY (free/fast), else OpenAI `whisper-1`
# using the OPENAI_API_KEY already present in prod (so transcription works without a new secret). Force
# with TRANSCRIBE_PROVIDER=groq|openai.
TRANSCRIBE_PROVIDER  = os.environ.get("TRANSCRIBE_PROVIDER", "").lower()
OPENAI_WHISPER_MODEL = os.environ.get("OPENAI_WHISPER_MODEL", "whisper-1")

# Caps (design D5). Synchronous v1: refuse media above the size cap honestly.
VIDEO_MAX_BYTES = int(os.environ.get("VIDEO_MAX_BYTES", str(300 * 1024 * 1024)))  # 300 MB upload cap
WHISPER_MAX_BYTES = int(os.environ.get("WHISPER_MAX_BYTES", str(24 * 1024 * 1024)))  # Groq ~25 MB
FFMPEG_TIMEOUT = int(os.environ.get("FFMPEG_TIMEOUT", "300"))

# Key frames (design D3): on by default, small cap; toggle/cap via env.
VIDEO_FRAMES     = os.environ.get("VIDEO_FRAMES", "1").lower() not in ("0", "false", "no", "off")
VIDEO_MAX_FRAMES = int(os.environ.get("VIDEO_MAX_FRAMES", "4"))

VIDEO_EXTS = (".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v", ".mpeg", ".mpg")
AUDIO_EXTS = (".mp3", ".wav", ".m4a", ".ogg", ".opus", ".aac", ".flac", ".wma")
VIDEO_HOSTS = ("youtube.com", "youtu.be", "vimeo.com", "tiktok.com", "dailymotion.com", "twitch.tv")


# ── helpers ───────────────────────────────────────────────────────────────────
def _ffmpeg_exe():
    """Resolve an ffmpeg binary: imageio-ffmpeg wheel first (D1), then PATH."""
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        from shutil import which
        return which("ffmpeg")


def _run_ffmpeg(args) -> bool:
    import subprocess
    exe = _ffmpeg_exe()
    if not exe:
        return False
    try:
        r = subprocess.run([exe, *args], capture_output=True, timeout=FFMPEG_TIMEOUT)
        return r.returncode == 0
    except Exception:
        return False


def _suffix(name: str) -> str:
    ext = os.path.splitext(name or "")[1]
    return ext if ext else ".bin"


def _write_temp(data: bytes, suffix: str) -> str:
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)
    return path


def _cleanup(paths):
    for p in paths:
        if not p:
            continue
        try:
            os.remove(p)
        except Exception:
            pass


def _vtt_to_text(vtt: str) -> str:
    """Strip WebVTT/SRT timestamps, cue numbers and tags; de-duplicate consecutive lines."""
    out, prev = [], None
    for raw in (vtt or "").splitlines():
        line = raw.strip()
        if not line or line == "WEBVTT" or "-->" in line or line.isdigit():
            continue
        line = re.sub(r"<[^>]+>", "", line)  # inline tags
        line = re.sub(r"^\d+:\d+:\d+[.,]\d+\s*", "", line)
        if line and line != prev:
            out.append(line)
            prev = line
    return "\n".join(out).strip()


# ── transcription (mockable seams) ──────────────────────────────────────────────
def extract_audio(src_path: str):
    """ffmpeg -> 16 kHz mono audio for Whisper. Returns the audio path or None."""
    out = src_path + ".16k.m4a"
    ok = _run_ffmpeg(["-i", src_path, "-vn", "-ac", "1", "-ar", "16000", "-b:a", "32k", "-y", out])
    return out if ok and os.path.exists(out) and os.path.getsize(out) > 0 else None


def extract_frames(src_path: str, n: int):
    """ffmpeg -> up to n key frames (scene change, then a fallback thumbnail). Returns image paths."""
    if n <= 0:
        return []
    pat = src_path + ".frame%03d.jpg"
    _run_ffmpeg(["-i", src_path, "-vf", "select=gt(scene\\,0.4),scale=640:-1",
                 "-frames:v", str(n), "-vsync", "vfr", "-y", pat])
    frames = sorted(glob.glob(src_path + ".frame*.jpg"))
    if not frames:  # fallback: a single thumbnail near the start
        thumb = src_path + ".frame001.jpg"
        if _run_ffmpeg(["-ss", "1", "-i", src_path, "-frames:v", "1", "-vf", "scale=640:-1", "-y", thumb]) \
                and os.path.exists(thumb):
            frames = [thumb]
    return frames[:n]


def _transcribe_file(audio_path: str) -> str:
    """Transcribe a local audio file via the configured provider. "" on any failure (honest).

    Auto: Groq Whisper if GROQ_API_KEY is set (free/fast), else OpenAI `whisper-1` with OPENAI_API_KEY.
    """
    provider = TRANSCRIBE_PROVIDER or ("groq" if GROQ_API_KEY else "openai")
    try:
        from openai import OpenAI
        if provider == "groq" and GROQ_API_KEY:
            client, model = OpenAI(api_key=GROQ_API_KEY, base_url=GROQ_BASE_URL), WHISPER_MODEL
        else:
            key = os.environ.get("OPENAI_API_KEY", "")
            if not key:
                return ""
            client, model = OpenAI(api_key=key), OPENAI_WHISPER_MODEL
        with open(audio_path, "rb") as f:
            t = client.audio.transcriptions.create(
                model=model,
                file=(os.path.basename(audio_path), f, "application/octet-stream"),
                language="es",
            )
        return (getattr(t, "text", "") or "").strip()
    except Exception:
        return ""


def transcribe_bytes(data: bytes, filename: str = "", content_type: str = "") -> str:
    """Bytes (audio or video) -> transcript. Audio under the Whisper limit goes straight to Whisper (keeps
    the voice-note path working without ffmpeg); otherwise ffmpeg extracts/compresses the audio first."""
    if not data:
        return ""
    if len(data) > VIDEO_MAX_BYTES:
        print(f"[_media] media demasiado grande: {len(data)} > {VIDEO_MAX_BYTES}")
        return ""
    name = (filename or "").lower()
    ctype = (content_type or "").lower()
    is_audio = ctype.startswith("audio/") or name.endswith(AUDIO_EXTS)

    src = _write_temp(data, _suffix(name))
    audio_path = None
    try:
        if is_audio and len(data) <= WHISPER_MAX_BYTES:
            audio_path = src  # already audio and small enough — no ffmpeg needed
        else:
            audio_path = extract_audio(src)
        if not audio_path:
            return ""
        return _transcribe_file(audio_path)
    finally:
        _cleanup([src, audio_path if audio_path != src else None])


# ── video (transcript + optional frames) ────────────────────────────────────────
def video_to_text(data: bytes, filename: str = "", content_type: str = "") -> str:
    """Transcript + (optional) vision descriptions of a few key frames, combined for indexing."""
    transcript = transcribe_bytes(data, filename, content_type)

    frames_text = ""
    if VIDEO_FRAMES and data and len(data) <= VIDEO_MAX_BYTES:
        src = _write_temp(data, _suffix(filename))
        frame_paths = []
        try:
            frame_paths = extract_frames(src, VIDEO_MAX_FRAMES)
            if frame_paths:
                from ._extract import extract_image
                descs = []
                for fp in frame_paths:
                    try:
                        with open(fp, "rb") as fh:
                            d = extract_image(fh.read(), "image/jpeg")
                        if d.strip():
                            descs.append(d.strip())
                    except Exception:
                        continue
                if descs:
                    frames_text = "\n\n".join(f"[Fotograma {i+1}] {d}" for i, d in enumerate(descs))
        finally:
            _cleanup([src, *frame_paths])

    parts = []
    if transcript.strip():
        parts.append("TRANSCRIPCIÓN:\n" + transcript.strip())
    if frames_text.strip():
        parts.append("CONTENIDO EN PANTALLA (fotogramas):\n" + frames_text.strip())
    return "\n\n".join(parts).strip()


# ── links (yt-dlp) ───────────────────────────────────────────────────────────────
def is_video_url(url: str) -> bool:
    u = (url or "").lower()
    if any(h in u for h in VIDEO_HOSTS):
        return True
    if "drive.google.com" in u and ("/file/" in u or "/video" in u):
        return True
    return False


def _ytdlp_subtitles(url: str):
    """Download existing/auto captions (es/en) and return their text, or None."""
    try:
        import yt_dlp
        d = tempfile.mkdtemp()
        opts = {
            "skip_download": True, "writesubtitles": True, "writeautomaticsub": True,
            "subtitleslangs": ["es", "en"], "subtitlesformat": "vtt",
            "outtmpl": os.path.join(d, "%(id)s.%(ext)s"), "quiet": True, "no_warnings": True,
        }
        with yt_dlp.YoutubeDL(opts) as y:
            y.download([url])
        vtts = glob.glob(os.path.join(d, "*.vtt"))
        if not vtts:
            return None
        with open(vtts[0], encoding="utf-8", errors="replace") as fh:
            return _vtt_to_text(fh.read()) or None
    except Exception:
        return None


def _ytdlp_audio(url: str):
    """Download the best audio track to a temp file; return its path or None."""
    try:
        import yt_dlp
        d = tempfile.mkdtemp()
        opts = {"format": "bestaudio/best", "outtmpl": os.path.join(d, "%(id)s.%(ext)s"),
                "quiet": True, "no_warnings": True}
        with yt_dlp.YoutubeDL(opts) as y:
            y.download([url])
        files = [f for f in glob.glob(os.path.join(d, "*")) if os.path.isfile(f)]
        return files[0] if files else None
    except Exception:
        return None


def media_url_to_text(url: str) -> str:
    """Video link -> captions if available, else downloaded audio -> transcript. "" on failure (honest)."""
    url = (url or "").strip()
    if not url:
        return ""
    subs = _ytdlp_subtitles(url)
    if subs and subs.strip():
        return subs.strip()
    audio_path = _ytdlp_audio(url)
    if not audio_path:
        return ""
    try:
        with open(audio_path, "rb") as f:
            data = f.read()
        return transcribe_bytes(data, os.path.basename(audio_path), "audio/unknown")
    finally:
        _cleanup([audio_path])


# ── dispatch helpers used by strategy.py ────────────────────────────────────────
def is_media_file(filename: str, content_type: str = "") -> bool:
    n = (filename or "").lower()
    c = (content_type or "").lower()
    return c.startswith(("audio/", "video/")) or n.endswith(VIDEO_EXTS) or n.endswith(AUDIO_EXTS)


def media_to_text(data: bytes, filename: str = "", content_type: str = "") -> str:
    n = (filename or "").lower()
    c = (content_type or "").lower()
    is_video = c.startswith("video/") or n.endswith(VIDEO_EXTS)
    return video_to_text(data, filename, content_type) if is_video else transcribe_bytes(data, filename, content_type)

"""Tests for the Drive attach path (change hub-drive-attach). The _gdrive seam is fully mocked —
no network. Covers: parse_file_id variants; excluded subtree -> 403 nothing processed; unsupported
extension -> 400 with the accepted list; happy path (.txt, intent pend) through the REAL
ingest_resource pipeline -> inbox row written; unconfigured seam -> 503.
"""
import os

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("FASTAPI_GM_API_KEY", "test-key-123")
os.environ.setdefault("FASTAPI_API_KEY", "test-key-123")

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from api_gateway.main import app
from api_gateway.routers import _gdrive
from api_gateway.routers import strategy as strategy_mod

H = {"X-API-Key": "test-key-123"}


def test_parse_file_id_variants():
    fid = "1AbC_dEfGhIjKlMnOpQrStUvWxYz1234"
    assert _gdrive.parse_file_id(f"https://drive.google.com/file/d/{fid}/view?usp=sharing") == fid
    assert _gdrive.parse_file_id(f"https://docs.google.com/document/d/{fid}/edit") == fid
    assert _gdrive.parse_file_id(f"https://drive.google.com/open?id={fid}") == fid
    assert _gdrive.parse_file_id(fid) == fid
    assert _gdrive.parse_file_id("https://lafalla.co/no-es-drive") is None
    assert _gdrive.parse_file_id("") is None


def test_excluded_subtree_refused(monkeypatch):
    def fake_fetch(link):
        raise HTTPException(403, "Archivo excluido: pertenece a la carpeta de datos personales "
                                 "(socios/prestadores), que el Centro de Gerencia no procesa.")
    monkeypatch.setattr(_gdrive, "fetch", fake_fetch)
    with TestClient(app) as c:
        r = c.post("/api/strategy/ingest-drive", headers=H,
                   json={"link": "https://drive.google.com/file/d/x123456789012345/view", "intent": "obs"})
    assert r.status_code == 403
    assert "datos personales" in r.json()["detail"]


def test_unsupported_extension_rejected(monkeypatch):
    monkeypatch.setattr(_gdrive, "fetch", lambda link: ("malware.exe", b"MZ..."))
    with TestClient(app) as c:
        r = c.post("/api/strategy/ingest-drive", headers=H,
                   json={"link": "1AbC_dEfGhIjKlMnOpQrStUvWxYz1234", "intent": "obs"})
    assert r.status_code == 400
    assert ".pdf" in r.json()["detail"]  # the accepted list is named


def test_unconfigured_seam_503(monkeypatch):
    monkeypatch.setattr(_gdrive, "fetch",
                        lambda link: (_ for _ in ()).throw(HTTPException(503, "Google Drive no configurado")))
    with TestClient(app) as c:
        r = c.post("/api/strategy/ingest-drive", headers=H,
                   json={"link": "1AbC_dEfGhIjKlMnOpQrStUvWxYz1234"})
    assert r.status_code == 503


def test_happy_path_pipes_into_real_pipeline(tmp_path, monkeypatch):
    """intent=pend needs no LLM: the Drive bytes must land in inbox_items via ingest_resource."""
    url = f"sqlite:///{tmp_path / 'drive.db'}"
    eng = create_engine(url)
    with eng.begin() as c:
        c.execute(text("CREATE TABLE inbox_items (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                       "tipo TEXT, texto TEXT, origen TEXT, procesado BOOLEAN)"))
    monkeypatch.setattr(strategy_mod, "DATABASE_URL", url)
    monkeypatch.setattr(_gdrive, "fetch", lambda link: ("acta-semanal.txt", b"Acta de la jornada."))
    with TestClient(app) as c:
        r = c.post("/api/strategy/ingest-drive", headers=H,
                   json={"link": "https://drive.google.com/file/d/1AbC_dEfGhIjKlMnOpQrStUvWx/view",
                         "intent": "pend"})
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True and "acta-semanal.txt" in r.json()["message"]
    with eng.connect() as c:
        row = c.execute(text("SELECT texto FROM inbox_items")).fetchone()
    assert row is not None and "acta-semanal.txt" in row[0]


def test_requires_api_key():
    with TestClient(app) as c:
        r = c.post("/api/strategy/ingest-drive", json={"link": "x"})
    assert r.status_code in (401, 403)

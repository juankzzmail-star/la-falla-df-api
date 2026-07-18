"""Director delegation (change delegate-director-tasks): tasks are pushed into each director's OWN
Google Tasks (domain-wide delegation, no password) and emailed from gerencia@; the inbound sync sweeps
ALL accounts (CEO + directors); the Gmail seam is honest-503 without creds. Seams are monkeypatched —
no network.
"""
import os

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("FASTAPI_GM_API_KEY", "test-key-123")
os.environ.setdefault("FASTAPI_API_KEY", "test-key-123")

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api_gateway.db import get_db
from api_gateway.main import app
from api_gateway.routers import _cascade, _gmail, _gtasks

H = {"X-API-Key": "test-key-123"}

_DDL = [
    "CREATE TABLE plans (id INTEGER PRIMARY KEY AUTOINCREMENT, pct_completado_real NUMERIC NOT NULL DEFAULT 0)",
    """CREATE TABLE tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT, plan_id INTEGER, titulo TEXT, area TEXT, responsable TEXT,
        estado TEXT NOT NULL DEFAULT 'pendiente', fecha_vencimiento DATE, fecha_completada DATE,
        peso_pct NUMERIC NOT NULL DEFAULT 0, google_task_id TEXT, google_calendar_event_id TEXT)""",
]


@pytest.fixture()
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    with engine.begin() as c:
        for d in _DDL:
            c.execute(text(d))
    TS = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override():
        db = TS()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override
    with TestClient(app) as cl:
        cl._engine = engine
        yield cl
    app.dependency_overrides.clear()


def test_gmail_seam_503_without_creds(monkeypatch):
    monkeypatch.delenv("GOOGLE_SERVICE_ACCOUNT_JSON", raising=False)
    with pytest.raises(HTTPException) as ei:
        _gmail.send_email(to="comercial@lafalla.co", subject="x", body_text="y")
    assert ei.value.status_code == 503


def test_sync_sweeps_all_director_accounts(client, monkeypatch):
    seen = []
    monkeypatch.setattr(_gtasks, "list_tasks", lambda **k: seen.append(k.get("subject")) or [])
    r = client.post("/api/tasks/sync-google", headers=H)
    assert r.status_code == 200, r.text
    assert r.json() == {"scanned": 0, "updated": 0}
    # swept the CEO + the 4 director accounts (the unique routing aliases)
    assert set(seen) == set(_cascade.DIRECTOR_ALIAS.values())
    assert "gerencia@lafalla.co" in seen and "comercial@lafalla.co" in seen


def test_import_google_creates_direct_tasks(client, monkeypatch):
    """change import-google-tasks: pull each account's Google Tasks into the Centro as direct tasks,
    mapping the account -> director/area and due -> fecha_vencimiento."""
    fake = {
        "comercial@lafalla.co": [
            {"google_task_id": "gi1", "title": "Cerrar feria", "status": "needsAction",
             "due": "2026-09-01T00:00:00.000Z", "completed": None, "notes": ""},
        ],
        "audiovisual@lafalla.co": [
            {"google_task_id": "gi2", "title": "Entregar corte", "status": "completed",
             "due": "2026-07-01T00:00:00.000Z", "completed": "2026-06-20T00:00:00.000Z", "notes": ""},
        ],
    }
    monkeypatch.setattr(_gtasks, "list_tasks", lambda **k: fake.get(k.get("subject"), []))
    r = client.post("/api/tasks/import-google", headers=H)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["imported"] == 2 and body["accounts"] == 5
    with client._engine.connect() as c:
        row = c.execute(text("SELECT titulo, responsable, area, estado, fecha_vencimiento "
                             "FROM tasks WHERE google_task_id='gi1'")).fetchone()
    assert row.responsable == "Juan Carlos" and row.area == "Comercial"
    assert str(row.fecha_vencimiento) == "2026-09-01" and row.estado == "pendiente"


def test_import_google_is_idempotent(client, monkeypatch):
    fake = [{"google_task_id": "gi9", "title": "T", "status": "needsAction",
             "due": None, "completed": None, "notes": ""}]
    monkeypatch.setattr(_gtasks, "list_tasks",
                        lambda **k: fake if k.get("subject") == "comercial@lafalla.co" else [])
    r1 = client.post("/api/tasks/import-google", headers=H).json()
    r2 = client.post("/api/tasks/import-google", headers=H).json()
    assert r1["imported"] == 1 and r2["imported"] == 0 and r2["updated"] == 1
    with client._engine.connect() as c:
        n = c.execute(text("SELECT COUNT(*) FROM tasks WHERE google_task_id='gi9'")).scalar()
    assert n == 1   # no duplicate on re-import


def test_insert_task_targets_director_list(monkeypatch):
    """insert_task forwards the impersonation subject (the director's account) to the seam."""
    captured = {}

    class _FakeTasks:
        def insert(self, tasklist, body):
            captured["tasklist"] = tasklist
            captured["title"] = body.get("title")

            class _Exec:
                def execute(self_inner):
                    return {"id": "dgid"}
            return _Exec()

    class _FakeSvc:
        def tasks(self):
            return _FakeTasks()

    monkeypatch.setattr(_gtasks, "_service", lambda subject=None: captured.update(subject=subject) or _FakeSvc())
    gid = _gtasks.insert_task("Tarea Beto", notes="n", subject="proyectos@lafalla.co")
    assert gid == "dgid"
    assert captured["subject"] == "proyectos@lafalla.co"   # impersonated the director, not the CEO

"""Google Tasks inbound reconcile + ownership routing (change google-tasks-dashboard).
The `_gtasks` seam is monkeypatched — no network, no real Google. Isolated in-memory SQLite with
raw DDL (the ORM Task carries cross-area FKs, so the endpoint uses raw SQL, mirrored here).
"""
import os
import types

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
from api_gateway.routers import _gtasks, _gmail, _cascade
from api_gateway.routers.tasks import route_outbound_task

H = {"X-API-Key": "test-key-123"}

_DDL = [
    "CREATE TABLE plans (id INTEGER PRIMARY KEY AUTOINCREMENT, pct_completado_real NUMERIC NOT NULL DEFAULT 0)",
    """CREATE TABLE tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT, plan_id INTEGER, titulo TEXT, area TEXT, responsable TEXT,
        estado TEXT NOT NULL DEFAULT 'pendiente', fecha_vencimiento DATE, fecha_completada DATE,
        peso_pct NUMERIC NOT NULL DEFAULT 0, google_task_id TEXT)""",
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


def _seed(client, gid="g1", estado="pendiente", peso=100):
    with client._engine.begin() as c:
        c.execute(text("INSERT INTO plans (id, pct_completado_real) VALUES (1, 0)"))
        c.execute(text("INSERT INTO tasks (plan_id, titulo, estado, peso_pct, google_task_id) "
                       "VALUES (1, 'T', :e, :p, :g)"), {"e": estado, "p": peso, "g": gid})


def _task(client, gid="g1"):
    with client._engine.connect() as c:
        return c.execute(text("SELECT estado, fecha_completada FROM tasks WHERE google_task_id=:g"),
                         {"g": gid}).fetchone()


# ── Auth ──────────────────────────────────────────────────────────────────────
def test_sync_google_requires_api_key(client):
    assert client.post("/api/tasks/sync-google").status_code in (401, 403)


# ── Inbound reconcile ─────────────────────────────────────────────────────────
def test_sync_reconciles_completed_task(client, monkeypatch):
    _seed(client, gid="g1")
    monkeypatch.setattr(_gtasks, "list_tasks", lambda **k: [
        {"google_task_id": "g1", "status": "completed", "completed": "2026-06-10T00:00:00.000Z",
         "title": "T", "due": None, "notes": ""},
    ])
    r = client.post("/api/tasks/sync-google", headers=H)
    assert r.status_code == 200, r.text
    assert r.json() == {"scanned": 1, "updated": 1}
    row = _task(client)
    assert row[0] == "completada" and str(row[1]) == "2026-06-10"
    with client._engine.connect() as c:
        pct = c.execute(text("SELECT pct_completado_real FROM plans WHERE id=1")).scalar()
    assert float(pct) == 100.0   # plan % recomputed from the now-completed task


def test_sync_ignores_unknown_and_already_done(client, monkeypatch):
    _seed(client, gid="g1", estado="completada")
    monkeypatch.setattr(_gtasks, "list_tasks", lambda **k: [
        {"google_task_id": "g1", "status": "completed", "completed": "2026-06-10T00:00:00.000Z"},
        {"google_task_id": "ZZZ", "status": "completed", "completed": "2026-06-10T00:00:00.000Z"},
    ])
    r = client.post("/api/tasks/sync-google", headers=H)
    assert r.json() == {"scanned": 2, "updated": 0}   # g1 already done, ZZZ unknown


# ── Honest 503 (seam unconfigured) ────────────────────────────────────────────
def test_seam_503_without_creds(monkeypatch):
    monkeypatch.delenv("GOOGLE_SERVICE_ACCOUNT_JSON", raising=False)
    with pytest.raises(HTTPException) as ei:
        _gtasks.list_ceo_tasks()
    assert ei.value.status_code == 503


# ── Ownership routing ─────────────────────────────────────────────────────────
def test_route_ceo_syncs_director_emits(monkeypatch):
    monkeypatch.setattr(_gtasks, "insert_task", lambda *a, **k: "gid123")

    ceo = types.SimpleNamespace(responsable="Clementino", titulo="X", area="Transversal",
                                plan_id=1, fecha_vencimiento=None, google_task_id=None,
                                google_calendar_event_id=None)
    r = route_outbound_task(ceo)
    assert r["routed"] == "ceo_gtasks" and ceo.google_task_id == "gid123"

    # change delegate-director-tasks: a director task is now delegated INTO the director's OWN Google
    # Tasks (impersonate their account, subject=alias) and emailed from gerencia@.
    calls = {}
    monkeypatch.setattr(_gtasks, "insert_task",
                        lambda *a, **k: calls.update(subject=k.get("subject")) or "dg1")
    monkeypatch.setattr(_gmail, "send_email",
                        lambda **k: calls.update(emailed_to=k.get("to")) or "m1")
    director = types.SimpleNamespace(responsable="Juan Carlos", titulo="Y", area="Comercial",
                                     plan_id=1, fecha_vencimiento=None, google_task_id=None,
                                     google_calendar_event_id=None)
    r2 = route_outbound_task(director)
    assert r2["routed"] == "director_emit"
    assert r2["alias"] == "comercial@lafalla.co"
    assert r2["google_task_id"] == "dg1"
    assert calls["subject"] == "comercial@lafalla.co"          # wrote into the director's Google Tasks
    assert calls.get("emailed_to") == "comercial@lafalla.co"   # emailed from gerencia@
    assert r2["emailed"] is True


def test_alias_map_covers_all_directors():
    assert _cascade.alias_for_director("Beto") == "proyectos@lafalla.co"
    assert _cascade.alias_for_director("Iván") == "audiovisual@lafalla.co"
    assert _cascade.alias_for_director("Quinaya") == "investigaciones@lafalla.co"

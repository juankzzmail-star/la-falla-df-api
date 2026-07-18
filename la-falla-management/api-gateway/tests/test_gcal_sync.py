"""Google Calendar seam (change google-calendar-dashboard). The `_gcal` seam is monkeypatched — no
network, no real Google. Isolated in-memory SQLite mirroring the prod `tasks` columns the endpoint
touches (incl. google_calendar_event_id).
"""
import os
import types
from datetime import date

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
from api_gateway.routers import _gcal
from api_gateway.routers.tasks import route_outbound_task

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


def _seed(client, venc="2026-09-01", evt=None):
    with client._engine.begin() as c:
        c.execute(text("INSERT INTO plans (id, pct_completado_real) VALUES (1, 0)"))
        c.execute(text(
            "INSERT INTO tasks (plan_id, titulo, area, responsable, estado, fecha_vencimiento, "
            "peso_pct, google_calendar_event_id) "
            "VALUES (1, 'Revisar caja', 'DC', 'Clementino', 'pendiente', :v, 100, :e)"),
            {"v": venc, "e": evt})


def _evt(client):
    with client._engine.connect() as c:
        return c.execute(text("SELECT google_calendar_event_id FROM tasks WHERE id=1")).scalar()


# ── Auth ──────────────────────────────────────────────────────────────────────
def test_sync_calendar_requires_api_key(client):
    assert client.post("/api/tasks/1/sync-calendar").status_code in (401, 403)


# ── Endpoint upsert ───────────────────────────────────────────────────────────
def test_sync_calendar_upserts_and_stores(client, monkeypatch):
    _seed(client)
    monkeypatch.setattr(_gcal, "upsert_event", lambda **k: "evt_123")
    r = client.post("/api/tasks/1/sync-calendar", headers=H)
    assert r.status_code == 200, r.text
    assert r.json() == {"task_id": 1, "google_calendar_event_id": "evt_123"}
    assert _evt(client) == "evt_123"


def test_sync_calendar_422_without_due_date(client, monkeypatch):
    _seed(client, venc=None)
    monkeypatch.setattr(_gcal, "upsert_event", lambda **k: "should_not_be_called")
    r = client.post("/api/tasks/1/sync-calendar", headers=H)
    assert r.status_code == 422


def test_sync_calendar_404_unknown(client):
    r = client.post("/api/tasks/999/sync-calendar", headers=H)
    assert r.status_code == 404


# ── Honest 503 (seam unconfigured) ────────────────────────────────────────────
def test_seam_503_without_creds(monkeypatch):
    monkeypatch.delenv("GOOGLE_SERVICE_ACCOUNT_JSON", raising=False)
    with pytest.raises(HTTPException) as ei:
        _gcal.upsert_event(summary="x", due_date=date(2026, 9, 1))
    assert ei.value.status_code == 503


# ── Ownership routing: CEO task mirrors to calendar; director task does not ────
def test_route_ceo_mirrors_calendar(monkeypatch):
    from api_gateway.routers import _gtasks
    monkeypatch.setattr(_gtasks, "insert_task", lambda *a, **k: "g1")
    monkeypatch.setattr(_gcal, "upsert_event", lambda **k: "evt_9")
    ceo = types.SimpleNamespace(responsable="Clementino", titulo="x", area="DC", plan_id=1,
                                google_task_id=None, google_calendar_event_id=None,
                                fecha_vencimiento=date(2026, 9, 1))
    r = route_outbound_task(ceo)
    assert r["routed"] == "ceo_gtasks"
    assert r.get("google_calendar_event_id") == "evt_9"
    assert ceo.google_calendar_event_id == "evt_9"


def test_route_director_no_calendar(monkeypatch):
    called = {"cal": False}
    monkeypatch.setattr(_gcal, "upsert_event",
                        lambda **k: called.__setitem__("cal", True) or "x")
    director = types.SimpleNamespace(responsable="Juan Carlos", titulo="x", area="DC", plan_id=1,
                                     google_task_id=None, google_calendar_event_id=None,
                                     fecha_vencimiento=date(2026, 9, 1))
    r = route_outbound_task(director)
    assert r["routed"] == "director_emit" and r["alias"] == "comercial@lafalla.co"
    assert called["cal"] is False

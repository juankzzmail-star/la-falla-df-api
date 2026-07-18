"""change connect-execution-strategy: link the directors' real imported tasks to the hito each one
advances. Gentil (LLM seam) proposes; only clear matches are linked (operational tasks left unlinked).
POST /tasks/link-hitos sets tasks.milestone_id so that task's completion feeds the hito's avance. The LLM
seam is monkeypatched -> no network. Isolated in-memory SQLite."""
import os

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("FASTAPI_GM_API_KEY", "test-key-123")
os.environ.setdefault("FASTAPI_API_KEY", "test-key-123")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api_gateway.db import get_db
from api_gateway.main import app
from api_gateway.routers import _cascade

H = {"X-API-Key": "test-key-123"}

_DDL = [
    """CREATE TABLE roadmap_milestones (
        id INTEGER PRIMARY KEY AUTOINCREMENT, titulo TEXT NOT NULL, orden INTEGER NOT NULL DEFAULT 0,
        estado TEXT NOT NULL DEFAULT 'pendiente', area TEXT, anio INTEGER, trimestre INTEGER,
        fecha_inicio TIMESTAMP, fecha_fin_planificada TIMESTAMP, fecha_completado TIMESTAMP,
        depends_on TEXT, version_id INTEGER, pct_completado NUMERIC NOT NULL DEFAULT 0,
        peso NUMERIC NOT NULL DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
    """CREATE TABLE tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT, plan_id INTEGER, milestone_id INTEGER, titulo TEXT,
        area TEXT, responsable TEXT, estado TEXT NOT NULL DEFAULT 'pendiente', google_task_id TEXT)""",
]


@pytest.fixture()
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    with engine.begin() as c:
        for ddl in _DDL:
            c.execute(text(ddl))
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


def test_generate_hito_links_for_tasks_validates_ids(monkeypatch):
    """The seam keeps only pairs whose ids exist; drops invented ids and duplicate tasks."""
    monkeypatch.setattr(_cascade, "_chat_json", lambda *a, **k: {"links": [
        {"task_id": 1, "milestone_id": 10},   # valid
        {"task_id": 1, "milestone_id": 11},   # duplicate task -> dropped
        {"task_id": 99, "milestone_id": 10},  # unknown task -> dropped
        {"task_id": 2, "milestone_id": 77},   # unknown hito -> dropped
    ]})
    out = _cascade.generate_hito_links_for_tasks(
        [{"id": 1, "titulo": "Guion"}, {"id": 2, "titulo": "Web"}],
        [{"id": 10, "titulo": "Circuito Audiovisual"}],
    )
    assert out == [{"task_id": 1, "milestone_id": 10}]


def test_link_hitos_endpoint_links_imported_tasks(client, monkeypatch):
    with client._engine.begin() as c:
        c.execute(text("INSERT INTO roadmap_milestones (id,titulo,estado) VALUES "
                       "(10,'Circuito Audiovisual','in_progress')"))
        c.execute(text("INSERT INTO tasks (id,titulo,plan_id,milestone_id,google_task_id) VALUES "
                       "(1,'Redacción del guion del documental',NULL,NULL,'g1'), "
                       "(2,'Pagar servicios de oficina',NULL,NULL,'g2')"))

    def fake_link(tasks, hitos):  # Gentil links the guion to the audiovisual hito, omits the operational task
        return [{"task_id": t["id"], "milestone_id": 10} for t in tasks if "guion" in (t["titulo"] or "").lower()]

    monkeypatch.setattr(_cascade, "generate_hito_links_for_tasks", fake_link)
    body = client.post("/api/tasks/link-hitos", headers=H).json()
    assert body["linked"] == 1 and body["candidatas"] == 2
    with client._engine.connect() as c:
        assert c.execute(text("SELECT milestone_id FROM tasks WHERE id=1")).scalar() == 10
        assert c.execute(text("SELECT milestone_id FROM tasks WHERE id=2")).scalar() is None
    # idempotent: only the still-unlinked operational task remains a candidate; nothing new linked
    body2 = client.post("/api/tasks/link-hitos", headers=H).json()
    assert body2["linked"] == 0 and body2["candidatas"] == 1


def test_link_hitos_no_hitos_is_honest(client, monkeypatch):
    with client._engine.begin() as c:
        c.execute(text("INSERT INTO tasks (id,titulo,plan_id,milestone_id,google_task_id) "
                       "VALUES (1,'X',NULL,NULL,'g1')"))
    r = client.post("/api/tasks/link-hitos", headers=H)
    assert r.status_code == 200 and r.json()["estado"] == "sin_hitos"

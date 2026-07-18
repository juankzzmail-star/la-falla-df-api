"""DB + API tests for the Estrategia -> Plan -> Tareas cascade (change strategy-cascade).

Runs in the `api_gateway` package layout (CI/container). Isolated in-memory SQLite with
StaticPool (one shared DB per test). The three LLM seams in routers/_cascade are monkeypatched
— no network, no production Postgres. Tables are created from portable raw DDL (the ORM Plan
has a Postgres JSONB column and Task has cross-area FKs, so ORM `create_all`/`__table__.create`
can't run on SQLite — same approach as test_document_rag).

Covers tasks.md §7.2 / spec scenarios: intent=estrategia upserts goals; estrategia with no goals
degrades to a daily suggestion; generate-from-goals creates proposed plans with the area director;
approve flips to activo and creates pending tasks for the director; approve is idempotent;
503 when no provider; auth on /api/*.
"""
import os

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("FASTAPI_GM_API_KEY", "test-key-123")
os.environ.setdefault("FASTAPI_API_KEY", "test-key-123")
os.environ.setdefault("OPENAI_API_KEY", "test-openai")  # presence only; seams are monkeypatched

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api_gateway.db import get_db
from api_gateway.main import app
from api_gateway.routers import _cascade as cascade

H = {"X-API-Key": "test-key-123"}

# DDL mirrors the prod Postgres CHECK constraints (areas, plan/task estado, prioridad) so the
# suite catches constraint violations like the plans_estado_check that blocked 'propuesto' in prod.
_AREAS = "'Comercial','Proyectos','Investigacion','Audiovisual','Transversal'"
_DDL = [
    # change unify-strategy-execution evolved the shared schema; mirror the new columns/table here.
    """CREATE TABLE roadmap_cycles (
        id INTEGER PRIMARY KEY AUTOINCREMENT, anio INTEGER NOT NULL UNIQUE, nombre TEXT,
        estado TEXT NOT NULL DEFAULT 'activo', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
    f"""CREATE TABLE strategic_goals (
        id INTEGER PRIMARY KEY AUTOINCREMENT, codigo TEXT UNIQUE NOT NULL, titulo TEXT NOT NULL,
        area TEXT NOT NULL CHECK (area IN ({_AREAS})), fecha_inicio DATE, fecha_fin_meta DATE,
        peso_porcentaje NUMERIC, estado TEXT NOT NULL DEFAULT 'activo'
        CHECK (estado IN ('activo','pausado','cerrado')), milestone_id INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
    f"""CREATE TABLE plans (
        id INTEGER PRIMARY KEY AUTOINCREMENT, codigo TEXT UNIQUE NOT NULL, titulo TEXT NOT NULL,
        area TEXT NOT NULL CHECK (area IN ({_AREAS})), goal_id INTEGER, responsable TEXT,
        anio INTEGER, ciclo_id INTEGER, fecha_inicio DATE,
        fecha_fin_planificada DATE, baseline_curva_s TEXT, pct_completado_real NUMERIC NOT NULL DEFAULT 0,
        pct_completado_plan NUMERIC NOT NULL DEFAULT 0, estado TEXT NOT NULL DEFAULT 'activo'
        CHECK (estado IN ('propuesto','activo','pausado','cerrado')),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
    """CREATE TABLE tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT, plan_id INTEGER NOT NULL, titulo TEXT NOT NULL,
        responsable TEXT, area TEXT, fecha_inicio DATE, fecha_vencimiento DATE, fecha_completada DATE,
        prioridad TEXT NOT NULL DEFAULT 'media' CHECK (prioridad IN ('critica','alta','media','baja')),
        es_hito INTEGER NOT NULL DEFAULT 0,
        estado TEXT NOT NULL DEFAULT 'pendiente'
        CHECK (estado IN ('pendiente','en_progreso','completada','bloqueada','cancelada')),
        motivo_bloqueo TEXT, url_entregable TEXT,
        peso_pct NUMERIC NOT NULL DEFAULT 0, google_task_id TEXT, google_calendar_event_id TEXT,
        stakeholder_id INTEGER, edt_node_id INTEGER,
        project_id INTEGER, milestone_id INTEGER, origen TEXT NOT NULL DEFAULT 'directa'
        CHECK (origen IN ('directa','proyecto')),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
    """CREATE TABLE daily_suggestions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, fecha DATE NOT NULL, tag TEXT NOT NULL, titulo TEXT NOT NULL,
        cuerpo TEXT, estado TEXT NOT NULL DEFAULT 'pendiente', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
]


@pytest.fixture()
def client(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    with engine.begin() as c:
        for ddl in _DDL:
            c.execute(text(ddl))
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    # Keep RAG indexing a no-op (best-effort path in strategy.py) — no network in tests.
    monkeypatch.setattr("api_gateway.routers.rag.embed_and_store", lambda **k: 0, raising=False)
    with TestClient(app) as c:
        c._engine = engine  # for raw-SQL verification of tasks (ORM Task carries cross-area FKs)
        yield c
    app.dependency_overrides.clear()


def _tasks_for(client, plan_id):
    with client._engine.connect() as conn:
        return conn.execute(
            text("SELECT estado, responsable, es_hito FROM tasks WHERE plan_id = :p"),
            {"p": plan_id},
        ).fetchall()


def _seed_goal(client, codigo="COM-2030-01", area="Comercial"):
    r = client.post("/api/goals", json={"codigo": codigo, "titulo": "Crecer ventas", "area": area,
                                        "fecha_inicio": "2026-01-01", "fecha_fin_meta": "2026-12-31",
                                        "peso_porcentaje": 40}, headers=H)
    assert r.status_code == 201, r.text
    return r.json()["id"]


# ── Auth ─────────────────────────────────────────────────────────────────────
def test_cascade_requires_api_key(client):
    assert client.post("/api/plans/generate-from-goals", json={"goal_ids": [1]}).status_code in (401, 403)
    assert client.post("/api/plans/1/approve").status_code in (401, 403)
    assert client.post("/api/strategy/ingest-resource", data={"intent": "estrategia"}).status_code in (401, 403)


# ── intent=estrategia ────────────────────────────────────────────────────────
def test_estrategia_intent_creates_goals(client, monkeypatch):
    monkeypatch.setattr(cascade, "extract_goals_from_text", lambda t: [
        {"codigo": "COM-2030-01", "titulo": "Triplicar alianzas", "area": "Comercial", "peso_porcentaje": 50},
    ])
    r = client.post("/api/strategy/ingest-resource",
                    data={"intent": "estrategia"},
                    files={"file": ("estrategia.txt", b"Documento de estrategia comercial.", "text/plain")},
                    headers=H)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["strategy_found"] is True
    assert body["metas_creadas"] == 1
    goals = client.get("/api/goals", headers=H).json()
    assert [g["codigo"] for g in goals] == ["COM-2030-01"]


def test_estrategia_no_goals_degrades_to_suggestion(client, monkeypatch):
    monkeypatch.setattr(cascade, "extract_goals_from_text", lambda t: [])
    r = client.post("/api/strategy/ingest-resource",
                    data={"intent": "estrategia"},
                    files={"file": ("ruido.txt", b"Una nota sin estrategia.", "text/plain")},
                    headers=H)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["strategy_found"] is False
    assert "observaci" in body["message"].lower()
    assert client.get("/api/goals", headers=H).json() == []


# ── goals -> plans ───────────────────────────────────────────────────────────
def test_generate_plans_from_goals(client, monkeypatch):
    gid = _seed_goal(client, area="Comercial")
    monkeypatch.setattr(cascade, "generate_plans_for_goal", lambda goal: [
        {"codigo": "COM-2030-01-P1", "titulo": "Plan de alianzas",
         "fecha_inicio": "2026-01-01", "fecha_fin_planificada": "2026-12-31"},
    ])
    r = client.post("/api/plans/generate-from-goals", json={"goal_ids": [gid]}, headers=H)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["planes_creados"] == 1
    plan = body["plans"][0]
    assert plan["estado"] == "propuesto"
    assert plan["goal_id"] == gid
    assert plan["responsable"] == "Juan Carlos"   # Comercial -> Juan Carlos
    assert plan["baseline_curva_s"]                # non-empty scaffold


def test_generate_plans_503_without_provider(client, monkeypatch):
    gid = _seed_goal(client)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    # No seam mock -> real generate_plans_for_goal -> _client_model -> 503
    r = client.post("/api/plans/generate-from-goals", json={"goal_ids": [gid]}, headers=H)
    assert r.status_code == 503


# ── plan approval -> per-director tasks ──────────────────────────────────────
def _seed_plan(client, area="Proyectos", codigo="PRO-P1"):
    r = client.post("/api/plans", json={"codigo": codigo, "titulo": "Plan piloto", "area": area,
                                        "estado": "propuesto"}, headers=H)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_approve_generates_tasks_for_director(client, monkeypatch):
    pid = _seed_plan(client, area="Proyectos")
    monkeypatch.setattr(cascade, "generate_tasks_for_plan", lambda plan: [
        {"titulo": "Definir alcance", "es_hito": True, "prioridad": "alta", "peso_pct": 50},
        {"titulo": "Ejecutar piloto", "es_hito": False, "prioridad": "media", "peso_pct": 50},
    ])
    r = client.post(f"/api/plans/{pid}/approve", headers=H)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["estado"] == "activo"
    assert body["tareas_creadas"] == 2
    assert body["responsable"] == "Beto"          # Proyectos -> Beto
    rows = _tasks_for(client, pid)
    assert len(rows) == 2
    assert all(r[0] == "pendiente" and r[1] == "Beto" for r in rows)
    assert any(r[2] for r in rows)                # at least one hito


def test_approve_is_idempotent(client, monkeypatch):
    pid = _seed_plan(client, area="Audiovisual", codigo="AV-P1")
    monkeypatch.setattr(cascade, "generate_tasks_for_plan", lambda plan: [
        {"titulo": "T1", "prioridad": "media", "peso_pct": 100},
    ])
    first = client.post(f"/api/plans/{pid}/approve", headers=H).json()
    assert first["tareas_creadas"] == 1
    second = client.post(f"/api/plans/{pid}/approve", headers=H).json()
    assert second["tareas_creadas"] == 0          # no duplicates
    assert second["estado"] == "activo"
    assert len(_tasks_for(client, pid)) == 1


# ── Transversal area (change ingest-real-strategy) ───────────────────────────
def test_transversal_goal_generates_plans_owned_by_ceo(client, monkeypatch):
    # Gerencia/CEO objectives land as area='Transversal' and must pass the widened CHECK.
    gid = _seed_goal(client, codigo="GOV-2026-01", area="Transversal")
    monkeypatch.setattr(cascade, "generate_plans_for_goal", lambda goal: [
        {"codigo": "GOV-2026-01-P1", "titulo": "Gobierno corporativo",
         "fecha_inicio": "2026-01-01", "fecha_fin_planificada": "2026-12-31"},
    ])
    r = client.post("/api/plans/generate-from-goals", json={"goal_ids": [gid]}, headers=H)
    assert r.status_code == 200, r.text
    plan = r.json()["plans"][0]
    assert plan["responsable"] == "Clementino"     # Transversal -> CEO


def test_director_for_transversal_is_ceo():
    assert cascade.director_for("Transversal") == "Clementino"


def test_goals_prompt_maps_directions_and_excludes_chores():
    p = cascade.GOALS_PROMPT
    assert "Transversal" in p
    assert "Gerencia" in p and "CEO" in p
    # explicit chore-exclusion instruction (Lección: trámites no son metas)
    assert "EXCLUYE" in p and ("IVA" in p or "operativa" in p)

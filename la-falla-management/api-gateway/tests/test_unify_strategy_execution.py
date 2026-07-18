"""DB + API tests for change unify-strategy-execution.

Wires the two halves into the 5-level model (HITO de empresa -> META-DE-HITO -> PLAN anual -> TAREAS,
+ emergent PROYECTOS). Isolated in-memory SQLite + StaticPool; the LLM cascade seams are
monkeypatched (no network, no production Postgres). DDL mirrors the prod CHECK constraints and the
new columns from ddl_v11_unify.sql. The ORM RoadmapMilestone carries an ARRAY(depends_on) column, so
seeded rows leave it NULL and the hito-cycle logic is exercised through the pure helper.

Covers: hito DAG cycle rejection; company-wide hito (area null) + quarters derivation; honest
roadmap-2030 empty state (no fabricated 78/22); annual plan stamped with anio/ciclo_id; task origen
('directa' from approve, 'proyecto' from a project task); edt_node_id assignable via the API;
pct_completado_plan interpolation; auth guard.
"""
import os

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("FASTAPI_GM_API_KEY", "test-key-123")
os.environ.setdefault("FASTAPI_API_KEY", "test-key-123")
os.environ.setdefault("OPENAI_API_KEY", "test-openai")  # presence only; seams are monkeypatched

from datetime import date

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api_gateway.db import get_db
from api_gateway.main import app
from api_gateway.routers import _cascade as cascade
from api_gateway.routers import roadmap as roadmap_router
from api_gateway.routers.plans import _interp_plan_pct

H = {"X-API-Key": "test-key-123"}
_AREAS = "'Comercial','Proyectos','Investigacion','Audiovisual','Transversal'"

_DDL = [
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
        anio INTEGER, ciclo_id INTEGER, fecha_inicio DATE, fecha_fin_planificada DATE,
        baseline_curva_s TEXT, pct_completado_real NUMERIC NOT NULL DEFAULT 0,
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
        motivo_bloqueo TEXT, url_entregable TEXT, peso_pct NUMERIC NOT NULL DEFAULT 0,
        google_task_id TEXT, google_calendar_event_id TEXT, stakeholder_id INTEGER, edt_node_id INTEGER,
        project_id INTEGER, milestone_id INTEGER, origen TEXT NOT NULL DEFAULT 'directa'
        CHECK (origen IN ('directa','proyecto')),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
    """CREATE TABLE roadmap_milestones (
        id INTEGER PRIMARY KEY AUTOINCREMENT, titulo TEXT NOT NULL, orden INTEGER NOT NULL DEFAULT 0,
        estado TEXT NOT NULL DEFAULT 'pendiente', area TEXT, anio INTEGER, trimestre INTEGER,
        fecha_inicio TIMESTAMP, fecha_fin_planificada TIMESTAMP, fecha_completado TIMESTAMP,
        depends_on TEXT, version_id INTEGER, pct_completado NUMERIC NOT NULL DEFAULT 0,
        peso NUMERIC NOT NULL DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
    f"""CREATE TABLE projects (
        id INTEGER PRIMARY KEY AUTOINCREMENT, codigo TEXT UNIQUE NOT NULL, nombre TEXT NOT NULL,
        area TEXT NOT NULL CHECK (area IN ({_AREAS})), presupuesto NUMERIC NOT NULL DEFAULT 0,
        ejecutado NUMERIC NOT NULL DEFAULT 0, estado TEXT NOT NULL DEFAULT 'activo',
        plan_id INTEGER, milestone_id INTEGER, anio INTEGER, origen TEXT NOT NULL DEFAULT 'planeado',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
    """CREATE TABLE risks (
        id INTEGER PRIMARY KEY AUTOINCREMENT, descripcion TEXT, area TEXT, impacto INTEGER,
        probabilidad INTEGER, nivel_riesgo INTEGER, estado_mitigacion TEXT DEFAULT 'monitoreado',
        analisis_gentil TEXT, plan_mitigacion TEXT, fecha_analisis TIMESTAMP)""",
    # change plan-quarterly-milestones: the quarter lives on the plan (Q1–Q4), not the hito.
    """CREATE TABLE plan_quarterly_goals (
        id INTEGER PRIMARY KEY AUTOINCREMENT, plan_id INTEGER NOT NULL,
        trimestre INTEGER NOT NULL CHECK (trimestre BETWEEN 1 AND 4), meta TEXT NOT NULL,
        objetivo_medible TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (plan_id, trimestre))""",
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
    monkeypatch.setattr("api_gateway.routers.rag.embed_and_store", lambda **k: 0, raising=False)
    with TestClient(app) as c:
        c._engine = engine
        yield c
    app.dependency_overrides.clear()


def _exec(client, sql, **p):
    with client._engine.begin() as conn:
        conn.execute(text(sql), p)


def _rows(client, sql, **p):
    with client._engine.connect() as conn:
        return conn.execute(text(sql), p).fetchall()


# ── Pure: planned-progress interpolation ─────────────────────────────────────
def test_interp_plan_pct_mid_timeline_nonzero():
    baseline = [{"mes": "2026-01", "pct_plan": 10}, {"mes": "2026-06", "pct_plan": 50},
                {"mes": "2026-12", "pct_plan": 100}]
    assert _interp_plan_pct(baseline, date(2026, 7, 1)) == 50    # latest bucket <= month
    assert _interp_plan_pct(baseline, date(2025, 1, 1)) == 0.0   # before the curve
    assert _interp_plan_pct([], date(2026, 7, 1)) == 0.0         # no baseline


# ── Pure: hito DAG cycle detection (the endpoint's validation helper) ─────────
class _M:
    def __init__(self, mid, deps): self.id = mid; self.depends_on = deps

class _FakeQuery:
    def __init__(self, rows): self._rows = rows
    def all(self): return self._rows

class _FakeDB:
    def __init__(self, rows): self._rows = rows
    def query(self, *a, **k): return _FakeQuery(self._rows)


def test_hito_cycle_is_rejected():
    rows = [_M(1, []), _M(2, [1])]   # H2 depends on H1
    with pytest.raises(HTTPException) as exc:
        roadmap_router._assert_milestone_acyclic(_FakeDB(rows), 1, [2])  # H1 -> H2 closes a cycle
    assert exc.value.status_code == 400


def test_hito_acyclic_passes():
    rows = [_M(1, []), _M(2, [1])]
    roadmap_router._assert_milestone_acyclic(_FakeDB(rows), 3, [2])      # new H3 -> H2: acyclic, no raise


# ── Quarters endpoint: re-pointed to the PLANS' quarterly goals (change plan-quarterly-milestones) ──
def test_quarters_sourced_from_plan_quarterly_goals(client):
    _exec(client, "INSERT INTO plans (codigo, titulo, area, anio) VALUES ('PL-COM','Plan Comercial','Comercial',2026)")
    pid = _rows(client, "SELECT id FROM plans WHERE codigo = 'PL-COM'")[0][0]
    _exec(client, "INSERT INTO plan_quarterly_goals (plan_id, trimestre, meta) VALUES (:p, 1, 'Cerrar 3 alianzas')", p=pid)
    _exec(client, "INSERT INTO plan_quarterly_goals (plan_id, trimestre, meta) VALUES (:p, 3, 'FDC 2026')", p=pid)
    _exec(client, "INSERT INTO plans (codigo, titulo, area, anio) VALUES ('PL-28','Plan 2028','Proyectos',2028)")
    pid28 = _rows(client, "SELECT id FROM plans WHERE codigo = 'PL-28'")[0][0]
    _exec(client, "INSERT INTO plan_quarterly_goals (plan_id, trimestre, meta) VALUES (:p, 2, 'otra')", p=pid28)  # other year
    r = client.get("/api/roadmap/quarters?anio=2026", headers=H)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["anio"] == 2026 and body["total"] == 2
    by_q = {q["trimestre"]: q["items"] for q in body["quarters"]}
    assert len(by_q[1]) == 1 and by_q[1][0]["meta"] == "Cerrar 3 alianzas" and by_q[1][0]["area"] == "Comercial"
    assert len(by_q[3]) == 1 and len(by_q[2]) == 0


def test_quarters_requires_api_key(client):
    assert client.get("/api/roadmap/quarters?anio=2026").status_code in (401, 403)


# ── roadmap-2030: honest empty (NO fabricated 78/22) ─────────────────────────
def test_roadmap_2030_empty_is_honest(client):
    r = client.get("/api/dashboard/roadmap-2030", headers=H)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["has_data"] is False and body["data_state"] == "empty"
    arcs = {a["label"]: a["value"] for a in body["arcs"]}
    assert arcs["ENTREGAS"] is None      # was a silent 78
    assert arcs["RIESGO"] is None        # was a silent 22
    assert arcs["EJE ESTRAT."] is None
    assert body["v2030_pct"] == 0


# ── Annual plan stamped with the active cycle ────────────────────────────────
def test_generate_plans_stamp_anio_and_ciclo(client, monkeypatch):
    _exec(client, "INSERT INTO roadmap_cycles (anio, nombre, estado) VALUES (2026, 'Ciclo 2026', 'activo')")
    cid = _rows(client, "SELECT id FROM roadmap_cycles WHERE anio = 2026")[0][0]
    gid = client.post("/api/goals", json={"codigo": "COM-2026-01", "titulo": "Red nacional",
                      "area": "Comercial", "fecha_inicio": "2026-01-01",
                      "fecha_fin_meta": "2026-12-31"}, headers=H).json()["id"]
    monkeypatch.setattr(cascade, "generate_plans_for_goal", lambda goal: [
        {"codigo": "PLAN-COM-2026", "titulo": "Plan Comercial 2026",
         "fecha_inicio": "2026-01-01", "fecha_fin_planificada": "2026-12-31"},
    ])
    r = client.post("/api/plans/generate-from-goals", json={"goal_ids": [gid]}, headers=H)
    assert r.status_code == 200, r.text
    plan = r.json()["plans"][0]
    assert plan["anio"] == 2026
    assert plan["ciclo_id"] == cid


# ── Task origins: 'directa' from approve, 'proyecto' from a project task ──────
def test_approve_tasks_are_directa_and_carry_hito(client, monkeypatch):
    # meta-de-hito linked to a hito; its plan's direct tasks default to that hito.
    _exec(client, "INSERT INTO roadmap_milestones (id, titulo, anio, trimestre) VALUES (7, 'Hito 7', 2026, 1)")
    _exec(client, "INSERT INTO strategic_goals (codigo, titulo, area, milestone_id) "
                  "VALUES ('M-1', 'Meta', 'Proyectos', 7)")
    gid = _rows(client, "SELECT id FROM strategic_goals WHERE codigo = 'M-1'")[0][0]
    pid = client.post("/api/plans", json={"codigo": "PRO-2026", "titulo": "Plan", "area": "Proyectos",
                      "goal_id": gid, "estado": "propuesto"}, headers=H).json()["id"]
    monkeypatch.setattr(cascade, "generate_tasks_for_plan", lambda plan: [
        {"titulo": "T1", "es_hito": True, "prioridad": "alta", "peso_pct": 100},
    ])
    assert client.post(f"/api/plans/{pid}/approve", headers=H).status_code == 200
    rows = _rows(client, "SELECT origen, milestone_id FROM tasks WHERE plan_id = :p", p=pid)
    assert rows and rows[0][0] == "directa" and rows[0][1] == 7


def test_complete_task_rolls_up_to_linked_hito(client):
    # change populate-hito-rollup: completing a task lifts the plan's real % and recomputes its linked
    # hito's % through plans.goal_id -> strategic_goals.milestone_id (the roll-up the QA sweep left untested).
    _exec(client, "INSERT INTO roadmap_milestones (id, titulo, anio) VALUES (12, 'Hito 12', 2026)")
    _exec(client, "INSERT INTO strategic_goals (codigo, titulo, area, milestone_id) "
                  "VALUES ('M-12', 'Meta', 'Proyectos', 12)")
    gid = _rows(client, "SELECT id FROM strategic_goals WHERE codigo='M-12'")[0][0]
    _exec(client, "INSERT INTO plans (codigo, titulo, area, goal_id) VALUES ('PRO-12','Plan','Proyectos',:g)", g=gid)
    pid = _rows(client, "SELECT id FROM plans WHERE codigo='PRO-12'")[0][0]
    _exec(client, "INSERT INTO tasks (plan_id, titulo, peso_pct, estado) VALUES (:p,'T1',60,'pendiente')", p=pid)
    _exec(client, "INSERT INTO tasks (plan_id, titulo, peso_pct, estado) VALUES (:p,'T2',40,'pendiente')", p=pid)
    tid = _rows(client, "SELECT id FROM tasks WHERE plan_id=:p AND titulo='T1'", p=pid)[0][0]
    assert float(_rows(client, "SELECT pct_completado FROM roadmap_milestones WHERE id=12")[0][0]) == 0.0

    assert client.post(f"/api/tasks/{tid}/complete", headers=H).status_code == 200
    assert float(_rows(client, "SELECT pct_completado_real FROM plans WHERE id=:p", p=pid)[0][0]) == 60.0
    assert float(_rows(client, "SELECT pct_completado FROM roadmap_milestones WHERE id=12")[0][0]) == 60.0


def test_create_task_with_project_is_proyecto(client):
    pid = client.post("/api/plans", json={"codigo": "P-X", "titulo": "Plan", "area": "Proyectos",
                      "estado": "activo"}, headers=H).json()["id"]
    _exec(client, "INSERT INTO projects (codigo, nombre, area, origen) "
                  "VALUES ('RC02', 'Rutas', 'Proyectos', 'convocatoria')")
    proj_id = _rows(client, "SELECT id FROM projects WHERE codigo = 'RC02'")[0][0]
    r = client.post("/api/tasks", json={"plan_id": pid, "titulo": "Rodaje", "responsable": "Beto",
                    "project_id": proj_id}, headers=H)
    assert r.status_code == 201, r.text
    assert r.json()["origen"] == "proyecto"
    assert r.json()["project_id"] == proj_id


# ── edt_node_id assignable via the API (fixes the ORM<->schema drift) ─────────
def test_edt_node_id_assignable_via_patch(client):
    pid = client.post("/api/plans", json={"codigo": "P-Y", "titulo": "Plan", "area": "Audiovisual",
                      "estado": "activo"}, headers=H).json()["id"]
    tid = client.post("/api/tasks", json={"plan_id": pid, "titulo": "Pieza", "responsable": "Iván"},
                      headers=H).json()["id"]
    r = client.patch(f"/api/tasks/{tid}", json={"edt_node_id": 42}, headers=H)
    assert r.status_code == 200, r.text
    assert r.json()["edt_node_id"] == 42

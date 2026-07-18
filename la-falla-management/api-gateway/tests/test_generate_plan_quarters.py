"""API tests for change generate-plan-quarters.

The Centro de Mando derives a plan's quarterly goals from its REAL tasks via the LLM seam
(`_cascade.generate_quarters_for_plan`) — proposes, the human approves/edits via PUT. The seam is
monkeypatched here: NO network, NO production Postgres. Isolated in-memory SQLite + StaticPool.

Covers: generation writes the proposed Q's (and GET returns them); 422 when the plan has no dated tasks;
503 (no provider) writes nothing; auth guard; 404 unknown plan; anio stamped from the active cycle.
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
from api_gateway.routers import _cascade

H = {"X-API-Key": "test-key-123"}

_DDL = [
    """CREATE TABLE roadmap_cycles (
        id INTEGER PRIMARY KEY AUTOINCREMENT, anio INTEGER NOT NULL UNIQUE, nombre TEXT,
        estado TEXT NOT NULL DEFAULT 'activo', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
    """CREATE TABLE plans (
        id INTEGER PRIMARY KEY AUTOINCREMENT, codigo TEXT UNIQUE NOT NULL, titulo TEXT NOT NULL,
        area TEXT NOT NULL CHECK (area IN ('Comercial','Proyectos','Investigacion','Audiovisual','Transversal')),
        goal_id INTEGER, responsable TEXT, anio INTEGER, ciclo_id INTEGER, fecha_inicio DATE,
        fecha_fin_planificada DATE, baseline_curva_s TEXT, pct_completado_real NUMERIC NOT NULL DEFAULT 0,
        pct_completado_plan NUMERIC NOT NULL DEFAULT 0, estado TEXT NOT NULL DEFAULT 'activo',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
    """CREATE TABLE tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT, plan_id INTEGER NOT NULL, titulo TEXT NOT NULL,
        fecha_vencimiento DATE, peso_pct NUMERIC NOT NULL DEFAULT 0,
        estado TEXT NOT NULL DEFAULT 'pendiente')""",
    """CREATE TABLE plan_quarterly_goals (
        id INTEGER PRIMARY KEY AUTOINCREMENT, plan_id INTEGER NOT NULL,
        trimestre INTEGER NOT NULL CHECK (trimestre BETWEEN 1 AND 4), meta TEXT NOT NULL,
        objetivo_medible TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (plan_id, trimestre))""",
]


@pytest.fixture()
def client():
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


def _plan_with_tasks(client, codigo="PG", anio=None):
    _exec(client, "INSERT INTO plans (codigo, titulo, area, anio) VALUES (:c, :c, 'Comercial', :y)", c=codigo, y=anio)
    pid = _rows(client, "SELECT id FROM plans WHERE codigo = :c", c=codigo)[0][0]
    _exec(client, "INSERT INTO tasks (plan_id, titulo, fecha_vencimiento) VALUES (:p, 'Contactar agremiaciones', '2026-02-01')", p=pid)
    _exec(client, "INSERT INTO tasks (plan_id, titulo, fecha_vencimiento) VALUES (:p, 'Programa de beneficios', '2026-05-01')", p=pid)
    return pid


def test_generate_writes_proposed_quarters(client, monkeypatch):
    pid = _plan_with_tasks(client, "PG1")
    monkeypatch.setattr(_cascade, "generate_quarters_for_plan", lambda plan, by_q: [
        {"trimestre": 1, "meta": "Activar la red de agremiaciones", "objetivo_medible": "3 alianzas"},
        {"trimestre": 2, "meta": "Lanzar el programa de beneficios", "objetivo_medible": None},
    ])
    r = client.post(f"/api/plans/{pid}/quarters/generate", headers=H)
    assert r.status_code == 200, r.text
    qs = {q["trimestre"]: q for q in r.json()["quarters"]}
    assert qs[1]["meta"] == "Activar la red de agremiaciones" and qs[1]["objetivo_medible"] == "3 alianzas"
    assert qs[2]["meta"] == "Lanzar el programa de beneficios"
    assert qs[3]["meta"] is None
    # persisted
    assert _rows(client, "SELECT count(*) FROM plan_quarterly_goals WHERE plan_id = :p", p=pid)[0][0] == 2


def test_generate_stamps_anio_from_active_cycle(client, monkeypatch):
    _exec(client, "INSERT INTO roadmap_cycles (anio, nombre, estado) VALUES (2026, 'Ciclo 2026', 'activo')")
    pid = _plan_with_tasks(client, "PG2", anio=None)
    monkeypatch.setattr(_cascade, "generate_quarters_for_plan", lambda plan, by_q: [{"trimestre": 1, "meta": "M"}])
    assert client.post(f"/api/plans/{pid}/quarters/generate", headers=H).status_code == 200
    assert _rows(client, "SELECT anio FROM plans WHERE id = :p", p=pid)[0][0] == 2026


def test_generate_422_when_no_dated_tasks(client, monkeypatch):
    _exec(client, "INSERT INTO plans (codigo, titulo, area) VALUES ('PG3', 'x', 'Comercial')")
    pid = _rows(client, "SELECT id FROM plans WHERE codigo = 'PG3'")[0][0]
    _exec(client, "INSERT INTO tasks (plan_id, titulo, fecha_vencimiento) VALUES (:p, 'sin fecha', NULL)", p=pid)
    called = {"n": 0}
    monkeypatch.setattr(_cascade, "generate_quarters_for_plan",
                        lambda plan, by_q: called.__setitem__("n", called["n"] + 1) or [])
    r = client.post(f"/api/plans/{pid}/quarters/generate", headers=H)
    assert r.status_code == 422
    assert called["n"] == 0  # seam not even called when there is nothing to derive


def test_generate_503_no_provider_writes_nothing(client, monkeypatch):
    pid = _plan_with_tasks(client, "PG4")

    def _raise(plan, by_q):
        raise HTTPException(503, "No hay proveedor LLM configurado")

    monkeypatch.setattr(_cascade, "generate_quarters_for_plan", _raise)
    r = client.post(f"/api/plans/{pid}/quarters/generate", headers=H)
    assert r.status_code == 503
    assert _rows(client, "SELECT count(*) FROM plan_quarterly_goals WHERE plan_id = :p", p=pid)[0][0] == 0


def test_generate_requires_api_key(client):
    pid = _plan_with_tasks(client, "PG5")
    assert client.post(f"/api/plans/{pid}/quarters/generate").status_code in (401, 403)


def test_generate_unknown_plan_is_404(client):
    assert client.post("/api/plans/999999/quarters/generate", headers=H).status_code == 404


# ── Year-scoping (change populate-hito-rollup) ───────────────────────────────────

def test_generate_ignores_tasks_from_another_year_422(client, monkeypatch):
    # A plan stamped 2026 whose only tasks are dated 2024 has no cycle-year tasks -> 422, seam not called.
    _exec(client, "INSERT INTO plans (codigo, titulo, area, anio) VALUES ('PG6', 'x', 'Comercial', 2026)")
    pid = _rows(client, "SELECT id FROM plans WHERE codigo = 'PG6'")[0][0]
    _exec(client, "INSERT INTO tasks (plan_id, titulo, fecha_vencimiento) VALUES (:p, 'vieja 2024', '2024-02-15')", p=pid)
    called = {"n": 0}
    monkeypatch.setattr(_cascade, "generate_quarters_for_plan",
                        lambda plan, by_q: called.__setitem__("n", called["n"] + 1) or [])
    r = client.post(f"/api/plans/{pid}/quarters/generate", headers=H)
    assert r.status_code == 422
    assert called["n"] == 0  # 2024 tasks do not count toward the plan's 2026 quarters


def test_generate_buckets_only_cycle_year_tasks(client, monkeypatch):
    # A plan stamped 2026 with both 2024 and 2026 tasks: only the 2026 ones reach the seam.
    _exec(client, "INSERT INTO plans (codigo, titulo, area, anio) VALUES ('PG7', 'x', 'Comercial', 2026)")
    pid = _rows(client, "SELECT id FROM plans WHERE codigo = 'PG7'")[0][0]
    _exec(client, "INSERT INTO tasks (plan_id, titulo, fecha_vencimiento) VALUES (:p, 'vieja Q1-2024', '2024-02-15')", p=pid)
    _exec(client, "INSERT INTO tasks (plan_id, titulo, fecha_vencimiento) VALUES (:p, 'nueva Q2-2026', '2026-05-10')", p=pid)
    seen: dict = {}

    def _capture(plan, by_q):
        seen.update(by_q)
        return [{"trimestre": 2, "meta": "Q2 real"}]

    monkeypatch.setattr(_cascade, "generate_quarters_for_plan", _capture)
    r = client.post(f"/api/plans/{pid}/quarters/generate", headers=H)
    assert r.status_code == 200, r.text
    assert set(seen.keys()) == {2}  # only the 2026 Q2 task was bucketed; the 2024 Q1 task was ignored
    assert "nueva Q2-2026" in seen[2] and all("vieja" not in t for t in seen[2])

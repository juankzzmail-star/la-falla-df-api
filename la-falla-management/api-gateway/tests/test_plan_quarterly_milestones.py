"""DB + API tests for change plan-quarterly-milestones.

The quarter (Q1–Q4) lives on the PLAN, not the hito (model §12, D9–D11). Each plan owns four quarterly
goals (meta + optional objetivo_medible); the per-quarter % is DERIVED from real task completion at read
time and is never stored. Isolated in-memory SQLite + StaticPool; no network, no production Postgres.

Covers: the pure derived-% helper (quarter bucketing by due date, peso ratio, empty -> "sin datos",
all-zero-peso count fallback); GET/PUT /plans/{id}/quarters (shape, 422 out-of-range, 422 duplicate,
404 unknown plan); the UNIQUE(plan_id, trimestre) DB constraint; the re-pointed /roadmap/quarters
(sourced from plan goals); and /roadmap/active-cycle (active + honest empty).
"""
import os

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("FASTAPI_GM_API_KEY", "test-key-123")
os.environ.setdefault("FASTAPI_API_KEY", "test-key-123")

from datetime import date

import pytest
import sqlalchemy
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api_gateway.db import get_db
from api_gateway.main import app
from api_gateway.routers.plans import _derive_quarter_pcts, _quarter_of

H = {"X-API-Key": "test-key-123"}
_AREAS = "'Comercial','Proyectos','Investigacion','Audiovisual','Transversal'"

_DDL = [
    """CREATE TABLE roadmap_cycles (
        id INTEGER PRIMARY KEY AUTOINCREMENT, anio INTEGER NOT NULL UNIQUE, nombre TEXT,
        estado TEXT NOT NULL DEFAULT 'activo', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
    f"""CREATE TABLE plans (
        id INTEGER PRIMARY KEY AUTOINCREMENT, codigo TEXT UNIQUE NOT NULL, titulo TEXT NOT NULL,
        area TEXT NOT NULL CHECK (area IN ({_AREAS})), goal_id INTEGER, responsable TEXT,
        anio INTEGER, ciclo_id INTEGER, fecha_inicio DATE, fecha_fin_planificada DATE,
        baseline_curva_s TEXT, pct_completado_real NUMERIC NOT NULL DEFAULT 0,
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


def _plan(client, codigo, area="Comercial", anio=2026):
    _exec(client, "INSERT INTO plans (codigo, titulo, area, anio) VALUES (:c, :c, :a, :y)",
          c=codigo, a=area, y=anio)
    return _rows(client, "SELECT id FROM plans WHERE codigo = :c", c=codigo)[0][0]


# ── Pure: derived per-quarter % (no DB) ──────────────────────────────────────
def test_quarter_of_buckets():
    assert _quarter_of(date(2026, 1, 15)) == 1
    assert _quarter_of(date(2026, 4, 1)) == 2
    assert _quarter_of(date(2026, 9, 30)) == 3
    assert _quarter_of(date(2026, 12, 31)) == 4
    assert _quarter_of("2026-07-15") == 3      # ISO string (SQLite raw row)
    assert _quarter_of(None) is None
    assert _quarter_of("garbage") is None


def test_derive_quarter_pcts_ratios():
    rows = [
        (date(2026, 2, 1), 60, "completada"),
        (date(2026, 3, 1), 40, "pendiente"),
        (date(2026, 5, 1), 50, "completada"),   # Q2 all done -> 100
    ]
    pcts = _derive_quarter_pcts(rows)
    assert pcts[1] == 60.0                       # 60 done / 100 total
    assert pcts[2] == 100.0
    assert pcts[3] is None                       # no contributing work -> "sin datos"
    assert pcts[4] is None


def test_derive_quarter_pcts_zero_peso_count_fallback():
    rows = [(date(2026, 2, 1), 0, "completada"), (date(2026, 2, 15), 0, "pendiente")]
    assert _derive_quarter_pcts(rows)[1] == 50.0  # 1 of 2 by count when every peso is 0


def test_derive_quarter_pcts_year_scoped():
    # change populate-hito-rollup: a 2024 task is not attributed to a 2026 plan's quarter.
    rows = [
        (date(2024, 2, 1), 100, "completada"),   # 2024 Q1 -> ignored when anio=2026
        (date(2026, 5, 1), 100, "completada"),   # 2026 Q2 -> counted
    ]
    pcts = _derive_quarter_pcts(rows, anio=2026)
    assert pcts[1] is None                        # the 2024 task does not count toward 2026 Q1
    assert pcts[2] == 100.0
    assert _derive_quarter_pcts(rows)[1] == 100.0  # anio=None keeps the year-blind behavior


# ── API: GET/PUT /plans/{id}/quarters ────────────────────────────────────────
def test_get_quarters_derives_pct_from_tasks(client):
    pid = _plan(client, "PQ")
    _exec(client, "INSERT INTO tasks (plan_id, titulo, fecha_vencimiento, peso_pct, estado) "
                  "VALUES (:p,'a','2026-02-01',60,'completada')", p=pid)
    _exec(client, "INSERT INTO tasks (plan_id, titulo, fecha_vencimiento, peso_pct, estado) "
                  "VALUES (:p,'b','2026-03-01',40,'pendiente')", p=pid)
    assert client.put(f"/api/plans/{pid}/quarters",
                      json={"quarters": [{"trimestre": 1, "meta": "M1"}]}, headers=H).status_code == 200
    r = client.get(f"/api/plans/{pid}/quarters", headers=H)
    assert r.status_code == 200, r.text
    qs = {q["trimestre"]: q for q in r.json()["quarters"]}
    assert qs[1]["meta"] == "M1" and qs[1]["pct"] == 60.0   # 60 done / 100 total
    assert qs[2]["pct"] is None and qs[2]["meta"] is None    # no tasks in Q2 -> sin datos
    assert len(r.json()["quarters"]) == 4


def test_get_quarters_year_scoped_ignores_other_year(client):
    # change populate-hito-rollup: a plan stamped 2026 whose only task is dated 2024 reports "sin datos".
    pid = _plan(client, "PY", anio=2026)
    _exec(client, "INSERT INTO tasks (plan_id, titulo, fecha_vencimiento, peso_pct, estado) "
                  "VALUES (:p,'vieja 2024','2024-02-01',100,'completada')", p=pid)
    assert client.put(f"/api/plans/{pid}/quarters",
                      json={"quarters": [{"trimestre": 1, "meta": "M1"}]}, headers=H).status_code == 200
    r = client.get(f"/api/plans/{pid}/quarters", headers=H)
    assert r.status_code == 200, r.text
    qs = {q["trimestre"]: q for q in r.json()["quarters"]}
    assert qs[1]["meta"] == "M1"      # the goal stays defined
    assert qs[1]["pct"] is None       # but no 2026 work -> sin datos (the 2024 task is not counted)


def test_put_quarters_rejects_out_of_range(client):
    pid = _plan(client, "PV")
    r = client.put(f"/api/plans/{pid}/quarters",
                   json={"quarters": [{"trimestre": 5, "meta": "x"}]}, headers=H)
    assert r.status_code == 422


def test_put_quarters_rejects_duplicate_trimestre(client):
    pid = _plan(client, "PD")
    r = client.put(f"/api/plans/{pid}/quarters",
                   json={"quarters": [{"trimestre": 1, "meta": "a"}, {"trimestre": 1, "meta": "b"}]}, headers=H)
    assert r.status_code == 422


def test_quarters_unknown_plan_is_404(client):
    assert client.get("/api/plans/9999/quarters", headers=H).status_code == 404
    assert client.put("/api/plans/9999/quarters",
                      json={"quarters": [{"trimestre": 1, "meta": "a"}]}, headers=H).status_code == 404


def test_quarters_requires_api_key(client):
    pid = _plan(client, "PK")
    assert client.get(f"/api/plans/{pid}/quarters").status_code in (401, 403)


# ── DB-state: the UNIQUE(plan_id, trimestre) constraint ──────────────────────
def test_unique_plan_trimestre_constraint(client):
    pid = _plan(client, "PU")
    _exec(client, "INSERT INTO plan_quarterly_goals (plan_id, trimestre, meta) VALUES (:p,1,'a')", p=pid)
    with pytest.raises(sqlalchemy.exc.IntegrityError):
        _exec(client, "INSERT INTO plan_quarterly_goals (plan_id, trimestre, meta) VALUES (:p,1,'b')", p=pid)


# ── API: /roadmap/quarters re-pointed to plan goals + /roadmap/active-cycle ──
def test_roadmap_quarters_sourced_from_plan_goals(client):
    pid = _plan(client, "PL-COM", area="Comercial", anio=2026)
    _exec(client, "INSERT INTO plan_quarterly_goals (plan_id, trimestre, meta) VALUES (:p,1,'Cerrar 3 alianzas')", p=pid)
    _exec(client, "INSERT INTO plan_quarterly_goals (plan_id, trimestre, meta) VALUES (:p,3,'FDC 2026')", p=pid)
    other = _plan(client, "PL-28", area="Proyectos", anio=2028)   # different year must not leak
    _exec(client, "INSERT INTO plan_quarterly_goals (plan_id, trimestre, meta) VALUES (:p,2,'otra')", p=other)
    r = client.get("/api/roadmap/quarters?anio=2026", headers=H)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["anio"] == 2026 and body["total"] == 2
    by_q = {q["trimestre"]: q["items"] for q in body["quarters"]}
    assert len(by_q[1]) == 1 and by_q[1][0]["meta"] == "Cerrar 3 alianzas" and by_q[1][0]["area"] == "Comercial"
    assert len(by_q[3]) == 1 and len(by_q[2]) == 0


def test_active_cycle_returns_active(client):
    _exec(client, "INSERT INTO roadmap_cycles (anio, nombre, estado) VALUES (2026,'Ciclo 2026','activo')")
    r = client.get("/api/roadmap/active-cycle", headers=H)
    assert r.status_code == 200, r.text
    assert r.json()["anio"] == 2026


def test_active_cycle_empty_is_honest(client):
    r = client.get("/api/roadmap/active-cycle", headers=H)
    assert r.status_code == 200, r.text
    assert r.json()["anio"] is None

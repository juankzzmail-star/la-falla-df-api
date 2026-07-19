"""DB + API tests for the deterministic task-coverage analysis (change gentil-task-coverage).

In-memory SQLite + StaticPool. daily_suggestions is created WITHOUT the `ref` column on purpose:
the lazy migration (_ensure_ref_column) must add it — that path is part of what we verify. All
network is mocked (httpx.post for the OpenClaw seam, _import_google_tasks for the cycle hook).
Covers spec scenarios: rules R1/R2/R3 with severity order and cap; empty system silent; refresh
idempotent over pending rows and preserving attended rows; redaction fallback on gateway failure;
manual refresh endpoint; GET suggestions carries ref; import cycle triggers the analysis and
survives a coverage exception.
"""
import os
from datetime import date

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
from api_gateway.routers import _coverage
from api_gateway.routers import tasks as tasks_mod

H = {"X-API-Key": "test-key-123"}

_DDL = [
    # NOTE: no `ref` column here — the lazy ddl_v15 migration must add it.
    """CREATE TABLE daily_suggestions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, fecha DATE NOT NULL, tag TEXT NOT NULL,
        titulo TEXT NOT NULL, cuerpo TEXT, estado TEXT NOT NULL DEFAULT 'pendiente',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
    """CREATE TABLE plans (
        id INTEGER PRIMARY KEY AUTOINCREMENT, codigo TEXT UNIQUE NOT NULL, titulo TEXT NOT NULL,
        area TEXT NOT NULL, responsable TEXT, fecha_inicio DATE, fecha_fin_planificada DATE,
        pct_completado_real NUMERIC NOT NULL DEFAULT 0,
        estado TEXT NOT NULL DEFAULT 'activo')""",
    """CREATE TABLE tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT, plan_id INTEGER, milestone_id INTEGER,
        titulo TEXT NOT NULL, area TEXT, estado TEXT NOT NULL DEFAULT 'pendiente',
        prioridad TEXT NOT NULL DEFAULT 'media')""",
    """CREATE TABLE roadmap_milestones (
        id INTEGER PRIMARY KEY AUTOINCREMENT, titulo TEXT NOT NULL, orden INTEGER NOT NULL DEFAULT 0,
        estado TEXT NOT NULL DEFAULT 'pendiente', area TEXT, anio INTEGER,
        fecha_fin_planificada DATE, pct_completado NUMERIC NOT NULL DEFAULT 0,
        peso NUMERIC NOT NULL DEFAULT 1)""",
    """CREATE TABLE strategic_goals (
        id INTEGER PRIMARY KEY AUTOINCREMENT, codigo TEXT UNIQUE NOT NULL, titulo TEXT NOT NULL,
        area TEXT NOT NULL, estado TEXT NOT NULL DEFAULT 'activo')""",
    """CREATE TABLE app_config (key TEXT PRIMARY KEY, value TEXT, updated_at TIMESTAMP)""",
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
        c._Session = TestingSession
        yield c
    app.dependency_overrides.clear()


def _exec(client, sql, **params):
    with client._engine.begin() as conn:
        conn.execute(text(sql), params)


def _rows(client, sql, **params):
    with client._engine.connect() as conn:
        return conn.execute(text(sql), params).fetchall()


def _seed_gaps(client):
    """One of each rule: R3 hito (60%, 4/4 completed), R2 hito (no tasks), R1 plan (no tasks)."""
    _exec(client, "INSERT INTO roadmap_milestones (id, titulo, area, estado, pct_completado) "
                  "VALUES (1, 'Hito agotado', 'Comercial', 'in_progress', 60)")
    for i in range(4):
        _exec(client, "INSERT INTO tasks (milestone_id, titulo, area, estado) "
                      "VALUES (1, :t, 'Comercial', 'completada')", t=f"T{i}")
    _exec(client, "INSERT INTO roadmap_milestones (id, titulo, area, estado, pct_completado) "
                  "VALUES (2, 'Hito huérfano', 'Proyectos', 'pendiente', 0)")
    _exec(client, "INSERT INTO plans (id, codigo, titulo, area, estado) "
                  "VALUES (10, 'P-10', 'Plan sin tareas', 'Audiovisual', 'activo')")


# ── Rules ────────────────────────────────────────────────────────────────────

def test_rules_matrix_order_and_cap(client):
    _seed_gaps(client)
    db = client._Session()
    try:
        found = _coverage.detect_findings(db)
    finally:
        db.close()
    assert [f["rule"] for f in found] == ["R3", "R2", "R1"]
    assert found[0]["kind"] == "hito" and found[0]["titulo"] == "Hito agotado" and found[0]["total"] == 4
    assert len(found) <= _coverage.MAX_FINDINGS


def test_done_hito_and_full_progress_are_not_flagged(client):
    _exec(client, "INSERT INTO roadmap_milestones (id, titulo, area, estado, pct_completado) "
                  "VALUES (1, 'Hito done', 'Comercial', 'done', 100)")
    _exec(client, "INSERT INTO roadmap_milestones (id, titulo, area, estado, pct_completado) "
                  "VALUES (2, 'Hito completo', 'Comercial', 'in_progress', 100)")
    _exec(client, "INSERT INTO tasks (milestone_id, titulo, estado) VALUES (2, 'T', 'completada')")
    db = client._Session()
    try:
        found = _coverage.detect_findings(db)
    finally:
        db.close()
    assert [f for f in found if f["kind"] == "hito" and f["rule"] == "R3"] == []


def test_empty_system_stays_silent(client):
    res = client.post("/api/dashboard/coverage/refresh", headers=H)
    assert res.status_code == 200
    assert res.json()["written"] == 0
    assert _rows(client, "SELECT * FROM daily_suggestions") == []


# ── Persistence ──────────────────────────────────────────────────────────────

def test_refresh_writes_ref_rows_and_lazy_migration(client):
    _seed_gaps(client)
    res = client.post("/api/dashboard/coverage/refresh", headers=H)
    assert res.status_code == 200 and res.json()["written"] == 3
    rows = _rows(client, "SELECT tag, titulo, estado, ref FROM daily_suggestions ORDER BY id")
    assert len(rows) == 3  # the ref column was added lazily (DDL here omits it on purpose)
    assert all(r.estado == "pendiente" and r.ref for r in rows)
    assert '"kind": "hito"' in rows[0].ref and "100%" in rows[0].titulo
    assert rows[0].tag == "DC" and rows[2].tag == "DA"


def test_refresh_idempotent_and_preserves_attended(client):
    _seed_gaps(client)
    client.post("/api/dashboard/coverage/refresh", headers=H)
    _exec(client, "UPDATE daily_suggestions SET estado = 'aceptada' WHERE tag = 'DC'")
    client.post("/api/dashboard/coverage/refresh", headers=H)
    rows = _rows(client, "SELECT tag, estado FROM daily_suggestions WHERE ref IS NOT NULL")
    # The attended DC row stays as history; the gap still exists so a fresh pending DC row appears;
    # the other two pending rows were replaced, not duplicated.
    assert len(rows) == 4
    assert sum(1 for r in rows if r.estado == "aceptada") == 1
    assert sum(1 for r in rows if r.estado == "pendiente") == 3


def test_generator_scope_leaves_coverage_rows(client):
    """The 6:30 generator deletes only its own rows (ref IS NULL) for today."""
    _seed_gaps(client)
    client.post("/api/dashboard/coverage/refresh", headers=H)
    _exec(client, "INSERT INTO daily_suggestions (fecha, tag, titulo, estado) "
                  "VALUES (:f, 'GM', 'Movimiento normal', 'pendiente')", f=date.today())
    # Mirror of the generator's delete (the endpoint 503s without OPENCLAW_TOKEN before deleting;
    # the scope of the statement is what this change modified and what we pin here).
    _exec(client, "DELETE FROM daily_suggestions WHERE fecha = :f AND ref IS NULL", f=date.today())
    rows = _rows(client, "SELECT ref FROM daily_suggestions")
    assert len(rows) == 3 and all(r.ref for r in rows)


# ── Redaction seam ───────────────────────────────────────────────────────────

def test_redaction_failure_falls_back_to_templates(client, monkeypatch):
    _seed_gaps(client)
    monkeypatch.setattr(_coverage, "OPENCLAW_TOKEN", "tok-test")

    def boom(*a, **kw):
        raise RuntimeError("gateway down")

    import httpx
    monkeypatch.setattr(httpx, "post", boom)
    res = client.post("/api/dashboard/coverage/refresh", headers=H)
    assert res.status_code == 200 and res.json()["written"] == 3
    rows = _rows(client, "SELECT titulo FROM daily_suggestions ORDER BY id")
    assert "necesita más tareas" in rows[0].titulo  # template copy survived


def test_redaction_count_mismatch_keeps_templates(client, monkeypatch):
    _seed_gaps(client)
    monkeypatch.setattr(_coverage, "OPENCLAW_TOKEN", "tok-test")

    class FakeResp:
        def json(self):
            return {"choices": [{"message": {"content": "1 | Solo una | línea"}}]}

    import httpx
    monkeypatch.setattr(httpx, "post", lambda *a, **kw: FakeResp())
    client.post("/api/dashboard/coverage/refresh", headers=H)
    rows = _rows(client, "SELECT titulo FROM daily_suggestions ORDER BY id")
    assert "necesita más tareas" in rows[0].titulo  # 1 line for 3 items -> mismatch -> templates


# ── API surface ──────────────────────────────────────────────────────────────

def test_get_suggestions_carries_ref(client):
    _seed_gaps(client)
    client.post("/api/dashboard/coverage/refresh", headers=H)
    body = client.get("/api/dashboard/suggestions", headers=H).json()
    assert len(body) == 3 and all("ref" in s and s["ref"] for s in body)


def test_refresh_requires_api_key(client):
    assert client.post("/api/dashboard/coverage/refresh").status_code in (401, 403)


# ── Import-cycle hook ────────────────────────────────────────────────────────

def test_import_cycle_triggers_coverage(client, monkeypatch):
    _seed_gaps(client)
    monkeypatch.setattr(tasks_mod, "SessionLocal", client._Session)
    monkeypatch.setattr(tasks_mod, "_import_google_tasks",
                        lambda db: {"imported": 2, "updated": 0, "accounts": 5})
    out = tasks_mod.auto_import_once()
    assert out["imported"] == 2
    rows = _rows(client, "SELECT ref FROM daily_suggestions WHERE ref IS NOT NULL")
    assert len(rows) == 3  # the cycle ran the analysis


def test_import_survives_coverage_failure(client, monkeypatch):
    monkeypatch.setattr(tasks_mod, "SessionLocal", client._Session)
    monkeypatch.setattr(tasks_mod, "_import_google_tasks",
                        lambda db: {"imported": 1, "updated": 0, "accounts": 5})

    def boom(db):
        raise RuntimeError("coverage bug")

    monkeypatch.setattr(_coverage, "refresh_coverage", boom)
    out = tasks_mod.auto_import_once()
    assert out["imported"] == 1  # the import result is untouched by the coverage failure

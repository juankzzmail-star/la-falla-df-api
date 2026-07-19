"""DB + API tests for the persistent task reader switch (change reset-task-reader-switch).

In-memory SQLite + StaticPool with the interview DDL plus app_config. The Google seam is mocked
(`_import_google_tasks` monkeypatched) — no network. Covers spec scenarios: missing key defaults
ON; reset turns the switch OFF (file-based sqlite so the endpoint's own engine sees the same DB);
estrategia answer wakes the reader with exactly one immediate import; non-strategy answers do not;
manual import re-enables; auto_import_once gate matrix (off+no-goals skips, off+goals self-heals,
on imports) with progress markers recorded; stale importing marker reads false; GET /api/interview
carries tasks_reader and tareas reports waiting when off+empty but the real status when tasks exist.
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
from api_gateway.routers import strategy as strategy_mod
from api_gateway.routers import tasks as tasks_mod

H = {"X-API-Key": "test-key-123"}
_AREAS = "'Comercial','Proyectos','Investigacion','Audiovisual'"
_AREAS_RISK = "'Comercial','Proyectos','Investigacion','Audiovisual','Transversal'"

_DDL = [
    """CREATE TABLE app_config (key TEXT PRIMARY KEY, value TEXT, updated_at TIMESTAMP)""",
    f"""CREATE TABLE strategic_goals (
        id INTEGER PRIMARY KEY AUTOINCREMENT, codigo TEXT UNIQUE NOT NULL, titulo TEXT NOT NULL,
        area TEXT NOT NULL CHECK (area IN ({_AREAS})), fecha_inicio DATE, fecha_fin_meta DATE,
        peso_porcentaje NUMERIC, estado TEXT NOT NULL DEFAULT 'activo')""",
    f"""CREATE TABLE plans (
        id INTEGER PRIMARY KEY AUTOINCREMENT, codigo TEXT UNIQUE NOT NULL, titulo TEXT NOT NULL,
        area TEXT NOT NULL CHECK (area IN ({_AREAS})), goal_id INTEGER, responsable TEXT,
        fecha_inicio DATE, fecha_fin_planificada DATE,
        estado TEXT NOT NULL DEFAULT 'activo' CHECK (estado IN ('propuesto','activo','pausado','cerrado')))""",
    """CREATE TABLE tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT, plan_id INTEGER, titulo TEXT NOT NULL,
        area TEXT, estado TEXT NOT NULL DEFAULT 'pendiente',
        prioridad TEXT NOT NULL DEFAULT 'media' CHECK (prioridad IN ('critica','alta','media','baja')))""",
    f"""CREATE TABLE risks (
        id INTEGER PRIMARY KEY AUTOINCREMENT, descripcion TEXT NOT NULL,
        area TEXT NOT NULL CHECK (area IN ({_AREAS_RISK})),
        impacto INTEGER NOT NULL, probabilidad INTEGER NOT NULL, nivel_riesgo INTEGER NOT NULL,
        estado_mitigacion TEXT NOT NULL DEFAULT 'monitoreado', origen TEXT NOT NULL DEFAULT 'ceo_manual',
        analisis_gentil TEXT, plan_mitigacion TEXT, fecha_analisis TIMESTAMP)""",
    """CREATE TABLE roadmap_milestones (
        id INTEGER PRIMARY KEY AUTOINCREMENT, titulo TEXT NOT NULL, orden INTEGER NOT NULL DEFAULT 0,
        estado TEXT NOT NULL DEFAULT 'pendiente', area TEXT, anio INTEGER, trimestre INTEGER,
        fecha_fin_planificada DATE, pct_completado NUMERIC NOT NULL DEFAULT 0, peso NUMERIC NOT NULL DEFAULT 1)""",
    """CREATE TABLE financial_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT, fecha DATE NOT NULL,
        caja_operativa NUMERIC NOT NULL DEFAULT 0, reservas_estrategicas NUMERIC NOT NULL DEFAULT 0,
        credito_disponible NUMERIC NOT NULL DEFAULT 0, gasto_mensual_promedio NUMERIC NOT NULL DEFAULT 0,
        liquidez_total NUMERIC NOT NULL DEFAULT 0, meses_respiracion NUMERIC NOT NULL DEFAULT 0)""",
    f"""CREATE TABLE area_kpi_config (
        id INTEGER PRIMARY KEY AUTOINCREMENT, area TEXT NOT NULL UNIQUE CHECK (area IN ({_AREAS})),
        kpi_code TEXT NOT NULL, label TEXT NOT NULL, target NUMERIC, period TEXT DEFAULT 'mensual')""",
    """CREATE TABLE dashboard_pending_panels (
        id INTEGER PRIMARY KEY AUTOINCREMENT, panel_id TEXT NOT NULL, endpoint TEXT NOT NULL,
        razon TEXT, llena_con TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, resuelto_en TIMESTAMP,
        domain TEXT, grupo TEXT, pregunta TEXT, campos_destino TEXT, respuesta TEXT, validada_en TIMESTAMP)""",
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


def _one(client, sql, **params):
    with client._engine.connect() as conn:
        return conn.execute(text(sql), params).fetchone()


def _flag(client):
    row = _one(client, "SELECT value FROM app_config WHERE key = 'tasks_reader_enabled'")
    return row[0] if row else None


# ── Switch helpers ───────────────────────────────────────────────────────────

def test_missing_key_defaults_to_enabled(client):
    db = client._Session()
    try:
        assert tasks_mod.tasks_reader_enabled(db) is True
    finally:
        db.close()


def test_set_and_read_roundtrip(client):
    db = client._Session()
    try:
        tasks_mod.set_tasks_reader(db, False)
        db.commit()
        assert tasks_mod.tasks_reader_enabled(db) is False
        tasks_mod.set_tasks_reader(db, True)
        db.commit()
        assert tasks_mod.tasks_reader_enabled(db) is True
    finally:
        db.close()
    assert _flag(client) == "1"


def test_missing_app_config_table_defaults_on_and_session_survives():
    """No app_config at all (bare DB): default ON and the swallowed error must not poison the
    session (rollback guard) — later queries in the same session still work."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    with engine.begin() as c:
        c.execute(text("CREATE TABLE strategic_goals (id INTEGER PRIMARY KEY, codigo TEXT)"))
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        assert tasks_mod.tasks_reader_enabled(db) is True
        assert db.execute(text("SELECT COUNT(*) FROM strategic_goals")).scalar() == 0
    finally:
        db.close()


def test_enable_is_idempotent_and_fires_one_import(client, monkeypatch):
    started = []
    monkeypatch.setattr(tasks_mod, "auto_import_enabled", lambda: True)
    monkeypatch.setattr(tasks_mod.threading, "Thread",
                        lambda **kw: type("T", (), {"start": lambda self: started.append(kw)})())
    db = client._Session()
    try:
        tasks_mod.set_tasks_reader(db, False)
        db.commit()
        assert tasks_mod.enable_tasks_reader_and_import(db) is True
        assert tasks_mod.enable_tasks_reader_and_import(db) is False  # already ON -> no-op
    finally:
        db.close()
    assert _flag(client) == "1"
    assert len(started) == 1  # exactly one immediate import


def test_importing_marker_staleness(client):
    db = client._Session()
    try:
        _exec(client, "INSERT INTO app_config (key, value, updated_at) "
                      "VALUES ('tasks_reader_importing', '1', CURRENT_TIMESTAMP)")
        assert tasks_mod.reader_importing(db) is True
        _exec(client, "UPDATE app_config SET updated_at = '2020-01-01 00:00:00' "
                      "WHERE key = 'tasks_reader_importing'")
        assert tasks_mod.reader_importing(db) is False  # dead cycle cannot wedge the state
    finally:
        db.close()


# ── auto_import_once gate matrix ─────────────────────────────────────────────

@pytest.fixture()
def cycle_env(client, monkeypatch):
    """Route auto_import_once at the fixture DB and mock the Google import core."""
    calls = []

    def fake_import(db):
        calls.append(1)
        return {"imported": 3, "updated": 1, "accounts": 5}

    monkeypatch.setattr(tasks_mod, "SessionLocal", client._Session)
    monkeypatch.setattr(tasks_mod, "_import_google_tasks", fake_import)
    return calls


def test_cycle_skips_when_reader_off_and_no_strategy(client, cycle_env):
    _exec(client, "INSERT INTO app_config (key, value) VALUES ('tasks_reader_enabled', '0')")
    out = tasks_mod.auto_import_once()
    assert out == {"skipped": "reader-off"}
    assert cycle_env == []  # google core never touched


def test_cycle_self_heals_when_strategy_exists(client, cycle_env):
    _exec(client, "INSERT INTO app_config (key, value) VALUES ('tasks_reader_enabled', '0')")
    _exec(client, "INSERT INTO strategic_goals (codigo, titulo, area) VALUES ('COM-1','Meta','Comercial')")
    out = tasks_mod.auto_import_once()
    assert out["imported"] == 3
    assert cycle_env == [1]
    assert _flag(client) == "1"  # the cycle woke the reader itself


def test_cycle_imports_when_reader_on_and_records_progress(client, cycle_env):
    out = tasks_mod.auto_import_once()  # missing key = ON
    assert out["imported"] == 3
    row = _one(client, "SELECT value FROM app_config WHERE key = 'tasks_reader_last_import'")
    assert row is not None and '"imported": 3' in row[0]
    marker = _one(client, "SELECT value FROM app_config WHERE key = 'tasks_reader_importing'")
    assert marker[0] == "0"  # cleared in the finally


# ── API integration ──────────────────────────────────────────────────────────

def test_reset_turns_reader_off(tmp_path, monkeypatch):
    """File-based sqlite so the endpoint's own engine (created from strategy.DATABASE_URL) sees
    the same database we assert against."""
    url = f"sqlite:///{tmp_path / 'reset.db'}"
    eng = create_engine(url)
    with eng.begin() as c:
        c.execute(text("CREATE TABLE app_config (key TEXT PRIMARY KEY, value TEXT, updated_at TIMESTAMP)"))
        c.execute(text("CREATE TABLE tasks (id INTEGER PRIMARY KEY, titulo TEXT)"))
        c.execute(text("INSERT INTO tasks (titulo) VALUES ('fantasma')"))
        c.execute(text("INSERT INTO app_config (key, value) VALUES ('tasks_reader_enabled', '1')"))
    monkeypatch.setattr(strategy_mod, "DATABASE_URL", url)
    monkeypatch.setattr(strategy_mod, "RESET_PASSWORD", "pw-test")
    with TestClient(app) as c:
        res = c.request("DELETE", "/api/strategy/reset", headers=H, json={"password": "pw-test"})
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True and data["tasks_reader_off"] is True
    assert "lector de tareas quedó apagado" in data["message"]
    with eng.connect() as c:
        assert c.execute(text("SELECT COUNT(*) FROM tasks")).scalar() == 0
        val = c.execute(text("SELECT value FROM app_config WHERE key='tasks_reader_enabled'")).scalar()
    assert val == "0"


def test_reset_idempotent_on_switch(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'reset2.db'}"
    eng = create_engine(url)
    with eng.begin() as c:
        c.execute(text("CREATE TABLE app_config (key TEXT PRIMARY KEY, value TEXT, updated_at TIMESTAMP)"))
        c.execute(text("INSERT INTO app_config (key, value) VALUES ('tasks_reader_enabled', '0')"))
    monkeypatch.setattr(strategy_mod, "DATABASE_URL", url)
    monkeypatch.setattr(strategy_mod, "RESET_PASSWORD", "pw-test")
    with TestClient(app) as c:
        res = c.request("DELETE", "/api/strategy/reset", headers=H, json={"password": "pw-test"})
    assert res.status_code == 200 and res.json()["tasks_reader_off"] is True
    with eng.connect() as c:
        assert c.execute(text("SELECT value FROM app_config WHERE key='tasks_reader_enabled'")).scalar() == "0"


def test_estrategia_answer_wakes_reader(client, monkeypatch):
    started = []
    monkeypatch.setattr(tasks_mod, "auto_import_enabled", lambda: True)
    monkeypatch.setattr(tasks_mod.threading, "Thread",
                        lambda **kw: type("T", (), {"start": lambda self: started.append(kw)})())
    _exec(client, "INSERT INTO app_config (key, value) VALUES ('tasks_reader_enabled', '0')")
    res = client.post("/api/interview/answer", headers=H, json={
        "domain": "estrategia",
        "answer": {"goals": [{"codigo": "COM-1", "titulo": "Meta comercial", "area": "Comercial",
                              "fecha_inicio": str(date.today()), "fecha_fin_meta": "2030-12-31",
                              "peso_porcentaje": 40}]},
    })
    assert res.status_code == 200, res.text
    assert _flag(client) == "1"
    assert len(started) == 1


def test_non_strategy_answer_does_not_wake_reader(client):
    _exec(client, "INSERT INTO app_config (key, value) VALUES ('tasks_reader_enabled', '0')")
    res = client.post("/api/interview/answer", headers=H, json={
        "domain": "liquidez",
        "answer": {"caja_operativa": 100000000, "reservas_estrategicas": 50000000,
                   "credito_disponible": 20000000, "gasto_mensual_promedio": 30000000},
    })
    assert res.status_code == 200, res.text
    assert _flag(client) == "0"  # only estrategia flips the switch


def test_manual_import_reenables_reader(client, monkeypatch):
    monkeypatch.setattr(tasks_mod, "_import_google_tasks",
                        lambda db: {"imported": 0, "updated": 0, "accounts": 0})
    _exec(client, "INSERT INTO app_config (key, value) VALUES ('tasks_reader_enabled', '0')")
    res = client.post("/api/tasks/import-google", headers=H)
    assert res.status_code == 200
    assert _flag(client) == "1"  # explicit CEO action outranks the gate


def test_interview_payload_carries_tasks_reader_and_waiting(client):
    _exec(client, "INSERT INTO app_config (key, value) VALUES ('tasks_reader_enabled', '0')")
    # Active plan + zero tasks would be 'thin' with the reader ON; OFF explains the absence.
    _exec(client, "INSERT INTO plans (codigo, titulo, area, responsable, fecha_inicio, "
                  "fecha_fin_planificada, estado) VALUES "
                  "('P-1','Plan','Comercial','Juan Carlos', :fi, '2026-12-31', 'activo')",
          fi=str(date.today()))
    body = client.get("/api/interview", headers=H).json()
    tr = body["tasks_reader"]
    assert tr["enabled"] is False and tr["importing"] is False and tr["last_import"] is None
    assert body["domain_status"]["tareas"] == "waiting"
    assert all(q["domain"] != "tareas" for q in body["questions"])


def test_existing_tasks_reported_honestly_with_reader_off(client):
    _exec(client, "INSERT INTO app_config (key, value) VALUES ('tasks_reader_enabled', '0')")
    _exec(client, "INSERT INTO tasks (plan_id, titulo, area, estado) VALUES (1, 'T1', 'Comercial', 'pendiente')")
    body = client.get("/api/interview", headers=H).json()
    assert body["domain_status"]["tareas"] == "ok"  # presence is never masked by the switch


def test_get_interview_does_not_write_the_switch(client):
    client.get("/api/interview", headers=H)
    assert _flag(client) is None  # read-only: no row materialized

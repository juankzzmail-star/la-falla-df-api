"""DB + API tests for the completeness interview (change completeness-interview).

Isolated in-memory SQLite + StaticPool, portable raw DDL mirroring the prod CHECK constraints.
The only LLM seam (parse_freetext_answer) is exercised for its honest-503 path; the structured
answer paths need no network. Covers spec scenarios: empty domains -> gap questions; thin domains
-> enrich; full dashboard -> empty queue + 100%; registry has 7 specialists and excludes
daily_suggestions; questions ask inputs not results; validated write-back (risks/liquidez) with
computed values; rejection of out-of-range and objective-instead-of-current answers; inferred plans
are enrich not gap; auth on /api/*; honest 503 with no provider.
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
from api_gateway.routers import _interview

H = {"X-API-Key": "test-key-123"}
_AREAS = "'Comercial','Proyectos','Investigacion','Audiovisual'"
_AREAS_RISK = "'Comercial','Proyectos','Investigacion','Audiovisual','Transversal'"

_DDL = [
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
        id INTEGER PRIMARY KEY AUTOINCREMENT, plan_id INTEGER NOT NULL, titulo TEXT NOT NULL,
        area TEXT, estado TEXT NOT NULL DEFAULT 'pendiente',
        prioridad TEXT NOT NULL DEFAULT 'media' CHECK (prioridad IN ('critica','alta','media','baja')))""",
    f"""CREATE TABLE risks (
        id INTEGER PRIMARY KEY AUTOINCREMENT, descripcion TEXT NOT NULL,
        area TEXT NOT NULL CHECK (area IN ({_AREAS_RISK})),
        impacto INTEGER NOT NULL CHECK (impacto BETWEEN 1 AND 5),
        probabilidad INTEGER NOT NULL CHECK (probabilidad BETWEEN 1 AND 5),
        nivel_riesgo INTEGER NOT NULL,
        estado_mitigacion TEXT NOT NULL DEFAULT 'monitoreado'
            CHECK (estado_mitigacion IN ('monitoreado','en_mitigacion','critico','resuelto')),
        origen TEXT NOT NULL DEFAULT 'ceo_manual',
        analisis_gentil TEXT, plan_mitigacion TEXT, fecha_analisis TIMESTAMP)""",
    """CREATE TABLE roadmap_milestones (
        id INTEGER PRIMARY KEY AUTOINCREMENT, titulo TEXT NOT NULL, orden INTEGER NOT NULL DEFAULT 0,
        estado TEXT NOT NULL DEFAULT 'pendiente'
            CHECK (estado IN ('done','in_progress','delayed','pendiente')),
        area TEXT, anio INTEGER, trimestre INTEGER, fecha_fin_planificada DATE,
        pct_completado NUMERIC NOT NULL DEFAULT 0, peso NUMERIC NOT NULL DEFAULT 1)""",
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
        yield c
    app.dependency_overrides.clear()


def _exec(client, sql, **params):
    with client._engine.begin() as conn:
        conn.execute(text(sql), params)


def _rows(client, sql, **params):
    with client._engine.connect() as conn:
        return conn.execute(text(sql), params).fetchall()


def _seed_all_ok(client):
    """Seed every domain so the dashboard is complete (no questions)."""
    _exec(client, "INSERT INTO strategic_goals (codigo, titulo, area, fecha_inicio, fecha_fin_meta, peso_porcentaje) "
                  "VALUES ('COM-1','Meta','Comercial', :fi, '2030-12-31', 40)", fi=date.today().isoformat())
    _exec(client, "INSERT INTO roadmap_milestones (titulo, orden, estado) VALUES ('Hito 1', 1, 'in_progress')")
    _exec(client, "INSERT INTO financial_snapshots (fecha, caja_operativa, reservas_estrategicas, credito_disponible, gasto_mensual_promedio, liquidez_total, meses_respiracion) "
                  "VALUES (:f, 5000000, 2000000, 1000000, 800000, 8000000, 10)", f=date.today().isoformat())
    _exec(client, "INSERT INTO risks (descripcion, area, impacto, probabilidad, nivel_riesgo, estado_mitigacion) "
                  "VALUES ('Riesgo', 'Comercial', 3, 3, 9, 'monitoreado')")
    for a in ("Comercial", "Proyectos", "Investigacion", "Audiovisual"):
        _exec(client, "INSERT INTO area_kpi_config (area, kpi_code, label, target, period) "
                      "VALUES (:a, 'K', 'KPI', 100, 'mensual')", a=a)


# ── Auth ─────────────────────────────────────────────────────────────────────
def test_interview_requires_api_key(client):
    assert client.get("/api/interview").status_code in (401, 403)
    assert client.post("/api/interview/answer", json={"domain": "riesgos", "answer": {}}).status_code in (401, 403)


# ── Registry shape ────────────────────────────────────────────────────────────
def test_registry_has_seven_specialists_excluding_suggestions():
    assert len(_interview.SPECIALISTS) == 7
    assert "daily_suggestions" not in _interview.SPECIALISTS
    assert "daily_suggestions" in _interview.EXCLUDED_DOMAINS


def test_estrategia_validator_accepts_transversal():
    # change ingest-real-strategy: governance goals are area='Transversal'.
    ok, err, _ = _interview._validate_estrategia(
        {"goals": [{"codigo": "GOV-1", "titulo": "Gobierno", "area": "Transversal"}]})
    assert ok, err


def test_questions_ask_inputs_not_computed_results():
    liq = _interview.SPECIALISTS["liquidez"]["ask_inputs"]
    assert "gasto_mensual_promedio" in liq
    assert "meses_respiracion" not in liq and "liquidez_total" not in liq
    rsk = _interview.SPECIALISTS["riesgos"]["ask_inputs"]
    assert "impacto" in rsk and "probabilidad" in rsk
    assert "nivel_riesgo" not in rsk


# ── Detection -> questions ────────────────────────────────────────────────────
def test_empty_domains_become_gap_questions(client):
    r = client.get("/api/interview", headers=H)
    assert r.status_code == 200, r.text
    by_domain = {q["domain"]: q for q in r.json()["questions"]}
    for dom in ("riesgos", "roadmap", "liquidez", "kpi_areas"):
        assert by_domain[dom]["grupo"] == "gap", dom
    assert by_domain["riesgos"]["target_table"] == "risks"


def test_thin_strategic_goals_yield_enrich(client):
    _exec(client, "INSERT INTO strategic_goals (codigo, titulo, area, peso_porcentaje) "
                  "VALUES ('COM-1','Meta','Comercial', NULL)")  # missing peso + fecha_inicio
    q = {x["domain"]: x for x in client.get("/api/interview", headers=H).json()["questions"]}
    assert q["estrategia"]["grupo"] == "enrich"


def test_inferred_plans_are_enrich_not_gap(client):
    _exec(client, "INSERT INTO plans (codigo, titulo, area, responsable, fecha_fin_planificada) "
                  "VALUES ('P-1','Plan','Comercial', NULL, NULL)")  # thin: null responsable/fecha
    q = {x["domain"]: x for x in client.get("/api/interview", headers=H).json()["questions"]}
    assert q["planes"]["grupo"] == "enrich"   # never 'gap'


def test_full_dashboard_yields_no_questions(client):
    _seed_all_ok(client)
    body = client.get("/api/interview", headers=H).json()
    assert body["questions"] == []
    assert body["completitud_pct"] == 100


# ── Write-back + validation ───────────────────────────────────────────────────
def test_submit_risk_writeback_computes_nivel(client):
    answer = {"risks": [{"descripcion": "Dependencia de un solo financiador", "area": "Comercial",
                         "impacto": 4, "probabilidad": 3, "estado_mitigacion": "en_mitigacion"}]}
    # register the panel first so resolution has something to close
    client.get("/api/interview", headers=H)
    r = client.post("/api/interview/answer", json={"domain": "riesgos", "answer": answer}, headers=H)
    assert r.status_code == 200, r.text
    assert r.json()["estado"] == "resuelto"
    rows = _rows(client, "SELECT impacto, probabilidad, nivel_riesgo FROM risks")
    assert len(rows) == 1 and rows[0][2] == rows[0][0] * rows[0][1] == 12
    resolved = _rows(client, "SELECT resuelto_en FROM dashboard_pending_panels WHERE panel_id='riesgos'")
    assert resolved and resolved[0][0] is not None


def test_submit_risk_out_of_range_rejected(client):
    answer = {"risks": [{"descripcion": "x", "area": "Comercial", "impacto": 9,
                         "probabilidad": 3, "estado_mitigacion": "monitoreado"}]}
    r = client.post("/api/interview/answer", json={"domain": "riesgos", "answer": answer}, headers=H)
    assert r.status_code == 422
    assert _rows(client, "SELECT COUNT(*) FROM risks")[0][0] == 0


def test_submit_liquidez_writeback_computes_runway(client):
    answer = {"fecha": date.today().isoformat(), "caja_operativa": 6000000,
              "reservas_estrategicas": 2000000, "credito_disponible": 1000000,
              "gasto_mensual_promedio": 900000}
    client.get("/api/interview", headers=H)
    r = client.post("/api/interview/answer", json={"domain": "liquidez", "answer": answer}, headers=H)
    assert r.status_code == 200, r.text
    rows = _rows(client, "SELECT liquidez_total, meses_respiracion FROM financial_snapshots")
    assert len(rows) == 1
    assert float(rows[0][0]) == 9000000.0
    assert round(float(rows[0][1]), 2) == 10.0   # 9.0M / 0.9M


def test_submit_liquidez_rejects_objective(client):
    # Mentions finance but supplies a TARGET, not a current actual (Lección A).
    answer = {"es_objetivo": True, "caja_operativa": 99999999, "reservas_estrategicas": 0,
              "credito_disponible": 0, "gasto_mensual_promedio": 85000000}
    r = client.post("/api/interview/answer", json={"domain": "liquidez", "answer": answer}, headers=H)
    assert r.status_code == 422
    assert _rows(client, "SELECT COUNT(*) FROM financial_snapshots")[0][0] == 0


def test_submit_roadmap_captures_anio(client):
    # The 'Ejecución 2030' grid flips from DEMO (anio NULL seed) to real only when hitos carry a year.
    # Two capture paths: explicit `anio`, and `anio` derived from the year of `fecha_fin_planificada`.
    answer = {"milestones": [
        {"titulo": "Cumbre ACMI", "orden": 1, "estado": "in_progress", "area": "Audiovisual", "anio": 2026},
        {"titulo": "Escalado nacional", "orden": 2, "estado": "pendiente", "area": "Comercial",
         "fecha_fin_planificada": "2030-12-31"},
    ]}
    client.get("/api/interview", headers=H)
    r = client.post("/api/interview/answer", json={"domain": "roadmap", "answer": answer}, headers=H)
    assert r.status_code == 200, r.text
    anios = {t: a for t, a in _rows(client, "SELECT titulo, anio FROM roadmap_milestones ORDER BY orden")}
    assert anios["Cumbre ACMI"] == 2026          # explicit anio
    assert anios["Escalado nacional"] == 2030    # derived from fecha_fin_planificada year


def test_submit_unknown_domain_rejected(client):
    r = client.post("/api/interview/answer", json={"domain": "nope", "answer": {}}, headers=H)
    assert r.status_code == 400


# ── Honest 503 (LLM seam) ─────────────────────────────────────────────────────
def test_freetext_parse_503_without_provider(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as ei:
        _interview.parse_freetext_answer("riesgos", "tenemos un riesgo grande con el financiador")
    assert ei.value.status_code == 503

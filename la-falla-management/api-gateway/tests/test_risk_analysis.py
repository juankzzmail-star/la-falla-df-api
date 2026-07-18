"""ddl_v14 / risk radar: Gentil's deep brain (DeepSeek V4 Pro) analyses each risk and proposes new
strategic risks from live signals. Covers the new, risky pieces in isolation (SQLite + StaticPool,
no Postgres, no real DeepSeek call — the brain is monkeypatched):
  (1) _brain.parse_json robustness (clean / fenced / prose-wrapped / invalid);
  (2) RiskOut exposes plan_mitigacion as a real list (JSON-text column → list);
  (3) POST /risks/{id}/analyze persists analisis_gentil + plan_mitigacion + fecha_analisis;
  (4) POST /risks/heartbeat analyses pending risks, is idempotent, and proposes deduped new risks;
  (5) heartbeat 503s honestly when the deep brain is unconfigured.
"""
import os
import json
from datetime import date, timedelta

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("FASTAPI_GM_API_KEY", "test-key-123")
os.environ.setdefault("FASTAPI_API_KEY", "test-key-123")
os.environ.setdefault("DEEPSEEK_API_KEY", "test-deepseek-key")  # makes _brain.available() True

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api_gateway.db import get_db
from api_gateway.main import app
from api_gateway.routers import _brain

H = {"X-API-Key": "test-key-123"}

_DDL_RISKS = """CREATE TABLE risks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    descripcion TEXT NOT NULL, area TEXT NOT NULL,
    impacto INTEGER NOT NULL, probabilidad INTEGER NOT NULL, nivel_riesgo INTEGER NOT NULL,
    estado_mitigacion TEXT NOT NULL DEFAULT 'monitoreado', responsable TEXT,
    origen TEXT NOT NULL DEFAULT 'ceo_manual',
    fecha_identificacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP, fecha_revision TIMESTAMP,
    project_id INTEGER, estrategia TEXT DEFAULT 'Mitigar', plan_accion TEXT,
    causa TEXT, efecto TEXT, paquete TEXT,
    analisis_gentil TEXT, plan_mitigacion TEXT, fecha_analisis TIMESTAMP)"""

_DDL_TASKS = """CREATE TABLE tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT, area TEXT, estado TEXT, fecha_vencimiento DATE)"""


@pytest.fixture()
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    overdue = (date.today() - timedelta(days=10)).isoformat()
    with engine.begin() as c:
        c.execute(text(_DDL_RISKS))
        c.execute(text(_DDL_TASKS))
        # two risks without Gentil's analysis yet (pending)
        c.execute(text("INSERT INTO risks (descripcion, area, impacto, probabilidad, nivel_riesgo, origen) "
                       "VALUES ('Sobrecosto en Rutas Cafeteras 02','Dirección de Proyectos',4,4,16,'ceo_manual')"))
        c.execute(text("INSERT INTO risks (descripcion, area, impacto, probabilidad, nivel_riesgo, origen) "
                       "VALUES ('Silencio de MinCultura','Dirección Comercial',3,3,9,'ceo_manual')"))
        # a live signal so the radar has something to ground a proposal on
        c.execute(text("INSERT INTO tasks (area, estado, fecha_vencimiento) "
                       "VALUES ('Dirección Audiovisual','pendiente',:d)"), {"d": overdue})
    TS = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override():
        db = TS()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override
    with TestClient(app) as cl:
        yield cl
    app.dependency_overrides.clear()


# ── _brain.parse_json (pure, no DB) ─────────────────────────────────────────
def test_parse_clean_object():
    assert _brain.parse_json('{"analisis":"x","plan_mitigacion":["a"]}')["analisis"] == "x"


def test_parse_markdown_fenced():
    raw = '```json\n{"analisis":"y","plan_mitigacion":[]}\n```'
    assert _brain.parse_json(raw)["analisis"] == "y"


def test_parse_prose_wrapped():
    raw = 'Claro, aquí va:\n{"nuevos_riesgos":[]}\nListo.'
    assert _brain.parse_json(raw) == {"nuevos_riesgos": []}


def test_parse_invalid_raises():
    with pytest.raises(ValueError):
        _brain.parse_json("ni json ni nada parseable")


# ── analyze endpoint ────────────────────────────────────────────────────────
def test_analyze_persists_and_returns_list(client, monkeypatch):
    monkeypatch.setattr(_brain, "deep_analysis", lambda *a, **k: json.dumps(
        {"analisis": "El sobrecosto ya está ocurriendo durante el rodaje activo.",
         "plan_mitigacion": ["Auditar gastos con el director de proyectos", "Renegociar post-producción"]}))
    rid = client.get("/api/risks", headers=H).json()[0]["id"]
    r = client.post(f"/api/risks/{rid}/analyze", headers=H)
    assert r.status_code == 200
    body = r.json()
    assert body["analisis_gentil"].startswith("El sobrecosto")
    assert body["plan_mitigacion"] == ["Auditar gastos con el director de proyectos", "Renegociar post-producción"]
    assert body["fecha_analisis"] is not None
    # persisted: re-reading the list exposes plan_mitigacion as a real array, not a JSON string
    again = [x for x in client.get("/api/risks", headers=H).json() if x["id"] == rid][0]
    assert isinstance(again["plan_mitigacion"], list) and len(again["plan_mitigacion"]) == 2


def test_analyze_missing_404(client, monkeypatch):
    monkeypatch.setattr(_brain, "deep_analysis", lambda *a, **k: '{"analisis":"x","plan_mitigacion":[]}')
    assert client.post("/api/risks/9999/analyze", headers=H).status_code == 404


def test_analyze_bad_format_502(client, monkeypatch):
    monkeypatch.setattr(_brain, "deep_analysis", lambda *a, **k: "esto no es json")
    rid = client.get("/api/risks", headers=H).json()[0]["id"]
    assert client.post(f"/api/risks/{rid}/analyze", headers=H).status_code == 502


# ── heartbeat (analyse pending + propose new, deduped) ───────────────────────
def _fake_brain(system, prompt, *a, **k):
    if "nuevos_riesgos" in prompt:
        return json.dumps({"nuevos_riesgos": [
            {"descripcion": "Dependencia de una sola persona en Audiovisual", "area": "Dirección Audiovisual",
             "impacto": 4, "probabilidad": 3, "estrategia": "Mitigar", "analisis": "Carga estructural.",
             "plan_mitigacion": ["Mapear un respaldo audiovisual"]},
            # duplicate of an existing risk — must be deduped out
            {"descripcion": "Silencio de MinCultura", "area": "Dirección Comercial", "impacto": 3, "probabilidad": 3},
        ]})
    return json.dumps({"analisis": "Análisis profundo de Gentil.", "plan_mitigacion": ["Acción 1", "Acción 2"]})


def test_heartbeat_analyses_and_proposes(client, monkeypatch):
    monkeypatch.setattr(_brain, "deep_analysis", _fake_brain)
    out = client.post("/api/risks/heartbeat", headers=H).json()
    assert out["analizados"] == 2          # both seeded risks lacked analysis
    assert out["propuestos"] == 1          # one new; the MinCultura dup was filtered
    risks = client.get("/api/risks", headers=H).json()
    autos = [r for r in risks if r["origen"] == "gentil_auto"]
    assert len(autos) == 1 and autos[0]["nivel_riesgo"] == 12  # 4×3
    # idempotent: nothing left to analyse on a second pass
    out2 = client.post("/api/risks/heartbeat", headers=H).json()
    assert out2["analizados"] == 0


def test_heartbeat_503_without_brain(client, monkeypatch):
    monkeypatch.setattr(_brain, "available", lambda: False)
    assert client.post("/api/risks/heartbeat", headers=H).status_code == 503

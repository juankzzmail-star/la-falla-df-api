"""change openclaw-daily-reading: la 'Lectura del día' la redacta el cerebro de Gentil (gateway
OpenClaw, model="openclaw"), no una llamada directa a la API de Groq. Cubre:
  (1) parseo ROBUSTO del JSON de OpenClaw (puede venir con fences markdown o envuelto en prosa);
  (2) edición PERSISTENTE del CEO (antes solo cambiaba estado local y se perdía al recargar),
      manteniendo la sugerencia visible (editar != resolver);
  (3) GET de hoy + PATCH de estado.
SQLite aislado + StaticPool (no toca Postgres de prod). El generador en sí usa SQL Postgres-only
(FILTER) y no se prueba aquí — se valida la pieza nueva y arriesgada: el parser y la edición."""
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
from api_gateway.routers.dashboard import _parse_suggestions_json

H = {"X-API-Key": "test-key-123"}

_DDL = """CREATE TABLE daily_suggestions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, fecha DATE NOT NULL, tag TEXT NOT NULL,
    titulo TEXT NOT NULL, cuerpo TEXT, estado TEXT NOT NULL DEFAULT 'pendiente',
    ref TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"""


@pytest.fixture()
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    today = date.today().isoformat()
    with engine.begin() as c:
        c.execute(text(_DDL))
        c.execute(text("INSERT INTO daily_suggestions (fecha, tag, titulo, cuerpo, estado) "
                       "VALUES (:f,'DC','Llamar a Risaralda','Ventana óptima esta semana.','pendiente')"), {"f": today})
        c.execute(text("INSERT INTO daily_suggestions (fecha, tag, titulo, cuerpo, estado) "
                       "VALUES (:f,'DP','Revisar sobrecosto','Desviación +7%.','pendiente')"), {"f": today})
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


# ── parseo de la respuesta de OpenClaw (función pura, sin DB) ─────────────
# Formato JSON (sigue soportado por si el gateway lo devuelve)
def test_parse_clean_array():
    out = _parse_suggestions_json('[{"tag":"DC","titulo":"X","cuerpo":"Y"}]')
    assert out == [{"tag": "DC", "titulo": "X", "cuerpo": "Y"}]


def test_parse_markdown_fenced():
    raw = '```json\n[{"tag":"DP","titulo":"A","cuerpo":"B"}]\n```'
    assert _parse_suggestions_json(raw)[0]["tag"] == "DP"


def test_parse_prose_wrapped():
    raw = 'Claro, aquí van los 3 movimientos de hoy:\n[{"tag":"DA","titulo":"A","cuerpo":"B"}]\n¡Éxitos!'
    assert _parse_suggestions_json(raw)[0]["tag"] == "DA"


# Formato pipes 'TAG | Título | Cuerpo' (lo que OpenClaw devuelve de forma fiable con tool_choice=none)
def test_parse_pipe_lines():
    raw = ("DC | Llamar a MinCultura | Van 24 días sin respuesta.\n"
           "DP | Revisar sobrecosto Rutas | Desviación +7%, validar línea base.\n"
           "DA | Aprobar guion ACMI | Entrega el viernes.")
    out = _parse_suggestions_json(raw)
    assert [s["tag"] for s in out] == ["DC", "DP", "DA"]
    assert out[0]["titulo"] == "Llamar a MinCultura"
    assert out[1]["cuerpo"].startswith("Desviación +7%")


def test_parse_pipe_with_preamble_and_markdown():
    # tolera prosa antes, negritas y comillas — y descarta líneas que no son movimientos
    raw = ("Aquí están tus 3 movimientos:\n"
           'DC | **Cerrar propuesta Risaralda** | "Ventana óptima esta semana."\n'
           "Nota: prioriza lo comercial.")
    out = _parse_suggestions_json(raw)
    assert len(out) == 1
    assert out[0]["tag"] == "DC"
    assert out[0]["titulo"] == "Cerrar propuesta Risaralda"
    assert out[0]["cuerpo"] == "Ventana óptima esta semana."


def test_parse_invalid_raises():
    with pytest.raises(ValueError):
        _parse_suggestions_json("no hay ni json ni líneas con pipes aquí")


# ── endpoints ─────────────────────────────────────────────────────────────
def test_get_returns_today(client):
    rows = client.get("/api/dashboard/suggestions", headers=H).json()
    assert len(rows) == 2
    assert {r["estado"] for r in rows} == {"pendiente"}


def test_edit_persists_and_marks_editada(client):
    rid = client.get("/api/dashboard/suggestions", headers=H).json()[0]["id"]
    r = client.patch(f"/api/dashboard/suggestions/{rid}",
                     json={"titulo": "Título editado por el CEO", "cuerpo": "Nuevo contexto."}, headers=H)
    assert r.status_code == 200
    body = r.json()
    assert body["titulo"] == "Título editado por el CEO"
    assert body["cuerpo"] == "Nuevo contexto."
    # editar es una interacción que CONSUME: queda 'editada' (sale del panel; el front filtra 'pendiente')
    assert body["estado"] == "editada"
    # el texto refinado persiste (queda en el registro)
    again = client.get("/api/dashboard/suggestions", headers=H).json()
    edited = [x for x in again if x["id"] == rid][0]
    assert edited["titulo"] == "Título editado por el CEO"
    assert edited["estado"] == "editada"


def test_status_patch_resolves(client):
    rid = client.get("/api/dashboard/suggestions", headers=H).json()[0]["id"]
    r = client.patch(f"/api/dashboard/suggestions/{rid}/status", json={"estado": "aceptada"}, headers=H)
    assert r.status_code == 200 and r.json()["estado"] == "aceptada"


def test_edit_missing_404(client):
    r = client.patch("/api/dashboard/suggestions/9999", json={"titulo": "x"}, headers=H)
    assert r.status_code == 404

"""edt-name-transform-remove (AUD-018): EDT node names are persisted VERBATIM — no LLM rename, no "{}".

Runs in the image layout (`import api_gateway`). `EDT_LLM_MODE` is forced to 'mock' (prod's real value) to
LOCK the regression: the OLD code routed `nombre` through `_transform_name` → the mock LLM, which returns the
literal "{}" for any non-keyword name. These tests fail against the old code and pass once the transform is
removed.

ARRAY columns (consulted/informed/predecesores) are left NULL — SQLite cannot bind python lists (verified) and
these tests only concern `nombre`.
"""
import os

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("FASTAPI_GM_API_KEY", "test-key-123")
os.environ.setdefault("FASTAPI_API_KEY", "test-key-123")
os.environ["EDT_LLM_MODE"] = "mock"  # prod value; the old transform yielded "{}" under mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api_gateway.db import get_db
from api_gateway.main import app

H = {"X-API-Key": "test-key-123"}

_DDL_PROJECTS = """CREATE TABLE projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo TEXT UNIQUE NOT NULL, nombre TEXT NOT NULL, area TEXT NOT NULL,
    presupuesto NUMERIC NOT NULL DEFAULT 0, ejecutado NUMERIC NOT NULL DEFAULT 0,
    estado TEXT NOT NULL DEFAULT 'activo',
    plan_id INTEGER, milestone_id INTEGER, anio INTEGER, origen TEXT NOT NULL DEFAULT 'planeado',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"""

_DDL_EDT = """CREATE TABLE edt_nodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL, parent_id INTEGER,
    codigo TEXT NOT NULL, nivel INTEGER NOT NULL DEFAULT 1, nombre TEXT NOT NULL,
    descripcion_dict TEXT, responsable TEXT, accountable TEXT,
    consulted TEXT, informed TEXT, predecesores TEXT,
    costo_estimado NUMERIC DEFAULT 0, duracion_dias INTEGER DEFAULT 0, porcentaje_avance INTEGER DEFAULT 0,
    es_paquete_trabajo BOOLEAN DEFAULT 1, es_hito BOOLEAN DEFAULT 0,
    estado TEXT DEFAULT 'planificado', alerta TEXT,
    approved_by TEXT, approved_at TIMESTAMP, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"""


@pytest.fixture()
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    with engine.begin() as c:
        c.execute(text(_DDL_PROJECTS))
        c.execute(text(_DDL_EDT))
        c.execute(text("INSERT INTO projects (codigo, nombre, area) "
                       "VALUES ('RC02', 'Rutas Cafeteras 02', 'Audiovisual')"))
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


def test_create_edt_node_stores_name_verbatim(client):
    r = client.post("/api/projects/1/edt", headers=H,
                    json={"codigo": "1.1", "nombre": "Instalar 30 equipos"})
    assert r.status_code == 201, r.text
    assert r.json()["nombre"] == "Instalar 30 equipos"   # never "{}", never transformed


def test_patch_edt_node_stores_name_verbatim(client):
    nid = client.post("/api/projects/1/edt", headers=H,
                      json={"codigo": "1.2", "nombre": "x"}).json()["id"]
    r = client.patch(f"/api/projects/1/edt/{nid}", headers=H,
                     json={"nombre": "Filmar escena nocturna"})
    assert r.status_code == 200, r.text
    assert r.json()["nombre"] == "Filmar escena nocturna"


def test_name_untouched_under_mock_mode(client):
    # Under EDT_LLM_MODE=mock (prod's value) the old code stored "{}". It must now be verbatim.
    r = client.post("/api/projects/1/edt", headers=H,
                    json={"codigo": "1.3", "nombre": "Contratar guionista senior"})
    assert r.status_code == 201, r.text
    assert r.json()["nombre"] == "Contratar guionista senior"
    assert r.json()["nombre"] != "{}"

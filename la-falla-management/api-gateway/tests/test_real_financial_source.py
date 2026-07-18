"""change real-financial-source: la caja del Centro de Mando sale del libro real (MOVIMIENTOS 2026, lo
lleva el Director Comercial y Financiero), no de un placeholder. /dashboard/financial-snapshots expone la
fuente (spreadsheet_id -> view_url / download_url .xlsx) y la matemática de runway funciona con reservas=0
(el colchón real es la línea de crédito, no un fondo de reservas separado). SQLite aislado + StaticPool."""
import os

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

H = {"X-API-Key": "test-key-123"}

_DDL = [
    """CREATE TABLE financial_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT, fecha DATE NOT NULL,
        caja_operativa NUMERIC NOT NULL DEFAULT 0, reservas_estrategicas NUMERIC NOT NULL DEFAULT 0,
        credito_disponible NUMERIC NOT NULL DEFAULT 0, gasto_mensual_promedio NUMERIC NOT NULL DEFAULT 0,
        liquidez_total NUMERIC NOT NULL DEFAULT 0, meses_respiracion NUMERIC NOT NULL DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
    """CREATE TABLE financial_flows (
        id INTEGER PRIMARY KEY AUTOINCREMENT, tipo TEXT NOT NULL, descripcion TEXT NOT NULL,
        monto NUMERIC NOT NULL, horizonte_dias INTEGER, frecuencia TEXT, fecha_estimada DATE, origen TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
    """CREATE TABLE financial_data_sources (
        id INTEGER PRIMARY KEY AUTOINCREMENT, fuente TEXT NOT NULL UNIQUE, spreadsheet_id TEXT,
        ultima_sincronizacion TIMESTAMP, estado TEXT DEFAULT 'ok')""",
]

SHEET_ID = "1ANHhfeWECyf9bv3tQbe003wtZvijJGFy6hXB7XV1iPY"


@pytest.fixture()
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    with engine.begin() as c:
        for ddl in _DDL:
            c.execute(text(ddl))
        # snapshot real de cierre marzo: caja 543K (banco), sin reservas, crédito = respaldo del fundador
        c.execute(text(
            "INSERT INTO financial_snapshots (fecha, caja_operativa, reservas_estrategicas, "
            "credito_disponible, gasto_mensual_promedio, liquidez_total, meses_respiracion) "
            "VALUES ('2026-03-30', 543227, 0, 7167061, 7700000, 7710288, 1.0)"))
        c.execute(text(
            "INSERT INTO financial_data_sources (fuente, spreadsheet_id, ultima_sincronizacion, estado) "
            "VALUES ('MOVIMIENTOS 2026 — Dir. Comercial y Financiera', :sid, '2026-04-08T00:57:00', 'ok')"),
            {"sid": SHEET_ID})
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


def test_source_exposes_drive_links(client):
    src = client.get("/api/dashboard/financial-snapshots", headers=H).json()["source"]
    assert src is not None
    assert src["spreadsheet_id"] == SHEET_ID
    assert src["view_url"] == f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit"
    assert src["download_url"] == f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=xlsx"
    # nunca exponer la fuente ficticia "Quinaya" — la caja la lleva el Director Comercial y Financiero
    assert "Quinaya" not in src["fuente"]


def test_runway_with_zero_reserves(client):
    latest = client.get("/api/dashboard/financial-snapshots", headers=H).json()["latest"]
    # cash runway = caja pura (sin reservas) / gasto = 0.5432.../7.7 ≈ 0.1 meses -> rojo (crisis)
    assert latest["cash_runway_meses"] == 0.1
    assert latest["cash_runway_rag"] == "rojo"
    # funded runway = (caja + crédito del fundador) / gasto ≈ 1.0 meses -> sigue rojo, pero respira
    assert latest["funded_runway_meses"] == 1.0
    assert latest["funded_runway_rag"] == "rojo"


def test_no_quinaya_source_string(client):
    """La fuente jamás debe llamarse 'Quinaya' (es la Directora de Investigación, no quien lleva la caja)."""
    data = client.get("/api/dashboard/financial-snapshots", headers=H).json()
    assert "Quinaya" not in (data["source"]["fuente"] if data.get("source") else "")

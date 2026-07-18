"""change rigorous-progress-math: /dashboard/financial-snapshots separates CASH runway (caja + reservas,
what you actually hold) from FUNDED runway (+ undrawn credit, a contingent cushion, NOT cash) — CFI /
startup-finance doctrine. Each gets a RAG band (<3 rojo / 3-6 ambar / 6-12 ok / >12 verde). Isolated
in-memory SQLite + StaticPool."""
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
]


@pytest.fixture()
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    with engine.begin() as c:
        for ddl in _DDL:
            c.execute(text(ddl))
    TS = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override():
        db = TS()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override
    with TestClient(app) as cl:
        cl._engine = engine
        yield cl
    app.dependency_overrides.clear()


def _snap(client, fecha, caja, reservas, credito, gasto):
    liq = caja + reservas + credito
    with client._engine.begin() as c:
        c.execute(text(
            "INSERT INTO financial_snapshots (fecha, caja_operativa, reservas_estrategicas, "
            "credito_disponible, gasto_mensual_promedio, liquidez_total, meses_respiracion) "
            "VALUES (:f,:c,:r,:cr,:g,:lt,:m)"),
            {"f": fecha, "c": caja, "r": reservas, "cr": credito, "g": gasto, "lt": liq,
             "m": round(liq / gasto, 2) if gasto else 0})


def test_cash_runway_separated_from_funded(client):
    # caja 5.2M + reservas 2.8M = 8.0M cash ; + crédito 1.2M = 9.2M funded ; gasto 0.75M/mes
    _snap(client, "2026-06-01", 5_200_000, 2_800_000, 1_200_000, 750_000)
    latest = client.get("/api/dashboard/financial-snapshots", headers=H).json()["latest"]
    assert latest["cash_runway_meses"] == 10.7      # (5.2+2.8)/0.75, sin contar crédito
    assert latest["funded_runway_meses"] == 12.3    # +crédito como colchón
    assert latest["cash_runway_rag"] == "ok"        # 6-12 meses
    assert latest["funded_runway_rag"] == "verde"   # >12 meses


def test_runway_rag_bands(client):
    # caja pura 2 meses -> rojo ; con crédito 4 meses -> ambar
    _snap(client, "2026-06-10", 1_000_000, 0, 1_000_000, 500_000)
    latest = client.get("/api/dashboard/financial-snapshots", headers=H).json()["latest"]
    assert latest["cash_runway_meses"] == 2.0 and latest["cash_runway_rag"] == "rojo"
    assert latest["funded_runway_meses"] == 4.0 and latest["funded_runway_rag"] == "ambar"


def test_latest_is_most_recent_snapshot(client):
    _snap(client, "2026-05-01", 1_000_000, 0, 0, 500_000)      # viejo: 2 meses
    _snap(client, "2026-06-01", 6_000_000, 0, 0, 500_000)      # nuevo: 12 meses
    latest = client.get("/api/dashboard/financial-snapshots", headers=H).json()["latest"]
    assert latest["cash_runway_meses"] == 12.0                 # toma el más reciente

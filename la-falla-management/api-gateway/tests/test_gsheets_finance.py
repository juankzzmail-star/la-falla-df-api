"""change real-financial-source (instant push): the real cash ledger MOVIMIENTOS 2026 is read straight
from Google Sheets and upserted on every edit via an Apps Script webhook. Tests cover the pure parser
(no network) against ledger-shaped rows, and the webhook's own-token auth + happy path (Sheets fetch
mocked). Isolated in-memory SQLite + StaticPool."""
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
from api_gateway.routers import _gsheets_finance as gsf

# ── ledger-shaped fixture (mirrors the real MOVIMIENTOS 2026 layout) ─────────────────────────────
TABS = {
    "ENERO 2026": [
        ["$6,458,023.34", "Viene de Dic 2025", "FECHA", "$6,458,069.91", "saldo BCS 31/12/25"],
        ["-$6,458,199.00", "Transferencia a Juan Carlos para pago de IVA", "20/1/2026"],
        ["$891,801.00", "Préstamo Clemen para completar pago IVA"],
        ["-$46.46", "Saldo despúes de pagos", "$0.11", "Extracto 31/01/2026"],
    ],
    "FEBRERO 2026": [
        ["-$46.46", "Saldo despúes de pagos", "$0.11", "Extracto 31/01/2026"],   # ARRASTRE (cierre enero)
        ["$17,294,480.00", "Pago MINCULTURA", "11/2/2026"],
        ["$24,426,775.33", "Saldo despúes de pagos", "pendiente extracto 28/2/2026"],  # cierre real feb
    ],
    "MARZO 2026": [
        ["$24,426,775.33", "Saldo despúes de pagos", "pendiente extracto 28/2/2026"],  # ARRASTRE (cierre feb)
        ["-$1,486.00", "Gravamen movimientos financieros", "25/3/2026"],
        ["$542,931.33", "Saldo despúes de pagos", "", "$543,227.00", "saldo a 30/03/2026"],  # cierre real mar
    ],
    "PRÉSTAMOS CLEMEN": [
        ["MONTO", "CONCEPTO", "FECHA"],
        ["$891,801.00", "Préstamo Clemen para completar pago IVA", "20/1/2026"],
        ["$40,000.00", "Préstamo Créditos autom", "5/2/2026"],
        ["$6,900,000.00", "Préstamo Clemen primer pago Diálogo ACMI", "6/2/2026"],
        ["-$2,400,000.00", "Abono honorarios", "12/3/2026"],
        ["$7,431,801.00", "TOTAL"],
    ],
}


# ── pure parser (no network) ─────────────────────────────────────────────────────────────────────
def test_money_parsing():
    assert gsf._money("$6,458,070.00") == 6458070.0
    assert gsf._money("-$46.46") == -46.46
    assert gsf._money("($1,234)") == -1234.0
    assert gsf._money("pendiente extracto") is None
    assert gsf._money("") is None


def test_parser_reproduces_real_ledger():
    snaps = gsf.parse_movimientos(TABS)
    assert [str(s["fecha"]) for s in snaps] == ["2026-01-31", "2026-02-28", "2026-03-30"]
    ene, feb, mar = snaps
    # caja prefers the official bank-extract figure over the computed col-A value
    assert ene["caja_operativa"] == 0.11          # Extracto 31/01/2026
    assert feb["caja_operativa"] == 24426775.33   # no extract yet -> computed
    assert mar["caja_operativa"] == 543227.0      # saldo a 30/03/2026
    # reservas always 0; credito = founder backing accumulated to that month-end
    assert all(s["reservas_estrategicas"] == 0.0 for s in snaps)
    assert ene["credito_disponible"] == 891801.0
    assert feb["credito_disponible"] == 7831801.0
    assert mar["credito_disponible"] == 5431801.0   # incluye el abono -2.4M del 12/3
    assert all(s["gasto_mensual_promedio"] == gsf.GASTO_MENSUAL for s in snaps)


def test_parser_ignores_non_month_tabs_and_total_row():
    snaps = gsf.parse_movimientos({"Resumen": [["x"]], "PRÉSTAMOS CLEMEN": TABS["PRÉSTAMOS CLEMEN"]})
    assert snaps == []  # no month tabs -> nothing


# ── webhook (own token) + happy path (Sheets fetch mocked) ───────────────────────────────────────
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
    """CREATE TABLE app_config (key TEXT PRIMARY KEY, value TEXT, updated_at TIMESTAMP)""",
]
SID = "1ANHhfeWECyf9bv3tQbe003wtZvijJGFy6hXB7XV1iPY"


@pytest.fixture()
def client(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    with engine.begin() as c:
        for ddl in _DDL:
            c.execute(text(ddl))
        c.execute(text("INSERT INTO app_config (key, value) VALUES ('finance_webhook_token','secret-xyz')"))
        c.execute(text("INSERT INTO financial_data_sources (fuente, spreadsheet_id, ultima_sincronizacion) "
                       "VALUES ('MOVIMIENTOS 2026', :sid, NULL)"), {"sid": SID})
    TS = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override():
        db = TS()
        try:
            yield db
        finally:
            db.close()

    # mock la lectura real de Sheets -> (título, filas). El título permite seguir el archivo del año.
    monkeypatch.setattr(gsf, "fetch_movimientos", lambda sid: ("MOVIMIENTOS 2026", TABS))

    app.dependency_overrides[get_db] = override
    with TestClient(app) as cl:
        cl._engine = engine
        yield cl
    app.dependency_overrides.clear()


def test_webhook_rejects_bad_token(client):
    assert client.post("/hooks/financial-sheets?token=nope").status_code == 401


def test_webhook_503_when_token_unconfigured(client):
    with client._engine.begin() as c:
        c.execute(text("DELETE FROM app_config"))
    assert client.post("/hooks/financial-sheets?token=secret-xyz").status_code == 503


def test_webhook_imports_real_ledger(client):
    r = client.post("/hooks/financial-sheets?token=secret-xyz")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and body["snapshots"] == 3
    assert body["latest"] == "2026-03-30" and body["caja_latest"] == 543227.0
    # y el dashboard ahora sirve esos datos reales
    latest = client.get("/api/dashboard/financial-snapshots", headers={"X-API-Key": "test-key-123"}).json()["latest"]
    assert latest["caja_operativa"] == 543227.0 and latest["reservas_estrategicas"] == 0.0


def test_webhook_follows_reported_sheet(client):
    """n8n reporta el ID del archivo nuevo del año -> el tablero se re-apunta a él automáticamente."""
    new_id = "1NEWyearFILEabcdef1234567890XYZ"   # p.ej. MOVIMIENTOS 2027
    r = client.post(f"/hooks/financial-sheets?token=secret-xyz&sheet={new_id}")
    assert r.status_code == 200 and r.json()["ok"] is True
    src = client.get("/api/dashboard/financial-snapshots", headers={"X-API-Key": "test-key-123"}).json()["source"]
    assert src["spreadsheet_id"] == new_id   # la fuente quedó apuntando al archivo reportado


def test_webhook_rejects_malformed_sheet(client):
    assert client.post("/hooks/financial-sheets?token=secret-xyz&sheet=../etc").status_code == 400

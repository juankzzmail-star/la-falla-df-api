"""DB + API tests for the oportunidades router (Fase 3).

Runs in the `api_gateway` package layout (CI/container). Uses an isolated
in-memory SQLite with StaticPool so every request shares one DB. No network,
no production Postgres. The router emits portable SQL via SQLAlchemy, so the
upsert/filter logic is exercised against SQLite here.

Covers tasks.md §6.2/§6.3/§6.4: idempotent upsert, triage preservation across
re-sync, ADN threshold filter, and auth (401/403).
"""
import os

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("FASTAPI_GM_API_KEY", "test-key-123")
os.environ.setdefault("FASTAPI_API_KEY", "test-key-123")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api_gateway.db import get_db
from api_gateway.main import app
from api_gateway.models import Oportunidad

H = {"X-API-Key": "test-key-123"}


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # Create ONLY the oportunidades table (it has no FKs). create_all() would fail
    # resolving tasks.stakeholder_id -> stakeholders_master, which is owned by área 03
    # and not modeled here. The router only touches `oportunidades`.
    Oportunidad.__table__.create(engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    Oportunidad.__table__.drop(engine)


def _rec(rid="recA", nombre="Conv A", adn=90, prioridad="PRIORITARIA", **kw):
    rec = {"airtable_record_id": rid, "nombre": nombre, "adn_score": adn, "prioridad": prioridad}
    rec.update(kw)
    return rec


def test_sync_requires_api_key(client):
    r = client.post("/api/oportunidades/sync", json=[_rec()])
    assert r.status_code in (401, 403)


def test_list_requires_api_key(client):
    r = client.get("/api/oportunidades")
    assert r.status_code in (401, 403)


def test_sync_inserts_then_upserts_idempotent(client):
    r1 = client.post("/api/oportunidades/sync", json=[_rec(adn=90)], headers=H)
    assert r1.status_code == 200
    assert r1.json() == {"inserted": 1, "updated": 0, "total": 1}

    # Re-sync the same airtable_record_id: update in place, never duplicate.
    r2 = client.post("/api/oportunidades/sync", json=[_rec(adn=95)], headers=H)
    assert r2.json() == {"inserted": 0, "updated": 1, "total": 1}

    rows = client.get("/api/oportunidades", headers=H).json()
    assert len(rows) == 1
    assert rows[0]["adn_score"] == 95


def test_triage_state_survives_resync(client):
    client.post("/api/oportunidades/sync", json=[_rec()], headers=H)
    op_id = client.get("/api/oportunidades", headers=H).json()[0]["id"]

    rp = client.patch(
        f"/api/oportunidades/{op_id}",
        json={"estado_seguimiento": "descartada"},
        headers=H,
    )
    assert rp.status_code == 200
    assert rp.json()["estado_seguimiento"] == "descartada"

    # A fresh sync updates synced fields but must NOT clobber the CEO's triage.
    client.post("/api/oportunidades/sync", json=[_rec(adn=99)], headers=H)
    row = client.get("/api/oportunidades", headers=H).json()[0]
    assert row["estado_seguimiento"] == "descartada"
    assert row["adn_score"] == 99


def test_list_filters_min_adn(client):
    client.post(
        "/api/oportunidades/sync",
        json=[_rec("recHi", "High", adn=90), _rec("recLo", "Low", adn=40)],
        headers=H,
    )
    hi = client.get("/api/oportunidades?min_adn=70", headers=H).json()
    assert {o["airtable_record_id"] for o in hi} == {"recHi"}


def test_list_solo_vigentes_hides_expired(client):
    client.post(
        "/api/oportunidades/sync",
        json=[
            _rec("recPast", "Vencida", fecha_cierre="2000-01-01"),
            _rec("recFuture", "Vigente", fecha_cierre="2999-01-01"),
        ],
        headers=H,
    )
    vig = client.get("/api/oportunidades?solo_vigentes=true", headers=H).json()
    assert {o["airtable_record_id"] for o in vig} == {"recFuture"}


def test_patch_rejects_unknown_state(client):
    client.post("/api/oportunidades/sync", json=[_rec()], headers=H)
    op_id = client.get("/api/oportunidades", headers=H).json()[0]["id"]
    r = client.patch(
        f"/api/oportunidades/{op_id}", json={"estado_seguimiento": "xyz"}, headers=H
    )
    assert r.status_code == 400


def test_patch_404_for_missing(client):
    r = client.patch(
        "/api/oportunidades/99999", json={"estado_seguimiento": "perseguir"}, headers=H
    )
    assert r.status_code == 404

"""Tests for two backend hardening improvements:
- B (edt-cycle-guard): EDT dependency-cycle detection (projects.py) — pure graph logic + the DB guard.
- A (stakeholder-impact): decision -> real stakeholders_master classifications (stakeholders.py).

No real Postgres: the EDT ORM uses Postgres ARRAY columns, so the DB layer is exercised with a fake
session; the impact endpoint uses a fake db via dependency_overrides. Logic is covered by pure-function
tests. Covers the mandatory verification (mocked external, isolated, endpoint + auth checks).
"""
import os

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("FASTAPI_GM_API_KEY", "test-key-123")
os.environ.setdefault("FASTAPI_API_KEY", "test-key-123")

import pytest
from fastapi import HTTPException

from api_gateway.routers import projects as pj
from api_gateway.routers import stakeholders as sh

H = {"X-API-Key": "test-key-123"}


# ── B: EDT cycle detection (pure) ───────────────────────────────────────────────
def test_edt_cycle_self_dependency():
    assert pj.edt_cycle_chain({"1.1": []}, "1.1", ["1.1"]) is not None


def test_edt_cycle_direct():
    chain = pj.edt_cycle_chain({"1.1": ["1.2"], "1.2": []}, "1.2", ["1.1"])
    assert chain and chain[0] == chain[-1]


def test_edt_cycle_transitive():
    adj = {"1.1": [], "1.2": ["1.1"], "1.3": ["1.2"]}
    chain = pj.edt_cycle_chain(adj, "1.1", ["1.3"])   # 1.1 -> 1.3 -> 1.2 -> 1.1
    assert chain and chain[0] == chain[-1] == "1.1"


def test_edt_no_cycle():
    adj = {"1.1": [], "1.2": ["1.1"]}
    assert pj.edt_cycle_chain(adj, "1.2", ["1.1"]) is None
    assert pj.edt_cycle_chain(adj, "1.3", ["1.1", "1.2"]) is None   # brand-new node, no cycle
    assert pj.edt_cycle_chain(adj, "1.2", []) is None               # clearing deps is fine


def test_find_any_edt_cycle():
    assert pj.find_any_edt_cycle({"a": ["b"], "b": ["a"]}) is not None
    assert pj.find_any_edt_cycle({"a": ["b"], "b": ["c"], "c": []}) is None


# ── B: EDT guard against a fake DB session ──────────────────────────────────────
class _FakeNode:
    def __init__(self, codigo, preds):
        self.codigo = codigo
        self.predecesores = preds
        self.project_id = 1


class _FakeQuery:
    def __init__(self, nodes):
        self._n = nodes

    def filter(self, *a, **k):
        return self

    def all(self):
        return self._n


class _FakeDB:
    def __init__(self, nodes):
        self._n = nodes

    def query(self, model):
        return _FakeQuery(self._n)

    def get(self, model, _id):
        return object()  # project/node exists


def test_assert_edt_acyclic_raises_on_cycle():
    db = _FakeDB([_FakeNode("1.1", []), _FakeNode("1.2", ["1.1"])])
    with pytest.raises(HTTPException) as exc:
        pj._assert_edt_acyclic(db, 1, "1.1", ["1.2"])   # 1.1 -> 1.2 -> 1.1
    assert exc.value.status_code == 400


def test_assert_edt_acyclic_passes_when_ok():
    db = _FakeDB([_FakeNode("1.1", []), _FakeNode("1.2", ["1.1"])])
    pj._assert_edt_acyclic(db, 1, "1.3", ["1.1"])       # no exception
    pj._assert_edt_acyclic(db, 1, "1.2", None)          # nothing to check


def test_validate_edt_reports_cycle_and_dangling():
    db = _FakeDB([_FakeNode("a", ["b"]), _FakeNode("b", ["a"])])
    res = pj.validate_edt(1, db)
    assert res["ok"] is False and res["cycle"]
    db2 = _FakeDB([_FakeNode("a", ["zzz"])])             # zzz no existe
    res2 = pj.validate_edt(1, db2)
    assert res2["ok"] is False and res2["dangling"] == {"a": ["zzz"]}
    db3 = _FakeDB([_FakeNode("a", []), _FakeNode("b", ["a"])])
    assert pj.validate_edt(1, db3)["ok"] is True


# ── A: stakeholder impact (pure) ────────────────────────────────────────────────
def test_relevant_classifications():
    assert "Institucional / Gobierno" in sh.relevant_classifications("Aplicar a la convocatoria de MinCultura")
    assert "Clientes" in sh.relevant_classifications("Cerrar el contrato con un cliente nuevo")
    assert "Aliados" in sh.relevant_classifications("Firmar alianza con ACMI")
    assert sh.relevant_classifications("texto sin relación con nada") == []


# ── A: impact endpoint with a fake DB (dependency_overrides) ────────────────────
class _FakeRow:
    def __init__(self, mapping):
        self._mapping = mapping


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _FakeImpactDB:
    def __init__(self, rows):
        self._rows = rows

    def execute(self, _q, _params=None):
        return _FakeResult(self._rows)


def _client_with_db(rows):
    from fastapi.testclient import TestClient
    from api_gateway.main import app
    from api_gateway.db import get_db
    app.dependency_overrides[get_db] = lambda: _FakeImpactDB(rows)
    return TestClient(app), app, get_db


def test_impact_endpoint_returns_real_stakeholders():
    rows = [_FakeRow({"id": 1, "nombre": "MinCultura", "rol": "Fondo",
                      "clasificacion_negocio": "Institucional / Gobierno",
                      "correo": None, "observaciones": None})]
    client, app, get_db = _client_with_db(rows)
    try:
        r = client.post("/api/stakeholders/impact-analysis", headers=H,
                        json={"decision": "Aplicar a la convocatoria de MinCultura (fondo público)"})
        assert r.status_code == 200, r.text
        b = r.json()
        assert b["classifications_touched"] == ["Institucional / Gobierno"]
        assert b["affected_count"] == 1
        assert b["affected_stakeholders"][0]["nombre"] == "MinCultura"
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_impact_endpoint_no_keywords_is_empty():
    client, app, get_db = _client_with_db([])
    try:
        r = client.post("/api/stakeholders/impact-analysis", headers=H,
                        json={"decision": "una nota neutra sin terminos de negocio"})
        assert r.status_code == 200, r.text
        assert r.json()["affected_count"] == 0
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_impact_endpoint_requires_key():
    from fastapi.testclient import TestClient
    from api_gateway.main import app
    assert TestClient(app).post("/api/stakeholders/impact-analysis",
                                json={"decision": "x"}).status_code in (401, 403)

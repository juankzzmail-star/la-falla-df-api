"""DB + API tests for change populate-hito-rollup (hito-rollup-linkage capability).

The cascade creates metas (strategic_goals) without a milestone_id; hitos come from the completeness
interview. POST /goals/link-hitos ties the meta→hito knot (the LLM proposes, the human approves) so
recompute_milestone_pct derives a real hito %. The LLM seam (_cascade.generate_hito_links_for_metas) is
monkeypatched: NO network, NO production Postgres. Isolated in-memory SQLite + StaticPool.

Covers: batch link persists proposals + recomputes the hito %; already-linked metas are skipped; the
endpoint ignores a proposal for an unknown meta; no hitos -> honest empty (no writes, seam not called);
no provider -> 503 (no writes); PUT /goals/{id}/milestone set/clear/422/404; _plan_hito resolves the link;
plus pure tests of the seam's id-validation (no model call when there is nothing to match).
"""
import os

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("FASTAPI_GM_API_KEY", "test-key-123")
os.environ.setdefault("FASTAPI_API_KEY", "test-key-123")

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from api_gateway.db import get_db
from api_gateway.main import app
from api_gateway.routers import _cascade
from api_gateway.routers.tasks import _plan_hito

H = {"X-API-Key": "test-key-123"}
_AREAS = "'Comercial','Proyectos','Investigacion','Audiovisual','Transversal'"

_DDL = [
    f"""CREATE TABLE strategic_goals (
        id INTEGER PRIMARY KEY AUTOINCREMENT, codigo TEXT UNIQUE NOT NULL, titulo TEXT NOT NULL,
        area TEXT NOT NULL CHECK (area IN ({_AREAS})), fecha_inicio DATE, fecha_fin_meta DATE,
        peso_porcentaje NUMERIC, estado TEXT NOT NULL DEFAULT 'activo', milestone_id INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
    f"""CREATE TABLE plans (
        id INTEGER PRIMARY KEY AUTOINCREMENT, codigo TEXT UNIQUE NOT NULL, titulo TEXT NOT NULL,
        area TEXT NOT NULL CHECK (area IN ({_AREAS})), goal_id INTEGER, anio INTEGER,
        pct_completado_real NUMERIC NOT NULL DEFAULT 0, estado TEXT NOT NULL DEFAULT 'activo',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
    # depends_on is TEXT (left NULL) so the ORM RoadmapMilestone's ARRAY column maps cleanly on SQLite.
    """CREATE TABLE roadmap_milestones (
        id INTEGER PRIMARY KEY AUTOINCREMENT, titulo TEXT NOT NULL, orden INTEGER NOT NULL DEFAULT 0,
        estado TEXT NOT NULL DEFAULT 'pendiente', area TEXT, anio INTEGER, trimestre INTEGER,
        fecha_inicio TIMESTAMP, fecha_fin_planificada TIMESTAMP, fecha_completado TIMESTAMP,
        depends_on TEXT, version_id INTEGER, pct_completado NUMERIC NOT NULL DEFAULT 0,
        peso NUMERIC NOT NULL DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
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


def _exec(client, sql, **p):
    with client._engine.begin() as conn:
        conn.execute(text(sql), p)


def _rows(client, sql, **p):
    with client._engine.connect() as conn:
        return conn.execute(text(sql), p).fetchall()


def _hito(client, hid, titulo="Hito"):
    _exec(client, "INSERT INTO roadmap_milestones (id, titulo, anio) VALUES (:i, :t, 2026)", i=hid, t=titulo)


def _meta(client, codigo, area="Audiovisual", milestone_id=None):
    _exec(client, "INSERT INTO strategic_goals (codigo, titulo, area, milestone_id) VALUES (:c, :c, :a, :m)",
          c=codigo, a=area, m=milestone_id)
    return _rows(client, "SELECT id FROM strategic_goals WHERE codigo = :c", c=codigo)[0][0]


# ── POST /goals/link-hitos ───────────────────────────────────────────────────
def test_link_assigns_proposed_hitos(client, monkeypatch):
    _hito(client, 1, "Documental 2026")
    m1 = _meta(client, "AUD-01")
    m2 = _meta(client, "AUD-02")
    monkeypatch.setattr(_cascade, "generate_hito_links_for_metas",
                        lambda metas, hitos: [{"meta_id": m1, "milestone_id": 1}, {"meta_id": m2, "milestone_id": 1}])
    r = client.post("/api/goals/link-hitos", headers=H)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["estado"] == "linked" and body["linked"] == 2
    assert _rows(client, "SELECT milestone_id FROM strategic_goals WHERE id = :i", i=m1)[0][0] == 1
    assert _rows(client, "SELECT milestone_id FROM strategic_goals WHERE id = :i", i=m2)[0][0] == 1


def test_link_skips_already_linked(client, monkeypatch):
    _hito(client, 1)
    _meta(client, "AUD-01", milestone_id=1)          # already linked -> not offered to the seam
    unlinked = _meta(client, "AUD-02")
    seen = {}

    def _seam(metas, hitos):
        seen["meta_ids"] = [m["id"] for m in metas]
        return [{"meta_id": unlinked, "milestone_id": 1}]

    monkeypatch.setattr(_cascade, "generate_hito_links_for_metas", _seam)
    r = client.post("/api/goals/link-hitos", headers=H)
    assert r.status_code == 200, r.text
    assert seen["meta_ids"] == [unlinked]            # the already-linked meta was skipped
    assert r.json()["linked"] == 1


def test_link_ignores_proposal_for_unknown_meta(client, monkeypatch):
    _hito(client, 1)
    m1 = _meta(client, "AUD-01")
    monkeypatch.setattr(_cascade, "generate_hito_links_for_metas",
                        lambda metas, hitos: [{"meta_id": 999999, "milestone_id": 1}])   # meta not in the set
    r = client.post("/api/goals/link-hitos", headers=H)
    assert r.status_code == 200, r.text
    assert r.json()["linked"] == 0
    assert _rows(client, "SELECT milestone_id FROM strategic_goals WHERE id = :i", i=m1)[0][0] is None


def test_link_no_hitos_is_honest_empty(client, monkeypatch):
    _meta(client, "AUD-01")
    called = {"n": 0}
    monkeypatch.setattr(_cascade, "generate_hito_links_for_metas",
                        lambda metas, hitos: called.__setitem__("n", called["n"] + 1) or [])
    r = client.post("/api/goals/link-hitos", headers=H)
    assert r.status_code == 200, r.text
    assert r.json()["estado"] == "sin_hitos" and r.json()["linked"] == 0
    assert called["n"] == 0                           # seam never called when there are no hitos
    assert _rows(client, "SELECT milestone_id FROM strategic_goals")[0][0] is None


def test_link_503_no_provider_writes_nothing(client, monkeypatch):
    _hito(client, 1)
    m1 = _meta(client, "AUD-01")

    def _raise(metas, hitos):
        raise HTTPException(503, "No hay proveedor LLM configurado")

    monkeypatch.setattr(_cascade, "generate_hito_links_for_metas", _raise)
    r = client.post("/api/goals/link-hitos", headers=H)
    assert r.status_code == 503
    assert _rows(client, "SELECT milestone_id FROM strategic_goals WHERE id = :i", i=m1)[0][0] is None


def test_link_recomputes_hito_pct(client, monkeypatch):
    _hito(client, 1)
    m = _meta(client, "AUD-01")
    _exec(client, "INSERT INTO plans (codigo, titulo, area, goal_id, pct_completado_real) "
                  "VALUES ('P1','P1','Audiovisual',:g,40)", g=m)
    monkeypatch.setattr(_cascade, "generate_hito_links_for_metas",
                        lambda metas, hitos: [{"meta_id": m, "milestone_id": 1}])
    r = client.post("/api/goals/link-hitos", headers=H)
    assert r.status_code == 200, r.text
    pct = _rows(client, "SELECT pct_completado FROM roadmap_milestones WHERE id = 1")[0][0]
    assert float(pct) == 40.0                         # the hito now derives 40% from its linked plan (was 0)
    assert 1 in r.json()["hitos_recomputados"]


def test_link_requires_api_key(client):
    assert client.post("/api/goals/link-hitos").status_code in (401, 403)


# ── PUT /goals/{id}/milestone ────────────────────────────────────────────────
def test_put_milestone_sets_and_recomputes(client):
    _hito(client, 5)
    m = _meta(client, "AUD-01")
    _exec(client, "INSERT INTO plans (codigo, titulo, area, goal_id, pct_completado_real) "
                  "VALUES ('P1','P1','Audiovisual',:g,30)", g=m)
    r = client.put(f"/api/goals/{m}/milestone", json={"milestone_id": 5}, headers=H)
    assert r.status_code == 200, r.text
    assert r.json()["milestone_id"] == 5
    assert _rows(client, "SELECT milestone_id FROM strategic_goals WHERE id = :i", i=m)[0][0] == 5
    assert float(_rows(client, "SELECT pct_completado FROM roadmap_milestones WHERE id = 5")[0][0]) == 30.0


def test_put_milestone_invalid_hito_422(client):
    m = _meta(client, "AUD-01")
    r = client.put(f"/api/goals/{m}/milestone", json={"milestone_id": 424242}, headers=H)
    assert r.status_code == 422
    assert _rows(client, "SELECT milestone_id FROM strategic_goals WHERE id = :i", i=m)[0][0] is None


def test_put_milestone_clears_link(client):
    _hito(client, 5)
    m = _meta(client, "AUD-01", milestone_id=5)
    r = client.put(f"/api/goals/{m}/milestone", json={"milestone_id": None}, headers=H)
    assert r.status_code == 200, r.text
    assert _rows(client, "SELECT milestone_id FROM strategic_goals WHERE id = :i", i=m)[0][0] is None


def test_put_milestone_unknown_goal_404(client):
    _hito(client, 5)
    assert client.put("/api/goals/999999/milestone", json={"milestone_id": 5}, headers=H).status_code == 404


# ── _plan_hito resolves the link (roll-up coverage flagged by the QA sweep) ───
def test_plan_hito_resolves_via_meta_link(client):
    _hito(client, 9)
    linked = _meta(client, "AUD-01", milestone_id=9)
    unlinked = _meta(client, "AUD-02")
    _exec(client, "INSERT INTO plans (codigo, titulo, area, goal_id) VALUES ('P1','P1','Audiovisual',:g)", g=linked)
    _exec(client, "INSERT INTO plans (codigo, titulo, area, goal_id) VALUES ('P2','P2','Audiovisual',:g)", g=unlinked)
    pid1 = _rows(client, "SELECT id FROM plans WHERE codigo='P1'")[0][0]
    pid2 = _rows(client, "SELECT id FROM plans WHERE codigo='P2'")[0][0]
    with Session(client._engine) as db:
        assert _plan_hito(db, pid1) == 9              # plan -> meta -> hito
        assert _plan_hito(db, pid2) is None           # unlinked meta -> no hito


# ── Pure: the LLM seam validates ids (no network) ────────────────────────────
def test_generate_hito_links_discards_invalid_ids(monkeypatch):
    metas = [{"id": 1, "codigo": "A", "titulo": "A", "area": "Audiovisual"},
             {"id": 2, "codigo": "B", "titulo": "B", "area": "Comercial"}]
    hitos = [{"id": 10, "titulo": "H", "area": None, "anio": 2026}]
    monkeypatch.setattr(_cascade, "_chat_json", lambda system, user: {"links": [
        {"meta_id": 1, "milestone_id": 10},        # valid -> kept
        {"meta_id": 2, "milestone_id": 999},       # invalid hito id -> dropped
        {"meta_id": 777, "milestone_id": 10},      # invalid meta id -> dropped
        {"meta_id": 1, "milestone_id": 10},        # duplicate meta -> dropped
        {"meta_id": "x", "milestone_id": 10},      # unparseable -> dropped
    ]})
    assert _cascade.generate_hito_links_for_metas(metas, hitos) == [{"meta_id": 1, "milestone_id": 10}]


def test_generate_hito_links_empty_when_no_inputs(monkeypatch):
    called = {"n": 0}
    monkeypatch.setattr(_cascade, "_chat_json", lambda s, u: called.__setitem__("n", called["n"] + 1) or {})
    assert _cascade.generate_hito_links_for_metas([], [{"id": 1}]) == []
    assert _cascade.generate_hito_links_for_metas([{"id": 1}], []) == []
    assert called["n"] == 0                           # never calls the model when there is nothing to match

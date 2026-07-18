"""change rigorous-progress-math: evidence-weighted EVM avance per hito. A 'done' is capped by its real
task evidence (STRICT: ≥80% weighted tasks done → 100; below → real %, capped 90); in-progress/delayed
rise from the WEIGHTED task roll-up (es_hito × prioridad, so a milestone-grade task ≠ an errand);
pendiente is a hard 0. A 'done' whose evidence is below the credit threshold is flagged 'verificar
respaldo'. Isolated in-memory SQLite (no network, no prod Postgres)."""
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
from api_gateway.routers.roadmap import milestone_avance, milestone_sin_respaldo

H = {"X-API-Key": "test-key-123"}

_DDL = [
    """CREATE TABLE roadmap_milestones (
        id INTEGER PRIMARY KEY AUTOINCREMENT, titulo TEXT NOT NULL, orden INTEGER NOT NULL DEFAULT 0,
        estado TEXT NOT NULL DEFAULT 'pendiente', area TEXT, anio INTEGER, trimestre INTEGER,
        fecha_inicio TIMESTAMP, fecha_fin_planificada TIMESTAMP, fecha_completado TIMESTAMP,
        depends_on TEXT, version_id INTEGER, pct_completado NUMERIC NOT NULL DEFAULT 0,
        peso NUMERIC NOT NULL DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
    # hito_real_work() weights each linked task by es_hito × prioridad
    """CREATE TABLE tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT, plan_id INTEGER, milestone_id INTEGER, titulo TEXT,
        area TEXT, responsable TEXT, estado TEXT NOT NULL DEFAULT 'pendiente',
        prioridad TEXT NOT NULL DEFAULT 'media', es_hito INTEGER NOT NULL DEFAULT 0,
        fecha_vencimiento DATE, fecha_completada DATE, google_task_id TEXT)""",
    # roadmap-2030 also reads plans (captación) and risks (riesgo) for its other arcs
    """CREATE TABLE plans (id INTEGER PRIMARY KEY AUTOINCREMENT, area TEXT,
        estado TEXT NOT NULL DEFAULT 'activo', pct_completado_real NUMERIC NOT NULL DEFAULT 0)""",
    """CREATE TABLE risks (id INTEGER PRIMARY KEY AUTOINCREMENT, nivel_riesgo INTEGER NOT NULL DEFAULT 0,
        estado_mitigacion TEXT NOT NULL DEFAULT 'monitoreado',
        analisis_gentil TEXT, plan_mitigacion TEXT, fecha_analisis TIMESTAMP)""",
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


# ── helper-level math (wpct is the WEIGHTED completion ratio in [0,1]) ───────────────────────
def test_avance_helper_evidence_weighted_and_strict():
    assert milestone_avance("done", 0.0, False) == 100.0   # done, no tasks -> trusted (flagged elsewhere)
    assert milestone_avance("done", 0.85, True) == 100.0   # strong evidence (>=0.8) -> full credit
    assert milestone_avance("done", 0.50, True) == 50.0    # STRICT: weak 'done' shows real %, capped 90
    assert milestone_avance("done", 0.0, True) == 0.0      # 'done' but zero done tasks -> 0
    assert milestone_avance("in_progress", 0.42, True) == 42.0
    assert milestone_avance("delayed", 1.0, True) == 100.0
    assert milestone_avance("pendiente", 1.0, True) == 0.0   # declared not-started: evidence cannot inflate
    assert milestone_avance("in_progress", 0.0, False) == 10.0   # "started" floor, no linked tasks
    assert milestone_avance("delayed", 0.0, False) == 5.0


def test_sin_respaldo_flags_unproven_done():
    assert milestone_sin_respaldo("done", 0.0, False) is True    # no tasks at all
    assert milestone_sin_respaldo("done", 0.50, True) is True    # below the credit threshold
    assert milestone_sin_respaldo("done", 0.85, True) is False   # proven
    assert milestone_sin_respaldo("in_progress", 0.0, True) is False
    assert milestone_sin_respaldo("pendiente", 0.0, False) is False


# ── endpoint: weighting + strict discount end to end ────────────────────────────────────────
def test_milestones_endpoint_weighted_and_strict(client):
    with client._engine.begin() as c:
        c.execute(text(
            "INSERT INTO roadmap_milestones (id,titulo,orden,estado) VALUES "
            "(1,'Done sin tareas',1,'done'), (2,'En progreso ponderado',2,'in_progress'), "
            "(3,'Done sin respaldo',3,'done'), (4,'Pendiente',4,'pendiente')"))
        # hito 2: a milestone-grade high-priority task DONE (weight 4.5) + a minor task pending (weight 1)
        #         -> weighted 4.5/5.5 = 0.818, NOT 1/2 = 0.5: a hito-task pushes more than an errand.
        c.execute(text("INSERT INTO tasks (milestone_id,titulo,estado,es_hito,prioridad,google_task_id) "
                       "VALUES (2,'entregable clave','completada',1,'alta','g1'), "
                       "(2,'recado menor','pendiente',0,'media','g2')"))
        # hito 3: declared done but only 1 of 4 minor tasks complete -> weighted 0.25 -> STRICT -> 25, flagged
        c.execute(text("INSERT INTO tasks (milestone_id,titulo,estado,es_hito,prioridad,google_task_id) "
                       "VALUES (3,'t1','completada',0,'media','g3'), (3,'t2','pendiente',0,'media','g4'), "
                       "(3,'t3','pendiente',0,'media','g5'), (3,'t4','pendiente',0,'media','g6')"))
    r = client.get("/api/roadmap/milestones", headers=H)
    assert r.status_code == 200, r.text
    by_id = {m["id"]: m for m in r.json()}
    # done, no backing -> trusted 100 but flagged
    assert by_id[1]["avance"] == 100.0 and by_id[1]["sin_respaldo"] is True and by_id[1]["tareas_total"] == 0
    # in-progress rises by the WEIGHT of real work (0.818), not the raw 1/2 count
    assert by_id[2]["avance"] == 81.8 and by_id[2]["sin_respaldo"] is False
    assert by_id[2]["tareas_total"] == 2 and by_id[2]["tareas_done"] == 1
    # strict discount: a 'done' with only 25% of its weighted tasks done reads 25, flagged (not a free 100)
    assert by_id[3]["avance"] == 25.0 and by_id[3]["sin_respaldo"] is True
    # pendiente -> hard 0
    assert by_id[4]["avance"] == 0.0 and by_id[4]["sin_respaldo"] is False


def test_peso_tier_weights_the_vision_rollup(client):
    """change rigorous-progress-math: the 2030 roll-up is Σ(peso·avance)/Σpeso, NOT a simple average.
    Two hitos, one done (100) one pendiente (0); raising the done hito's peso pulls the vision % up."""
    with client._engine.begin() as c:
        c.execute(text("INSERT INTO roadmap_milestones (id,titulo,orden,estado,peso) VALUES "
                       "(1,'Critico hecho',1,'done',3), (2,'Menor pendiente',2,'pendiente',1)"))
    # weighted: (3·100 + 1·0)/4 = 75 ; equal baseline: (100+0)/2 = 50
    body = client.get("/api/dashboard/roadmap-2030", headers=H).json()
    assert body["v2030_pct"] == 75.0
    assert body["v2030_pct_equal"] == 50.0


def test_patch_peso_reweights_vision_live(client):
    """The CEO assigns a strategic tier via PATCH /roadmap/milestones/{id} {peso}; the weighted 2030
    roll-up reacts immediately. change rigorous-progress-math (tier setter)."""
    with client._engine.begin() as c:
        c.execute(text("INSERT INTO roadmap_milestones (id,titulo,orden,estado,peso) VALUES "
                       "(1,'Crítico hecho',1,'done',1), (2,'Menor pendiente',2,'pendiente',1)"))
    assert client.get("/api/dashboard/roadmap-2030", headers=H).json()["v2030_pct"] == 50.0  # peso 1/1
    r = client.patch("/api/roadmap/milestones/1", json={"peso": 3}, headers=H)                # -> Crítico
    assert r.status_code == 200 and float(r.json()["peso"]) == 3.0
    assert client.get("/api/dashboard/roadmap-2030", headers=H).json()["v2030_pct"] == 75.0  # (3·100+0)/4


def test_new_hito_is_born_normal_tier(client):
    """General rule (NOT hardcoded per title): any newly created hito defaults to Normal (peso 1); the
    loader/CEO may set its tier at creation. The rule molds to whatever hitos are loaded — incl. a full
    reload of real data — so it stays valid across cycles."""
    r = client.post("/api/roadmap/milestones", json={"titulo": "Hito real recargado", "orden": 1}, headers=H)
    assert r.status_code == 201 and float(r.json()["peso"]) == 1.0          # default Normal
    r2 = client.post("/api/roadmap/milestones",
                     json={"titulo": "Hito crítico real", "orden": 2, "peso": 3}, headers=H)
    assert r2.status_code == 201 and float(r2.json()["peso"]) == 3.0        # loader may set the tier

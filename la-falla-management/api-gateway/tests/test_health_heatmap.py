"""change rigorous-progress-math: the Pulso is now a CONTINUOUS 0–100 composite index (weighted geometric
mean of on_schedule/on_time/flow), each signal weighted by task importance (es_hito × prioridad), and the
company score is SIZE-WEIGHTED by workload — no 4-band collapse, no average-of-averages. RAG (≥80/60/40)
is only a coloring. Isolated in-memory SQLite + StaticPool; portable DDL. Also covers the period-aware
HOY/SEMANA/MENSUAL driver and the active-cycle scoping (legacy ghosts excluded)."""
import os
from datetime import date, timedelta

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


def _d(n):
    return (date.today() + timedelta(days=n)).isoformat()


OLD = _d(-40)     # >30 días tarde  -> severidad 1.0
MID = _d(-15)     # 7-30 días tarde -> 0.7
LATE3 = _d(-3)    # <7 días tarde   -> 0.3
FUT = _d(40)      # futuro, no vencida

_DDL = [
    """CREATE TABLE tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT, area TEXT, estado TEXT NOT NULL DEFAULT 'pendiente',
        prioridad TEXT NOT NULL DEFAULT 'media', es_hito INTEGER NOT NULL DEFAULT 0,
        fecha_inicio DATE, fecha_vencimiento DATE, fecha_completada DATE,
        plan_id INTEGER, google_task_id TEXT)""",
    """CREATE TABLE roadmap_cycles (id INTEGER PRIMARY KEY AUTOINCREMENT, anio INTEGER,
        nombre TEXT, estado TEXT)""",
    """CREATE TABLE plans (id INTEGER PRIMARY KEY AUTOINCREMENT, area TEXT, anio INTEGER)""",
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


def _add(client, area, estado, venc=None, completed=None, es_hito=0, prioridad="media",
         plan_id=None, gid=None):
    with client._engine.begin() as c:
        c.execute(text(
            "INSERT INTO tasks (area, estado, prioridad, es_hito, fecha_vencimiento, fecha_completada, "
            "plan_id, google_task_id) VALUES (:a,:e,:pr,:h,:v,:fc,:pl,:g)"),
            {"a": area, "e": estado, "pr": prioridad, "h": es_hito, "v": venc, "fc": completed,
             "pl": plan_id, "g": gid})


def _areas(client):
    return {a["name"]: a for a in client.get("/api/dashboard/health-heatmap", headers=H).json()["areas"]}


def test_health_requires_api_key(client):
    assert client.get("/api/dashboard/health-heatmap").status_code in (401, 403)


def test_all_overdue_none_done_reads_near_zero(client):
    # 5 tareas abiertas, todas vencidas hace >30 días, ninguna a tiempo -> casi 0 (antes: 40 fijo)
    for _ in range(5):
        _add(client, "Comercial", "pendiente", venc=OLD)
    com = _areas(client)["Comercial"]
    assert 0 < com["score"] < 10 and com["nivel"] == 1      # crítico, continuo (no banda 40)
    assert com["backlog_sev"] == 100.0                       # todo el peso abierto está vencido-añejo


def test_mostly_on_time_reads_healthy(client):
    for _ in range(8):                                       # 8 completadas a tiempo
        _add(client, "Investigacion", "completada", venc=MID, completed=_d(-20))
    for _ in range(2):                                       # 2 abiertas a futuro (no vencidas)
        _add(client, "Investigacion", "pendiente", venc=FUT)
    inv = _areas(client)["Investigacion"]
    assert inv["score"] >= 80 and inv["nivel"] == 4          # sano
    assert inv["on_time_pct"] == 80.0                        # 8/10 a tiempo


def test_blocked_tanks_the_score(client):
    _add(client, "Comercial", "bloqueada", venc=FUT)         # bloqueada, ni siquiera vencida
    com = _areas(client)["Comercial"]
    assert com["score"] < 40 and com["nivel"] == 1


def test_empty_area_is_sin_datos(client):
    _add(client, "Comercial", "pendiente", venc=OLD)
    areas = _areas(client)
    assert areas["Comercial"]["score"] is not None
    assert areas["Proyectos"]["score"] is None              # sin tareas -> sin datos, nunca fabricado


def test_es_hito_overdue_weighs_more_than_a_minor_task(client):
    # Misma forma (1 vencida + 1 futura) en dos áreas, pero la VENCIDA es hito en A y menor en B.
    _add(client, "Comercial", "pendiente", venc=OLD, es_hito=1)   # hito vencido (peso 3)
    _add(client, "Comercial", "pendiente", venc=FUT, es_hito=0)   # menor futura (peso 1)
    _add(client, "Audiovisual", "pendiente", venc=OLD, es_hito=0)  # menor vencida (peso 1)
    _add(client, "Audiovisual", "pendiente", venc=FUT, es_hito=1)  # hito futuro (peso 3)
    areas = _areas(client)
    # severidad de backlog ponderada: A (hito vencido) = 3/4 = 75% ; B (menor vencida) = 1/4 = 25%
    assert areas["Comercial"]["backlog_sev"] == 75.0
    assert areas["Audiovisual"]["backlog_sev"] == 25.0
    assert areas["Comercial"]["score"] < areas["Audiovisual"]["score"]


def test_global_is_size_weighted_not_average_of_averages(client):
    # Área grande y sana (10 tareas) + área chica y crítica (1 tarea). El global pondera por carga.
    for _ in range(10):
        _add(client, "Comercial", "completada", venc=MID, completed=_d(-20))
    _add(client, "Audiovisual", "pendiente", venc=OLD)
    body = client.get("/api/dashboard/health-heatmap", headers=H).json()
    assert body["salud_global"] > body["salud_global_simple"]   # el peso por tamaño jala hacia la grande
    assert body["salud_global"] >= 80 and body["salud_global_simple"] < 60


def test_period_horizon_breakdown(client):
    """El driver HOY/SEMANA/MENSUAL (vencen acumulado hoy ⊆ semana ⊆ mensual) y sin_agenda siguen vivos."""
    _add(client, "Comercial", "pendiente", venc=OLD)                 # vencida (backlog)
    _add(client, "Comercial", "pendiente", venc=_d(0))               # vence hoy
    _add(client, "Comercial", "pendiente", venc=_d(3))               # vence esta semana
    _add(client, "Comercial", "pendiente", venc=_d(20))              # vence este mes
    _add(client, "Audiovisual", "pendiente", venc=OLD)               # solo vencida, nada agendado
    areas = _areas(client)
    com = areas["Comercial"]["periodo"]
    assert com["hoy"]["vencen"] == 1 and com["hoy"]["sin_agenda"] is False
    assert com["semana"]["vencen"] == 2 and com["mensual"]["vencen"] == 3
    av = areas["Audiovisual"]["periodo"]
    assert av["hoy"]["sin_agenda"] is True and av["mensual"]["sin_agenda"] is True


def test_active_cycle_scopes_out_legacy_ghosts(client):
    with client._engine.begin() as c:
        c.execute(text("INSERT INTO roadmap_cycles (anio,nombre,estado) VALUES (2026,'C','activo')"))
        c.execute(text("INSERT INTO plans (id, area, anio) VALUES (1,'Comercial',2026), (2,'Comercial',2024)"))
    _add(client, "Comercial", "pendiente", venc=OLD, plan_id=1)        # plan 2026 -> cuenta
    _add(client, "Comercial", "pendiente", venc=OLD, plan_id=2)        # plan 2024 -> excluido (ghost)
    _add(client, "Audiovisual", "pendiente", venc=OLD, gid="g_imp")    # importada directa -> cuenta
    body = client.get("/api/dashboard/health-heatmap", headers=H).json()
    areas = {a["name"]: a for a in body["areas"]}
    assert body["anio"] == 2026
    assert areas["Comercial"]["overdue"] == 1                          # solo la 2026 (la 2024 excluida)
    assert areas["Comercial"]["score"] is not None and areas["Comercial"]["score"] < 40
    assert areas["Audiovisual"]["overdue"] == 1                        # la importada directa cuenta
    assert areas["Proyectos"]["score"] is None                        # nada -> sin datos

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import datetime

from ..db import get_db
from ..models import (
    Plan, PlanQuarterlyGoal, RoadmapCycle, RoadmapMilestone, RoadmapVersion, StrategicGoal,
)
from .projects import edt_cycle_chain  # reuse the proven pure cycle detector (change unify-strategy-execution)

router = APIRouter(prefix="/roadmap", tags=["roadmap"])


class MilestoneOut(BaseModel):
    id: int
    titulo: str
    orden: int
    estado: str
    area: Optional[str]
    anio: Optional[int] = None
    trimestre: Optional[int] = None
    fecha_inicio: Optional[datetime]
    fecha_fin_planificada: Optional[datetime]
    fecha_completado: Optional[datetime]
    depends_on: Optional[list]
    version_id: Optional[int]
    pct_completado: float
    peso: float = 1.0            # change rigorous-progress-math: strategic-tier weight for the EVM roll-up
    avance: float = 0.0          # change connect-execution-strategy: ONE coherent estado-aware progress
    sin_respaldo: bool = False   # 'done' with no completed task backing it -> "verificar respaldo"
    tareas_total: int = 0        # real tasks that advance this hito (weighted by es_hito × prioridad)
    tareas_done: int = 0

    class Config:
        from_attributes = True


class MilestoneCreate(BaseModel):
    titulo: str
    orden: int
    estado: str = "pendiente"
    area: Optional[str] = None
    anio: Optional[int] = None
    trimestre: Optional[int] = Field(None, ge=1, le=4)
    fecha_inicio: Optional[datetime] = None
    fecha_fin_planificada: Optional[datetime] = None
    depends_on: Optional[list] = None
    version_id: Optional[int] = None
    pct_completado: float = 0.0
    # change rigorous-progress-math: every hito is born Normal (1); the loader/CEO may set its strategic
    # tier at creation. NOT hardcoded per title — it molds to whatever hitos are loaded (incl. a full
    # reload of real data), so the weighting rule survives across cycles.
    peso: float = 1.0


class MilestonePatch(BaseModel):
    titulo: Optional[str] = None
    estado: Optional[str] = None
    area: Optional[str] = None
    anio: Optional[int] = None
    trimestre: Optional[int] = Field(None, ge=1, le=4)
    pct_completado: Optional[float] = None
    # change rigorous-progress-math: strategic-tier weight for the EVM roll-up (Normal 1 / Alto 2 / Crítico 3).
    peso: Optional[float] = Field(None, ge=0.5, le=5)
    fecha_completado: Optional[datetime] = None
    depends_on: Optional[list] = None


def _assert_milestone_acyclic(db: Session, target_id, new_depends_on) -> None:
    """Raise HTTP 400 if setting `target_id`'s depends_on would form a cycle in the hito DAG.
    Reuses edt_cycle_chain() with string-keyed ids (change unify-strategy-execution)."""
    if not new_depends_on:
        return
    rows = db.query(RoadmapMilestone).all()
    adjacency = {str(m.id): [str(x) for x in (m.depends_on or [])] for m in rows}
    chain = edt_cycle_chain(adjacency, str(target_id), [str(x) for x in new_depends_on])
    if chain:
        raise HTTPException(
            400,
            "Dependencia circular entre hitos: " + " → ".join(chain) +
            ". Un hito no puede depender (directa o indirectamente) de sí mismo.",
        )


# ── Rigorous progress math (change rigorous-progress-math) ───────────────────────────────
# Per-task weight: a milestone-grade task (es_hito) and a high-priority task weigh more than an errand,
# so a hito does NOT advance the same for finishing a minor task as for finishing the deliverable that
# defines it. Standard practice (EVM weighted-milestone / agile priority weighting): work items are not
# counted as equal units. peso_pct exists but is unpopulated (default 0) on imported tasks, so we weight
# by the two populated signals — es_hito and prioridad. Range 0.5 … 4.5. Portable (Postgres + sqlite).
_TASK_WEIGHT = (
    "(CASE WHEN {p}es_hito THEN 3.0 ELSE 1.0 END) * "
    "(CASE {p}prioridad WHEN 'alta' THEN 1.5 WHEN 'baja' THEN 0.5 ELSE 1.0 END)"
)

# Rules of credit (EVM "Milestone Weighting with Percent Complete", ANSI/EIA-748): a declared status
# sets a floor; verified tasks provide the continuum. A 'done' is capped by its evidence (the STRICT
# policy the CEO chose): ≥80% of its weighted tasks done → full 100; below that → its real %, capped 90.
UMBRAL_RESPALDO = 0.80   # evidence ratio a 'done' needs to keep full credit
DONE_CAP = 90.0          # a below-threshold 'done' cannot read more than this
_AVANCE_FLOOR = {"in_progress": 10.0, "delayed": 5.0}   # small "started" credit when a hito has no tasks


def milestone_avance(estado: str, wpct, has_tasks: bool) -> float:
    """ONE coherent, evidence-weighted progress per hito (change rigorous-progress-math). `wpct` is the
    WEIGHTED task-completion ratio in [0,1] (None/0 when the hito has no linked tasks):
      done        → 100 if no tasks (legacy/untracked, trusted but flagged); else STRICT cap by evidence
      in_progress → max(floor, 100·wpct)     delayed → max(floor, 100·wpct)
      pendiente   → 0 (declared not-started; evidence does not inflate it)."""
    if estado == "done":
        if not has_tasks:
            return 100.0                                  # nothing to contradict → trust + flag
        if (wpct or 0) >= UMBRAL_RESPALDO:
            return 100.0
        return round(min(100.0 * (wpct or 0), DONE_CAP), 1)   # strict: show real %, capped
    if estado in ("pendiente", "pending"):
        return 0.0
    floor = _AVANCE_FLOOR.get(estado, 0.0)
    if has_tasks:
        return round(max(floor, 100.0 * (wpct or 0)), 1)
    return floor


def milestone_sin_respaldo(estado: str, wpct, has_tasks: bool) -> bool:
    """Flag a 'done' hito whose task evidence does not back the claim — no linked tasks, or weighted
    completion below the credit threshold. It still shows its (now-discounted) number, but the flag keeps
    the headline honest about lacking proof ('verificar respaldo')."""
    if estado != "done":
        return False
    return (not has_tasks) or (float(wpct or 0) < UMBRAL_RESPALDO)


def hito_real_work(db: Session) -> dict:
    """Per hito: WEIGHTED task completion over the tasks EXPLICITLY attributed to it (tasks.milestone_id
    = hito). A milestone-grade / high-priority task weighs more than a trivial one (see _TASK_WEIGHT), so
    a hito advances by the WEIGHT of real work done, not a raw task count. Cancelled tasks are excluded
    from numerator AND denominator; blocked/pending count as 0 but stay in the denominator. We attribute
    by the explicit link, NOT the loose plan→meta chain, so the stale legacy backlog does not inflate it.
    Returns {milestone_id: {"total", "done", "wtotal", "wdone", "wpct", "has_tasks"}} — total/done are raw
    counts kept for the 'N/M tareas reales hechas' display. change rigorous-progress-math."""
    W = _TASK_WEIGHT.format(p="t.")
    rows = db.execute(text(
        "SELECT m.id AS mid, "
        "COUNT(t.id) AS total, "
        "SUM(CASE WHEN t.estado = 'completada' THEN 1 ELSE 0 END) AS done, "
        f"COALESCE(SUM({W}), 0) AS wtotal, "
        f"COALESCE(SUM(CASE WHEN t.estado = 'completada' THEN {W} ELSE 0 END), 0) AS wdone "
        "FROM roadmap_milestones m "
        "LEFT JOIN tasks t ON t.milestone_id = m.id AND t.estado <> 'cancelada' "
        "GROUP BY m.id"
    )).fetchall()
    out = {}
    for r in rows:
        total = int(r.total or 0)
        wtotal = float(r.wtotal or 0)
        wdone = float(r.wdone or 0)
        out[r.mid] = {"total": total, "done": int(r.done or 0),
                      "wtotal": round(wtotal, 2), "wdone": round(wdone, 2),
                      "wpct": round(wdone / wtotal, 4) if wtotal else 0.0,
                      "has_tasks": total > 0}
    return out


def recompute_milestone_pct(db: Session, milestone_id) -> None:
    """Derive a hito's pct_completado from the work that advances it: the average real % of the plans
    linked to it via their meta-de-hito (plans.goal_id -> strategic_goals.milestone_id).
    change unify-strategy-execution."""
    if not milestone_id:
        return
    db.execute(text(
        "UPDATE roadmap_milestones SET pct_completado = ("
        "  SELECT COALESCE(AVG(p.pct_completado_real), 0) FROM plans p "
        "  JOIN strategic_goals g ON g.id = p.goal_id WHERE g.milestone_id = :mid"
        ") WHERE id = :mid"
    ), {"mid": milestone_id})
    db.commit()


@router.get("/milestones", response_model=List[MilestoneOut])
def list_milestones(version_id: Optional[int] = None, db: Session = Depends(get_db)):
    q = db.query(RoadmapMilestone)
    if version_id:
        q = q.filter(RoadmapMilestone.version_id == version_id)
    rows = q.order_by(RoadmapMilestone.orden).all()
    work = hito_real_work(db)  # WEIGHTED real task completion per hito (es_hito × prioridad)
    for m in rows:  # derived (not persisted): evidence-weighted avance + "verificar respaldo" + counts
        info = work.get(m.id, {"total": 0, "done": 0, "wpct": 0.0, "has_tasks": False})
        m.avance = milestone_avance(m.estado, info["wpct"], info["has_tasks"])
        m.sin_respaldo = milestone_sin_respaldo(m.estado, info["wpct"], info["has_tasks"])
        m.tareas_total = info["total"]
        m.tareas_done = info["done"]
    return rows


@router.post("/milestones", response_model=MilestoneOut, status_code=201)
def create_milestone(body: MilestoneCreate, db: Session = Depends(get_db)):
    _assert_milestone_acyclic(db, "__new__", body.depends_on)
    m = RoadmapMilestone(**body.model_dump())
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


@router.patch("/milestones/{milestone_id}", response_model=MilestoneOut)
def update_milestone(milestone_id: int, body: MilestonePatch, db: Session = Depends(get_db)):
    m = db.get(RoadmapMilestone, milestone_id)
    if not m:
        raise HTTPException(404, "Hito no encontrado")
    patch = body.model_dump(exclude_unset=True)
    if "depends_on" in patch and patch["depends_on"] is not None:
        _assert_milestone_acyclic(db, milestone_id, patch["depends_on"])
    for k, v in patch.items():
        setattr(m, k, v)
    db.commit()
    db.refresh(m)
    return m


@router.get("/quarters")
def roadmap_quarters(anio: int = Query(..., description="Año del ciclo, ej. 2026"),
                     db: Session = Depends(get_db)):
    """Per-quarter roadmap for a year, sourced from the PLANS' quarterly goals (change
    plan-quarterly-milestones — the quarter lives on the plan, not the hito). Reuses the envelope
    shape; each item is a plan's quarterly goal with a DERIVED pct. Empty year -> total 0 (honest)."""
    from .plans import _plan_quarter_pcts  # lazy import: avoids the plans<->roadmap module cycle

    plans = db.query(Plan).filter(Plan.anio == anio).order_by(Plan.area).all()
    quarters = {q: [] for q in (1, 2, 3, 4)}
    total = 0
    for plan in plans:
        goals = db.query(PlanQuarterlyGoal).filter(PlanQuarterlyGoal.plan_id == plan.id).all()
        if not goals:
            continue
        pcts = _plan_quarter_pcts(db, plan.id)
        for g in goals:
            if g.trimestre in quarters:
                quarters[g.trimestre].append({
                    "plan_id": plan.id,
                    "area": plan.area,
                    "meta": g.meta,
                    "objetivo_medible": g.objetivo_medible,
                    "pct": pcts.get(g.trimestre),
                })
                total += 1
    return {
        "anio": anio,
        "total": total,
        "quarters": [{"trimestre": q, "items": quarters[q]} for q in (1, 2, 3, 4)],
    }


@router.get("/active-cycle")
def active_cycle(db: Session = Depends(get_db)):
    """The active annual planning cycle (`roadmap_cycles WHERE estado='activo'`). The front anchors the
    roadmap year to this instead of the browser clock (kills the latent 2027 empty-dashboard bug).
    Honest empty (`anio=null`) when no cycle is active — the front then shows "sin datos", not a guess."""
    cycle = (
        db.query(RoadmapCycle)
        .filter(RoadmapCycle.estado == "activo")
        .order_by(RoadmapCycle.anio.desc())
        .first()
    )
    if not cycle:
        return {"anio": None, "ciclo_id": None, "nombre": None}
    return {"anio": cycle.anio, "ciclo_id": cycle.id, "nombre": cycle.nombre}


@router.get("/milestones/{milestone_id}/cascade-impact")
def cascade_impact(milestone_id: int, db: Session = Depends(get_db)):
    """Árbol determinístico de hitos que dependen del hito dado."""
    all_milestones = db.query(RoadmapMilestone).all()
    index = {m.id: m for m in all_milestones}
    visited = set()

    def walk(mid):
        if mid in visited or mid not in index:
            return None
        visited.add(mid)
        m = index[mid]
        dependents = [
            walk(x.id) for x in all_milestones
            if x.depends_on and mid in x.depends_on
        ]
        return {
            "id": m.id,
            "titulo": m.titulo,
            "estado": m.estado,
            "pct_completado": float(m.pct_completado),
            "dependientes": [d for d in dependents if d],
        }

    root = walk(milestone_id)
    if not root:
        raise HTTPException(404, "Hito no encontrado")
    return root

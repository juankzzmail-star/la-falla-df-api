from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Plan, PlanQuarterlyGoal, RoadmapCycle, StrategicGoal
from .roadmap import recompute_milestone_pct  # cascade roll-up: plan % -> hito %
from .tasks import _plan_hito  # reuse the meta-de-hito resolver (plan -> hito)
from ..schemas import (
    CurvaSBaseline,
    GeneratePlansRequest,
    GeneratePlansResponse,
    PlanApproveResponse,
    PlanCreate,
    PlanOut,
    PlanQuartersIn,
    PlanQuartersOut,
    PlanUpdate,
    QuarterlyGoalOut,
)
from . import _cascade

router = APIRouter(prefix="/plans", tags=["plans"])


def _parse_date(value) -> Optional[date]:
    """Best-effort ISO date parse from an LLM seam value; None on failure."""
    if isinstance(value, date):
        return value
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


# ─── unify-strategy-execution helpers ────────────────────────────────────────────
def _active_cycle(db: Session) -> Optional[RoadmapCycle]:
    """The active annual planning cycle, or None. Plans of a cycle carry its anio/ciclo_id."""
    return (
        db.query(RoadmapCycle)
        .filter(RoadmapCycle.estado == "activo")
        .order_by(RoadmapCycle.anio.desc())
        .first()
    )


def _anio_for(goal, cycle) -> Optional[int]:
    """Year for a generated plan: the active cycle's year, else inferred from the meta-de-hito dates."""
    if cycle:
        return cycle.anio
    for d in (getattr(goal, "fecha_fin_meta", None), getattr(goal, "fecha_inicio", None)):
        if d:
            return d.year
    return None


def _interp_plan_pct(baseline, today: date) -> float:
    """Planned % from the curva-S baseline at `today`: the pct_plan of the latest monthly bucket whose
    month <= today (0 before the curve). baseline = [{mes:'YYYY-MM', pct_plan: number}, ...] in order."""
    if not baseline:
        return 0.0
    ym = f"{today.year:04d}-{today.month:02d}"
    val = 0.0
    for pt in baseline:
        try:
            mes = str(pt.get("mes"))
            pct = float(pt.get("pct_plan") or 0)
        except (AttributeError, TypeError, ValueError):
            continue
        if mes <= ym:
            val = pct
        else:
            break
    return round(val, 1)


# ─── plan-quarterly-milestones: the quarter lives on the plan; its % is DERIVED ──────
def _quarter_of(d) -> Optional[int]:
    """Calendar quarter (1..4) of a date or ISO date string; None if it cannot be parsed.
    Accepts both python `date` (Postgres) and 'YYYY-MM-DD' strings (SQLite raw rows)."""
    if isinstance(d, str):
        d = _parse_date(d)
    if not isinstance(d, date):
        return None
    return (d.month - 1) // 3 + 1


def _year_of(d) -> Optional[int]:
    """Calendar year of a date or ISO date string; None if it cannot be parsed (mirrors _quarter_of)."""
    if isinstance(d, str):
        d = _parse_date(d)
    if not isinstance(d, date):
        return None
    return d.year


def _derive_quarter_pcts(rows, anio: Optional[int] = None) -> dict:
    """Per-quarter % derived from real task completion. `rows` = iterable of
    (fecha_vencimiento, peso_pct, estado). For each quarter 1..4:
    `pct = 100 * Σ peso(completed in Q) / Σ peso(all in Q)`; `None` when the quarter has no
    contributing work ("sin datos"). Falls back to a count ratio when every peso in the quarter is 0.
    Tasks without a due date cannot be attributed to a quarter and are ignored. When `anio` is given the
    derivation is **year-scoped**: a task whose due-date year ≠ `anio` is ignored, so a plan's quarters
    reflect only its cycle year (change populate-hito-rollup); `anio=None` keeps the year-blind behavior.
    Pure + DB-portable (no SQL EXTRACT/strftime) — the gate's SQLite and prod Postgres compute the same value."""
    agg = {q: {"tp": 0.0, "dp": 0.0, "tn": 0, "dn": 0} for q in (1, 2, 3, 4)}
    for fv, peso, estado in rows:
        q = _quarter_of(fv)
        if q is None:
            continue
        if anio is not None and _year_of(fv) != anio:
            continue                                          # year-scoped: another year's task isn't this plan's quarter
        try:
            w = float(peso or 0)
        except (TypeError, ValueError):
            w = 0.0
        a = agg[q]
        a["tp"] += w
        a["tn"] += 1
        if estado == "completada":
            a["dp"] += w
            a["dn"] += 1
    out = {}
    for q, a in agg.items():
        if a["tn"] == 0:
            out[q] = None                                   # no contributing work -> "sin datos"
        elif a["tp"] > 0:
            out[q] = round(100 * a["dp"] / a["tp"], 1)
        else:
            out[q] = round(100 * a["dn"] / a["tn"], 1)       # all-zero-peso count fallback
    return out


def _plan_quarter_pcts(db: Session, plan_id: int) -> dict:
    """Derived per-quarter % for a plan, from its tasks' due dates + completion (portable raw SQL —
    same reason the cascade uses text() for tasks: the ORM Task carries cross-area FKs). Year-scoped to the
    plan's `anio` when set, so tasks from another year do not leak into this plan's quarters."""
    anio = db.execute(text("SELECT anio FROM plans WHERE id = :pid"), {"pid": plan_id}).scalar()
    rows = db.execute(
        text("SELECT fecha_vencimiento, peso_pct, estado FROM tasks WHERE plan_id = :pid"),
        {"pid": plan_id},
    ).fetchall()
    return _derive_quarter_pcts(((r[0], r[1], r[2]) for r in rows), anio=anio)


@router.get("", response_model=List[PlanOut])
def list_plans(
    area: Optional[str] = Query(None),
    goal_id: Optional[int] = Query(None),
    estado: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(Plan)
    if area:
        q = q.filter(Plan.area == area)
    if goal_id:
        q = q.filter(Plan.goal_id == goal_id)
    if estado:
        q = q.filter(Plan.estado == estado)
    return q.order_by(Plan.area, Plan.codigo).all()


@router.post("", response_model=PlanOut, status_code=201)
def create_plan(body: PlanCreate, db: Session = Depends(get_db)):
    if db.query(Plan).filter(Plan.codigo == body.codigo).first():
        raise HTTPException(409, f"Plan con codigo '{body.codigo}' ya existe")
    plan = Plan(**body.model_dump())
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


@router.get("/{plan_id}", response_model=PlanOut)
def get_plan(plan_id: int, db: Session = Depends(get_db)):
    plan = db.query(Plan).filter(Plan.id == plan_id).first()
    if not plan:
        raise HTTPException(404, f"Plan {plan_id} not found")
    return plan


@router.patch("/{plan_id}", response_model=PlanOut)
def update_plan(plan_id: int, body: PlanUpdate, db: Session = Depends(get_db)):
    plan = db.query(Plan).filter(Plan.id == plan_id).first()
    if not plan:
        raise HTTPException(404, f"Plan {plan_id} not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(plan, field, value)
    db.commit()
    db.refresh(plan)
    return plan


@router.delete("/{plan_id}")
def delete_plan(plan_id: int, db: Session = Depends(get_db)):
    plan = db.query(Plan).filter(Plan.id == plan_id).first()
    if not plan:
        raise HTTPException(404, f"Plan {plan_id} not found")
    db.delete(plan)
    db.commit()
    return {"deleted": True, "id": plan_id}


@router.put("/{plan_id}/curva-s-baseline", response_model=PlanOut)
def set_curva_s_baseline(plan_id: int, body: CurvaSBaseline, db: Session = Depends(get_db)):
    plan = db.query(Plan).filter(Plan.id == plan_id).first()
    if not plan:
        raise HTTPException(404, f"Plan {plan_id} not found")
    plan.baseline_curva_s = body.baseline
    db.commit()
    db.refresh(plan)
    return plan


@router.post("/{plan_id}/recalculate", response_model=PlanOut)
def recalculate_plan(plan_id: int, db: Session = Depends(get_db)):
    plan = db.query(Plan).filter(Plan.id == plan_id).first()
    if not plan:
        raise HTTPException(404, f"Plan {plan_id} not found")
    completed_pct = db.execute(
        text("SELECT COALESCE(SUM(peso_pct), 0) FROM tasks WHERE plan_id = :pid AND estado = 'completada'"),
        {"pid": plan_id},
    ).scalar()
    plan.pct_completado_real = float(completed_pct)
    # change unify-strategy-execution: planned % is the curva-S baseline interpolated to today.
    plan.pct_completado_plan = _interp_plan_pct(plan.baseline_curva_s, date.today())
    db.commit()
    # Cascade roll-up: the plan's hito % is the avg of its plans' real % — recompute so the
    # company hito doesn't go stale (change unify-strategy-execution).
    recompute_milestone_pct(db, _plan_hito(db, plan.id))
    db.refresh(plan)
    return plan


# ─── Plan quarterly goals (change plan-quarterly-milestones) ─────────────────────
@router.get("/{plan_id}/quarters", response_model=PlanQuartersOut)
def get_plan_quarters(plan_id: int, db: Session = Depends(get_db)):
    """The plan's four quarterly goals (meta + optional objetivo_medible) with a per-quarter `pct`
    DERIVED from real task completion. A quarter with no defined meta returns meta=null; a quarter with
    no contributing work returns pct=null ("sin datos")."""
    plan = db.query(Plan).filter(Plan.id == plan_id).first()
    if not plan:
        raise HTTPException(404, f"Plan {plan_id} not found")
    goals = {
        g.trimestre: g
        for g in db.query(PlanQuarterlyGoal).filter(PlanQuarterlyGoal.plan_id == plan_id).all()
    }
    pcts = _plan_quarter_pcts(db, plan_id)
    quarters = [
        QuarterlyGoalOut(
            trimestre=t,
            meta=goals[t].meta if t in goals else None,
            objetivo_medible=goals[t].objetivo_medible if t in goals else None,
            pct=pcts.get(t),
        )
        for t in (1, 2, 3, 4)
    ]
    return PlanQuartersOut(plan_id=plan_id, area=plan.area, quarters=quarters)


@router.put("/{plan_id}/quarters", response_model=PlanQuartersOut)
def set_plan_quarters(plan_id: int, body: PlanQuartersIn, db: Session = Depends(get_db)):
    """Define/replace the plan's quarterly goals. trimestre is validated 1..4 by the schema (422 on
    out-of-range); a duplicate trimestre in the body is also rejected 422. The % is never stored."""
    plan = db.query(Plan).filter(Plan.id == plan_id).first()
    if not plan:
        raise HTTPException(404, f"Plan {plan_id} not found")
    seen = set()
    for q in body.quarters:
        if q.trimestre in seen:
            raise HTTPException(422, f"Trimestre {q.trimestre} duplicado en el plan")
        seen.add(q.trimestre)
    # Idempotent replace of this plan's quarterly goals.
    db.query(PlanQuarterlyGoal).filter(PlanQuarterlyGoal.plan_id == plan_id).delete()
    for q in body.quarters:
        db.add(PlanQuarterlyGoal(
            plan_id=plan_id, trimestre=q.trimestre, meta=q.meta, objetivo_medible=q.objetivo_medible,
        ))
    db.commit()
    return get_plan_quarters(plan_id, db)


@router.post("/{plan_id}/quarters/generate", response_model=PlanQuartersOut)
def generate_plan_quarters(plan_id: int, db: Session = Depends(get_db)):
    """The Centro de Mando derives the plan's quarterly goals from its REAL tasks via the LLM seam
    (change generate-plan-quarters): group the plan's tasks by quarter, propose a meta per quarter, and
    write them as the plan's quarterly goals (the human refines via PUT — "el LLM propone, el humano
    aprueba"). Honest 503 if no provider (raised before any write); 422 if the plan has no dated tasks.
    Stamps anio from the active cycle when missing, so the result surfaces in the roadmap modal."""
    plan = db.query(Plan).filter(Plan.id == plan_id).first()
    if not plan:
        raise HTTPException(404, f"Plan {plan_id} not found")
    # Year-scope: a plan's quarters belong to its cycle year. Resolve the target year first (the active
    # cycle when the plan has none) so only that year's tasks define its quarters; stamp the plan only once
    # we know we'll generate, so a 422/503 leaves it untouched (change populate-hito-rollup).
    target_anio = plan.anio
    if not target_anio:
        cycle = _active_cycle(db)
        if cycle:
            target_anio = cycle.anio

    rows = db.execute(
        text("SELECT fecha_vencimiento, titulo FROM tasks WHERE plan_id = :pid"), {"pid": plan_id}
    ).fetchall()
    by_q: dict = {}
    for fv, titulo in rows:
        q = _quarter_of(fv)
        if not q:
            continue
        if target_anio is not None and _year_of(fv) != target_anio:
            continue                                          # only the plan's cycle-year tasks define its quarters
        by_q.setdefault(q, []).append((titulo or "").strip())
    if not by_q:
        raise HTTPException(422, "El plan no tiene tareas con fecha de vencimiento en su año de ciclo para derivar trimestres")

    plan_dict = {"codigo": plan.codigo, "titulo": plan.titulo, "area": plan.area}
    proposed = _cascade.generate_quarters_for_plan(plan_dict, by_q)  # raises 503 before any write

    # Stamp the resolved cycle year now that we're generating, so the result surfaces in the roadmap modal.
    if not plan.anio and target_anio is not None:
        plan.anio = target_anio

    for q in proposed:
        existing = (
            db.query(PlanQuarterlyGoal)
            .filter(PlanQuarterlyGoal.plan_id == plan_id, PlanQuarterlyGoal.trimestre == q["trimestre"])
            .first()
        )
        if existing:
            existing.meta = q["meta"]
            existing.objetivo_medible = q.get("objetivo_medible")
        else:
            db.add(PlanQuarterlyGoal(
                plan_id=plan_id, trimestre=q["trimestre"], meta=q["meta"],
                objetivo_medible=q.get("objetivo_medible"),
            ))
    db.commit()
    return get_plan_quarters(plan_id, db)


# ─── Strategy cascade: goals -> plans -> tasks (change strategy-cascade) ──────────

@router.post("/generate-from-goals", response_model=GeneratePlansResponse)
def generate_plans_from_goals(body: GeneratePlansRequest, db: Session = Depends(get_db)):
    """Propose plans for one or more strategic goals via the LLM seam. Plans land in
    estado='propuesto', linked by goal_id, with responsable=area director and a curva-S scaffold.
    Idempotent by plan codigo. Honest 503 when no provider (raised inside the seam)."""
    created = updated = 0
    out: List[Plan] = []
    cycle = _active_cycle(db)                      # stamp the annual cycle on generated plans
    ciclo_id = cycle.id if cycle else None

    for goal_id in body.goal_ids:
        goal = db.query(StrategicGoal).filter(StrategicGoal.id == goal_id).first()
        if not goal:
            continue
        anio = _anio_for(goal, cycle)
        goal_dict = {
            "codigo": goal.codigo, "titulo": goal.titulo, "area": goal.area,
            "fecha_inicio": goal.fecha_inicio, "fecha_fin_meta": goal.fecha_fin_meta,
        }
        proposed = _cascade.generate_plans_for_goal(goal_dict)
        for idx, p in enumerate(proposed, 1):
            codigo = (p.get("codigo") or f"{goal.codigo}-P{idx}").strip()
            fi = _parse_date(p.get("fecha_inicio")) or goal.fecha_inicio
            ff = _parse_date(p.get("fecha_fin_planificada")) or goal.fecha_fin_meta
            director = _cascade.director_for(goal.area)
            baseline = _cascade.curva_s_scaffold(fi, ff)

            existing = db.query(Plan).filter(Plan.codigo == codigo).first()
            if existing:
                existing.titulo = p.get("titulo") or existing.titulo
                existing.area = goal.area
                existing.goal_id = goal.id
                existing.responsable = director
                existing.anio = anio
                existing.ciclo_id = ciclo_id
                existing.fecha_inicio = fi
                existing.fecha_fin_planificada = ff
                existing.baseline_curva_s = baseline
                existing.estado = "propuesto"
                updated += 1
                out.append(existing)
            else:
                plan = Plan(
                    codigo=codigo, titulo=p.get("titulo") or codigo, area=goal.area,
                    goal_id=goal.id, responsable=director, anio=anio, ciclo_id=ciclo_id,
                    fecha_inicio=fi, fecha_fin_planificada=ff, baseline_curva_s=baseline,
                    estado="propuesto",
                )
                db.add(plan)
                created += 1
                out.append(plan)

    db.commit()
    for p in out:
        db.refresh(p)
    return {"planes_creados": created, "planes_actualizados": updated, "plans": out}


@router.post("/{plan_id}/approve", response_model=PlanApproveResponse)
def approve_plan(plan_id: int, db: Session = Depends(get_db)):
    """Approve a plan: flip to estado='activo' and generate its tasks via the LLM seam,
    assigned to the area's director. Idempotent — does not duplicate tasks if any exist."""
    plan = db.query(Plan).filter(Plan.id == plan_id).first()
    if not plan:
        raise HTTPException(404, f"Plan {plan_id} not found")

    director = _cascade.director_for(plan.area)
    # Raw SQL for tasks: the ORM Task model carries cross-area FKs (stakeholders_master,
    # edt_nodes) that aren't mapped here, so an ORM flush of Task triggers FK resolution.
    # Portable INSERT/COUNT via text() sidesteps that (consistent with strategy.py).
    existing_tasks = db.execute(
        text("SELECT COUNT(*) FROM tasks WHERE plan_id = :pid"), {"pid": plan.id}
    ).scalar() or 0
    if existing_tasks:
        # Already has tasks — just ensure it's active, never duplicate.
        plan.estado = "activo"
        db.commit()
        return {"plan_id": plan.id, "estado": plan.estado,
                "tareas_creadas": 0, "responsable": director}

    plan_dict = {
        "codigo": plan.codigo, "titulo": plan.titulo, "area": plan.area,
        "fecha_inicio": plan.fecha_inicio, "fecha_fin_planificada": plan.fecha_fin_planificada,
    }
    tareas = _cascade.generate_tasks_for_plan(plan_dict)  # raises 503 if no provider — before any write

    plan.estado = "activo"
    # The plan's hito comes from its meta-de-hito (strategic_goals.milestone_id); direct tasks
    # advance that hito by default (change unify-strategy-execution).
    hito_id = None
    if plan.goal_id:
        hito_id = db.execute(
            text("SELECT milestone_id FROM strategic_goals WHERE id = :gid"), {"gid": plan.goal_id}
        ).scalar()
    created = 0
    for t in tareas:
        prioridad = (t.get("prioridad") or "media").strip()
        if prioridad not in ("alta", "media", "baja"):
            prioridad = "media"
        try:
            peso = float(t.get("peso_pct") or 0)
        except (TypeError, ValueError):
            peso = 0.0
        db.execute(text(
            "INSERT INTO tasks (plan_id, titulo, responsable, area, fecha_inicio, fecha_vencimiento, "
            "prioridad, es_hito, estado, peso_pct, origen, milestone_id) VALUES "
            "(:plan_id, :titulo, :responsable, :area, :fi, :fv, :prioridad, :es_hito, 'pendiente', :peso, "
            "'directa', :mid)"
        ), {
            "plan_id": plan.id,
            "titulo": (t.get("titulo") or "Tarea").strip(),
            "responsable": director,
            "area": plan.area,
            "fi": _parse_date(t.get("fecha_inicio")) or plan.fecha_inicio,
            "fv": _parse_date(t.get("fecha_vencimiento")) or plan.fecha_fin_planificada,
            "prioridad": prioridad,
            "es_hito": bool(t.get("es_hito", False)),
            "peso": peso,
            "mid": hito_id,
        })
        created += 1

    db.commit()
    return {"plan_id": plan.id, "estado": plan.estado,
            "tareas_creadas": created, "responsable": director}

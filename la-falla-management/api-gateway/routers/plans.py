from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Plan
from ..schemas import CurvaSBaseline, PlanCreate, PlanOut, PlanUpdate

router = APIRouter(prefix="/plans", tags=["plans"])


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
    db.commit()
    db.refresh(plan)
    return plan

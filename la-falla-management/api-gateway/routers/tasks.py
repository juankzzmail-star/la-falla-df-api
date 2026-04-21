import os
from datetime import date
from typing import List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Plan, Task
from ..schemas import TaskBlockRequest, TaskCreate, TaskOut, TaskUpdate

router = APIRouter(prefix="/tasks", tags=["tasks"])

N8N_WEBHOOK_NOTIFICACIONES = os.environ.get("N8N_WEBHOOK_NOTIFICACIONES", "")
N8N_WEBHOOK_SYNC_GOOGLE    = os.environ.get("N8N_WEBHOOK_SYNC_GOOGLE", "")
N8N_WEBHOOK_SECRET         = os.environ.get("N8N_WEBHOOK_SECRET", "")


@router.get("", response_model=List[TaskOut])
def list_tasks(
    plan_id: Optional[int] = Query(None),
    area: Optional[str] = Query(None),
    responsable: Optional[str] = Query(None),
    estado: Optional[str] = Query(None),
    es_hito: Optional[bool] = Query(None),
    limit: int = Query(200, le=1000),
    db: Session = Depends(get_db),
):
    q = db.query(Task)
    if plan_id:
        q = q.filter(Task.plan_id == plan_id)
    if area:
        q = q.filter(Task.area == area)
    if responsable:
        q = q.filter(Task.responsable == responsable)
    if estado:
        q = q.filter(Task.estado == estado)
    if es_hito is not None:
        q = q.filter(Task.es_hito == es_hito)
    return q.order_by(Task.fecha_vencimiento).limit(limit).all()


@router.post("", response_model=TaskOut, status_code=201)
async def create_task(body: TaskCreate, db: Session = Depends(get_db)):
    task = Task(**body.model_dump())
    db.add(task)
    db.commit()
    db.refresh(task)
    if N8N_WEBHOOK_SYNC_GOOGLE:
        await _fire(N8N_WEBHOOK_SYNC_GOOGLE, _payload(task, "created"))
    return task


@router.get("/{task_id}", response_model=TaskOut)
def get_task(task_id: int, db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(404, f"Task {task_id} not found")
    return task


@router.patch("/{task_id}", response_model=TaskOut)
async def update_task(task_id: int, body: TaskUpdate, db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(404, f"Task {task_id} not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(task, field, value)
    db.commit()
    db.refresh(task)
    if N8N_WEBHOOK_SYNC_GOOGLE:
        await _fire(N8N_WEBHOOK_SYNC_GOOGLE, _payload(task, "updated"))
    return task


@router.delete("/{task_id}")
def delete_task(task_id: int, db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(404, f"Task {task_id} not found")
    db.delete(task)
    db.commit()
    return {"deleted": True, "id": task_id}


@router.post("/{task_id}/complete", response_model=TaskOut)
async def complete_task(task_id: int, db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(404, f"Task {task_id} not found")

    task.estado = "completada"
    task.fecha_completada = date.today()
    db.commit()

    # Recalculate plan % completion
    plan = db.query(Plan).filter(Plan.id == task.plan_id).first()
    if plan:
        completed_pct = db.execute(
            text("SELECT COALESCE(SUM(peso_pct), 0) FROM tasks WHERE plan_id = :pid AND estado = 'completada'"),
            {"pid": plan.id},
        ).scalar()
        plan.pct_completado_real = float(completed_pct)
        db.commit()

    db.refresh(task)

    if task.es_hito and N8N_WEBHOOK_NOTIFICACIONES:
        await _fire(N8N_WEBHOOK_NOTIFICACIONES, {
            "tipo": "hito_completado",
            "task_id": task.id,
            "titulo": task.titulo,
            "area": task.area,
            "responsable": task.responsable,
            "plan_id": task.plan_id,
            "pct_completado_real": float(plan.pct_completado_real) if plan else 0,
        })

    if N8N_WEBHOOK_SYNC_GOOGLE:
        await _fire(N8N_WEBHOOK_SYNC_GOOGLE, _payload(task, "completed"))

    return task


@router.post("/{task_id}/block", response_model=TaskOut)
async def block_task(task_id: int, body: TaskBlockRequest, db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(404, f"Task {task_id} not found")

    task.estado = "bloqueada"
    task.motivo_bloqueo = body.motivo_bloqueo
    db.commit()
    db.refresh(task)

    if N8N_WEBHOOK_NOTIFICACIONES:
        await _fire(N8N_WEBHOOK_NOTIFICACIONES, {
            "tipo": "tarea_bloqueada",
            "task_id": task.id,
            "titulo": task.titulo,
            "area": task.area,
            "responsable": task.responsable,
            "motivo": body.motivo_bloqueo,
        })

    return task


def _payload(task: Task, action: str) -> dict:
    return {
        "action": action,
        "task_id": task.id,
        "titulo": task.titulo,
        "responsable": task.responsable,
        "area": task.area,
        "estado": task.estado,
        "fecha_vencimiento": task.fecha_vencimiento.isoformat() if task.fecha_vencimiento else None,
        "es_hito": task.es_hito,
        "google_task_id": task.google_task_id,
        "google_calendar_event_id": task.google_calendar_event_id,
        "plan_id": task.plan_id,
    }


async def _fire(url: str, payload: dict) -> None:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(url, json=payload, headers={"X-Webhook-Secret": N8N_WEBHOOK_SECRET})
    except Exception:
        pass  # fire-and-forget; never fail the main request

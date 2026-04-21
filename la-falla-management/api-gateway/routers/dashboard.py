from datetime import date
from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..db import get_db
from ..schemas import AlertItem, AreaSummary

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=List[AreaSummary])
def get_summary(db: Session = Depends(get_db)):
    rows = db.execute(text("SELECT * FROM v_dashboard_ceo ORDER BY area")).fetchall()
    return [dict(r._mapping) for r in rows]


@router.get("/curva-s/{plan_id}")
def get_curva_s(plan_id: int, db: Session = Depends(get_db)):
    real_rows = db.execute(
        text("SELECT semana, pct_real_acumulado FROM v_curva_s_real WHERE plan_id = :pid ORDER BY semana"),
        {"pid": plan_id},
    ).fetchall()
    real_map = {r.semana: float(r.pct_real_acumulado) for r in real_rows}

    baseline = db.execute(
        text("SELECT baseline_curva_s FROM plans WHERE id = :pid"),
        {"pid": plan_id},
    ).scalar()

    data = []
    if baseline:
        for point in baseline:
            semana = point.get("semana", "")
            data.append({
                "semana": semana,
                "pct_planificado": float(point.get("pct_planificado", 0)),
                "pct_real": real_map.get(semana),
            })

    return {"plan_id": plan_id, "data": data}


@router.get("/gantt/{area}")
def get_gantt(area: str, db: Session = Depends(get_db)):
    rows = db.execute(
        text("""
            SELECT t.id, t.titulo, t.responsable, t.area, t.estado, t.prioridad,
                   t.fecha_inicio, t.fecha_vencimiento, t.fecha_completada,
                   t.es_hito, t.peso_pct, p.titulo AS plan_titulo
            FROM tasks t
            JOIN plans p ON p.id = t.plan_id
            WHERE t.area = :area
            ORDER BY t.fecha_vencimiento ASC NULLS LAST
        """),
        {"area": area},
    ).fetchall()
    return [dict(r._mapping) for r in rows]


@router.get("/alerts", response_model=List[AlertItem])
def get_alerts(db: Session = Depends(get_db)):
    alerts: List[AlertItem] = []
    today = date.today()

    overdue = db.execute(text("""
        SELECT t.id, t.titulo, t.area, t.responsable, t.fecha_vencimiento
        FROM tasks t
        WHERE t.estado NOT IN ('completada','cancelada')
          AND t.fecha_vencimiento < :today
        ORDER BY t.fecha_vencimiento ASC
        LIMIT 20
    """), {"today": today}).fetchall()

    for r in overdue:
        alerts.append(AlertItem(
            tipo="vencida",
            descripcion=f"Tarea vencida: {r.titulo} (venció {r.fecha_vencimiento})",
            area=r.area,
            responsable=r.responsable,
            tarea_id=r.id,
        ))

    blocked = db.execute(text("""
        SELECT t.id, t.titulo, t.area, t.responsable, t.motivo_bloqueo
        FROM tasks t
        WHERE t.estado = 'bloqueada'
        ORDER BY t.updated_at DESC
        LIMIT 20
    """)).fetchall()

    for r in blocked:
        alerts.append(AlertItem(
            tipo="bloqueada",
            descripcion=f"Tarea bloqueada: {r.titulo} — {r.motivo_bloqueo}",
            area=r.area,
            responsable=r.responsable,
            tarea_id=r.id,
        ))

    red_stakeholders = db.execute(text("""
        SELECT DISTINCT ON (shl.stakeholder_id)
            shl.stakeholder_id, sm.nombre, shl.razon
        FROM stakeholder_health_log shl
        JOIN stakeholders_master sm ON sm.id = shl.stakeholder_id
        WHERE shl.salud = 'rojo'
        ORDER BY shl.stakeholder_id, shl.calculado_en DESC
        LIMIT 10
    """)).fetchall()

    for r in red_stakeholders:
        alerts.append(AlertItem(
            tipo="stakeholder_rojo",
            descripcion=f"Stakeholder en rojo: {r.nombre} — {r.razon}",
            stakeholder_id=r.stakeholder_id,
        ))

    return alerts

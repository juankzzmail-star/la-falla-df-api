from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import StakeholderHealthLog
from ..schemas import HealthLogCreate, HealthLogOut

router = APIRouter(prefix="/stakeholder-health", tags=["stakeholder-health"])


@router.post("", response_model=List[HealthLogOut], status_code=201)
def create_health_logs(body: List[HealthLogCreate], db: Session = Depends(get_db)):
    logs = [StakeholderHealthLog(**item.model_dump()) for item in body]
    db.add_all(logs)
    db.commit()
    for log in logs:
        db.refresh(log)
    return logs


@router.get("", response_model=List[HealthLogOut])
def list_health_logs(
    salud: Optional[str] = Query(None),
    limit: int = Query(100, le=500),
    db: Session = Depends(get_db),
):
    q = db.query(StakeholderHealthLog)
    if salud:
        q = q.filter(StakeholderHealthLog.salud == salud)
    return q.order_by(StakeholderHealthLog.calculado_en.desc()).limit(limit).all()


@router.get("/current")
def get_current_health(salud: Optional[str] = Query(None), db: Session = Depends(get_db)):
    salud_filter = f"AND shl.salud = '{salud}'" if salud else ""
    rows = db.execute(text(f"""
        SELECT DISTINCT ON (shl.stakeholder_id)
            shl.id, shl.stakeholder_id, shl.salud, shl.razon,
            shl.dias_sin_contacto, shl.calculado_en, shl.resultado_ultima_interaccion,
            sm.nombre AS stakeholder_nombre, sm.clasificacion_negocio
        FROM stakeholder_health_log shl
        JOIN stakeholders_master sm ON sm.id = shl.stakeholder_id
        WHERE 1=1 {salud_filter}
        ORDER BY shl.stakeholder_id, shl.calculado_en DESC
    """)).fetchall()
    return [dict(r._mapping) for r in rows]

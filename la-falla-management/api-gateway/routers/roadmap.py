from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

from ..db import get_db
from ..models import RoadmapMilestone, RoadmapVersion, StrategicGoal

router = APIRouter(prefix="/roadmap", tags=["roadmap"])


class MilestoneOut(BaseModel):
    id: int
    titulo: str
    orden: int
    estado: str
    area: Optional[str]
    fecha_inicio: Optional[datetime]
    fecha_fin_planificada: Optional[datetime]
    fecha_completado: Optional[datetime]
    depends_on: Optional[list]
    version_id: Optional[int]
    pct_completado: float

    class Config:
        from_attributes = True


class MilestoneCreate(BaseModel):
    titulo: str
    orden: int
    estado: str = "pendiente"
    area: Optional[str] = None
    fecha_inicio: Optional[datetime] = None
    fecha_fin_planificada: Optional[datetime] = None
    depends_on: Optional[list] = None
    version_id: Optional[int] = None
    pct_completado: float = 0.0


class MilestonePatch(BaseModel):
    titulo: Optional[str] = None
    estado: Optional[str] = None
    pct_completado: Optional[float] = None
    fecha_completado: Optional[datetime] = None
    depends_on: Optional[list] = None


@router.get("/milestones", response_model=List[MilestoneOut])
def list_milestones(version_id: Optional[int] = None, db: Session = Depends(get_db)):
    q = db.query(RoadmapMilestone)
    if version_id:
        q = q.filter(RoadmapMilestone.version_id == version_id)
    return q.order_by(RoadmapMilestone.orden).all()


@router.post("/milestones", response_model=MilestoneOut, status_code=201)
def create_milestone(body: MilestoneCreate, db: Session = Depends(get_db)):
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
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(m, k, v)
    db.commit()
    db.refresh(m)
    return m


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

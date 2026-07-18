"""Oportunidades (Fase 3) — espejo de Airtable `Modalidades` + triage local del CEO.

Airtable (área 02) sigue siendo la fuente de verdad. El flujo n8n WF-GM-06 empuja las
convocatorias de alto ADN vía POST /api/oportunidades/sync (upsert idempotente por
`airtable_record_id`). El Centro de Mando solo consume (GET) y guarda el estado de
triage del CEO (PATCH). No se escribe de vuelta a Airtable.

Ver: openspec/changes/integrate-oportunidades-dashboard/ (proposal/design/tasks/spec)
"""
from datetime import date, datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Oportunidad

router = APIRouter(prefix="/oportunidades", tags=["oportunidades"])

ESTADOS_SEGUIMIENTO = {"nueva", "en_revision", "perseguir", "descartada"}


# ─── Pydantic models ──────────────────────────────────────────────

class OportunidadSyncItem(BaseModel):
    """Una convocatoria empujada por n8n (campos mapeados desde Airtable Modalidades)."""
    airtable_record_id: str
    nombre: str
    programa: Optional[str] = None
    entidad: Optional[str] = None
    presupuesto: Optional[str] = None
    fecha_cierre: Optional[date] = None
    url_convocatoria: Optional[str] = None
    pdf_bases: Optional[str] = None
    adn_score: Optional[int] = None
    prioridad: Optional[str] = None
    justificacion_adn: Optional[str] = None


class OportunidadOut(BaseModel):
    id: int
    airtable_record_id: str
    nombre: str
    programa: Optional[str]
    entidad: Optional[str]
    presupuesto: Optional[str]
    fecha_cierre: Optional[date]
    url_convocatoria: Optional[str]
    pdf_bases: Optional[str]
    adn_score: Optional[int]
    prioridad: Optional[str]
    justificacion_adn: Optional[str]
    estado_seguimiento: str
    synced_at: Optional[datetime]
    created_at: Optional[datetime]

    class Config:
        from_attributes = True


class OportunidadTriage(BaseModel):
    estado_seguimiento: str


# ─── Endpoints ────────────────────────────────────────────────────

# Campos que el sync puede sobreescribir (NUNCA estado_seguimiento ni created_at:
# esos son estado local del CEO y deben sobrevivir cualquier re-sync).
_SYNC_FIELDS = (
    "nombre", "programa", "entidad", "presupuesto", "fecha_cierre",
    "url_convocatoria", "pdf_bases", "adn_score", "prioridad", "justificacion_adn",
)


@router.post("/sync")
def sync_oportunidades(items: List[OportunidadSyncItem], db: Session = Depends(get_db)):
    """Upsert idempotente por `airtable_record_id`.

    - Inserta filas nuevas (estado_seguimiento='nueva' por defecto).
    - Actualiza en sitio las existentes preservando `estado_seguimiento` y `created_at`.
    - Re-correr el sync con los mismos records NO duplica filas.
    Devuelve el conteo {inserted, updated, total}.
    """
    inserted, updated = 0, 0
    for item in items:
        existing = (
            db.query(Oportunidad)
            .filter(Oportunidad.airtable_record_id == item.airtable_record_id)
            .first()
        )
        if existing:
            for field in _SYNC_FIELDS:
                setattr(existing, field, getattr(item, field))
            # `synced_at` se refresca solo (onupdate=func.now()).
            updated += 1
        else:
            db.add(Oportunidad(**item.model_dump()))
            inserted += 1
    db.commit()
    return {"inserted": inserted, "updated": updated, "total": inserted + updated}


@router.get("", response_model=List[OportunidadOut])
def list_oportunidades(
    prioridad: Optional[str] = None,
    min_adn: Optional[int] = None,
    estado_seguimiento: Optional[str] = None,
    solo_vigentes: bool = False,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    """Lista oportunidades. Orden: ADN desc, cierre asc (lo más urgente y relevante primero)."""
    q = db.query(Oportunidad)
    if prioridad:
        q = q.filter(Oportunidad.prioridad == prioridad)
    if min_adn is not None:
        q = q.filter(Oportunidad.adn_score >= min_adn)
    if estado_seguimiento:
        q = q.filter(Oportunidad.estado_seguimiento == estado_seguimiento)
    if solo_vigentes:
        q = q.filter(
            (Oportunidad.fecha_cierre.is_(None)) | (Oportunidad.fecha_cierre >= date.today())
        )
    q = q.order_by(
        Oportunidad.adn_score.desc().nullslast(),
        Oportunidad.fecha_cierre.asc().nullslast(),
    )
    return q.limit(min(max(limit, 1), 200)).all()


@router.patch("/{op_id}", response_model=OportunidadOut)
def update_triage(op_id: int, body: OportunidadTriage, db: Session = Depends(get_db)):
    """Set del estado de triage del CEO (nueva | en_revision | perseguir | descartada)."""
    if body.estado_seguimiento not in ESTADOS_SEGUIMIENTO:
        raise HTTPException(400, f"estado_seguimiento debe ser uno de: {sorted(ESTADOS_SEGUIMIENTO)}")
    o = db.get(Oportunidad, op_id)
    if not o:
        raise HTTPException(404, "Oportunidad no encontrada")
    o.estado_seguimiento = body.estado_seguimiento
    db.commit()
    db.refresh(o)
    return o

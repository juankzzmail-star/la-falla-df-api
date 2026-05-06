import os
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

from ..db import get_db

router = APIRouter(prefix="/stakeholders", tags=["stakeholders"])

N8N_HOST = os.environ.get("N8N_HOST", "")
N8N_API_KEY = os.environ.get("N8N_API_KEY", "")


# ─── Modelos ──────────────────────────────────────────────────────────────────

class StakeholderOut(BaseModel):
    id: int
    nombre: Optional[str]
    rol: Optional[str]
    correo: Optional[str]
    telefono: Optional[str]
    ubicacion: Optional[str]
    clasificacion_negocio: Optional[str]
    observaciones: Optional[str]
    servicios: Optional[str]
    linkedin_url: Optional[str]
    activo: Optional[bool]
    fecha_actualizacion: Optional[str]

    class Config:
        from_attributes = True


class StakeholderCreate(BaseModel):
    nombre: str
    rol: Optional[str] = None
    correo: Optional[str] = None
    telefono: Optional[str] = None
    ubicacion: Optional[str] = None
    clasificacion_negocio: str = "Prospecto por Identificar"
    observaciones: Optional[str] = None
    servicios: Optional[str] = None
    linkedin_url: Optional[str] = None


class StakeholderPatch(BaseModel):
    nombre: Optional[str] = None
    rol: Optional[str] = None
    correo: Optional[str] = None
    telefono: Optional[str] = None
    ubicacion: Optional[str] = None
    clasificacion_negocio: Optional[str] = None
    observaciones: Optional[str] = None
    servicios: Optional[str] = None
    linkedin_url: Optional[str] = None


def _row_to_out(row) -> dict:
    m = dict(row._mapping)
    return {
        "id": m.get("id"),
        "nombre": m.get("nombre"),
        "rol": m.get("rol"),
        "correo": m.get("correo") or m.get("email"),
        "telefono": m.get("telefono"),
        "ubicacion": m.get("ubicacion"),
        "clasificacion_negocio": m.get("clasificacion_negocio"),
        "observaciones": m.get("observaciones"),
        "servicios": m.get("servicios"),
        "linkedin_url": m.get("linkedin_url"),
        "activo": m.get("activo", True),
        "fecha_actualizacion": str(m.get("fecha_actualizacion", "")) if m.get("fecha_actualizacion") else None,
    }


def _notify_n8n(event: str, stakeholder_id: int, data: dict):
    """Dispara webhook en n8n para sincronizar cambios de stakeholders."""
    if not N8N_HOST:
        return
    try:
        import requests as _req
        _req.post(
            f"{N8N_HOST}/webhook/stakeholders-sync",
            json={"event": event, "stakeholder_id": stakeholder_id, "data": data},
            headers={"X-API-Key": N8N_API_KEY} if N8N_API_KEY else {},
            timeout=5,
        )
    except Exception:
        pass  # no bloquear si n8n no está disponible


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/stats")
def stakeholder_stats(db: Session = Depends(get_db)):
    """Resumen de stakeholders por clasificación."""
    rows = db.execute(text("""
        SELECT
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE activo = true OR activo IS NULL) AS activos,
            COUNT(*) FILTER (WHERE clasificacion_negocio = 'Clientes') AS clientes,
            COUNT(*) FILTER (WHERE clasificacion_negocio = 'Aliados') AS aliados,
            COUNT(*) FILTER (WHERE clasificacion_negocio = 'Institucional / Gobierno') AS institucionales,
            COUNT(*) FILTER (WHERE clasificacion_negocio = 'Proveedores (Locaciones)') AS proveedores,
            COUNT(*) FILTER (WHERE clasificacion_negocio = 'Prospecto por Identificar') AS prospectos,
            COUNT(*) FILTER (WHERE correo IS NOT NULL AND correo <> '') AS con_correo,
            COUNT(*) FILTER (WHERE telefono IS NOT NULL AND telefono <> '') AS con_telefono
        FROM stakeholders_master
    """)).fetchone()
    return dict(rows._mapping)


@router.get("", response_model=List[StakeholderOut])
def list_stakeholders(
    search: Optional[str] = None,
    clasificacion: Optional[str] = None,
    activo: Optional[bool] = None,
    limit: int = Query(default=50, le=500),
    offset: int = 0,
    db: Session = Depends(get_db),
):
    q = """
        SELECT id, nombre, rol, correo, telefono, ubicacion,
               clasificacion_negocio, observaciones, servicios, linkedin_url,
               activo, fecha_actualizacion
        FROM stakeholders_master
        WHERE 1=1
    """
    params: dict = {}
    if search:
        q += " AND (nombre ILIKE :search OR correo ILIKE :search OR ubicacion ILIKE :search OR rol ILIKE :search)"
        params["search"] = f"%{search}%"
    if clasificacion:
        q += " AND clasificacion_negocio = :clasificacion"
        params["clasificacion"] = clasificacion
    if activo is not None:
        q += " AND activo = :activo"
        params["activo"] = activo
    q += " ORDER BY nombre NULLS LAST LIMIT :limit OFFSET :offset"
    params["limit"] = limit
    params["offset"] = offset
    rows = db.execute(text(q), params).fetchall()
    return [_row_to_out(r) for r in rows]


@router.post("", response_model=StakeholderOut, status_code=201)
def create_stakeholder(body: StakeholderCreate, db: Session = Depends(get_db)):
    result = db.execute(
        text("""
            INSERT INTO stakeholders_master
                (nombre, rol, correo, telefono, ubicacion, clasificacion_negocio, observaciones, servicios, linkedin_url, activo)
            VALUES
                (:nombre, :rol, :correo, :telefono, :ubicacion, :clasificacion_negocio, :observaciones, :servicios, :linkedin_url, true)
            RETURNING id, nombre, rol, correo, telefono, ubicacion, clasificacion_negocio, observaciones, servicios, linkedin_url, activo, fecha_actualizacion
        """),
        body.model_dump(),
    ).fetchone()
    db.commit()
    out = _row_to_out(result)
    _notify_n8n("created", out["id"], out)
    return out


@router.get("/{stakeholder_id}", response_model=StakeholderOut)
def get_stakeholder(stakeholder_id: int, db: Session = Depends(get_db)):
    row = db.execute(
        text("""
            SELECT id, nombre, rol, correo, telefono, ubicacion,
                   clasificacion_negocio, observaciones, servicios, linkedin_url,
                   activo, fecha_actualizacion
            FROM stakeholders_master WHERE id = :id
        """),
        {"id": stakeholder_id},
    ).fetchone()
    if not row:
        raise HTTPException(404, "Stakeholder no encontrado")
    return _row_to_out(row)


@router.patch("/{stakeholder_id}", response_model=StakeholderOut)
def update_stakeholder(stakeholder_id: int, body: StakeholderPatch, db: Session = Depends(get_db)):
    data = body.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(400, "Sin campos para actualizar")

    field_map = {
        "nombre": "nombre", "rol": "rol", "correo": "correo",
        "telefono": "telefono", "ubicacion": "ubicacion",
        "clasificacion_negocio": "clasificacion_negocio",
        "observaciones": "observaciones", "servicios": "servicios",
        "linkedin_url": "linkedin_url",
    }
    sets = [f"{field_map[k]} = :{k}" for k in data if k in field_map]
    if not sets:
        raise HTTPException(400, "Sin campos válidos para actualizar")

    sets.append("fecha_actualizacion = NOW()")
    q = f"""
        UPDATE stakeholders_master SET {', '.join(sets)}
        WHERE id = :id
        RETURNING id, nombre, rol, correo, telefono, ubicacion, clasificacion_negocio, observaciones, servicios, linkedin_url, activo, fecha_actualizacion
    """
    data["id"] = stakeholder_id
    row = db.execute(text(q), data).fetchone()
    if not row:
        raise HTTPException(404, "Stakeholder no encontrado")
    db.commit()
    out = _row_to_out(row)
    _notify_n8n("updated", stakeholder_id, out)
    return out


@router.delete("/{stakeholder_id}", status_code=204)
def delete_stakeholder(stakeholder_id: int, db: Session = Depends(get_db)):
    result = db.execute(
        text("DELETE FROM stakeholders_master WHERE id = :id"),
        {"id": stakeholder_id},
    )
    if result.rowcount == 0:
        raise HTTPException(404, "Stakeholder no encontrado")
    db.commit()
    _notify_n8n("deleted", stakeholder_id, {})

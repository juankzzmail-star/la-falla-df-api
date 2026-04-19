"""
FastAPI — Stakeholders La Falla DF
Endpoints:
  GET  /healthz
  POST /classify
  POST /stakeholders
  GET  /stakeholders
  POST /interactions
  POST /linkedin/ingest
"""
import os
from datetime import datetime, timezone, timedelta
from typing import Optional, List

from fastapi import FastAPI, Depends, HTTPException, Security, Query
from fastapi.security.api_key import APIKeyHeader
from sqlalchemy.orm import Session
from sqlalchemy import text

from .db import get_db
from .models import Stakeholder, Interaction
from .schemas import (
    ClassifyRequest, ClassifyResponse,
    StakeholderCreate, StakeholderOut,
    InteractionCreate, InteractionOut,
    LinkedInIngest,
)
from .classifier import clasificar

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
API_KEY = os.environ.get("FASTAPI_API_KEY", "")
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=True)


def verify_key(key: str = Security(api_key_header)):
    if not API_KEY:
        raise HTTPException(500, "FASTAPI_API_KEY not configured on server")
    if key != API_KEY:
        raise HTTPException(403, "Invalid API key")
    return key


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="La Falla DF — Stakeholders API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url=None,
)


@app.get("/healthz", tags=["meta"])
def health():
    return {"status": "ok", "ts": datetime.now(timezone.utc).isoformat()}


# ---------------------------------------------------------------------------
# /classify
# ---------------------------------------------------------------------------
@app.post("/classify", response_model=ClassifyResponse, tags=["classify"])
def classify_contact(
    body: ClassifyRequest,
    _: str = Depends(verify_key),
):
    clas, razon = clasificar(body.model_dump())
    return ClassifyResponse(clasificacion=clas, razon=razon)


# ---------------------------------------------------------------------------
# /stakeholders
# ---------------------------------------------------------------------------
@app.post("/stakeholders", response_model=StakeholderOut, tags=["stakeholders"])
def create_stakeholder(
    body: StakeholderCreate,
    db: Session = Depends(get_db),
    _: str = Depends(verify_key),
):
    data = body.model_dump()
    clas, razon = clasificar(data)
    data["clasificacion_negocio"] = clas
    data["clasificacion"] = "WHATSAPP_INBOUND"
    row = Stakeholder(**data)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@app.get("/stakeholders", response_model=List[StakeholderOut], tags=["stakeholders"])
def list_stakeholders(
    clasificacion: Optional[str] = Query(None, description="Ej: Clientes, Aliados, Proveedores (Locaciones)"),
    con_telefono: Optional[bool] = Query(None),
    sin_interaccion_dias: Optional[int] = Query(None, description="Excluye contactados en los últimos N días"),
    linkedin_url: Optional[str] = Query(None),
    limit: int = Query(100, le=500),
    db: Session = Depends(get_db),
    _: str = Depends(verify_key),
):
    q = db.query(Stakeholder)

    if clasificacion:
        q = q.filter(Stakeholder.clasificacion_negocio == clasificacion)
    if con_telefono is True:
        q = q.filter(Stakeholder.telefono.isnot(None), Stakeholder.telefono != "")
    if con_telefono is False:
        q = q.filter(
            (Stakeholder.telefono.is_(None)) | (Stakeholder.telefono == "")
        )
    if linkedin_url:
        q = q.filter(Stakeholder.linkedin_url == linkedin_url)

    if sin_interaccion_dias:
        cutoff = datetime.now(timezone.utc) - timedelta(days=sin_interaccion_dias)
        interacted_ids = (
            db.query(Interaction.stakeholder_id)
            .filter(Interaction.timestamp >= cutoff)
            .distinct()
            .subquery()
        )
        q = q.filter(Stakeholder.id.notin_(interacted_ids))

    return q.limit(limit).all()


# ---------------------------------------------------------------------------
# /interactions
# ---------------------------------------------------------------------------
@app.post("/interactions", response_model=InteractionOut, tags=["interactions"])
def create_interaction(
    body: InteractionCreate,
    db: Session = Depends(get_db),
    _: str = Depends(verify_key),
):
    if body.direccion not in ("in", "out"):
        raise HTTPException(400, "direccion must be 'in' or 'out'")
    row = Interaction(**body.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


# ---------------------------------------------------------------------------
# /linkedin/ingest  (Chrome extension)
# ---------------------------------------------------------------------------
@app.post("/linkedin/ingest", tags=["linkedin"])
def linkedin_ingest(
    body: LinkedInIngest,
    db: Session = Depends(get_db),
    _: str = Depends(verify_key),
):
    existing = (
        db.query(Stakeholder)
        .filter(Stakeholder.linkedin_url == body.linkedin_url)
        .first()
    )
    if existing:
        return {
            "exists": True,
            "stakeholder_id": existing.id,
            "nombre": existing.nombre,
            "clasificacion_negocio": existing.clasificacion_negocio,
        }

    return {
        "exists": False,
        "nombre": body.nombre,
        "headline": body.headline,
        "empresa": body.empresa,
        "linkedin_url": body.linkedin_url,
    }

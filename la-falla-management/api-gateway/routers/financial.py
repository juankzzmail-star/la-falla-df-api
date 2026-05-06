import os
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from typing import List, Optional

from ..db import get_db
from ..models import FinancialSnapshot, FinancialFlow

router = APIRouter(prefix="/financial", tags=["financial"])

DATABASE_URL = os.environ.get("DATABASE_URL", "")


class SnapshotOut(BaseModel):
    id: int
    fecha: date
    caja_operativa: float
    reservas_estrategicas: float
    credito_disponible: float
    gasto_mensual_promedio: float
    liquidez_total: float
    meses_respiracion: float

    class Config:
        from_attributes = True


class SnapshotCreate(BaseModel):
    fecha: date
    caja_operativa: float
    reservas_estrategicas: float
    credito_disponible: float
    gasto_mensual_promedio: float


class FlowOut(BaseModel):
    id: int
    tipo: str
    descripcion: str
    monto: float
    horizonte_dias: Optional[int]
    frecuencia: Optional[str]
    fecha_estimada: Optional[date]
    origen: Optional[str]

    class Config:
        from_attributes = True


class FlowCreate(BaseModel):
    tipo: str
    descripcion: str
    monto: float
    horizonte_dias: Optional[int] = None
    frecuencia: Optional[str] = None
    fecha_estimada: Optional[date] = None
    origen: Optional[str] = None


@router.get("/snapshots", response_model=List[SnapshotOut])
def list_snapshots(limit: int = 12, db: Session = Depends(get_db)):
    rows = (
        db.query(FinancialSnapshot)
        .order_by(FinancialSnapshot.fecha.desc())
        .limit(limit)
        .all()
    )
    return rows


@router.post("/snapshots", response_model=SnapshotOut, status_code=201)
def create_snapshot(body: SnapshotCreate, db: Session = Depends(get_db)):
    total = body.caja_operativa + body.reservas_estrategicas + body.credito_disponible
    respiracion = total / body.gasto_mensual_promedio if body.gasto_mensual_promedio else 0
    s = FinancialSnapshot(**body.model_dump(), liquidez_total=total, meses_respiracion=respiracion)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


@router.get("/flows", response_model=List[FlowOut])
def list_flows(tipo: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(FinancialFlow)
    if tipo:
        q = q.filter(FinancialFlow.tipo == tipo)
    return q.order_by(FinancialFlow.fecha_estimada).all()


@router.post("/flows", response_model=FlowOut, status_code=201)
def create_flow(body: FlowCreate, db: Session = Depends(get_db)):
    f = FinancialFlow(**body.model_dump())
    db.add(f)
    db.commit()
    db.refresh(f)
    return f


# ─── Google Sheets sync ───────────────────────────────────────────────────────

class SheetSyncPayload(BaseModel):
    """Payload que envía n8n después de leer el Google Sheet de Quinaya."""
    fuente: str = "Google Sheets"         # nombre descriptivo de la hoja
    spreadsheet_id: Optional[str] = None  # ID del spreadsheet (para tracking)
    snapshot: Optional[SnapshotCreate] = None
    flows: Optional[List[FlowCreate]] = []


@router.post("/sync-sheets", status_code=200)
def sync_from_sheets(body: SheetSyncPayload):
    """
    Recibe datos financieros extraídos de Google Sheets por n8n (WF-GF-01).
    Crea snapshot y flujos. Registra la fuente en financial_data_sources.
    """
    if not DATABASE_URL:
        raise HTTPException(503, "DATABASE_URL no configurada.")

    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    synced_at = datetime.now(timezone.utc)
    snapshot_id = None
    flows_created = 0

    with engine.begin() as conn:
        # 1. Upsert en financial_data_sources
        conn.execute(text("""
            INSERT INTO financial_data_sources
                (fuente, spreadsheet_id, ultima_sincronizacion, estado)
            VALUES (:fuente, :sid, :ts, 'ok')
            ON CONFLICT (fuente) DO UPDATE SET
                ultima_sincronizacion = EXCLUDED.ultima_sincronizacion,
                spreadsheet_id = COALESCE(EXCLUDED.spreadsheet_id, financial_data_sources.spreadsheet_id),
                estado = 'ok'
        """), {
            "fuente": body.fuente,
            "sid": body.spreadsheet_id,
            "ts": synced_at,
        })

        # 2. Crear snapshot si viene en el payload
        if body.snapshot:
            s = body.snapshot
            total = s.caja_operativa + s.reservas_estrategicas + s.credito_disponible
            meses = round(total / s.gasto_mensual_promedio, 2) if s.gasto_mensual_promedio else 0
            row = conn.execute(text("""
                INSERT INTO financial_snapshots
                    (fecha, caja_operativa, reservas_estrategicas, credito_disponible,
                     gasto_mensual_promedio, meses_respiracion)
                VALUES (:fecha, :caja, :res, :cred, :gasto, :meses)
                ON CONFLICT (fecha) DO UPDATE SET
                    caja_operativa = EXCLUDED.caja_operativa,
                    reservas_estrategicas = EXCLUDED.reservas_estrategicas,
                    credito_disponible = EXCLUDED.credito_disponible,
                    gasto_mensual_promedio = EXCLUDED.gasto_mensual_promedio,
                    meses_respiracion = EXCLUDED.meses_respiracion
                RETURNING id
            """), {
                "fecha": s.fecha, "caja": s.caja_operativa,
                "res": s.reservas_estrategicas, "cred": s.credito_disponible,
                "gasto": s.gasto_mensual_promedio, "meses": meses,
            }).fetchone()
            if row:
                snapshot_id = row[0]

        # 3. Crear flujos si vienen en el payload
        for flow in (body.flows or []):
            conn.execute(text("""
                INSERT INTO financial_flows
                    (tipo, descripcion, monto, horizonte_dias, frecuencia, fecha_estimada, origen)
                VALUES (:tipo, :desc, :monto, :hdias, :freq, :fecha, :origen)
            """), {
                "tipo": flow.tipo, "desc": flow.descripcion, "monto": flow.monto,
                "hdias": flow.horizonte_dias, "freq": flow.frecuencia,
                "fecha": flow.fecha_estimada, "origen": flow.origen or body.fuente,
            })
            flows_created += 1

    return {
        "ok": True,
        "fuente": body.fuente,
        "synced_at": synced_at.isoformat(),
        "snapshot_id": snapshot_id,
        "flows_created": flows_created,
    }


@router.get("/data-sources")
def list_data_sources():
    """Lista las fuentes financieras configuradas y su último sync."""
    if not DATABASE_URL:
        raise HTTPException(503, "DATABASE_URL no configurada.")
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT fuente, spreadsheet_id, ultima_sincronizacion, estado
            FROM financial_data_sources
            ORDER BY ultima_sincronizacion DESC NULLS LAST
        """)).fetchall()
    return {"sources": [dict(r._mapping) for r in rows]}

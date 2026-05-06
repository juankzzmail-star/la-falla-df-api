from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime
import os, json

from ..db import get_db
from ..models import Risk, EdtNode

router = APIRouter(prefix="/risks", tags=["risks"])


class RiskOut(BaseModel):
    id: int
    descripcion: str
    area: str
    impacto: int
    probabilidad: int
    nivel_riesgo: int
    estado_mitigacion: str
    responsable: Optional[str]
    origen: str
    fecha_identificacion: Optional[datetime]
    fecha_revision: Optional[datetime]

    class Config:
        from_attributes = True


class RiskCreate(BaseModel):
    descripcion: str
    area: str
    impacto: int
    probabilidad: int
    estado_mitigacion: str = "monitoreado"
    responsable: Optional[str] = None
    origen: str = "ceo_manual"


class RiskPatch(BaseModel):
    impacto: Optional[int] = None
    probabilidad: Optional[int] = None
    estado_mitigacion: Optional[str] = None
    responsable: Optional[str] = None


@router.get("", response_model=List[RiskOut])
def list_risks(area: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(Risk)
    if area:
        q = q.filter(Risk.area == area)
    return q.order_by(Risk.nivel_riesgo.desc()).all()


@router.post("", response_model=RiskOut, status_code=201)
def create_risk(body: RiskCreate, db: Session = Depends(get_db)):
    data = body.model_dump()
    data['nivel_riesgo'] = data['impacto'] * data['probabilidad']
    r = Risk(**data)
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


@router.patch("/{risk_id}", response_model=RiskOut)
def update_risk(risk_id: int, body: RiskPatch, db: Session = Depends(get_db)):
    r = db.get(Risk, risk_id)
    if not r:
        raise HTTPException(404, "Riesgo no encontrado")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(r, k, v)
    r.nivel_riesgo = r.impacto * r.probabilidad
    db.commit()
    db.refresh(r)
    return r


@router.delete("/{risk_id}", status_code=204)
def delete_risk(risk_id: int, db: Session = Depends(get_db)):
    r = db.get(Risk, risk_id)
    if not r:
        raise HTTPException(404, "Riesgo no encontrado")
    db.delete(r)
    db.commit()


# ─── Project-scoped risks (Opción 1 + 3) ────────────────────────

class RiskValidateRequest(BaseModel):
    descripcion: str
    estrategia: str
    probabilidad: int
    impacto: int


@router.get("/projects/{project_id}/risks")
def list_project_risks(project_id: int, db: Session = Depends(get_db)):
    """Riesgos específicos del proyecto + sugerencias auto-detectadas."""
    activos = db.query(Risk).filter(Risk.project_id == project_id).order_by(Risk.nivel_riesgo.desc()).all()
    sugeridos = _auto_detect_risks(project_id, db)
    return {"sugeridos": sugeridos, "activos": [RiskOut.model_validate(r) for r in activos]}


@router.post("/projects/{project_id}/risks/validate")
async def validate_risk_gentil(project_id: int, body: RiskValidateRequest, db: Session = Depends(get_db)):
    """Valida riesgo con Gentil + RAG (si corpus disponible)."""
    try:
        from anthropic import Anthropic
    except ImportError:
        raise HTTPException(500, "Anthropic SDK no disponible")

    nr = body.probabilidad * body.impacto
    nivel = "crítico" if nr >= 15 else "alto" if nr >= 10 else "medio" if nr >= 6 else "bajo"

    # RAG context — graceful: funciona sin corpus
    context = ""
    try:
        rows = db.execute(text(
            "SELECT content FROM document_chunks WHERE document_type='riesgo' "
            "ORDER BY created_at DESC LIMIT 3"
        )).fetchall()
        if rows:
            context = "\n\n".join([r[0] for r in rows])
    except Exception:
        pass

    prompt = f"""Eres Gentil, asesor estratégico de La Falla DF. Evalúa este riesgo y da retroalimentación ejecutiva en 2-3 oraciones en español colombiano casual pero profesional.

Riesgo: {body.descripcion}
Estrategia propuesta: {body.estrategia}
Nivel: {nr} pts ({nivel}) — Probabilidad {body.probabilidad}/5 × Impacto {body.impacto}/5
{f'Contexto histórico:{chr(10)}{context}' if context else 'Sin contexto histórico disponible.'}

Responde directamente. Evalúa si la estrategia es apropiada para este nivel."""

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise HTTPException(500, "ANTHROPIC_API_KEY not set")

    try:
        client = Anthropic(api_key=api_key)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}]
        )
        return {"mensaje": msg.content[0].text, "nivel": nivel, "nr": nr}
    except Exception as e:
        raise HTTPException(500, f"Error calling Anthropic: {str(e)}")


def _auto_detect_risks(project_id: int, db: Session) -> List[dict]:
    """Auto-detecta riesgos sugeridos desde EDT nodes."""
    nodes = db.query(EdtNode).filter(EdtNode.project_id == project_id).all()
    sugeridos = []
    for n in nodes:
        if n.alerta and "bloqueado" in (n.alerta or "").lower():
            sugeridos.append({
                "id": f"RS-{n.codigo}",
                "descripcion": f"Paquete bloqueado: {n.nombre}",
                "probabilidad": 4,
                "impacto": 5,
                "estrategia_sugerida": "Evitar",
                "paquete": n.codigo,
                "origen": "openclaw_auto"
            })
    return sugeridos

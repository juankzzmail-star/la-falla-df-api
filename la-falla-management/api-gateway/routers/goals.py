import os
import json
import base64
from typing import List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from openai import OpenAI
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import StrategicGoal
from ..schemas import GoalCreate, GoalOut, GoalUpdate, DocumentIngestionRequest, DocumentIngestionResponse

router = APIRouter(prefix="/goals", tags=["goals"])

OPENAI_API_KEY  = os.environ.get("OPENAI_API_KEY", "")
FIRECRAWL_API_KEY = os.environ.get("FIRECRAWL_API_KEY", "")

STRATEGY_EXTRACTION_PROMPT = """
Eres un asistente experto en gestión estratégica empresarial.
Dado el texto de un documento de estrategia, extrae TODAS las metas estratégicas.

Responde ÚNICAMENTE con un objeto JSON con esta estructura exacta:
{
  "metas": [
    {
      "codigo": "string corto único (ej: COM-2030-01)",
      "titulo": "string: nombre claro de la meta",
      "area": "string: exactamente uno de Comercial | Proyectos | Investigacion | Audiovisual",
      "fecha_fin_meta": "string ISO 8601 (ej: 2030-12-31) o null",
      "peso_porcentaje": number entre 0 y 100 o null
    }
  ]
}

Reglas:
- Extrae metas explícitas e implícitas
- Si el área no está clara, infiere del contexto
- Si no hay fecha, usa null
- Los códigos deben ser únicos y descriptivos
""".strip()


@router.get("", response_model=List[GoalOut])
def list_goals(
    area: Optional[str] = Query(None),
    estado: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(StrategicGoal)
    if area:
        q = q.filter(StrategicGoal.area == area)
    if estado:
        q = q.filter(StrategicGoal.estado == estado)
    return q.order_by(StrategicGoal.area, StrategicGoal.codigo).all()


@router.post("", response_model=GoalOut, status_code=201)
def create_goal(body: GoalCreate, db: Session = Depends(get_db)):
    if db.query(StrategicGoal).filter(StrategicGoal.codigo == body.codigo).first():
        raise HTTPException(409, f"Goal con codigo '{body.codigo}' ya existe")
    goal = StrategicGoal(**body.model_dump())
    db.add(goal)
    db.commit()
    db.refresh(goal)
    return goal


@router.get("/{goal_id}", response_model=GoalOut)
def get_goal(goal_id: int, db: Session = Depends(get_db)):
    goal = db.query(StrategicGoal).filter(StrategicGoal.id == goal_id).first()
    if not goal:
        raise HTTPException(404, f"Goal {goal_id} not found")
    return goal


@router.patch("/{goal_id}", response_model=GoalOut)
def update_goal(goal_id: int, body: GoalUpdate, db: Session = Depends(get_db)):
    goal = db.query(StrategicGoal).filter(StrategicGoal.id == goal_id).first()
    if not goal:
        raise HTTPException(404, f"Goal {goal_id} not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(goal, field, value)
    db.commit()
    db.refresh(goal)
    return goal


@router.delete("/{goal_id}")
def delete_goal(goal_id: int, db: Session = Depends(get_db)):
    goal = db.query(StrategicGoal).filter(StrategicGoal.id == goal_id).first()
    if not goal:
        raise HTTPException(404, f"Goal {goal_id} not found")
    db.delete(goal)
    db.commit()
    return {"deleted": True, "id": goal_id}


@router.post("/from-document", response_model=DocumentIngestionResponse)
async def ingest_from_document(body: DocumentIngestionRequest, db: Session = Depends(get_db)):
    # 1. Extract text from source
    text = ""

    if body.url:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.firecrawl.dev/v1/scrape",
                headers={"Authorization": f"Bearer {FIRECRAWL_API_KEY}"},
                json={"url": body.url, "formats": ["markdown"]},
            )
            if resp.status_code != 200:
                raise HTTPException(502, f"Firecrawl error {resp.status_code}: {resp.text[:300]}")
            data = resp.json()
            text = data.get("data", {}).get("markdown", "") or data.get("data", {}).get("content", "")

    elif body.content_text:
        text = body.content_text

    elif body.content_base64:
        text = base64.b64decode(body.content_base64).decode("utf-8", errors="ignore")

    if not text.strip():
        raise HTTPException(400, "No se pudo extraer texto del documento")

    # 2. OpenAI extracts structured goals
    client = OpenAI(api_key=OPENAI_API_KEY)
    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": STRATEGY_EXTRACTION_PROMPT},
            {"role": "user", "content": text[:15000]},
        ],
        response_format={"type": "json_object"},
        temperature=0,
    )
    goals_data = json.loads(completion.choices[0].message.content).get("metas", [])

    if not goals_data:
        raise HTTPException(422, "La IA no encontró metas estratégicas en el documento")

    # 3. Upsert in PostgreSQL
    created_count = 0
    updated_count = 0
    result_goals = []

    for g in goals_data:
        codigo = g.get("codigo", "").strip()
        if not codigo:
            continue
        existing = db.query(StrategicGoal).filter(StrategicGoal.codigo == codigo).first()
        if existing:
            for field, value in g.items():
                if value is not None and hasattr(existing, field):
                    setattr(existing, field, value)
            updated_count += 1
            result_goals.append(existing)
        else:
            goal = StrategicGoal(**{k: v for k, v in g.items() if hasattr(StrategicGoal, k)})
            db.add(goal)
            created_count += 1
            result_goals.append(goal)

    db.commit()
    for g in result_goals:
        db.refresh(g)

    return {"metas_creadas": created_count, "metas_actualizadas": updated_count, "goals": result_goals}

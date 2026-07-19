"""Completeness-interview endpoints (change completeness-interview).

After ingestion, Gentil interviews the CEO to enrich thin endpoints (Group 1) and close empty ones
(Group 2). This router exposes: generate the interview from the current completeness state, list
the persisted open questions, and submit a validated answer that writes the target field(s).

Mounted under /api with the X-API-Key guard (see main.py). All business logic lives in
routers/_interview.py (orchestrator + specialist registry)."""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..db import get_db
from . import _interview

router = APIRouter(prefix="/interview", tags=["interview"])


class InterviewQuestion(BaseModel):
    domain: str
    panel_id: Optional[str]
    grupo: str
    target_table: str
    campos_destino: List[str]
    pregunta: str


class InterviewOut(BaseModel):
    completitud_pct: int
    domains_total: int
    domains_ok: int
    # Per-domain detection status: "ok" | "waiting" | "empty" | "thin". "waiting" marks
    # cascade-derived domains with nothing to derive from — excluded from the numerator.
    domain_status: Dict[str, str]
    questions: List[InterviewQuestion]


class AnswerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    domain: str
    answer: Dict[str, Any]


class AnswerResponse(BaseModel):
    domain: str
    panel_id: Optional[str]
    registros_escritos: int
    estado: str


@router.get("", response_model=InterviewOut)
def get_interview(db: Session = Depends(get_db)):
    """Detect thin/empty domains and persist each pending question into dashboard_pending_panels."""
    result = _interview.build_interview(db)

    # Persist gap/enrich questions onto the panels they map to (idempotent per open panel).
    for q in result["questions"]:
        pid = q["panel_id"]
        if not pid:
            continue
        existing = db.execute(text(
            "SELECT id FROM dashboard_pending_panels WHERE panel_id = :pid AND resuelto_en IS NULL"
        ), {"pid": pid}).fetchone()
        if existing:
            db.execute(text("""
                UPDATE dashboard_pending_panels
                SET domain = :domain, grupo = :grupo, pregunta = :pregunta, campos_destino = :campos
                WHERE id = :id
            """), {"domain": q["domain"], "grupo": q["grupo"], "pregunta": q["pregunta"],
                   "campos": ",".join(q["campos_destino"]), "id": existing[0]})
        else:
            db.execute(text("""
                INSERT INTO dashboard_pending_panels
                    (panel_id, endpoint, razon, llena_con, domain, grupo, pregunta, campos_destino)
                VALUES (:pid, :endpoint, :razon, :llena_con, :domain, :grupo, :pregunta, :campos)
            """), {"pid": pid, "endpoint": f"interview:{q['domain']}",
                   "razon": f"{q['target_table']} {q['grupo']}", "llena_con": q["pregunta"],
                   "domain": q["domain"], "grupo": q["grupo"], "pregunta": q["pregunta"],
                   "campos": ",".join(q["campos_destino"])})
    db.commit()
    return result


@router.get("/questions")
def list_open_questions(db: Session = Depends(get_db)):
    """The persisted, still-open interview questions (those with a panel)."""
    rows = db.execute(text("""
        SELECT panel_id, domain, grupo, pregunta, campos_destino
        FROM dashboard_pending_panels
        WHERE resuelto_en IS NULL AND pregunta IS NOT NULL
        ORDER BY id
    """)).fetchall()
    return {"questions": [
        {"panel_id": r[0], "domain": r[1], "grupo": r[2], "pregunta": r[3],
         "campos_destino": (r[4] or "").split(",") if r[4] else []}
        for r in rows
    ]}


@router.post("/answer", response_model=AnswerResponse)
def submit_answer(body: AnswerRequest, db: Session = Depends(get_db)):
    """Validate the answer against the domain specialist; on pass write target field(s) and resolve
    the panel; on fail returns 422 and the question stays open."""
    return _interview.submit_answer(db, body.domain, body.answer)

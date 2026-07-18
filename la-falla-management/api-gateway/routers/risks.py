import asyncio
import logging
import os
import json
from datetime import datetime, timezone, date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..db import get_db, SessionLocal
from ..models import Risk, EdtNode
from . import _brain

router = APIRouter(prefix="/risks", tags=["risks"])
log = logging.getLogger(__name__)


# Gentil's deep brain persona for every strategic risk task (ISO 31000 / PMI, Colombian Spanish).
GENTIL_RISK_SYSTEM = (
    "Eres Gentil, el segundo cerebro estratégico del CEO de La Falla Destino Fílmico, una productora "
    "audiovisual y gestora cultural en Colombia. Evalúas riesgos con criterio ejecutivo bajo ISO 31000 / "
    "PMI (matriz Impacto×Probabilidad). Hablas español colombiano profesional y directo, sin relleno ni "
    "jerga vacía. Devuelves SIEMPRE JSON válido, sin markdown."
)


def _norm(s: str) -> str:
    """Normalize a risk description for dedup (lowercase, collapse whitespace)."""
    return " ".join((s or "").lower().split())


def _nivel_label(nr: int) -> str:
    return "crítico" if nr >= 16 else "alto" if nr >= 10 else "medio" if nr >= 6 else "bajo"


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
    # Gentil's strategic analysis (ddl_v14, DeepSeek V4 Pro)
    analisis_gentil: Optional[str] = None
    plan_mitigacion: Optional[List[str]] = None
    fecha_analisis: Optional[datetime] = None

    @field_validator("plan_mitigacion", mode="before")
    @classmethod
    def _parse_plan(cls, v):
        """The column stores a JSON array as text; expose it as a real list. Tolerates a plain
        newline/bullet list too, so an older free-text value still renders."""
        if v is None or isinstance(v, list):
            return v
        if isinstance(v, str):
            s = v.strip()
            if not s:
                return None
            try:
                d = json.loads(s)
                return d if isinstance(d, list) else [str(d)]
            except json.JSONDecodeError:
                return [ln.strip("-•* ").strip() for ln in s.splitlines() if ln.strip()]
        return None

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


# ─── Gentil deep-brain analysis (DeepSeek V4 Pro) ───────────────

def _analyze_prompt(r: Risk) -> str:
    nr = (r.impacto or 0) * (r.probabilidad or 0)
    return f"""Analiza este riesgo del registro estratégico de La Falla y devuelve JSON.

Riesgo: {r.descripcion}
Área: {r.area}
Impacto: {r.impacto}/5 · Probabilidad: {r.probabilidad}/5 · Nivel I×P: {nr}/25 ({_nivel_label(nr)})
Estado de mitigación actual: {r.estado_mitigacion}
Responsable: {r.responsable or 'sin asignar'}

Devuelve EXACTAMENTE este JSON:
{{
  "analisis": "2-4 oraciones: por qué este riesgo importa AHORA, qué lo agrava y qué señales vigilar. Concreto y específico a La Falla, no genérico.",
  "plan_mitigacion": ["acción concreta 1", "acción concreta 2", "acción concreta 3"]
}}
El plan: 2-4 acciones ejecutables esta semana, cada una empieza con un verbo. SOLO JSON, sin markdown."""


def _apply_analysis(r: Risk, data: dict) -> None:
    """Persist a {analisis, plan_mitigacion[]} payload onto a Risk row."""
    analisis = (data.get("analisis") or data.get("analisis_gentil") or "").strip()
    plan = data.get("plan_mitigacion") or data.get("plan") or []
    if isinstance(plan, str):
        plan = [plan]
    r.analisis_gentil = analisis or None
    r.plan_mitigacion = json.dumps([str(p).strip() for p in plan if str(p).strip()], ensure_ascii=False)
    r.fecha_analisis = datetime.now(timezone.utc)


@router.post("/{risk_id}/analyze", response_model=RiskOut)
def analyze_risk(risk_id: int, db: Session = Depends(get_db)):
    """Gentil (DeepSeek V4 Pro) writes the executive analysis + mitigation plan for one risk.
    Fills the 'Heartbeat Matutino' placeholder the Risk Map modal has always promised."""
    r = db.get(Risk, risk_id)
    if not r:
        raise HTTPException(404, "Riesgo no encontrado")
    raw = _brain.deep_analysis(GENTIL_RISK_SYSTEM, _analyze_prompt(r), max_tokens=900)
    try:
        data = _brain.parse_json(raw)
    except ValueError as e:
        raise HTTPException(502, f"DeepSeek devolvió un formato inesperado: {e}")
    if not isinstance(data, dict):
        raise HTTPException(502, "DeepSeek no devolvió un objeto de análisis.")
    _apply_analysis(r, data)
    db.commit()
    db.refresh(r)
    return r


# ─── Risk radar (autonomous): propose new risks from live signals ───

def _gather_signals(db: Session) -> dict:
    """Collect the live operational signals Gentil can already see, to ground risk proposals.
    Each query degrades to empty on a backend that lacks the table (e.g. sqlite in tests)."""
    out = {"bloqueados": [], "backlog": []}
    try:
        rows = db.execute(text(
            "SELECT nombre, codigo FROM edt_nodes "
            "WHERE LOWER(COALESCE(alerta,'')) LIKE '%bloqueado%' LIMIT 12"
        )).fetchall()
        out["bloqueados"] = [f"{(r[1] or '').strip()} {r[0]}".strip() for r in rows]
    except Exception:
        db.rollback()  # a missing table leaves the tx poisoned; clear it before the next probe
    try:
        rows = db.execute(text(
            "SELECT area, COUNT(*) AS c FROM tasks "
            "WHERE fecha_vencimiento < :t "
            "AND COALESCE(estado,'') NOT IN ('completada','completado','done','hecho') "
            "GROUP BY area ORDER BY c DESC"
        ), {"t": date.today()}).fetchall()
        out["backlog"] = [(r[0], int(r[1])) for r in rows]
    except Exception:
        db.rollback()
    out["has_any"] = bool(out["bloqueados"] or out["backlog"])
    return out


def _propose_prompt(signals: dict, existing: List[str]) -> str:
    bloq = "\n".join(f"  - Paquete bloqueado: {b}" for b in signals["bloqueados"]) or "  - (ninguno)"
    back = "\n".join(f"  - {a or 'Sin área'}: {c} tareas vencidas" for a, c in signals["backlog"]) or "  - (ninguno)"
    ya = "\n".join(f"  - {d}" for d in existing) or "  - (ninguno)"
    return f"""Eres el radar de riesgos de La Falla. A partir de las SEÑALES OPERATIVAS reales de hoy,
propón riesgos ESTRATÉGICOS nuevos que el CEO debería tener en su matriz I×P y que NO estén ya cubiertos.

SEÑALES — paquetes de trabajo bloqueados (EDT):
{bloq}

SEÑALES — backlog vencido por área:
{back}

RIESGOS YA REGISTRADOS (no los repitas, ni reformulados):
{ya}

Reglas:
- Propón entre 0 y 3 riesgos. Si las señales no justifican un riesgo estratégico nuevo, devuelve lista vacía.
- Cada riesgo es una AMENAZA discreta (no una tarea vencida suelta): algo que, de materializarse, daña un objetivo.
- impacto y probabilidad son enteros 1-5. Sé honesto: no infles.
- area ∈ {{Dirección Comercial, Dirección de Proyectos, Dirección de Industria, Dirección Audiovisual, Transversal}}.

Devuelve EXACTAMENTE este JSON:
{{
  "nuevos_riesgos": [
    {{
      "descripcion": "...",
      "area": "...",
      "impacto": 4,
      "probabilidad": 3,
      "estrategia": "Mitigar | Evitar | Transferir | Aceptar",
      "analisis": "2-3 oraciones: por qué es un riesgo y qué lo dispara",
      "plan_mitigacion": ["acción 1", "acción 2"]
    }}
  ]
}}
SOLO JSON, sin markdown."""


def _propose_risks(db: Session) -> int:
    """Ask the deep brain for new strategic risks grounded in live signals; insert the genuinely
    new ones (deduped against the register) with origen='gentil_auto'. Returns how many were added."""
    signals = _gather_signals(db)
    if not signals["has_any"]:
        return 0
    existing = [d for (d,) in db.query(Risk.descripcion).all()]
    try:
        raw = _brain.deep_analysis(GENTIL_RISK_SYSTEM, _propose_prompt(signals, existing), max_tokens=1400)
        data = _brain.parse_json(raw)
    except (ValueError, HTTPException) as e:
        log.warning("risk radar proposal failed: %s", e)
        return 0
    nuevos = data.get("nuevos_riesgos") if isinstance(data, dict) else data
    if not isinstance(nuevos, list):
        return 0
    existing_norm = {_norm(e) for e in existing}
    added = 0
    now = datetime.now(timezone.utc)
    for n in nuevos:
        if not isinstance(n, dict):
            continue
        desc = (n.get("descripcion") or "").strip()
        if not desc or _norm(desc) in existing_norm:
            continue
        imp = max(1, min(5, int(n.get("impacto") or 3)))
        prob = max(1, min(5, int(n.get("probabilidad") or 3)))
        plan = n.get("plan_mitigacion") or []
        r = Risk(
            descripcion=desc,
            area=(n.get("area") or "Transversal").strip(),
            impacto=imp,
            probabilidad=prob,
            nivel_riesgo=imp * prob,
            estado_mitigacion="monitoreado",
            origen="gentil_auto",
            estrategia=(n.get("estrategia") or "Mitigar").strip(),
            analisis_gentil=(n.get("analisis") or "").strip() or None,
            plan_mitigacion=json.dumps([str(p).strip() for p in plan if str(p).strip()], ensure_ascii=False),
            fecha_analisis=now,
        )
        db.add(r)
        existing_norm.add(_norm(desc))
        added += 1
    if added:
        db.commit()
    return added


@router.post("/heartbeat")
def risk_heartbeat(propose: bool = True, limit_analyze: int = 8, db: Session = Depends(get_db)):
    """Morning radar tick: (1) analyse risks that still lack Gentil's read, (2) optionally propose
    new strategic risks from live signals. Idempotent — only touches un-analysed risks. 503 if the
    deep brain is unconfigured (honest, no fabrication)."""
    if not _brain.available():
        raise HTTPException(503, "DEEPSEEK_API_KEY no configurada — el radar de riesgos de Gentil no está activo.")
    pendientes = (
        db.query(Risk)
        .filter((Risk.analisis_gentil.is_(None)) | (Risk.analisis_gentil == ""))
        .order_by(Risk.nivel_riesgo.desc())
        .limit(max(0, limit_analyze))
        .all()
    )
    analizados = 0
    for r in pendientes:
        try:
            raw = _brain.deep_analysis(GENTIL_RISK_SYSTEM, _analyze_prompt(r), max_tokens=900)
            _apply_analysis(r, _brain.parse_json(raw))
            analizados += 1
        except (ValueError, HTTPException) as e:
            log.warning("risk %s analysis failed: %s", r.id, e)
            continue
    if analizados:
        db.commit()
    propuestos = _propose_risks(db) if propose else 0
    return {"analizados": analizados, "propuestos": propuestos}


# ─── Background radar loop (autonomous, no n8n) ─────────────────

def radar_enabled() -> bool:
    """The autonomous loop runs only when explicitly enabled AND the deep brain is configured."""
    return os.environ.get("RISK_RADAR_ENABLED", "0") == "1" and _brain.available()


def _radar_tick() -> None:
    db = SessionLocal()
    try:
        pendientes = (
            db.query(Risk)
            .filter((Risk.analisis_gentil.is_(None)) | (Risk.analisis_gentil == ""))
            .order_by(Risk.nivel_riesgo.desc())
            .limit(8)
            .all()
        )
        analizados = 0
        for r in pendientes:
            try:
                raw = _brain.deep_analysis(GENTIL_RISK_SYSTEM, _analyze_prompt(r), max_tokens=900)
                _apply_analysis(r, _brain.parse_json(raw))
                analizados += 1
            except Exception as e:
                log.warning("radar: risk %s analysis failed: %s", r.id, e)
        if analizados:
            db.commit()
        propuestos = _propose_risks(db)
        log.info("risk radar tick: analizados=%s propuestos=%s", analizados, propuestos)
    finally:
        db.close()


async def risk_radar_loop():
    """First tick a few minutes after boot, then every RISK_RADAR_INTERVAL_MIN (default 12h). The
    blocking LLM work runs in a worker thread so it never stalls the event loop."""
    interval = int(os.environ.get("RISK_RADAR_INTERVAL_MIN", "720")) * 60
    await asyncio.sleep(180)
    while True:
        try:
            await asyncio.to_thread(_radar_tick)
        except Exception as e:
            log.warning("risk radar loop error: %s", e)
        await asyncio.sleep(interval)


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
    """Valida un riesgo con el cerebro profundo de Gentil (DeepSeek V4 Pro) + RAG si hay corpus.
    Análisis estratégico = brain profundo (antes Anthropic Haiku; ahora unificado en DeepSeek)."""
    nr = body.probabilidad * body.impacto
    nivel = _nivel_label(nr)

    # RAG context — graceful: funciona sin corpus
    context = ""
    try:
        rows = db.execute(text(
            "SELECT chunk_text FROM document_chunks WHERE source_type = 'riesgo' "
            "ORDER BY created_at DESC LIMIT 3"
        )).fetchall()
        if rows:
            context = "\n\n".join([r[0] for r in rows])
    except Exception:
        pass

    prompt = f"""Evalúa este riesgo y da retroalimentación ejecutiva en 2-3 oraciones, español colombiano profesional.

Riesgo: {body.descripcion}
Estrategia propuesta: {body.estrategia}
Nivel: {nr} pts ({nivel}) — Probabilidad {body.probabilidad}/5 × Impacto {body.impacto}/5
{f'Contexto histórico:{chr(10)}{context}' if context else 'Sin contexto histórico disponible.'}

Devuelve JSON: {{"mensaje": "tu evaluación (¿es apropiada la estrategia para este nivel?)"}}"""

    raw = _brain.deep_analysis(GENTIL_RISK_SYSTEM, prompt, max_tokens=300)
    try:
        data = _brain.parse_json(raw)
        mensaje = data.get("mensaje") if isinstance(data, dict) else str(data)
    except ValueError:
        mensaje = raw.strip()
    return {"mensaje": mensaje or "Sin evaluación.", "nivel": nivel, "nr": nr}


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

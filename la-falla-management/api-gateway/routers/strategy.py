import logging
import os
from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import DailySuggestion, StrategicGoal

router = APIRouter(prefix="/strategy", tags=["strategy"])
log = logging.getLogger(__name__)

# Analysis LLM is provider-configurable (change wire-document-rag): default OpenAI gpt-4o-mini, since
# GROQ_API_KEY is absent from the api-gerencia container. Set ANALYSIS_PROVIDER=groq (+ GROQ_API_KEY in
# Easypanel) to move analysis to free Groq with no code change.
ANALYSIS_PROVIDER = os.environ.get("ANALYSIS_PROVIDER", "openai").lower()
ANALYSIS_MODEL    = os.environ.get("ANALYSIS_MODEL", "gpt-4o-mini")
OPENAI_API_KEY    = os.environ.get("OPENAI_API_KEY", "")
GROQ_API_KEY      = os.environ.get("GROQ_API_KEY", "")
GROQ_BASE_URL     = "https://api.groq.com/openai/v1"

RESET_PASSWORD = os.environ.get("STRATEGY_RESET_PASSWORD", "Lafalladf8178.")
DATABASE_URL   = os.environ.get("DATABASE_URL", "")

TABLES_TO_CLEAR = [
    "daily_suggestions",
    "risks",
    "financial_flows",
    "financial_snapshots",
    "roadmap_milestones",
    "roadmap_cycles",
    "roadmap_versions",
    "deliverables",
    "tasks",
    "plan_quarterly_goals",
    "plans",
    "edt_nodes",
    "projects",
    "strategic_goals",
    "inbox_items",
    "executive_feed_cache",
    "dashboard_pending_panels",
    "area_kpi_config",
    "operational_assets",
    "stakeholder_health_log",
    "oportunidades",
    "document_chunks",
]



class ResetRequest(BaseModel):
    password: str


# change hub-drive-attach: ONE unified accept list for both upload surfaces (dashboard "Subir
# recurso" + Hub) — union of the two previous lists + common images; nothing regresses.
ALLOWED_RESOURCE_EXTS = {
    ".pdf", ".doc", ".docx", ".txt", ".md", ".xlsx", ".xls", ".csv", ".pptx",
    ".js", ".jsx", ".ts", ".tsx", ".py", ".json", ".sql", ".html", ".css",
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg",
}


class DriveIngestRequest(BaseModel):
    link: str
    intent: str = "obs"


class _DriveUpload:
    """Duck-typed stand-in for FastAPI's UploadFile — ingest_resource only uses filename,
    content_type and await read(), so Drive bytes ride the exact same pipeline (design D2)."""
    def __init__(self, filename: str, data: bytes):
        self.filename = filename
        self.content_type = ""
        self._data = data

    async def read(self) -> bytes:
        return self._data


@router.post("/ingest-drive")
async def ingest_drive(body: DriveIngestRequest, db: Session = Depends(get_db)):
    """Attach a Google Drive file into the standard ingestion pipeline (change hub-drive-attach).
    Read-only: the Drive original is never touched. Server-side guards: personal-data subtree
    refused (403), unified extension list enforced (400), honest 503 when the seam lacks creds."""
    from . import _gdrive
    name, data = _gdrive.fetch(body.link)
    ext = os.path.splitext(name)[1].lower()
    if ext not in ALLOWED_RESOURCE_EXTS:
        raise HTTPException(400, f"Tipo de archivo no soportado ({ext or 'sin extensión'}). "
                                 f"Aceptados: {', '.join(sorted(ALLOWED_RESOURCE_EXTS))}")
    return await ingest_resource(file=_DriveUpload(name, data), intent=body.intent,
                                 url="", filename_hint=name, db=db)


INTENT_LABELS = {
    "estrategia": "Cargar Estrategia (metas → planes → tareas)",
    "plan": "Modificar Plan Estratégico",
    "obs":  "Generar Observaciones e Ideas",
    "pend": "Lista de Pendientes",
}


def _analysis_client_model():
    """Return (OpenAI-compatible client, model) for obs/plan analysis using the configured provider.

    Default OpenAI gpt-4o-mini. If ANALYSIS_PROVIDER=groq, use Groq (needs GROQ_API_KEY). Falls back to
    whichever key is present. Raises HTTP 503 if no provider is configured (honest, no fabrication).
    """
    from openai import OpenAI
    if ANALYSIS_PROVIDER == "groq":
        if GROQ_API_KEY:
            model = ANALYSIS_MODEL if ANALYSIS_MODEL and ANALYSIS_MODEL != "gpt-4o-mini" else "llama-3.3-70b-versatile"
            return OpenAI(api_key=GROQ_API_KEY, base_url=GROQ_BASE_URL), model
        if OPENAI_API_KEY:
            return OpenAI(api_key=OPENAI_API_KEY), "gpt-4o-mini"
        raise HTTPException(503, "ANALYSIS_PROVIDER=groq pero falta GROQ_API_KEY (y no hay OPENAI_API_KEY).")
    # default: openai
    if OPENAI_API_KEY:
        return OpenAI(api_key=OPENAI_API_KEY), (ANALYSIS_MODEL or "gpt-4o-mini")
    if GROQ_API_KEY:
        return OpenAI(api_key=GROQ_API_KEY, base_url=GROQ_BASE_URL), "llama-3.3-70b-versatile"
    raise HTTPException(503, "No hay proveedor de análisis configurado (OPENAI_API_KEY o GROQ_API_KEY).")


def _extract_text(data: bytes, filename: str, content_type: str) -> str:
    """Thin wrapper over the shared multi-format extractor (change multi-format-ingestion, D5).

    All format logic (PDF, DOCX, XLSX/XLS, PPTX, CSV, images via vision, text) lives in
    routers/_extract.py and is shared with chat.py /extract-file so the two upload paths never drift.
    Returns "" when a resource can't be read, so the caller reports it honestly (no fabrication).
    """
    from ._extract import extract_resource
    return extract_resource(data, filename, content_type)


@router.post("/ingest-resource")
async def ingest_resource(
    file: UploadFile = File(None),
    intent: str = Form("obs"),
    url: str = Form(""),
    filename_hint: str = Form(""),
    db: Session = Depends(get_db),
):
    """
    Recibe un documento (o URL) con una intención (estrategia/plan/obs/pend).
    - estrategia → extrae metas → strategic_goals (cascade). Si el doc no trae metas, degrada
      a observación (sin error, sin inventar). Opt-in: solo este intent toca el esquema estratégico.
    - plan → genera observaciones Y las guarda como sugerencias de plan para revisión
    - obs  → genera observaciones de Gentil y las guarda en daily_suggestions
    - pend → guarda referencia en inbox_items sin procesar (sin LLM)
    """
    if intent not in INTENT_LABELS:
        raise HTTPException(400, f"Intent inválido. Opciones: {list(INTENT_LABELS)}")

    if not DATABASE_URL:
        raise HTTPException(503, "DATABASE_URL no configurada.")

    # ── Extraer texto del recurso ────────────────────────────────
    resource_text = ""
    resource_name = filename_hint or url or "recurso_sin_nombre"

    if file and file.filename:
        data = await file.read()
        resource_name = file.filename
        ctype = file.content_type or ""
        from . import _media
        if _media.is_media_file(file.filename, ctype):
            # Video/audio -> transcript (+ optional key frames), indexed in the RAG (change video-ingestion)
            resource_text = _media.media_to_text(data, file.filename, ctype)
        else:
            resource_text = _extract_text(data, file.filename, ctype)
    elif url:
        resource_name = filename_hint or url
        # pend only files the reference, so it skips any fetch.
        if intent != "pend":
            from . import _media
            from ._extract import extract_url
            # Video links -> captions/transcription via yt-dlp; other links -> Firecrawl (multi-format D4).
            resource_text = _media.media_url_to_text(url) if _media.is_video_url(url) else extract_url(url)

    if not resource_text and intent != "pend":
        raise HTTPException(400, "No se pudo leer el contenido del recurso (¿escaneado o protegido?). "
                                 "Guárdalo con intent=pend o súbelo en otro formato.")

    # ── ESTRATEGIA: documento → strategic_goals (cascade, change strategy-cascade) ──
    # Opt-in: solo este intent intenta extraer metas. Si no hay metas, degrada a observación
    # (sin error, sin fabricar). Usa el ORM (db) — testeable y no toca el engine crudo.
    if intent == "estrategia":
        from . import _cascade
        goals = _cascade.extract_goals_from_text(resource_text)  # raises 503 if no provider
        today = date.today()
        if goals:
            created = updated = 0
            for g in goals:
                codigo = (g.get("codigo") or "").strip()
                if not codigo:
                    continue
                fields = {k: v for k, v in g.items() if hasattr(StrategicGoal, k) and v is not None}
                existing = db.query(StrategicGoal).filter(StrategicGoal.codigo == codigo).first()
                if existing:
                    for k, v in fields.items():
                        setattr(existing, k, v)
                    updated += 1
                else:
                    db.add(StrategicGoal(**fields))
                    created += 1
            db.commit()
            chunks_indexed = 0
            try:
                from .rag import embed_and_store
                chunks_indexed = embed_and_store(
                    source_type="documento", source_name=resource_name,
                    doc_text=resource_text, metadata={"intent": "estrategia", "fecha": str(today)},
                )
            except Exception:
                pass
            return {
                "ok": True, "intent": "estrategia", "strategy_found": True,
                "metas_creadas": created, "metas_actualizadas": updated,
                "resource": resource_name, "chunks_indexed": chunks_indexed,
                "message": f"{created + updated} meta(s) de '{resource_name}' cargadas a la estrategia. "
                           f"Genera planes desde /api/plans/generate-from-goals.",
            }
        # Sin metas: degrada a observación — guarda una sugerencia y avisa, sin error ni invento.
        db.add(DailySuggestion(
            fecha=today, tag="GM",
            titulo=f"Recurso sin estrategia: {resource_name[:50]}",
            cuerpo="Este documento no traía metas estratégicas claras; lo guardé como observación del día.",
            estado="pendiente",
        ))
        db.commit()
        chunks_indexed = 0
        try:
            from .rag import embed_and_store
            chunks_indexed = embed_and_store(
                source_type="documento", source_name=resource_name,
                doc_text=resource_text, metadata={"intent": "estrategia", "fecha": str(today)},
            )
        except Exception:
            pass
        return {
            "ok": True, "intent": "estrategia", "strategy_found": False,
            "resource": resource_name, "chunks_indexed": chunks_indexed,
            "message": "El documento no traía metas estratégicas claras; lo guardé como "
                       "observación del día (no se crearon metas).",
        }

    engine = create_engine(DATABASE_URL, pool_pre_ping=True)

    # ── PEND: guardar en inbox_items y salir (sin LLM) ───────────
    if intent == "pend":
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO inbox_items (tipo, texto, origen, procesado)
                VALUES ('doc', :texto, :origen, false)
            """), {
                "texto": f"Recurso diferido: {resource_name}",
                "origen": "Subir Recurso",
            })
        return {"ok": True, "intent": "pend",
                "message": f"'{resource_name}' guardado en bandeja de entrada para revisión posterior."}

    # ── OBS / PLAN: analizar con el proveedor configurado ────────
    client, model = _analysis_client_model()  # raises 503 if none configured

    mode_instruction = (
        "Vas a MODIFICAR el plan estratégico. Identifica cambios concretos al roadmap 2026-2030: hitos a agregar, fechas a ajustar, prioridades a cambiar."
        if intent == "plan"
        else "Vas a GENERAR OBSERVACIONES sin modificar el plan. Identifica insights, oportunidades y alertas clave para el CEO."
    )

    prompt = f"""Eres Gentil, segundo cerebro estratégico del CEO de La Falla D.F. (corporación audiovisual, Eje Cafetero, Colombia. Visión 2030: agencia ACMI líder).

{mode_instruction}

DOCUMENTO RECIBIDO — '{resource_name}':
{resource_text[:10000]}

Responde en ESPAÑOL COLOMBIANO con:
1. **Resumen ejecutivo** (2-3 oraciones: qué es y por qué importa para La Falla)
2. **3 observaciones clave** (lo más relevante para el CEO hoy)
3. **Acción inmediata sugerida** (1 movimiento concreto que Clementino puede hacer hoy)

Sé directo, cálido y ejecutivo. NO inventes cifras: usa solo montos que aparezcan en el documento. Máximo 250 palabras."""

    try:
        resp = client.chat.completions.create(
            model=model,
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
        )
        analysis = resp.choices[0].message.content or ""
    except Exception as e:
        raise HTTPException(500, f"Error generando análisis: {str(e)[:200]}")

    # Anti-hallucination guard: flag any amount asserted in the analysis that is NOT grounded in the
    # source text (digit<->word / verbatim). Flagged (not silently trusted), never fabricated as fact.
    try:
        from ._guards import ungrounded_amounts
        bad = ungrounded_amounts(analysis, resource_text)
        if bad:
            analysis += ("\n\n⚠️ _Nota de control: estas cifras no se pudieron verificar contra el "
                         "documento y podrían ser imprecisas: " + ", ".join(bad[:5]) + "._")
    except Exception:
        pass  # the guard must never block the main flow

    # Guardar como sugerencia del día
    tag = "GM"
    titulo = f"Recurso: {resource_name[:60]}"
    today = date.today()

    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO daily_suggestions (fecha, tag, titulo, cuerpo, estado)
            VALUES (:fecha, :tag, :titulo, :cuerpo, 'pendiente')
        """), {"fecha": today, "tag": tag, "titulo": titulo, "cuerpo": analysis})

        # Si es plan, también guardar en inbox para revisión manual
        if intent == "plan":
            conn.execute(text("""
                INSERT INTO inbox_items (tipo, texto, origen, procesado)
                VALUES ('doc', :texto, :origen, false)
            """), {
                "texto": f"[MODIFICAR PLAN] {resource_name}: {analysis[:500]}",
                "origen": "Subir Recurso",
            })

    # Auto-index document text for RAG (best-effort — never fail the main flow).
    chunks_indexed = 0
    if resource_text:
        try:
            from .rag import embed_and_store
            chunks_indexed = embed_and_store(
                source_type="documento",
                source_name=resource_name,
                doc_text=resource_text,
                metadata={"intent": intent, "fecha": str(today)},
            )
        except Exception:
            pass  # RAG is optional — don't fail the main flow

    return {
        "ok": True,
        "intent": intent,
        "resource": resource_name,
        "analysis": analysis,
        "chunks_indexed": chunks_indexed,
        "message": f"Análisis de '{resource_name}' guardado como sugerencia del día.",
    }


@router.delete("/reset")
def reset_strategy(req: ResetRequest):
    if not RESET_PASSWORD:
        raise HTTPException(status_code=503, detail="STRATEGY_RESET_PASSWORD no configurada en el servidor.")
    if req.password != RESET_PASSWORD:
        raise HTTPException(status_code=403, detail="Contraseña incorrecta. Operación cancelada.")
    if not DATABASE_URL:
        raise HTTPException(status_code=503, detail="DATABASE_URL no configurada.")

    try:
        engine = create_engine(DATABASE_URL, pool_pre_ping=True)
        cleared = []
        reader_off = False
        with engine.connect() as conn:
            for table in TABLES_TO_CLEAR:
                try:
                    conn.execute(text(f"TRUNCATE TABLE {table} RESTART IDENTITY CASCADE"))
                    conn.commit()
                    cleared.append(table)
                except Exception:
                    try:
                        conn.execute(text(f"DELETE FROM {table}"))
                        conn.commit()
                        cleared.append(table)
                    except Exception:
                        pass  # tabla no existe aún
            # change reset-task-reader-switch: silence the Google Tasks READER so the cleared tasks
            # do not reappear on the next automatic import cycle. Google Tasks itself is untouched;
            # the switch lives in app_config, which is deliberately NOT in TABLES_TO_CLEAR.
            try:
                from .tasks import set_tasks_reader
                set_tasks_reader(conn, False)
                conn.commit()
                reader_off = True
            except Exception:
                conn.rollback()  # app_config missing — reset still succeeds, disclosed in payload
        msg = ("Estrategia reiniciada. El dashboard está en blanco y el lector de tareas quedó apagado."
               if reader_off else
               "Estrategia reiniciada. El dashboard está en blanco (no se pudo apagar el lector de tareas).")
        return {"ok": True, "cleared_tables": cleared, "tasks_reader_off": reader_off, "message": msg}
    except Exception as e:
        log.error("Error al reiniciar la estrategia: %s", str(e)[:200])
        raise HTTPException(status_code=500, detail="Error al reiniciar la estrategia.")


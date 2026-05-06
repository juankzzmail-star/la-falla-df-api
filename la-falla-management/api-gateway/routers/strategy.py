import io
import json
import os
from datetime import date

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import create_engine, text

router = APIRouter(prefix="/strategy", tags=["strategy"])

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_BASE_URL = "https://api.groq.com/openai/v1"

RESET_PASSWORD = os.environ.get("STRATEGY_RESET_PASSWORD", "")
DATABASE_URL   = os.environ.get("DATABASE_URL", "")

TABLES_TO_CLEAR = [
    "daily_suggestions",
    "risks",
    "financial_flows",
    "financial_snapshots",
    "roadmap_milestones",
    "roadmap_versions",
    "deliverables",
    "tasks",
    "plans",
    "projects",
    "strategic_goals",
    "inbox_items",
    "executive_feed_cache",
    "dashboard_pending_panels",
    "area_kpi_config",
    "operational_assets",
]


class ResetRequest(BaseModel):
    password: str


INTENT_LABELS = {
    "plan": "Modificar Plan Estratégico",
    "obs":  "Generar Observaciones e Ideas",
    "pend": "Lista de Pendientes",
}


def _extract_text(data: bytes, filename: str, content_type: str) -> str:
    if filename.lower().endswith(".pdf") or content_type.startswith("application/pdf"):
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(data))
            pages = []
            for i, page in enumerate(reader.pages[:30]):
                t = page.extract_text() or ""
                if t.strip():
                    pages.append(f"[Pág {i+1}]\n{t}")
            return "\n\n".join(pages)[:15000]
        except Exception:
            return ""
    if filename.lower().endswith(".docx"):
        try:
            import zipfile
            import xml.etree.ElementTree as ET
            z = zipfile.ZipFile(io.BytesIO(data))
            if "word/document.xml" in z.namelist():
                xml_data = z.read("word/document.xml").decode("utf-8", errors="ignore")
                root = ET.fromstring(xml_data)
                ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
                return " ".join(elem.text for elem in root.iter(f"{ns}t") if elem.text)[:15000]
        except Exception:
            return ""
    try:
        return data.decode("utf-8", errors="replace")[:15000]
    except Exception:
        return ""


@router.post("/ingest-resource")
async def ingest_resource(
    file: UploadFile = File(None),
    intent: str = Form("obs"),
    url: str = Form(""),
    filename_hint: str = Form(""),
):
    """
    Recibe un documento (o URL) con una intención (plan/obs/pend).
    - plan → genera observaciones Y las guarda como sugerencias de plan para revisión
    - obs  → genera observaciones de Gentil y las guarda en daily_suggestions
    - pend → guarda referencia en inbox_items sin procesar
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
        resource_text = _extract_text(data, file.filename, file.content_type or "")
    elif url:
        resource_text = f"[Enlace externo: {url}]"

    if not resource_text and intent != "pend":
        raise HTTPException(400, "No se pudo extraer contenido del recurso. Intenta con intent=pend para guardarlo como pendiente.")

    engine = create_engine(DATABASE_URL, pool_pre_ping=True)

    # ── PEND: guardar en inbox_items y salir ─────────────────────
    if intent == "pend":
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO inbox_items (tipo, texto, origen, procesado)
                VALUES ('doc', :texto, :origen, false)
            """), {
                "texto": f"Recurso diferido: {resource_name}",
                "origen": "Subir Recurso",
            })
        return {"ok": True, "intent": "pend", "message": f"'{resource_name}' guardado en bandeja de entrada para revisión posterior."}

    # ── OBS / PLAN: llamar a GROQ ────────────────────────────────
    if not GROQ_API_KEY:
        raise HTTPException(503, "GROQ_API_KEY no configurada. No se puede generar observaciones.")

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

Sé directo, cálido y ejecutivo. Máximo 250 palabras."""

    try:
        from openai import OpenAI
        client = OpenAI(api_key=GROQ_API_KEY, base_url=GROQ_BASE_URL)
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
        )
        analysis = resp.choices[0].message.content or ""
    except Exception as e:
        raise HTTPException(500, f"Error generando análisis: {str(e)[:200]}")

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

    # Auto-embed document text for RAG (async, non-blocking — silently skip on error)
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
        with engine.begin() as conn:
            for table in TABLES_TO_CLEAR:
                try:
                    conn.execute(text(f"DELETE FROM {table}"))
                    cleared.append(table)
                except Exception:
                    pass  # tabla no existe aún
        return {"ok": True, "cleared_tables": cleared, "message": "Estrategia reiniciada. El dashboard está en blanco."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al reiniciar: {str(e)}")

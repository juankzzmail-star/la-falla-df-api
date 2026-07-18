import json
import os
from typing import Optional

from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel, ConfigDict
from sqlalchemy import create_engine, text

router = APIRouter(prefix="/chat", tags=["chat"])

GROQ_API_KEY     = os.environ.get("GROQ_API_KEY", "")
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DATABASE_URL     = os.environ.get("DATABASE_URL", "")

GROQ_BASE_URL     = "https://api.groq.com/openai/v1"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
FIRECRAWL_URL     = os.environ.get("FIRECRAWL_URL", "http://72.61.73.132:3002")  # reachable default; old 10.0.1.132 is dead infra
FIRECRAWL_API_KEY = os.environ.get("FIRECRAWL_API_KEY", "")

MODEL_IDS = {
    "haiku":  ("groq",     "llama-3.3-70b-versatile"),
    "sonnet": ("groq",     "llama-3.3-70b-versatile"),
    "opus":   ("deepseek", "deepseek-chat"),
}

BASE_SYSTEM_PROMPT = """Eres Gentil, el segundo cerebro estratégico del CEO de La Falla D.F.

**Tu rol:** Asistir a Clementino (Sebastián Vargas Betancour) desde el Centro de Mando Empresarial. Eres directo, cálido y ejecutivo. Hablas en español colombiano natural. Máximo 3 párrafos cortos salvo que la pregunta lo exija.

**La Falla D.F.:**
- Corporación ESAL. Propósito: hacer del Eje Cafetero un destino fílmico latinoamericano.
- NIT 901592326-3 · Pereira, Colombia · Visión 2030: agencia líder en ACMI

**Equipo:**
| Alias | Nombre | C.C. | Rol |
|---|---|---|---|
| Clementino | Sebastián Vargas Betancour | 1.088.318.817 | CEO / Gerente General / Rep. Legal |
| Juan Carlos | Juan Carlos Martinez | 10.113.841 | Dir. Comercial y Financiero — flujos de caja, liquidez, cartera |
| Beto | Alberto Antonio Gutiérrez | 1.088.004.078 | Dir. de Proyectos — EDT, cronograma, entregas |
| Iván | Iván Marín Díaz | 79.905.424 | Dir. Audiovisual — producción, piezas, engagement |
| Quinaya | Viviana Franco Gutiérrez | 1.088.316.300 | Investigación / Apoyo Comercial |
| Camilo | Juan Camilo Betancur | 1.088.029.541 | Miembro fundador |

**Gobernanza:**
- Decisiones que afecten patrimonio o convenios → escalación inmediata
- Riesgo I×P ≥ 16 → escalación en < 2 horas
- Oportunidad > $100M → escalación inmediata

**Herramientas disponibles (SOLO ESTAS — nunca uses otras):**
n8n_list_workflows · n8n_get_failed_executions · n8n_create_workflow · n8n_activate_workflow
send_email · check_services · render_chart · propose_automation · web_search · query_stakeholders · scrape_url

NUNCA uses brave_search, google_search, browser, playwright, ni ninguna herramienta no listada.
Para buscar en internet usa web_search. Para leer el contenido completo de una URL específica usa scrape_url.
Para consultar contactos/aliados/clientes usa query_stakeholders.
Si un archivo no tiene contenido extraíble, informa al CEO claramente sin intentar buscarlo.
CRÍTICO — alucinación de archivos: Si recibes un aviso de que el archivo NO pudo leerse (error de extracción, pypdf no disponible, tipo no soportado), NO menciones ni inventes personas, datos, ni contenido. Solo reporta el error y pide al CEO que comparta la información directamente. El CEO escribe "estas personas" refiriéndose al archivo — si no lo leíste, no sabes quiénes son.

**Capacidades reales que tienes:**
- Puedes BUSCAR en internet en tiempo real (usa web_search)
- Puedes LEER el contenido completo de cualquier URL (usa scrape_url — funciona con páginas con JavaScript como LinkedIn)
- Puedes CREAR automatizaciones en n8n (usa n8n_create_workflow)
- Puedes VER el estado de las automatizaciones y detectar fallos (n8n_list_workflows, n8n_get_failed_executions)
- Puedes ENVIAR correos electrónicos reales (send_email)
- Puedes VERIFICAR el estado de todos los servicios (check_services)
- Puedes GENERAR gráficas interactivas con datos (render_chart)
- Puedes PROPONER automatizaciones con análisis de ROI (propose_automation)

**Estrategia para buscar personas en LinkedIn:**
1. Usa web_search con query "nombre apellido LinkedIn site:linkedin.com"
2. Toma la URL del resultado y úsala con scrape_url para leer el perfil completo
3. Si LinkedIn bloquea el scraping, reporta la URL encontrada al CEO para que la visite manualmente

Cuando el CEO pida algo que implique una acción real, HAZLA usando las herramientas disponibles. No describas lo que harías — hazlo.

**Slash commands disponibles:**
Si el mensaje es un comando slash (/analiza, /riesgos, /caja, /hitos, /status, /n8n, /busca, etc.), ejecuta el comando apropiado.
"""


# ─── Pydantic models ──────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    model: str = "haiku"
    history: list[dict] = []
    file_text: str = ""
    file_name: str = ""
    image_b64: str = ""
    image_type: str = "image/jpeg"
    sender_id: Optional[str] = None
    sender_name: Optional[str] = None
    sender_email: Optional[str] = None
    channel: Optional[str] = None


class ChatResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    response: str
    model_used: str
    tool_artifacts: list[dict] = []


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/extract-file")
async def extract_file(file: UploadFile = File(...)):
    """Extrae texto de múltiples formatos (PDF, DOCX, XLSX/XLS, PPTX, CSV, imágenes, texto) para que
    Gentil los lea en el chat. Usa el extractor compartido (change multi-format-ingestion, D5) — la
    misma lógica que persiste en el RAG vía 'Subir Recurso', así los dos caminos no divergen."""
    data = await file.read()
    filename = file.filename or "unknown"
    from ._extract import extract_resource
    text = extract_resource(data, filename, file.content_type or "", max_chars=60000)
    if not text.strip():
        return {"filename": filename, "text": "",
                "warning": "No se pudo extraer contenido (¿escaneado, binario o protegido?). "
                           "Súbelo en 'Subir Recurso' o comparte el contenido como texto."}
    return {"filename": filename, "text": text}


@router.post("/transcribe")
async def transcribe_audio(audio: UploadFile = File(...)):
    """Transcribe nota de voz/audio (Groq Whisper) — usa el helper compartido (change video-ingestion, D6),
    el mismo que persiste media en el RAG vía 'Subir Recurso', así no divergen."""
    data = await audio.read()
    from ._media import transcribe_bytes
    text = transcribe_bytes(data, audio.filename or "audio.webm", audio.content_type or "audio/webm")
    if not text.strip():
        return {"text": "", "warning": "No se pudo transcribir el audio (¿silencio, formato o tamaño?)."}
    return {"text": text}


def _get_director_info(req: ChatRequest) -> str:
    # Check by email first
    email = (req.sender_email or "").strip().lower()
    if email:
        if email in ["sebastian@lafalla.co", "gerencia@lafalla.co", "info@lafalla.co"]:
            return "Clementino (Sebastián Vargas Betancour - CEO / Gerente General)"
        elif email in ["viviana@lafalla.co", "investigaciones@lafalla.co"]:
            return "Quinaya Qumir (Viviana Franco Gutiérrez - Directora de Investigaciones)"
        elif email in ["alberto@lafalla.co", "proyectos@lafalla.co"]:
            return "Beto (Alberto Antonio Gutiérrez Carvajal - Director de Proyectos)"
        elif email in ["ivan@lafalla.co", "audiovisual@lafalla.co"]:
            return "Iván (Iván Marín Díaz - Director Audiovisual y Creativo)"
        elif email in ["juancarlos@lafalla.co", "comercial@lafalla.co"]:
            return "Juan Carlos (Juan Carlos Martínez Vélez - Director Comercial)"
        elif email in ["camilo@lafalla.co"]:
            return "Camilo (Juan Camilo Betancur - Fiscal)"

    # Check by sender_id (e.g. phone number or Telegram username)
    sender_id = (req.sender_id or "").strip().lower()
    if sender_id:
        if sender_id in ["573001234567"] or "clementino" in sender_id or "sebavargas" in sender_id:
            return "Clementino (Sebastián Vargas Betancour - CEO / Gerente General)"
        elif "quinaya" in sender_id:
            return "Quinaya Qumir (Viviana Franco Gutiérrez - Directora de Investigaciones)"
        elif "beto" in sender_id:
            return "Beto (Alberto Antonio Gutiérrez Carvajal - Director de Proyectos)"
        elif "ivan" in sender_id:
            return "Iván (Iván Marín Díaz - Director Audiovisual y Creativo)"
        elif "juanca" in sender_id or "juancarlos" in sender_id:
            return "Juan Carlos (Juan Carlos Martínez Vélez - Director Comercial)"
        elif "camilo" in sender_id:
            return "Camilo (Juan Camilo Betancur - Fiscal)"

    # Check by sender_name
    name = (req.sender_name or "").strip().lower()
    if name:
        if "clementino" in name or "sebastián" in name or "sebastian" in name:
            return "Clementino (Sebastián Vargas Betancour - CEO / Gerente General)"
        elif "quinaya" in name or "viviana" in name:
            return "Quinaya Qumir (Viviana Franco Gutiérrez - Directora de Investigaciones)"
        elif "beto" in name or "alberto" in name:
            return "Beto (Alberto Antonio Gutiérrez Carvajal - Director de Proyectos)"
        elif "ivan" in name or "iván" in name:
            return "Iván (Iván Marín Díaz - Director Audiovisual y Creativo)"
        elif "juan carlos" in name or "juanca" in name or "juan" in name:
            return "Juan Carlos (Juan Carlos Martínez Vélez - Director Comercial)"
        elif "camilo" in name:
            return "Camilo (Juan Camilo Betancur - Fiscal)"

    return ""


def _oportunidades_command(arg: str) -> str:
    """Comando /oportunidades — top-N convocatorias vigentes por ADN y cierre.

    Determinístico: lee la DB directamente (sin LLM, sin costo de tokens).
    Funciona aunque el gateway de OpenClaw esté caído.
    """
    if not DATABASE_URL:
        return "No puedo consultar oportunidades: la base de datos no está configurada."

    limit = 5
    for p in arg.split():
        if p.isdigit():
            limit = min(max(int(p), 1), 15)
            break

    try:
        engine = create_engine(DATABASE_URL, pool_pre_ping=True)
        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT nombre, entidad, programa, adn_score, prioridad, fecha_cierre,
                       url_convocatoria, estado_seguimiento
                FROM oportunidades
                WHERE estado_seguimiento <> 'descartada'
                  AND (fecha_cierre IS NULL OR fecha_cierre >= CURRENT_DATE)
                ORDER BY adn_score DESC NULLS LAST, fecha_cierre ASC NULLS LAST
                LIMIT :lim
            """), {"lim": limit}).fetchall()
    except Exception as e:
        return (
            "No pude leer las oportunidades (¿ya se aplicó el ddl_v6 en la base?). "
            f"Detalle: {str(e)[:160]}"
        )

    if not rows:
        return (
            "No hay oportunidades vigentes registradas todavía. Cuando el flujo "
            "WF-GM-06 sincronice desde Búsqueda de Oportunidades, aparecerán aquí."
        )

    lines = [f"**Top {len(rows)} oportunidades vigentes** (por ADN y cierre):", ""]
    for i, r in enumerate(rows, 1):
        cierre = f"cierra {r.fecha_cierre}" if r.fecha_cierre else "sin fecha de cierre"
        entidad = r.entidad or r.programa or "—"
        adn = f"ADN {r.adn_score}/100" if r.adn_score is not None else "ADN s/d"
        prio = f" · {r.prioridad}" if r.prioridad else ""
        lines.append(f"{i}. **{r.nombre}** — {entidad} · {adn}{prio} · {cierre}")
        if r.url_convocatoria:
            lines.append(f"   {r.url_convocatoria}")
    return "\n".join(lines)


def _is_complex_prompt(text: str, req_model: str) -> bool:
    """Detecta si la pregunta es capciosa, requiere razonamiento profundo o análisis estratégico (DeepSeek)."""
    if req_model in ["opus", "deepseek"]:
        return True
    keywords = [
        "capciosa", "analiza", "simula", "escenario", "matriz de riesgo",
        "runway", "estratégico", "profundo", "por qué", "qué pasa si", "financiero",
        "dilema", "tradeoff", "trade-off", "evalúa", "razonamiento", "complejo", "por que"
    ]
    t = (text or "").lower()
    return len(t) > 300 or any(k in t for k in keywords)


@router.post("", response_model=ChatResponse)
def chat_with_gentil(req: ChatRequest):
    import requests as requests_lib

    # ── Comando local determinístico: /oportunidades ────────────────────────────
    msg_stripped = (req.message or "").strip()
    if msg_stripped.lower().startswith("/oportunidades"):
        arg = msg_stripped[len("/oportunidades"):].strip()
        return ChatResponse(
            response=_oportunidades_command(arg),
            model_used="comando-local",
            tool_artifacts=[],
        )

    # 1. Silent Director Identification
    extra_messages = []
    director_info = _get_director_info(req)
    if director_info:
        extra_messages.append({
            "role": "system",
            "content": f"[IDENTIFICACIÓN SILENCIOSA: El interlocutor actual es {director_info}. Dirígete a él de forma personalizada con su alias o nombre correspondiente, cargando inmediatamente su contexto de director/rol en La Falla D.F.]"
        })

    # 1b. Document grounding (RAG)
    if (req.message or "").strip():
        try:
            from .rag import similarity_search
            hits = similarity_search(req.message, limit=4, source_type="documento")
            if hits:
                ctx = "\n\n".join(
                    f"[{h['source_name']} · frag {h['chunk_index']} · sim {h['similarity']}]\n{h['chunk_text']}"
                    for h in hits
                )
                extra_messages.append({
                    "role": "system",
                    "content": (
                        "CONTEXTO DE DOCUMENTOS DEL CEO (recuperado de los recursos subidos al Centro de "
                        "Mando). Úsalo solo si es pertinente, cita el documento, y NO afirmes datos que no "
                        "estén aquí:\n\n" + ctx[:6000]
                    ),
                })
        except Exception:
            pass

    # 2. Build history and messages list
    history = req.history[-20:] if req.history else []

    user_text = req.message
    if req.file_text:
        is_extraction_failure = (
            req.file_text.startswith("[Archivo: ")
            and req.file_name in req.file_text
        )
        if is_extraction_failure:
            raw_warning = req.file_text.split("] ", 1)[-1] if "] " in req.file_text else req.file_text
            user_text = (
                f"[AVISO DEL SISTEMA: El CEO adjuntó '{req.file_name}' pero su contenido NO pudo leerse. "
                f"Error: {raw_warning[:300]}. "
                f"NO menciones personas ni datos del archivo — no lo leíste. "
                f"Informa al CEO del error y pídele que liste las personas directamente en el chat o use 'Subir Recurso'.]\n\n"
                + (req.message or "")
            )
        else:
            prefix = f"[Archivo adjunto: {req.file_name}]\n```\n{req.file_text[:50000]}\n```\n\n"
            user_text = prefix + (req.message or "Analiza este archivo y dame los puntos clave para el Centro de Mando.")

    if req.image_b64:
        user_content = [
            {"type": "text", "text": user_text or "¿Qué ves en esta imagen? Descríbela en el contexto del Centro de Mando de La Falla D.F."},
            {"type": "image_url", "image_url": {"url": f"data:{req.image_type};base64,{req.image_b64}"}}
        ]
    else:
        user_content = user_text

    user_message = {"role": "user", "content": user_content}
    messages = extra_messages + history + [user_message]

    # 3. Dynamic Model Selection: DeepSeek for complex/capciosa, Groq/Llama-3.3 for speed
    is_deepseek = DEEPSEEK_API_KEY and _is_complex_prompt(req.message, req.model)

    if is_deepseek:
        # Route to DeepSeek API
        headers = {
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "deepseek-chat",
            "messages": [{"role": "system", "content": BASE_SYSTEM_PROMPT}] + messages,
            "temperature": 0.3
        }
        try:
            r = requests_lib.post("https://api.deepseek.com/chat/completions", headers=headers, json=payload, timeout=60)
            if r.status_code == 200:
                response_data = r.json()
                final_text = response_data["choices"][0]["message"]["content"] or ""
                return ChatResponse(
                    response=final_text,
                    model_used="deepseek/deepseek-chat (razonamiento profundo)",
                    tool_artifacts=[]
                )
        except Exception as e:
            pass  # Fallback to Groq / OpenClaw gateway if DeepSeek times out

    # Default Route: Groq / OpenClaw Gateway (Llama-3.3-70B ultra-fast)
    OPENCLAW_URL = os.environ.get("OPENCLAW_URL", "http://172.18.0.1:18789/v1/chat/completions")
    OPENCLAW_TOKEN = os.environ.get("OPENCLAW_TOKEN", "")

    def _parse_response(response_data: dict, model_label: str) -> ChatResponse:
        final_text = response_data["choices"][0]["message"]["content"] or ""
        tool_artifacts = []
        import re
        code_blocks = re.findall(r'```(?:json)?\s*(\{.*?\})\s*```', final_text, re.DOTALL)
        for block in code_blocks:
            try:
                data_obj = json.loads(block.strip())
                if isinstance(data_obj, dict) and ("__chart__" in data_obj or "__proposal__" in data_obj):
                    tool_artifacts.append(data_obj)
            except Exception:
                pass
        return ChatResponse(response=final_text, model_used=model_label, tool_artifacts=tool_artifacts)

    # ── Intento 1: OpenClaw gateway (timeout corto para no bloquear UI) ──────────
    try:
        r = requests_lib.post(
            OPENCLAW_URL,
            headers={"Authorization": f"Bearer {OPENCLAW_TOKEN}", "Content-Type": "application/json"},
            json={"model": "openclaw", "messages": messages},
            timeout=15  # reducido de 120s → 15s para no bloquear la UI
        )
        if r.status_code == 200:
            return _parse_response(r.json(), "groq/llama-3.3-70b-versatile (OpenClaw)")
    except Exception:
        pass  # Silently fall through to Groq direct

    # ── Intento 2: Groq directo (fallback confiable) ─────────────────────────────
    if GROQ_API_KEY:
        try:
            groq_payload = {
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "system", "content": BASE_SYSTEM_PROMPT}] + messages,
                "temperature": 0.4,
                "max_tokens": 1024
            }
            r = requests_lib.post(
                f"{GROQ_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
                json=groq_payload,
                timeout=30
            )
            if r.status_code == 200:
                return _parse_response(r.json(), "groq/llama-3.3-70b-versatile (directo)")
            else:
                raise HTTPException(status_code=r.status_code, detail=f"Groq API error: {r.text[:300]}")
        except HTTPException:
            raise
        except Exception as groq_err:
            raise HTTPException(status_code=503, detail=f"Groq directo falló: {str(groq_err)[:200]}")

    raise HTTPException(status_code=503, detail="Sin gateway disponible: OpenClaw caído y GROQ_API_KEY no configurada.")


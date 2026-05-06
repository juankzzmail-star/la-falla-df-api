"""
EDT Onboarding Router — Conecta wizard frontend con Gentil

Flujo:
1. POST /api/edt-onboarding/ingest    → recibe project + docs, extrae con LLM
2. POST /api/edt-onboarding/questions → genera preguntas según gaps detectados
3. POST /api/edt-onboarding/synthesize → produce EDT final + persiste en DB

El LLM puede ser:
- DeepSeek V4 Pro (Nvidia NIM) — primario
- Groq Llama 3.3 70B — fallback rápido
- Modo MOCK (sin LLM) — para pruebas locales sin red

Sin dependencia de Anthropic (sin créditos disponibles).
"""

import os
import json
import time
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel
import requests as _req

router = APIRouter(prefix="/api/edt-onboarding", tags=["edt-onboarding"])

# ============================================================================
# MODELS
# ============================================================================

class ProjectInfo(BaseModel):
    name: str
    type: str   # audiovisual | investigacion | comercial | estrategico | mixto
    area: str   # GP | GA | GI | GCF


class IngestRequest(BaseModel):
    project: ProjectInfo
    documents: List[Dict[str, str]]  # [{name, content}]


class IngestResponse(BaseModel):
    extracted: Dict[str, Any]   # campos extraídos automáticamente
    confidence: Dict[str, float]  # confianza por campo
    gaps: List[str]               # qué falta para preguntar


class QuestionsRequest(BaseModel):
    project: ProjectInfo
    extracted: Dict[str, Any]
    gaps: List[str]


class QuestionsResponse(BaseModel):
    questions: List[Dict[str, str]]  # [{key, question, why_asking}]


class SynthesizeRequest(BaseModel):
    project: ProjectInfo
    extracted: Dict[str, Any]
    answers: Dict[str, Any]


class SynthesizeResponse(BaseModel):
    project_id: int
    edt_nodes: List[Dict[str, Any]]
    risks: List[Dict[str, Any]]
    milestones: List[Dict[str, Any]]
    pending_panels: List[str]
    summary: Dict[str, Any]


# ============================================================================
# LLM ADAPTER (DeepSeek / Claude / Mock)
# ============================================================================

LLM_MODE = os.environ.get("EDT_LLM_MODE", "mock")  # mock | groq | deepseek | auto

def call_llm(system: str, prompt: str, max_tokens: int = 2000) -> str:
    """Llama al LLM según el modo configurado.

    Modos disponibles:
    - mock     : sin red, respuestas pre-cocinadas (instantaneo, para tests)
    - groq     : Llama 3.3 70B en Groq (~1-7s, gratis con free tier 12K TPM)
    - deepseek : DeepSeek V3 chat directo via api.deepseek.com (~10-35s, pagado)
    - auto     : Groq primario -> DeepSeek fallback automatico (RECOMENDADO)

    Sin Anthropic, sin OpenAI — cascada simplificada de 2 niveles.
    """
    if LLM_MODE == "mock":
        return _mock_llm_response(prompt)

    if LLM_MODE == "groq":
        return _call_groq(system, prompt, max_tokens)

    if LLM_MODE == "deepseek":
        return _call_deepseek(system, prompt, max_tokens)

    if LLM_MODE == "auto":
        # Cascada simplificada: Groq (rapido + gratis) -> DeepSeek (lento + pagado)
        for fn, name in [(_call_groq, "Groq"), (_call_deepseek, "DeepSeek")]:
            try:
                return fn(system, prompt, max_tokens)
            except Exception as e:
                print(f"[EDT-Onboarding] {name} fallo: {e}, intentando siguiente...")
                continue
        raise HTTPException(503, "Todos los LLMs fallaron — revisar GROQ_API_KEY y DEEPSEEK_API_KEY")

    raise ValueError(f"LLM_MODE desconocido: {LLM_MODE}")


def _mock_llm_response(prompt: str) -> str:
    """
    Respuesta mockeada para pruebas sin API key.
    Detecta tipo de prompt por palabras clave y devuelve JSON estructurado.

    PRIORIDAD del matching (mas especifico primero):
    1. "GAPS DETECTADOS" -> es questions endpoint
    2. "DOCUMENTOS A ANALIZAR" -> es ingest endpoint
    3. fallback a heuristicas anteriores
    """
    pl = prompt.lower()

    # Match mas especifico primero — questions endpoint
    if "gaps detectados" in pl or "genera 3-7 preguntas" in pl:
        return json.dumps({
            "questions": [
                {
                    "key": "guionista",
                    "question": "Vi en los documentos que aún no han confirmado guionista. Iván sugirió a Laura M. (8M COP). ¿Quieres que te lo dé por confirmado o sigues evaluando?",
                    "why_asking": "Sin guionista confirmado, no puedo asignar la tarea 1.0.5 ni calcular ruta crítica completa."
                },
                {
                    "key": "editor",
                    "question": "El editor de la S01 (Carlos M.) no está disponible. Beto marcó esto como riesgo alto. ¿Tienes ya 1-2 candidatos o necesito sugerirte algunos del directorio?",
                    "why_asking": "El editor entra desde el día 1 de post (16 mayo). Sin nombre, todo el bloque 3.x queda sin responsable."
                },
                {
                    "key": "imprevistos",
                    "question": "Quinaya pidió subir el rubro de imprevistos del 3.5% al 7%. Beto propuso recortar de distribución. ¿Aplico ese cambio al presupuesto o prefieres revisarlo en la próxima reunión?",
                    "why_asking": "Esto afecta el panel de salud financiera del proyecto y la línea base de costo."
                },
                {
                    "key": "patrocinio_caficultor",
                    "question": "El patrocinio del caficultor regional (14M, 15% del total) está en negociación. ¿Lo cuento como confirmado para el escenario base o como contingente?",
                    "why_asking": "Si lo cuento contingente, el escenario base baja a 71M y necesito ajustar fases proporcionalmente."
                },
                {
                    "key": "metricas_exito",
                    "question": "La propuesta FDC menciona métricas (50K vistas, 7% engagement, 2 festivales). ¿Quieres que estas métricas pasen al dashboard como KPIs del proyecto post-entrega o son solo para el FDC?",
                    "why_asking": "Si son KPIs del proyecto, configuro el panel de seguimiento post-entrega ahora."
                }
            ]
        }, ensure_ascii=False)

    # Ingest endpoint — extraccion de docs
    if "documentos a analizar" in pl or "extraer" in pl or "extract" in pl:
        return json.dumps({
            "fases": [
                {"codigo": "1.0", "nombre": "Pre-producción", "duracion": 30},
                {"codigo": "2.0", "nombre": "Producción / Rodaje", "duracion": 15},
                {"codigo": "3.0", "nombre": "Post-producción", "duracion": 46},
                {"codigo": "4.0", "nombre": "Entrega y FDC", "duracion": 15}
            ],
            "tareas": [
                {"codigo": "1.1", "nombre": "Investigación de historias", "fase": "1.0", "duracion": 10, "responsable": "Equipo investigación"},
                {"codigo": "1.2", "nombre": "Scouting de locaciones", "fase": "1.0", "duracion": 10, "responsable": "Iván", "depende_de": ["1.1"]},
                {"codigo": "1.3", "nombre": "Casting", "fase": "1.0", "duracion": 12, "responsable": "Iván", "depende_de": ["1.1"]},
                {"codigo": "2.1", "nombre": "Rodaje Manizales urbano", "fase": "2.0", "duracion": 3, "responsable": "Iván"},
                {"codigo": "2.2", "nombre": "Rodaje Finca La Esperanza", "fase": "2.0", "duracion": 5, "responsable": "Iván"},
                {"codigo": "2.3", "nombre": "Rodaje Buenaventura", "fase": "2.0", "duracion": 4, "responsable": "Iván"},
                {"codigo": "3.1", "nombre": "Rough cut", "fase": "3.0", "duracion": 10, "responsable": "Editor"},
                {"codigo": "3.2", "nombre": "Color y sonido", "fase": "3.0", "duracion": 25, "responsable": "Editor"},
                {"codigo": "4.1", "nombre": "Aplicación FDC", "fase": "4.0", "duracion": 1, "responsable": "Beto"},
            ],
            "hitos": [
                {"codigo": "M1", "nombre": "Plan de rodaje aprobado", "fecha": "2026-04-30"},
                {"codigo": "M2", "nombre": "Material en disco entregado", "fecha": "2026-05-15"},
                {"codigo": "M3", "nombre": "Rough cut entregado", "fecha": "2026-05-25"},
                {"codigo": "M4", "nombre": "Máster final", "fecha": "2026-06-30"},
                {"codigo": "M5", "nombre": "Aplicación FDC enviada", "fecha": "2026-07-15"}
            ],
            "presupuesto_total": 85000000,
            "presupuesto_distribucion": {
                "talento": 0.35, "equipo_tecnico": 0.30,
                "produccion": 0.20, "post": 0.15
            },
            "stakeholders": [
                "MinCultura (FDC)", "Gobernación Caldas",
                "Alcaldía Manizales", "Federación Cafeteros",
                "Don Hernán (caficultor)"
            ],
            "riesgos": [
                {"descripcion": "Clima lluvioso en mayo Caldas", "impacto": 3, "probabilidad": 4},
                {"descripcion": "FDC convocatoria muy competida (12 propuestas)", "impacto": 5, "probabilidad": 3},
                {"descripcion": "Disponibilidad limitada de Don Hernán (5 días)", "impacto": 4, "probabilidad": 2},
                {"descripcion": "Editor nuevo sin trayectoria con La Falla", "impacto": 4, "probabilidad": 3}
            ],
            "responsables_definidos": ["Iván (director)", "Beto (productor)", "Carlos R. (DP)"],
            "responsables_pendientes": ["guionista", "editor", "sonidista"],
            "fechas_clave": {
                "inicio": "2026-04-01",
                "rodaje_inicio": "2026-05-01",
                "rodaje_fin": "2026-05-15",
                "entrega": "2026-07-07",
                "deadline_fdc": "2026-07-15"
            },
            "deadline_innegociable": "2026-07-15 (FDC)"
        }, ensure_ascii=False)

    if "preguntas" in prompt.lower() or "questions" in prompt.lower():
        return json.dumps({
            "questions": [
                {
                    "key": "guionista",
                    "question": "Vi en los documentos que aún no han confirmado guionista. Iván sugirió a Laura M. (8M COP). ¿Quieres que te lo dé por confirmado o sigues evaluando?",
                    "why_asking": "Sin guionista confirmado, no puedo asignar la tarea 1.0.5 ni calcular ruta crítica completa."
                },
                {
                    "key": "editor",
                    "question": "El editor de la S01 (Carlos M.) no está disponible. Beto marcó esto como riesgo alto. ¿Tienes ya 1-2 candidatos o necesito sugerirte algunos del directorio?",
                    "why_asking": "El editor entra desde el día 1 de post (16 mayo). Sin nombre, todo el bloque 3.x queda sin responsable."
                },
                {
                    "key": "imprevistos",
                    "question": "Quinaya pidió subir el rubro de imprevistos del 3.5% al 7%. Beto propuso recortar de distribución. ¿Aplico ese cambio al presupuesto o prefieres revisarlo en la próxima reunión?",
                    "why_asking": "Esto afecta el panel de salud financiera del proyecto y la línea base de costo."
                },
                {
                    "key": "patrocinio_caficultor",
                    "question": "El patrocinio del caficultor regional (14M, 15% del total) está en negociación. ¿Lo cuento como confirmado para el escenario base o como contingente?",
                    "why_asking": "Si lo cuento contingente, el escenario base baja a 71M y necesito ajustar fases proporcionalmente."
                },
                {
                    "key": "metricas_exito",
                    "question": "La propuesta FDC menciona métricas (50K vistas, 7% engagement, 2 festivales). ¿Quieres que estas métricas pasen al dashboard como KPIs del proyecto post-entrega o son solo para el FDC?",
                    "why_asking": "Si son KPIs del proyecto, configuro el panel de seguimiento post-entrega ahora."
                }
            ]
        }, ensure_ascii=False)

    return "{}"


def _call_deepseek(system: str, prompt: str, max_tokens: int) -> str:
    """DeepSeek V3 chat — directo via api.deepseek.com (con DEEPSEEK_API_KEY).
    Si DEEPSEEK_API_KEY no esta, fallback a Nvidia NIM con NVIDIA_API_KEY.
    """
    import requests

    deepseek_key = os.environ.get("DEEPSEEK_API_KEY")
    if deepseek_key:
        # DeepSeek directo (rapido + barato)
        url = "https://api.deepseek.com/v1/chat/completions"
        api_key = deepseek_key
        model = "deepseek-chat"
    else:
        # Fallback a Nvidia NIM
        api_key = os.environ.get("NVIDIA_API_KEY")
        if not api_key:
            raise HTTPException(500, "Ni DEEPSEEK_API_KEY ni NVIDIA_API_KEY configuradas")
        url = "https://integrate.api.nvidia.com/v1/chat/completions"
        model = "deepseek-ai/deepseek-v4-pro"

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"}
    }

    for attempt in range(3):
        try:
            r = requests.post(url, json=payload, headers=headers, timeout=90)
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"]
            if attempt == 2:
                raise HTTPException(503, f"DeepSeek error {r.status_code}: {r.text[:200]}")
        except requests.exceptions.RequestException:
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)
    raise HTTPException(503, "DeepSeek no respondió tras 3 intentos")


def _call_groq(system: str, prompt: str, max_tokens: int) -> str:
    """Groq Llama 3.3 70B — gratis, rápido, sin Anthropic.
    Reqs: GROQ_API_KEY env var. Endpoint compatible con OpenAI.
    """
    import requests
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise HTTPException(500, "GROQ_API_KEY no configurada")

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"}
    }

    r = requests.post(url, json=payload, headers=headers, timeout=30)
    if r.status_code != 200:
        raise HTTPException(503, f"Groq error {r.status_code}: {r.text[:200]}")
    return r.json()["choices"][0]["message"]["content"]


# ============================================================================
# ENDPOINTS
# ============================================================================

EXTRACTION_SYSTEM = """Eres Gentil, segundo cerebro del CEO de La Falla Destino Fílmico.
Tu tarea: extraer información estructurada de documentos de un proyecto audiovisual/empresarial
para construir su EDT (Estructura de Desglose del Trabajo).

Responde SIEMPRE en formato JSON. Devuelve SOLO JSON válido con esta estructura:
{
  "fases": [{codigo, nombre, duracion}],
  "tareas": [{codigo, nombre, fase, duracion, responsable, depende_de}],
  "hitos": [{codigo, nombre, fecha}],
  "presupuesto_total": number,
  "presupuesto_distribucion": {rubro: porcentaje},
  "stakeholders": [string],
  "riesgos": [{descripcion, impacto, probabilidad}],
  "responsables_definidos": [string],
  "responsables_pendientes": [string],
  "fechas_clave": {evento: fecha},
  "deadline_innegociable": string
}

Si no encuentras un campo, omítelo (no inventes datos)."""


QUESTIONS_SYSTEM = """Eres Gentil. Responde SIEMPRE en formato JSON.
Tu tarea: generar preguntas EMPRESARIALES (no técnicas) para llenar los gaps detectados en un proyecto.

Reglas:
1. Preguntas en lenguaje natural, como hablaría un colega cálido — no jerga PMI
2. Cada pregunta debe ser específica y accionable
3. Incluye SIEMPRE "why_asking" explicando qué endpoint/panel del dashboard
   se desbloquea con la respuesta
4. NO preguntes sobre cosas que ya están en los documentos extraídos
5. Prioriza preguntas que desbloquean ruta crítica y validación financiera

Devuelve JSON: {"questions": [{key, question, why_asking}]}"""


@router.post("/ingest", response_model=IngestResponse)
async def ingest_documents(req: IngestRequest):
    """
    Recibe project info + documentos. Llama a LLM para extraer estructura EDT.
    Detecta gaps (campos que no se pudieron extraer).
    """
    docs_text = "\n\n---DOCUMENTO---\n\n".join(
        f"## {d['name']}\n{d['content']}" for d in req.documents
    )

    prompt = f"""Proyecto: {req.project.name}
Tipo: {req.project.type}
Area: {req.project.area}

DOCUMENTOS A ANALIZAR:
{docs_text}

Extrae toda la informacion estructurada de EDT que puedas. Devuelve JSON."""

    raw = call_llm(EXTRACTION_SYSTEM, prompt)

    try:
        extracted = json.loads(raw)
    except json.JSONDecodeError:
        # Fallback: extraer JSON de markdown si el LLM lo envuelve
        if "```" in raw:
            raw = raw.split("```")[1].replace("json\n", "").strip()
        extracted = json.loads(raw)

    # Detectar gaps
    expected_fields = ["fases", "tareas", "hitos", "presupuesto_total",
                       "stakeholders", "riesgos", "responsables_definidos",
                       "fechas_clave"]
    gaps = []

    if not extracted.get("responsables_definidos") or len(extracted.get("responsables_definidos", [])) < 3:
        gaps.append("responsable")
    if extracted.get("responsables_pendientes"):
        gaps.append("responsables_pendientes")
    if not extracted.get("riesgos") or len(extracted.get("riesgos", [])) < 3:
        gaps.append("riesgos")
    if not extracted.get("presupuesto_total"):
        gaps.append("presupuesto")
    if "metricas_exito" not in extracted:
        gaps.append("metricas_exito")

    confidence = {f: (1.0 if extracted.get(f) else 0.0) for f in expected_fields}

    return IngestResponse(extracted=extracted, confidence=confidence, gaps=gaps)


@router.post("/questions", response_model=QuestionsResponse)
async def generate_questions(req: QuestionsRequest):
    """
    Genera preguntas empresariales basadas en los gaps detectados.
    """
    prompt = f"""Proyecto: {req.project.name} ({req.project.type})

INFORMACION YA EXTRAIDA DE DOCUMENTOS:
{json.dumps(req.extracted, ensure_ascii=False, indent=2)}

GAPS DETECTADOS (campos sin cubrir):
{', '.join(req.gaps)}

Genera 3-7 preguntas empresariales (no tecnicas) para Clementino/Beto.
Recuerda: para cada pregunta explica que panel del dashboard se desbloquea (why_asking).

Devuelve JSON: {{"questions": [...]}}"""

    raw = call_llm(QUESTIONS_SYSTEM, prompt)

    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        if "```" in raw:
            raw = raw.split("```")[1].replace("json\n", "").strip()
        result = json.loads(raw)

    return QuestionsResponse(questions=result.get("questions", []))


@router.post("/synthesize", response_model=SynthesizeResponse)
async def synthesize_project(req: SynthesizeRequest):
    """
    Combina extracted + answers y genera el EDT final.
    En producción: persistiría en PostgreSQL (edt_nodes, risks, milestones).
    En modo mock: devuelve estructura lista para mostrar en el dashboard.
    """
    extracted = req.extracted
    answers = req.answers

    def _safe_int(v, default=0):
        """Convierte v a int de forma segura — handles str, None, dict."""
        if v is None: return default
        if isinstance(v, (int, float)): return int(v)
        if isinstance(v, str):
            try:
                # Extraer primer numero del string (ej: "30 dias" -> 30)
                import re
                m = re.search(r'\d+', v)
                return int(m.group()) if m else default
            except (ValueError, AttributeError):
                return default
        return default

    # Construir EDT nodes desde fases + tareas
    edt_nodes = []
    for fase in extracted.get("fases", []):
        edt_nodes.append({
            "codigo": str(fase.get("codigo", "")),
            "nombre": str(fase.get("nombre", "")),
            "nivel": 1,
            "duracion_dias": _safe_int(fase.get("duracion")),
            "es_paquete_trabajo": True,
            "es_hito": False,
            "estado": "planificado"
        })

    for tarea in extracted.get("tareas", []):
        edt_nodes.append({
            "codigo": str(tarea.get("codigo", "")),
            "nombre": str(tarea.get("nombre", "")),
            "nivel": 2,
            "duracion_dias": _safe_int(tarea.get("duracion")),
            "responsable": _resolve_responsable(tarea.get("responsable"), answers),
            "predecesores": tarea.get("depende_de", []) or [],
            "es_paquete_trabajo": False,
            "es_hito": False,
            "estado": "planificado"
        })

    # Hitos
    milestones = [
        {**h, "es_hito": True, "estado": "planificado"}
        for h in extracted.get("hitos", [])
    ]

    # Riesgos (con respuestas adicionales si las hay)
    risks = [
        {**r, "estado_mitigacion": "monitoreado", "origen": "openclaw_auto"}
        for r in extracted.get("riesgos", [])
    ]

    # Detectar paneles pendientes (respuestas saltadas)
    pending_panels = [
        k for k, v in answers.items()
        if isinstance(v, dict) and v.get("_pending")
    ]

    # Resumen — uso _safe_int para tolerar tipos mixtos del LLM
    summary = {
        "duracion_total_dias": sum(_safe_int(f.get("duracion")) for f in extracted.get("fases", [])),
        "total_tareas": len(extracted.get("tareas", [])),
        "total_hitos": len(milestones),
        "presupuesto_total": _safe_int(extracted.get("presupuesto_total")),
        "stakeholders_count": len(extracted.get("stakeholders", [])),
        "riesgos_count": len(risks),
        "confidence": "alta" if len(pending_panels) == 0 else "media" if len(pending_panels) <= 2 else "baja"
    }

    # En producción: aquí se haría INSERT en PostgreSQL
    # project = Project(codigo=slug(req.project.name), nombre=req.project.name, area=req.project.area)
    # db.add(project); db.commit()
    # for node in edt_nodes: db.add(EdtNode(project_id=project.id, **node))
    # for risk in risks: db.add(Risk(project_id=project.id, **risk))
    # db.commit()

    # En modo mock: devolvemos sin persistir
    project_id = int(time.time())  # placeholder

    return SynthesizeResponse(
        project_id=project_id,
        edt_nodes=edt_nodes,
        risks=risks,
        milestones=milestones,
        pending_panels=pending_panels,
        summary=summary
    )


def _resolve_responsable(default_resp: Optional[str], answers: Dict[str, Any]) -> str:
    """Si una respuesta confirmó un responsable, úsala."""
    if not default_resp or default_resp.lower() == "pendiente":
        if answers.get("guionista") and isinstance(answers["guionista"], str):
            return answers["guionista"]
        if answers.get("editor") and isinstance(answers["editor"], str):
            return answers["editor"]
        return "POR ASIGNAR"
    return default_resp


@router.get("/mock-mode-status")
def mock_mode_status():
    """Endpoint de diagnóstico — confirma qué LLM está activo."""
    return {
        "mode": LLM_MODE,
        "available_modes": ["mock", "groq", "deepseek", "auto"],
        "primary_when_auto": "llama-3.3-70b-versatile (Groq)",
        "fallback_when_auto": "deepseek-chat (DeepSeek directo)",
        "cascade": "Groq -> DeepSeek (sin OpenAI, sin Anthropic)",
        "to_change": "Set EDT_LLM_MODE env var and restart"
    }


# ============================================================================
# TRANSCRIPCIÓN — Groq Whisper Large v3
# ============================================================================

AUDIO_EXTENSIONS = {".mp3", ".mp4", ".m4a", ".wav", ".ogg", ".webm", ".mpeg", ".mpga"}
MAX_AUDIO_BYTES = 25 * 1024 * 1024  # 25 MB (límite Groq)


@router.post("/transcribe")
async def transcribe_audio(file: UploadFile = File(...)):
    """
    Transcribe audio vía Groq Whisper Large v3.
    Formatos: mp3, mp4, m4a, wav, ogg, webm (máx 25 MB).
    Devuelve: {text: "..."}
    """
    GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
    if not GROQ_API_KEY:
        raise HTTPException(500, "GROQ_API_KEY no configurada en el servidor")

    content = await file.read()
    if len(content) > MAX_AUDIO_BYTES:
        raise HTTPException(413, f"Audio demasiado grande (máx 25 MB, recibido {len(content)//1024//1024} MB)")

    # Content-type fallback para extensiones sin mime type correcto
    ct = file.content_type or "audio/mpeg"
    if ct == "application/octet-stream":
        ext = (file.filename or "").rsplit(".", 1)[-1].lower()
        ct = f"audio/{ext}" if ext else "audio/mpeg"

    try:
        r = _req.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            files={"file": (file.filename or "audio.mp3", content, ct)},
            data={"model": "whisper-large-v3", "response_format": "text", "language": "es"},
            timeout=90,
        )
    except Exception as e:
        raise HTTPException(502, f"Error conectando con Groq Whisper: {e}")

    if r.status_code != 200:
        raise HTTPException(502, f"Groq Whisper {r.status_code}: {r.text[:300]}")

    return {"text": r.text.strip(), "filename": file.filename, "bytes": len(content)}

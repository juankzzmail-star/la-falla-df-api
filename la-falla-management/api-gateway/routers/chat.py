import io
import json
import os
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel, ConfigDict
from sqlalchemy import create_engine, text

router = APIRouter(prefix="/chat", tags=["chat"])

GROQ_API_KEY     = os.environ.get("GROQ_API_KEY", "")
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DATABASE_URL     = os.environ.get("DATABASE_URL", "")

GROQ_BASE_URL     = "https://api.groq.com/openai/v1"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
FIRECRAWL_URL     = os.environ.get("FIRECRAWL_URL", "http://10.0.1.132:3002")
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


# ─── Tool definitions for GROQ function calling ─────────────────────────────

GENTIL_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "n8n_list_workflows",
            "description": "Lista todos los workflows de automatización en n8n con su estado (activo/inactivo). Úsalo cuando el CEO pregunte por las automatizaciones existentes o quiera ver qué hay configurado.",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "n8n_get_failed_executions",
            "description": "Obtiene las últimas ejecuciones fallidas de n8n para detectar automatizaciones rotas y proponer reparación (self-healing). Úsalo cuando el CEO pregunte si hay fallos o para diagnóstico proactivo.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Número de ejecuciones fallidas a obtener (default 10)"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "n8n_create_workflow",
            "description": "Crea un workflow nuevo en n8n. Úsalo cuando el CEO pida una nueva automatización. IMPORTANTE: antes de crear, explica brevemente qué va a hacer el workflow.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Nombre descriptivo del workflow"},
                    "description": {"type": "string", "description": "Qué hace este workflow"},
                    "nodes": {"type": "array", "description": "Lista de nodos n8n en formato JSON válido"},
                    "connections": {"type": "object", "description": "Conexiones entre nodos"}
                },
                "required": ["name", "nodes", "connections"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "n8n_activate_workflow",
            "description": "Activa (pone en producción) un workflow de n8n por su ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "workflow_id": {"type": "string", "description": "ID del workflow a activar"}
                },
                "required": ["workflow_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "send_email",
            "description": "Envía un correo electrónico real. Úsalo cuando el CEO pida enviar un mensaje a alguien. Siempre confirma el destinatario y asunto antes de enviar si no está claro.",
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {"type": "string", "description": "Dirección de email del destinatario"},
                    "subject": {"type": "string", "description": "Asunto del correo"},
                    "body": {"type": "string", "description": "Cuerpo del correo. Puede incluir HTML básico."}
                },
                "required": ["to", "subject", "body"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_services",
            "description": "Verifica el estado real de todos los servicios del Centro de Mando: n8n, PostgreSQL, API gateway. Úsalo con /status o cuando el CEO pregunte si todo está funcionando.",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "render_chart",
            "description": "Genera una gráfica interactiva con datos reales. Úsala cuando el CEO pida ver estadísticas, tendencias, comparaciones o cualquier dato numérico en formato visual. La gráfica aparece directamente en el chat.",
            "parameters": {
                "type": "object",
                "properties": {
                    "chart_type": {
                        "type": "string",
                        "enum": ["bar", "line", "area", "pie", "radar"],
                        "description": "Tipo de gráfica: bar=barras, line=línea, area=área rellena, pie=torta, radar=araña"
                    },
                    "title": {"type": "string", "description": "Título de la gráfica"},
                    "subtitle": {"type": "string", "description": "Subtítulo opcional con contexto"},
                    "data": {
                        "type": "array",
                        "description": "Array de objetos JSON con los datos. Ej: [{\"mes\": \"Ene\", \"valor\": 420}]",
                        "items": {"type": "object"}
                    },
                    "x_key": {"type": "string", "description": "Nombre del campo para el eje X (categorías)"},
                    "y_key": {"type": "string", "description": "Nombre del campo para el eje Y (valores numéricos)"},
                    "color": {"type": "string", "description": "Color hex opcional. Default: #00ff41 (verde neón La Falla)"}
                },
                "required": ["chart_type", "title", "data", "x_key", "y_key"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "propose_automation",
            "description": "Propone una automatización al CEO con análisis de ROI preciso. Úsala de forma PROACTIVA cuando detectes un cuello de botella repetitivo que se puede automatizar. El CEO verá una tarjeta interactiva para aprobar o rechazar.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Nombre corto de la automatización (máx 60 caracteres)"},
                    "problema": {"type": "string", "description": "Descripción concreta del cuello de botella actual (qué hace alguien manualmente, cuánto tarda)"},
                    "solucion": {"type": "string", "description": "Qué haría la automatización exactamente, paso a paso"},
                    "area": {"type": "string", "enum": ["GCF", "GP", "GI", "GA", "Transversal"], "description": "Área beneficiada"},
                    "tiempo_ahorro_hrs_mes": {"type": "number", "description": "Horas ahorradas por mes (sé específico: calcúlalo)"},
                    "costo_impl_hrs": {"type": "number", "description": "Horas de desarrollo estimadas para implementar"},
                    "roi_semanas": {"type": "number", "description": "Semanas para recuperar la inversión de desarrollo"}
                },
                "required": ["title", "problema", "solucion", "area", "tiempo_ahorro_hrs_mes", "costo_impl_hrs", "roi_semanas"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Busca información actualizada en internet. Úsala cuando el CEO pida investigar algo en internet, necesite datos recientes, noticias, convocatorias, contactos, precios, regulaciones o cualquier información externa. También úsala cuando /busca sea invocado.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Consulta de búsqueda. Sé específico y usa los términos más relevantes."
                    },
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "query_stakeholders",
            "description": "Consulta el directorio de stakeholders de La Falla DF. Úsalo cuando el CEO pregunte por contactos, aliados, clientes, proveedores, instituciones, o cualquier persona/entidad del directorio. Puede filtrar por nombre, clasificación y ubicación.",
            "parameters": {
                "type": "object",
                "properties": {
                    "search": {
                        "type": "string",
                        "description": "Buscar por nombre, correo, ubicación o rol (búsqueda parcial)"
                    },
                    "clasificacion": {
                        "type": "string",
                        "enum": ["Clientes", "Aliados", "Institucional / Gobierno", "Proveedores (Locaciones)", "Prospecto por Identificar", "REVISIÓN_MANUAL"],
                        "description": "Filtrar por categoría de negocio"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Máximo de resultados (default 20)"
                    },
                    "stats_only": {
                        "type": "boolean",
                        "description": "Si es true, retorna solo estadísticas totales del directorio (sin listar contactos)"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "scrape_url",
            "description": "Lee el contenido completo de una URL web y lo retorna como texto limpio (markdown). Funciona con páginas JavaScript como LinkedIn, portales de convocatorias, artículos de noticias, perfiles públicos. Úsalo cuando el CEO proporciona una URL específica o cuando web_search retorna URLs que necesitas leer en profundidad.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "URL completa a leer (ej: https://linkedin.com/in/nombre-apellido)"
                    },
                    "only_main_content": {
                        "type": "boolean",
                        "description": "Si es true (default), extrae solo el contenido principal ignorando navegación y ads"
                    }
                },
                "required": ["url"]
            }
        }
    }
]


# ─── Tool executor ────────────────────────────────────────────────────────────

def _execute_tool(name: str, args: dict) -> str:
    from . import n8n_client

    try:
        # ── N8N: listar workflows ─────────────────────────────────────────────
        if name == "n8n_list_workflows":
            if not n8n_client.configured():
                return json.dumps({"error": "N8N no configurado. Falta N8N_HOST o N8N_API_KEY en el servidor."})
            data = n8n_client.list_workflows()
            workflows = data.get("data", [])
            summary = [
                {
                    "id": w["id"],
                    "name": w["name"],
                    "active": w.get("active", False),
                    "nodes": len(w.get("nodes", [])),
                    "updatedAt": w.get("updatedAt", ""),
                }
                for w in workflows[:25]
            ]
            return json.dumps({"total": len(workflows), "workflows": summary})

        # ── N8N: ejecuciones fallidas ─────────────────────────────────────────
        elif name == "n8n_get_failed_executions":
            if not n8n_client.configured():
                return json.dumps({"error": "N8N no configurado."})
            limit = int(args.get("limit", 10))
            data = n8n_client.get_executions(limit=limit * 3, status="error")
            execs = data.get("data", [])[:limit]
            summary = [
                {
                    "id": e["id"],
                    "workflow": e.get("workflowData", {}).get("name", "?"),
                    "startedAt": e.get("startedAt", ""),
                    "error": (
                        e.get("data", {})
                        .get("resultData", {})
                        .get("error", {})
                        .get("message", "Error desconocido")
                    )[:200],
                }
                for e in execs
            ]
            return json.dumps({"failed_count": len(execs), "executions": summary})

        # ── N8N: crear workflow ───────────────────────────────────────────────
        elif name == "n8n_create_workflow":
            if not n8n_client.configured():
                return json.dumps({"error": "N8N no configurado."})
            result = n8n_client.create_workflow(
                name=args["name"],
                nodes=args.get("nodes", []),
                connections=args.get("connections", {}),
            )
            return json.dumps({
                "success": True,
                "id": result.get("id"),
                "name": result.get("name"),
                "message": f"Workflow '{result.get('name')}' creado con ID {result.get('id')}. Actívalo con n8n_activate_workflow si está listo para producción.",
            })

        # ── N8N: activar workflow ─────────────────────────────────────────────
        elif name == "n8n_activate_workflow":
            if not n8n_client.configured():
                return json.dumps({"error": "N8N no configurado."})
            result = n8n_client.activate_workflow(args["workflow_id"])
            return json.dumps({"success": True, "active": result.get("active"), "id": args["workflow_id"]})

        # ── Enviar email ──────────────────────────────────────────────────────
        elif name == "send_email":
            webhook_url = os.environ.get("N8N_EMAIL_WEBHOOK_URL", "")
            to = args.get("to", "")
            subject = args.get("subject", "")
            body = args.get("body", "")

            if not webhook_url:
                return json.dumps({
                    "status": "no_configurado",
                    "instruccion": (
                        "Para activar email real: "
                        "(1) Crea un workflow en N8N con Webhook trigger + Gmail node. "
                        "(2) Copia la URL del webhook al .env como N8N_EMAIL_WEBHOOK_URL. "
                        "(3) Reinicia el servicio. "
                        "Por ahora el email no se envió."
                    ),
                    "to": to,
                    "subject": subject,
                    "draft_preview": body[:300],
                })

            import requests as _req
            r = _req.post(webhook_url, json={"to": to, "subject": subject, "body": body}, timeout=20)
            if r.ok:
                return json.dumps({"success": True, "to": to, "subject": subject, "message": f"Email enviado a {to}."})
            else:
                return json.dumps({"error": f"N8N respondió {r.status_code}: {r.text[:200]}"})

        # ── Verificar servicios ───────────────────────────────────────────────
        elif name == "check_services":
            from . import n8n_client as _n8n
            results = {}

            # N8N
            results["n8n"] = "ok" if _n8n.health() else "error"

            # PostgreSQL
            try:
                if DATABASE_URL:
                    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
                    with engine.connect() as c:
                        c.execute(text("SELECT 1"))
                    results["postgres"] = "ok"
                else:
                    results["postgres"] = "DATABASE_URL no configurada"
            except Exception as e:
                results["postgres"] = f"error: {str(e)[:80]}"

            # APIs externas
            import requests as _req
            for svc, url in [("groq_api", "https://api.groq.com"), ("deepseek_api", "https://api.deepseek.com")]:
                try:
                    r = _req.head(url, timeout=5)
                    results[svc] = "reachable"
                except Exception:
                    results[svc] = "unreachable"

            results["api_gateway"] = "ok"
            results["timestamp"] = datetime.now(timezone.utc).isoformat()
            return json.dumps(results)

        # ── Render chart (spec → frontend) ────────────────────────────────────
        elif name == "render_chart":
            spec = {k: args[k] for k in args if args.get(k) is not None}
            spec["__chart__"] = True
            if "color" not in spec:
                spec["color"] = "#00ff41"
            return json.dumps(spec)

        # ── Propuesta de automatización ───────────────────────────────────────
        elif name == "propose_automation":
            proposal = {k: args[k] for k in args if args.get(k) is not None}
            proposal["__proposal__"] = True
            return json.dumps(proposal)

        # ── Consulta directorio de stakeholders ──────────────────────────────
        elif name == "query_stakeholders":
            stats_only = args.get("stats_only", False)

            try:
                engine = create_engine(DATABASE_URL, pool_pre_ping=True) if DATABASE_URL else None
                if not engine:
                    return json.dumps({"error": "Base de datos no configurada."})

                with engine.connect() as conn:
                    if stats_only:
                        row = conn.execute(text("""
                            SELECT COUNT(*) AS total,
                                   COUNT(*) FILTER (WHERE clasificacion_negocio = 'Clientes') AS clientes,
                                   COUNT(*) FILTER (WHERE clasificacion_negocio = 'Aliados') AS aliados,
                                   COUNT(*) FILTER (WHERE clasificacion_negocio = 'Institucional / Gobierno') AS institucionales,
                                   COUNT(*) FILTER (WHERE clasificacion_negocio = 'Proveedores (Locaciones)') AS proveedores,
                                   COUNT(*) FILTER (WHERE clasificacion_negocio = 'Prospecto por Identificar') AS prospectos,
                                   COUNT(*) FILTER (WHERE correo IS NOT NULL AND correo <> '') AS con_correo,
                                   COUNT(*) FILTER (WHERE telefono IS NOT NULL AND telefono <> '') AS con_telefono
                            FROM stakeholders_master
                        """)).fetchone()
                        return json.dumps({"stats": dict(row._mapping)})

                    q = """
                        SELECT id, nombre, rol, correo, telefono, ubicacion, clasificacion_negocio, observaciones
                        FROM stakeholders_master WHERE 1=1
                    """
                    params: dict = {}
                    search = args.get("search", "")
                    clasificacion = args.get("clasificacion", "")
                    limit = min(int(args.get("limit", 20)), 50)

                    if search:
                        q += " AND (nombre ILIKE :search OR correo ILIKE :search OR ubicacion ILIKE :search OR rol ILIKE :search)"
                        params["search"] = f"%{search}%"
                    if clasificacion:
                        q += " AND clasificacion_negocio = :clasificacion"
                        params["clasificacion"] = clasificacion

                    q += " ORDER BY nombre NULLS LAST LIMIT :limit"
                    params["limit"] = limit
                    rows = conn.execute(text(q), params).fetchall()

                    results = [
                        {k: v for k, v in dict(r._mapping).items() if v is not None}
                        for r in rows
                    ]
                    return json.dumps({
                        "count": len(results),
                        "stakeholders": results,
                        "note": f"Mostrando {len(results)} de los primeros {limit} resultados." if len(results) == limit else ""
                    })
            except Exception as e:
                return json.dumps({"error": f"Error consultando stakeholders: {str(e)[:200]}"})

        # ── Búsqueda web ─────────────────────────────────────────────────────
        elif name == "web_search":
            query = args.get("query", "").strip()
            num_results = min(int(args.get("num_results", 5)), 10)
            if not query:
                return json.dumps({"error": "Query de búsqueda vacía."})

            serper_key  = os.environ.get("SERPER_API_KEY", "")
            brave_key   = os.environ.get("BRAVE_SEARCH_API_KEY", "")

            import requests as _req
            from urllib.parse import quote

            # Serper (Google results — mejor calidad)
            if serper_key:
                try:
                    r = _req.post(
                        "https://google.serper.dev/search",
                        headers={"X-API-KEY": serper_key, "Content-Type": "application/json"},
                        json={"q": query, "gl": "co", "hl": "es", "num": num_results},
                        timeout=15,
                    )
                    if r.ok:
                        data = r.json()
                        results = [
                            {"title": item.get("title", ""), "snippet": item.get("snippet", ""), "link": item.get("link", "")}
                            for item in data.get("organic", [])[:num_results]
                        ]
                        answer_box = data.get("answerBox", {})
                        return json.dumps({
                            "query": query, "source": "serper/google",
                            "answer_box": answer_box.get("answer") or answer_box.get("snippet") or "",
                            "results": results,
                        })
                except Exception as e:
                    pass  # fallback

            # Brave Search
            if brave_key:
                try:
                    r = _req.get(
                        "https://api.search.brave.com/res/v1/web/search",
                        headers={"Accept": "application/json", "X-Subscription-Token": brave_key},
                        params={"q": query, "count": num_results, "country": "CO", "search_lang": "es"},
                        timeout=15,
                    )
                    if r.ok:
                        data = r.json()
                        results = [
                            {"title": item.get("title", ""), "snippet": item.get("description", ""), "link": item.get("url", "")}
                            for item in data.get("web", {}).get("results", [])[:num_results]
                        ]
                        return json.dumps({"query": query, "source": "brave", "results": results})
                except Exception:
                    pass  # fallback

            # Firecrawl /v1/search — búsqueda nativa con Google integrado
            try:
                r = _req.post(
                    f"{FIRECRAWL_URL}/v1/search",
                    json={"query": query, "limit": num_results},
                    headers={"Authorization": f"Bearer {FIRECRAWL_API_KEY}"},
                    timeout=30,
                )
                if r.ok:
                    data = r.json()
                    if data.get("success") and data.get("data"):
                        results = [
                            {
                                "title": item.get("title", ""),
                                "snippet": item.get("description", ""),
                                "link": item.get("url", ""),
                            }
                            for item in data["data"][:num_results]
                            if item.get("url")
                        ]
                        if results:
                            return json.dumps({"query": query, "source": "firecrawl/search", "results": results})
            except Exception:
                pass

            return json.dumps({"query": query, "results": [], "warning": "Búsqueda sin resultados. Verifica que Firecrawl esté activo en el VPS."})

        # ── Scrape URL con Firecrawl ──────────────────────────────────────────
        elif name == "scrape_url":
            url = args.get("url", "").strip()
            if not url:
                return json.dumps({"error": "URL vacía."})
            only_main = args.get("only_main_content", True)
            import requests as _req
            try:
                payload = {
                    "url": url,
                    "formats": ["markdown"],
                    "onlyMainContent": only_main,
                }
                r = _req.post(
                    f"{FIRECRAWL_URL}/v1/scrape",
                    json=payload,
                    timeout=25,
                )
                if not r.ok:
                    return json.dumps({"error": f"Firecrawl error {r.status_code}: {r.text[:200]}", "url": url})
                data = r.json()
                if not data.get("success"):
                    return json.dumps({"error": data.get("error", "Firecrawl: sin contenido"), "url": url})
                content = data.get("data", {}).get("markdown", "") or ""
                metadata = data.get("data", {}).get("metadata", {})
                if not content.strip():
                    return json.dumps({
                        "url": url,
                        "title": metadata.get("title", ""),
                        "content": "",
                        "note": "La página no tiene contenido extraíble (puede requerir login o estar vacía).",
                    })
                return json.dumps({
                    "url": url,
                    "title": metadata.get("title", ""),
                    "content": content[:12000],
                    "chars": len(content),
                })
            except Exception as e:
                return json.dumps({"error": f"Error al raspar URL: {str(e)[:200]}", "url": url})

        else:
            return json.dumps({"error": f"Tool '{name}' no reconocida."})

    except Exception as e:
        return json.dumps({"error": str(e)})


# ─── Dashboard context ────────────────────────────────────────────────────────

def _get_dashboard_context() -> str:
    if not DATABASE_URL:
        return ""
    try:
        engine = create_engine(DATABASE_URL, pool_pre_ping=True)
        ctx = {}
        with engine.connect() as conn:
            r = conn.execute(text("""
                SELECT
                    COUNT(*) FILTER (WHERE estado='completada') AS done,
                    COUNT(*) FILTER (WHERE estado IN ('en_progreso','en_revisión')) AS wip,
                    COUNT(*) FILTER (WHERE fecha_vencimiento < CURRENT_DATE AND estado NOT IN ('completada','cancelada')) AS vencidas,
                    COUNT(*) AS total
                FROM tasks WHERE fecha_vencimiento IS NOT NULL
            """)).fetchone()
            if r:
                ctx['tareas'] = dict(r._mapping)

            r2 = conn.execute(text(
                "SELECT estado, COUNT(*) as n FROM roadmap_milestones GROUP BY estado"
            )).fetchall()
            ctx['hitos_2030'] = {row.estado: row.n for row in r2}

            r3 = conn.execute(text("""
                SELECT COUNT(*) FILTER (WHERE impacto*probabilidad>=16) AS criticos,
                       COUNT(*) FILTER (WHERE impacto*probabilidad BETWEEN 9 AND 15) AS moderados,
                       COUNT(*) AS total
                FROM risks
            """)).fetchone()
            if r3:
                ctx['riesgos'] = dict(r3._mapping)

            r4 = conn.execute(text("""
                SELECT caja_operativa, reservas_estrategicas, credito_disponible, gasto_mensual_promedio
                FROM financial_snapshots ORDER BY fecha DESC LIMIT 1
            """)).fetchone()
            if r4:
                ctx['financiero'] = dict(r4._mapping)

            r5 = conn.execute(text(
                "SELECT COUNT(*) FILTER (WHERE estado='nuevo') AS nuevos, COUNT(*) AS total FROM inbox_items"
            )).fetchone()
            if r5:
                ctx['inbox'] = dict(r5._mapping)

            # Stakeholders
            r6 = conn.execute(text(
                "SELECT COUNT(*) AS total FROM stakeholders_master"
            )).fetchone()
            if r6:
                ctx['stakeholders'] = dict(r6._mapping)

        lines = ["\n**ESTADO ACTUAL DEL CENTRO DE MANDO** (dato vivo):"]
        if 'tareas' in ctx:
            t = ctx['tareas']
            lines.append(f"- Tareas: {t.get('done',0)} completadas · {t.get('wip',0)} en progreso · {t.get('vencidas',0)} vencidas de {t.get('total',0)} totales")
        if 'hitos_2030' in ctx:
            h = ctx['hitos_2030']
            lines.append(f"- Hitos 2030: {h.get('completo',0)} completados · {h.get('en_curso',0)} en curso · {h.get('retrasado',0)} retrasados")
        if 'riesgos' in ctx:
            r = ctx['riesgos']
            lines.append(f"- Riesgos: {r.get('criticos',0)} críticos (I×P≥16) · {r.get('moderados',0)} moderados · {r.get('total',0)} totales")
        if 'financiero' in ctx:
            f = ctx['financiero']
            caja_total = (f.get('caja_operativa') or 0) + (f.get('reservas_estrategicas') or 0) + (f.get('credito_disponible') or 0)
            gasto = f.get('gasto_mensual_promedio') or 1
            meses = round(caja_total / gasto, 1) if gasto else '?'
            lines.append(f"- Liquidez: {caja_total/1_000_000:.1f}M COP total · {meses} meses de runway")
        if 'inbox' in ctx:
            i = ctx['inbox']
            lines.append(f"- Inbox: {i.get('nuevos',0)} items nuevos de {i.get('total',0)} totales")
        if 'stakeholders' in ctx:
            lines.append(f"- Directorio: {ctx['stakeholders'].get('total',0)} stakeholders registrados")
        lines.append(f"- Timestamp: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
        return "\n".join(lines)
    except Exception:
        return ""


# ─── Pydantic models ──────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    model: str = "haiku"
    history: list[dict] = []
    file_text: str = ""
    file_name: str = ""
    image_b64: str = ""
    image_type: str = "image/jpeg"


class ChatResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    response: str
    model_used: str
    tool_artifacts: list[dict] = []


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/extract-file")
async def extract_file(file: UploadFile = File(...)):
    """Extrae texto de PDF, DOCX o archivos de texto para que Gentil pueda leerlos."""
    data = await file.read()
    filename = file.filename or "unknown"

    # PDF — pdfplumber (primario, más robusto) → pypdf (fallback)
    if filename.lower().endswith(".pdf") or (file.content_type or "").startswith("application/pdf"):
        pages_text = []
        total_pages = 0

        # 1. pdfplumber — mejor extracción de tablas y texto en PDFs complejos
        try:
            import pdfplumber
            with pdfplumber.open(io.BytesIO(data)) as pdf:
                total_pages = len(pdf.pages)
                for i, page in enumerate(pdf.pages):
                    # Intentar extraer tabla primero, luego texto
                    tables = page.extract_tables() or []
                    table_text = ""
                    for table in tables:
                        for row in table:
                            row_clean = [str(c or "").strip() for c in row]
                            if any(row_clean):
                                table_text += " | ".join(row_clean) + "\n"
                    plain = page.extract_text() or ""
                    combined = (table_text + "\n" + plain).strip()
                    if combined:
                        pages_text.append(f"[Página {i+1}]\n{combined}")
        except Exception:
            pass

        # 2. Fallback: pypdf si pdfplumber no extrajo nada
        if not pages_text:
            try:
                from pypdf import PdfReader
                reader = PdfReader(io.BytesIO(data))
                total_pages = len(reader.pages)
                for i, page in enumerate(reader.pages):
                    t = page.extract_text() or ""
                    if t.strip():
                        pages_text.append(f"[Página {i+1}]\n{t}")
            except Exception as e:
                return {"filename": filename, "text": "", "pages": total_pages,
                        "warning": f"Error extrayendo PDF: {str(e)[:200]}"}

        text = "\n\n".join(pages_text)
        if not text.strip():
            return {"filename": filename, "text": "", "pages": total_pages,
                    "warning": "PDF escaneado o sin texto extraíble (imagen pura). Comparte el contenido como texto o usa Subir Recurso."}
        return {"filename": filename, "text": text[:60000], "pages": total_pages}

    # DOCX — extracción vía zip + XML
    if filename.lower().endswith(".docx"):
        try:
            import zipfile
            import xml.etree.ElementTree as ET
            z = zipfile.ZipFile(io.BytesIO(data))
            if "word/document.xml" in z.namelist():
                xml_data = z.read("word/document.xml").decode("utf-8", errors="ignore")
                root = ET.fromstring(xml_data)
                ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
                texts = [elem.text for elem in root.iter(f"{ns}t") if elem.text]
                return {"filename": filename, "text": " ".join(texts)[:20000]}
        except Exception as e:
            return {"filename": filename, "text": "", "warning": f"Error extrayendo DOCX: {str(e)[:200]}"}

    # CSV / TXT / Código
    if (file.content_type or "").startswith("text/") or filename.lower().endswith((".csv", ".txt", ".md", ".json", ".sql", ".py", ".js", ".ts")):
        return {"filename": filename, "text": data.decode("utf-8", errors="replace")[:20000]}

    return {"filename": filename, "text": "", "warning": f"Tipo no soportado para extracción automática: {filename}"}


@router.post("/transcribe")
async def transcribe_audio(audio: UploadFile = File(...)):
    """Transcribe nota de voz usando GROQ Whisper."""
    if not GROQ_API_KEY:
        raise HTTPException(status_code=503, detail="GROQ_API_KEY no configurada.")
    data = await audio.read()
    try:
        from openai import OpenAI
        client = OpenAI(api_key=GROQ_API_KEY, base_url=GROQ_BASE_URL)
        transcription = client.audio.transcriptions.create(
            model="whisper-large-v3",
            file=(audio.filename or "audio.webm", io.BytesIO(data), audio.content_type or "audio/webm"),
            language="es",
        )
        return {"text": transcription.text}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error de transcripción: {str(e)}")


@router.post("", response_model=ChatResponse)
def chat_with_gentil(req: ChatRequest):
    provider, model_id = MODEL_IDS.get(req.model, MODEL_IDS["haiku"])

    # Imagen adjunta → modelo visión de GROQ
    if req.image_b64:
        provider, model_id = "groq", "meta-llama/llama-4-scout-17b-16e-instruct"

    if provider == "groq" and not GROQ_API_KEY:
        raise HTTPException(status_code=503, detail="GROQ_API_KEY no configurada.")
    if provider == "deepseek" and not DEEPSEEK_API_KEY:
        if GROQ_API_KEY:
            provider, model_id = "groq", "llama-3.3-70b-versatile"
        else:
            raise HTTPException(status_code=503, detail="APIs no configuradas.")

    dashboard_ctx = _get_dashboard_context()
    system = BASE_SYSTEM_PROMPT + dashboard_ctx
    history = req.history[-20:] if req.history else []

    # Construir contenido del mensaje
    user_text = req.message
    if req.file_text:
        # El frontend envía "[Archivo: filename] <warning>" cuando la extracción falla.
        # El texto real de un archivo nunca empieza con "[Archivo: " seguido del nombre del archivo.
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

    messages = history + [{"role": "user", "content": user_content}]

    try:
        from openai import OpenAI
        client = OpenAI(
            api_key=GROQ_API_KEY if provider == "groq" else DEEPSEEK_API_KEY,
            base_url=GROQ_BASE_URL if provider == "groq" else DEEPSEEK_BASE_URL,
        )

        # Tool calling disponible en GROQ y DeepSeek (ambos soportan OpenAI function calling)
        use_tools = not req.image_b64
        tool_artifacts: list[dict] = []

        base_messages = [{"role": "system", "content": system}] + messages
        create_kwargs: dict = {
            "model": model_id,
            "max_tokens": 4000,
            "messages": base_messages,
        }
        if use_tools:
            create_kwargs["tools"] = GENTIL_TOOLS
            create_kwargs["tool_choice"] = "auto"

        resp = client.chat.completions.create(**create_kwargs)

        # ── Agentic tool loop (máx 5 rondas) ─────────────────────────────────
        MAX_ROUNDS = 15
        rounds = 0
        current_messages = list(base_messages)

        while (
            use_tools
            and resp.choices[0].finish_reason == "tool_calls"
            and rounds < MAX_ROUNDS
        ):
            rounds += 1
            assistant_msg = resp.choices[0].message

            current_messages.append({
                "role": "assistant",
                "content": assistant_msg.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments}
                    }
                    for tc in (assistant_msg.tool_calls or [])
                ]
            })

            for tc in (assistant_msg.tool_calls or []):
                try:
                    args = json.loads(tc.function.arguments) if tc.function.arguments else {}
                except json.JSONDecodeError:
                    args = {}

                result_str = _execute_tool(tc.function.name, args)

                try:
                    result_obj = json.loads(result_str)
                    if isinstance(result_obj, dict) and ("__chart__" in result_obj or "__proposal__" in result_obj):
                        tool_artifacts.append(result_obj)
                except Exception:
                    pass

                current_messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result_str,
                })

            resp = client.chat.completions.create(
                model=model_id,
                max_tokens=1500,
                messages=current_messages,
                tools=GENTIL_TOOLS,
                tool_choice="auto",
            )

        final_text = resp.choices[0].message.content or ""
        return ChatResponse(
            response=final_text,
            model_used=f"{provider}/{model_id}",
            tool_artifacts=tool_artifacts,
        )

    except Exception as e:
        if "401" in str(e) or "authentication" in str(e).lower() or "api key" in str(e).lower():
            raise HTTPException(status_code=401, detail=f"API key inválida para {provider}.")
        raise HTTPException(status_code=500, detail=f"Error al consultar {provider}: {str(e)}")

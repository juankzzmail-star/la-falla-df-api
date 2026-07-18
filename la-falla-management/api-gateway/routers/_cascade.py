"""Strategy cascade seams (change strategy-cascade).

Mockable LLM seams + deterministic helpers shared by the Estrategia -> Plan -> Tareas
flow. Goal extraction, plan generation and task generation are thin functions so the
tests monkeypatch them with no network. Provider resolution mirrors
strategy.py::_analysis_client_model — honest 503 when no provider is configured.

Kept import-light (no router imports) to avoid circular imports: strategy.py and
plans.py import FROM this module, never the other way around.
"""
import json
import os
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

# Area -> director (single source of truth). Tasks/plans set `responsable` from here.
AREA_DIRECTOR: Dict[str, str] = {
    "Comercial": "Juan Carlos",
    "Proyectos": "Beto",
    "Audiovisual": "Iván",
    "Investigacion": "Quinaya",
    "Gerencial": "Clementino",
    "Transversal": "Clementino",   # cross-cutting governance is owned by the CEO
}
DEFAULT_DIRECTOR = "Clementino"

# Director (by name) -> routing alias (change google-tasks-dashboard). Source: chat.py::_get_director_info
# + the comms standard (docs/estandar-comunicaciones-lafalla.md). When the CEO assigns a task to a
# director, the Centro de Mando emits it to this alias; the CEO's own tasks sync to his Google Tasks.
DIRECTOR_ALIAS: Dict[str, str] = {
    "Juan Carlos": "comercial@lafalla.co",
    "Beto": "proyectos@lafalla.co",
    "Iván": "audiovisual@lafalla.co",
    "Quinaya": "investigaciones@lafalla.co",
    "Clementino": "gerencia@lafalla.co",
}
CEO_NAME = "Clementino"


def director_for(area: Optional[str]) -> str:
    """Map an area to its responsible director; default to the CEO (Clementino)."""
    return AREA_DIRECTOR.get((area or "").strip(), DEFAULT_DIRECTOR)


def alias_for_director(name: Optional[str]) -> str:
    """Routing alias for a director name; default to the CEO's alias."""
    return DIRECTOR_ALIAS.get((name or "").strip(), DIRECTOR_ALIAS[CEO_NAME])


def director_for_account(account: Optional[str]) -> Optional[str]:
    """Reverse of DIRECTOR_ALIAS: a Workspace account email -> director name (None if unknown).
    Used to attribute imported Google Tasks to the right director (change import-google-tasks)."""
    acct = (account or "").strip().lower()
    for name, alias in DIRECTOR_ALIAS.items():
        if alias.lower() == acct:
            return name
    return None


def area_for_director(name: Optional[str]) -> Optional[str]:
    """Director name -> their area (first match in AREA_DIRECTOR); None if unknown. Clementino maps to
    'Gerencial' (his own tasks are not one of the four dashboard areas)."""
    n = (name or "").strip()
    for area, dname in AREA_DIRECTOR.items():
        if dname == n:
            return area
    return None


# ── Provider resolution (honest: 503 if none) ────────────────────────────────────
ANALYSIS_PROVIDER = os.environ.get("ANALYSIS_PROVIDER", "openai").lower()
ANALYSIS_MODEL    = os.environ.get("ANALYSIS_MODEL", "gpt-4o-mini")
GROQ_BASE_URL     = "https://api.groq.com/openai/v1"


def _client_model():
    """Return (OpenAI-compatible client, model). Raises HTTP 503 if no provider — never fabricate."""
    from openai import OpenAI
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    groq_key   = os.environ.get("GROQ_API_KEY", "")
    if ANALYSIS_PROVIDER == "groq" and groq_key:
        return OpenAI(api_key=groq_key, base_url=GROQ_BASE_URL), "llama-3.3-70b-versatile"
    if openai_key:
        return OpenAI(api_key=openai_key), (ANALYSIS_MODEL or "gpt-4o-mini")
    if groq_key:
        return OpenAI(api_key=groq_key, base_url=GROQ_BASE_URL), "llama-3.3-70b-versatile"
    raise HTTPException(503, "No hay proveedor LLM configurado (OPENAI_API_KEY o GROQ_API_KEY).")


def _chat_json(system: str, user: str, max_tokens: int = 1200) -> dict:
    """One JSON-mode completion. Isolated so tests can monkeypatch the whole seam above."""
    client, model = _client_model()
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user[:15000]}],
        response_format={"type": "json_object"},
        temperature=0,
        max_tokens=max_tokens,
    )
    return json.loads(resp.choices[0].message.content or "{}")


# ── Seam 1: document text -> strategic goals ─────────────────────────────────────
GOALS_PROMPT = """
Eres un asistente experto en gestión estratégica empresarial de La Falla D.F.
Dado el texto de un documento de estrategia, extrae TODAS las metas estratégicas REALES.
Responde ÚNICAMENTE con JSON: {"metas":[{"codigo":"string corto único (ej COM-2026-01)","titulo":"string","area":"exactamente uno de Comercial | Proyectos | Investigacion | Audiovisual | Transversal","fecha_fin_meta":"ISO 8601 o null","peso_porcentaje":"number 0-100 o null"}]}

Mapeo de ÁREA cuando el documento está organizado por dirección/sección (p. ej. encabezados '### Hoja: Dir. ...'):
- Dirección Comercial y/o Financiero  -> "Comercial"
- Dirección de Proyectos              -> "Proyectos"
- Dirección Audiovisual / Creativa    -> "Audiovisual"
- Dirección de Investigación          -> "Investigacion"
- Gerencia y/o CEO (gobierno transversal: jurídica, fiscal, contratos, equipo, representación) -> "Transversal"

Reglas:
- Infiere el área del encabezado de la sección/dirección; si no hay sección, infiere del contexto.
- EXCLUYE tareas puramente operativas o administrativas recurrentes (pagar IVA, renovar cámara de comercio,
  declaraciones, cumpleaños, agendas): NO son metas estratégicas, no las incluyas.
- Una meta estratégica describe un resultado/mejora esperada (con su indicador), no un trámite.
- Si no hay fecha usa null; códigos únicos y estables por área.
""".strip()


def extract_goals_from_text(text: str) -> List[Dict[str, Any]]:
    """LLM seam: parse strategic goals (metas) from document text. [] when none found."""
    if not (text or "").strip():
        return []
    data = _chat_json(GOALS_PROMPT, text)
    metas = data.get("metas", []) if isinstance(data, dict) else []
    return [m for m in metas if isinstance(m, dict) and (m.get("codigo") or "").strip()]


# ── Seam 2: goal -> plans ────────────────────────────────────────────────────────
PLANS_PROMPT = """
Eres Gentil, planificador estratégico de La Falla D.F. Dada UNA meta estratégica, propón de 1 a 3 PLANES concretos que la ejecuten.
Responde ÚNICAMENTE con JSON: {"planes":[{"codigo":"string corto único derivado del código de la meta (ej COM-2030-01-P1)","titulo":"string claro","fecha_inicio":"ISO 8601 o null","fecha_fin_planificada":"ISO 8601 o null"}]}
Reglas: planes accionables y medibles; no inventes cifras; máximo 3.
""".strip()


def generate_plans_for_goal(goal: Dict[str, Any]) -> List[Dict[str, Any]]:
    """LLM seam: propose plans for a goal dict (codigo, titulo, area, fecha_*)."""
    user = json.dumps({k: goal.get(k) for k in ("codigo", "titulo", "area", "fecha_inicio", "fecha_fin_meta")},
                      ensure_ascii=False, default=str)
    data = _chat_json(PLANS_PROMPT, user)
    planes = data.get("planes", []) if isinstance(data, dict) else []
    return [p for p in planes if isinstance(p, dict) and (p.get("titulo") or "").strip()]


# ── Seam 3: plan -> tasks ────────────────────────────────────────────────────────
TASKS_PROMPT = """
Eres Gentil, planificador de La Falla D.F. Dado UN plan, desglósalo en 2 a 6 TAREAS ejecutables por el equipo.
Responde ÚNICAMENTE con JSON: {"tareas":[{"titulo":"string","fecha_inicio":"ISO 8601 o null","fecha_vencimiento":"ISO 8601 o null","es_hito":true/false,"prioridad":"alta|media|baja","peso_pct":"number 0-100"}]}
Reglas: tareas concretas; al menos un hito; los peso_pct deben sumar ~100; no inventes cifras de dinero.
""".strip()


def generate_tasks_for_plan(plan: Dict[str, Any]) -> List[Dict[str, Any]]:
    """LLM seam: break a plan dict (codigo, titulo, area, fecha_*) into tasks."""
    user = json.dumps({k: plan.get(k) for k in ("codigo", "titulo", "area", "fecha_inicio", "fecha_fin_planificada")},
                      ensure_ascii=False, default=str)
    data = _chat_json(TASKS_PROMPT, user)
    tareas = data.get("tareas", []) if isinstance(data, dict) else []
    return [t for t in tareas if isinstance(t, dict) and (t.get("titulo") or "").strip()]


# ── Seam 4: plan + its tasks-by-quarter -> quarterly goals (change generate-plan-quarters) ───────
QUARTERS_PROMPT = """
Eres Gentil, planificador de La Falla D.F. Dado UN plan anual y sus TAREAS agrupadas por trimestre,
sintetiza la META de cada trimestre que tenga tareas: una frase-objetivo breve que resuma el RESULTADO
esperado de ese trimestre a partir de sus tareas reales (no las repitas una por una).
Responde ÚNICAMENTE con JSON: {"trimestres":[{"trimestre":1|2|3|4,"meta":"string","objetivo_medible":"string corto o null"}]}
Reglas: una meta por trimestre que tenga tareas; NO inventes trimestres sin tareas; resume, no copies;
no inventes cifras de dinero; objetivo_medible solo si se desprende de las tareas, si no null.
""".strip()


def generate_quarters_for_plan(plan: Dict[str, Any], tasks_by_quarter: Dict[int, List[str]]) -> List[Dict[str, Any]]:
    """LLM seam: propose a quarterly goal (meta) per quarter from the plan's real task titles, grouped by
    quarter. Returns [{trimestre, meta, objetivo_medible}]. Mirrors generate_plans_for_goal — monkeypatch
    this (or _chat_json) in tests; no network there. 503 (via _client_model) if no provider, before writes."""
    payload = {
        "plan": {k: plan.get(k) for k in ("codigo", "titulo", "area")},
        "trimestres": {str(q): tasks_by_quarter.get(q, []) for q in sorted(tasks_by_quarter)},
    }
    data = _chat_json(QUARTERS_PROMPT, json.dumps(payload, ensure_ascii=False, default=str))
    qs = data.get("trimestres", []) if isinstance(data, dict) else []
    out: List[Dict[str, Any]] = []
    for q in qs:
        if not isinstance(q, dict):
            continue
        try:
            t = int(q.get("trimestre"))
        except (TypeError, ValueError):
            continue
        meta = (q.get("meta") or "").strip()
        if t in (1, 2, 3, 4) and meta:
            out.append({"trimestre": t, "meta": meta, "objetivo_medible": (q.get("objetivo_medible") or None)})
    return out


# ── Seam 5: metas-de-hito + company hitos -> meta→hito links (change populate-hito-rollup) ───────
HITO_LINK_PROMPT = """
Eres Gentil, estratega de La Falla D.F. Tienes (a) las METAS de área (cada una es la contribución de una
dirección a un hito de empresa) y (b) los HITOS macro de la ruta a 2030 (de toda la empresa). Para CADA meta,
elige el ÚNICO hito que esa meta hace avanzar (el más afín por tema/resultado y, si ayuda, por año/área).
Responde ÚNICAMENTE con JSON: {"links":[{"meta_id":int,"milestone_id":int}]}
Reglas: usa SOLO los id que te paso (no inventes ids); si una meta no encaja claramente en ningún hito,
omítela (no la fuerces); a lo sumo un hito por meta; no inventes cifras de dinero.
""".strip()


def generate_hito_links_for_metas(metas: List[Dict[str, Any]], hitos: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """LLM seam: propose, for each unlinked meta-de-hito, the company hito it advances. `metas` =
    [{id, codigo, titulo, area}], `hitos` = [{id, titulo, area, anio}]. Returns [{meta_id, milestone_id}]
    keeping ONLY pairs whose ids exist in the inputs (no dangling refs, no invented ids). Mirrors the other
    seams — monkeypatch this (or _chat_json) in tests; no network there. 503 (via _client_model) before
    any caller write when no provider. Returns [] when there is nothing to propose."""
    if not metas or not hitos:
        return []
    meta_ids = {m.get("id") for m in metas}
    hito_ids = {h.get("id") for h in hitos}
    payload = {
        "metas": [{k: m.get(k) for k in ("id", "codigo", "titulo", "area")} for m in metas],
        "hitos": [{k: h.get(k) for k in ("id", "titulo", "area", "anio")} for h in hitos],
    }
    data = _chat_json(HITO_LINK_PROMPT, json.dumps(payload, ensure_ascii=False, default=str))
    links = data.get("links", []) if isinstance(data, dict) else []
    out: List[Dict[str, Any]] = []
    seen: set = set()
    for l in links:
        if not isinstance(l, dict):
            continue
        try:
            mid = int(l.get("meta_id"))
            hid = int(l.get("milestone_id"))
        except (TypeError, ValueError):
            continue
        if mid in meta_ids and hid in hito_ids and mid not in seen:
            seen.add(mid)
            out.append({"meta_id": mid, "milestone_id": hid})
    return out


# ── Seam 6: real director tasks -> task→hito links (change connect-execution-strategy-deeper) ────
TASK_HITO_LINK_PROMPT = """
Eres Gentil, estratega de La Falla D.F. Tienes (a) TAREAS reales de los directores (su trabajo del día a
día, traído de Google Tasks) y (b) los HITOS macro de la ruta a 2030. Para CADA tarea, decide si hace
avanzar CLARAMENTE alguno de los hitos; si sí, enlázala al ÚNICO hito más afín por tema/resultado (y por
área si ayuda). Responde ÚNICAMENTE con JSON: {"links":[{"task_id":int,"milestone_id":int}]}
Reglas: usa SOLO los id que te paso (no inventes ids); la MAYORÍA del trabajo operativo NO mapea a un hito
— si una tarea no hace avanzar ningún hito, OMÍTELA (no la fuerces); a lo sumo un hito por tarea.
""".strip()


def generate_hito_links_for_tasks(tasks: List[Dict[str, Any]], hitos: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """LLM seam: for each real director task, propose the company hito it advances (or omit it if it is
    purely operational). `tasks` = [{id, titulo, area, responsable}], `hitos` = [{id, titulo, area, anio}].
    Returns [{task_id, milestone_id}] keeping ONLY pairs whose ids exist in the inputs (no invented ids).
    Mirrors generate_hito_links_for_metas — monkeypatch this (or _chat_json) in tests; 503 before any
    caller write when no provider; [] when there is nothing to propose."""
    if not tasks or not hitos:
        return []
    task_ids = {t.get("id") for t in tasks}
    hito_ids = {h.get("id") for h in hitos}
    payload = {
        "tareas": [{k: t.get(k) for k in ("id", "titulo", "area", "responsable")} for t in tasks],
        "hitos": [{k: h.get(k) for k in ("id", "titulo", "area", "anio")} for h in hitos],
    }
    data = _chat_json(TASK_HITO_LINK_PROMPT, json.dumps(payload, ensure_ascii=False, default=str))
    links = data.get("links", []) if isinstance(data, dict) else []
    out: List[Dict[str, Any]] = []
    seen: set = set()
    for l in links:
        if not isinstance(l, dict):
            continue
        try:
            tid = int(l.get("task_id"))
            hid = int(l.get("milestone_id"))
        except (TypeError, ValueError):
            continue
        if tid in task_ids and hid in hito_ids and tid not in seen:
            seen.add(tid)
            out.append({"task_id": tid, "milestone_id": hid})
    return out


# ── Deterministic curva-S baseline scaffold (no LLM) ─────────────────────────────
def curva_s_scaffold(fecha_inicio: Optional[date], fecha_fin: Optional[date]) -> List[Dict[str, Any]]:
    """Evenly spaced monthly cumulative-% ramp between two dates. A sane default the CEO edits later.

    Returns [] when dates are missing/invalid. Uses a smooth S-shape (cumulative)."""
    if not fecha_inicio or not fecha_fin or fecha_fin <= fecha_inicio:
        return []
    # number of monthly buckets (at least 1)
    months = max(1, round((fecha_fin - fecha_inicio).days / 30.0))
    points: List[Dict[str, Any]] = []
    for i in range(1, months + 1):
        frac = i / months
        # simple smoothstep S-curve: 3f^2 - 2f^3
        pct = round((3 * frac ** 2 - 2 * frac ** 3) * 100, 1)
        d = fecha_inicio + timedelta(days=round(30.0 * i))
        points.append({"mes": d.strftime("%Y-%m"), "pct_plan": pct})
    return points

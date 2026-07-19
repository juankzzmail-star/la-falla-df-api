"""Completeness interview — orchestrator + per-domain specialist registry (change
completeness-interview).

After ingestion, the dashboard often has empty/thin domains. This module detects them and turns
each into a validated, write-back-capable question:
  - Group 1 (enrich): the domain has data but is thin or was INFERRED -> confirm/refine.
  - Group 2 (gap): the domain is genuinely empty -> ask the CEO a business question.

Design (docs/completeness-interview-map.md): ONE orchestrator + a registry of specialists, one per
DATA DOMAIN (not per hero card, not separate agents). The plumbing (detect -> ask -> validate ->
write -> resolve) is shared; only the per-domain data differs. Mirrors the seam pattern in
routers/_cascade.py and is kept import-light (no router imports) to avoid circular imports.

Two rules from the design:
  - Ask the formula's INPUTS, never the computed result (caja+gasto -> runway; impacto*prob ->
    nivel_riesgo). The DB/app computes the rest, which gives each specialist a free sanity check.
  - Validate the KIND of value the endpoint needs, not just the topic ("mention != answer"): the
    liquidez validator rejects financial *objectives* and demands a *current* snapshot.
"""
import os
from datetime import date, datetime, timezone

from fastapi import HTTPException
from sqlalchemy import text

from . import _cascade

# ── Domain constants ─────────────────────────────────────────────────────────
# The four direction cards. Goals may also be cross-cutting governance (Transversal, owned by the
# CEO); KPI config stays per-direction (the four cards), so it does NOT include Transversal.
AREAS_GOAL = {"Comercial", "Proyectos", "Investigacion", "Audiovisual"}
AREAS_GOAL_EXT = AREAS_GOAL | {"Transversal"}   # accepted areas for strategic goals
AREAS_RISK = AREAS_GOAL | {"Transversal"}
DIRECTORS = set(_cascade.AREA_DIRECTOR.values())
RISK_ESTADOS = {"monitoreado", "en_mitigacion", "critico", "resuelto"}
MILESTONE_ESTADOS = {"done", "in_progress", "delayed", "pendiente"}
PERIODS = {"mensual", "trimestral", "anual"}
TASK_PRIORIDADES = {"critica", "alta", "media", "baja"}

# A financial snapshot older than this is considered stale -> the liquidez panel needs a current one.
FINANCIAL_STALE_DAYS = 35
RUNWAY_SANITY_MAX = 60  # meses_respiracion plausible upper bound


def _today():
    return date.today()


# ── Detection helpers (deterministic, no LLM) ────────────────────────────────
def _count(db, sql, params=None):
    return int(db.execute(text(sql), params or {}).scalar() or 0)


# ── Validators (pure; return (ok, error, normalized)) ────────────────────────
def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _looks_like_objective(answer):
    """Lección A: reject a financial answer that supplies a TARGET instead of a current actual."""
    if answer.get("es_objetivo") or answer.get("objetivo"):
        return True
    blob = " ".join(str(answer.get(k, "")) for k in ("tipo", "nota", "label")).lower()
    return any(w in blob for w in ("objetivo", "meta", "target", "proyectad"))


def _is_current_date(value):
    if not value:
        return False
    try:
        d = value if isinstance(value, date) else datetime.fromisoformat(str(value)).date()
    except ValueError:
        return False
    return abs((_today() - d).days) <= FINANCIAL_STALE_DAYS


# ===== estrategia / strategic_goals ==========================================
def _detect_estrategia(db):
    n = _count(db, "SELECT COUNT(*) FROM strategic_goals")
    if n == 0:
        return "empty", []
    thin = db.execute(text(
        "SELECT codigo FROM strategic_goals WHERE peso_porcentaje IS NULL OR fecha_inicio IS NULL"
    )).fetchall()
    if thin:
        return "thin", [r[0] for r in thin]
    return "ok", []


def _validate_estrategia(answer):
    goals = answer.get("goals")
    if not isinstance(goals, list) or not goals:
        return False, "Falta la lista 'goals'.", None
    for g in goals:
        if g.get("area") not in AREAS_GOAL_EXT:
            return False, f"Área inválida: {g.get('area')}.", None
        peso = _num(g.get("peso_porcentaje"))
        if peso is not None and not (0 <= peso <= 100):
            return False, "peso_porcentaje debe estar entre 0 y 100.", None
        fi, ff = g.get("fecha_inicio"), g.get("fecha_fin_meta")
        if fi and ff and str(ff) <= str(fi):
            return False, "fecha_fin_meta debe ser posterior a fecha_inicio.", None
    return True, None, {"goals": goals}


def _write_estrategia(db, norm):
    n = 0
    for g in norm["goals"]:
        db.execute(text("""
            INSERT INTO strategic_goals (codigo, titulo, area, fecha_inicio, fecha_fin_meta, peso_porcentaje, estado)
            VALUES (:codigo, :titulo, :area, :fi, :ff, :peso, 'activo')
            ON CONFLICT (codigo) DO UPDATE SET
                titulo = EXCLUDED.titulo, area = EXCLUDED.area,
                fecha_inicio = COALESCE(EXCLUDED.fecha_inicio, strategic_goals.fecha_inicio),
                fecha_fin_meta = COALESCE(EXCLUDED.fecha_fin_meta, strategic_goals.fecha_fin_meta),
                peso_porcentaje = COALESCE(EXCLUDED.peso_porcentaje, strategic_goals.peso_porcentaje)
        """), {"codigo": g["codigo"], "titulo": g.get("titulo", g["codigo"]),
               "area": g["area"], "fi": g.get("fecha_inicio"), "ff": g.get("fecha_fin_meta"),
               "peso": g.get("peso_porcentaje")})
        n += 1
    return n


# ===== liquidez / financial_snapshots ========================================
def _detect_liquidez(db):
    row = db.execute(text("SELECT MAX(fecha) FROM financial_snapshots")).fetchone()
    latest = row[0] if row else None
    if not latest:
        return "empty", []
    if not _is_current_date(latest):
        return "empty", []  # stale snapshot -> needs a current one
    return "ok", []


def _validate_liquidez(answer):
    if _looks_like_objective(answer):
        return False, ("Eso parece un OBJETIVO, no la foto actual. Dame las cifras reales de hoy "
                       "(caja, reservas, crédito, gasto mensual)."), None
    fecha = answer.get("fecha") or _today().isoformat()
    if not _is_current_date(fecha):
        return False, "La fecha debe ser actual (de hoy). Dame la foto financiera vigente.", None
    caja = _num(answer.get("caja_operativa"))
    res = _num(answer.get("reservas_estrategicas"))
    cred = _num(answer.get("credito_disponible"))
    gasto = _num(answer.get("gasto_mensual_promedio"))
    if None in (caja, res, cred, gasto):
        return False, "Faltan cifras: caja_operativa, reservas_estrategicas, credito_disponible, gasto_mensual_promedio.", None
    if min(caja, res, cred) < 0 or gasto <= 0:
        return False, "Las cifras no pueden ser negativas y el gasto mensual debe ser > 0.", None
    liquidez = caja + res + cred
    meses = round(liquidez / gasto, 2)
    if not (0 <= meses <= RUNWAY_SANITY_MAX):
        return False, f"El runway calculado ({meses} meses) es implausible; revisa caja o gasto.", None
    return True, None, {"fecha": str(fecha), "caja": caja, "res": res, "cred": cred,
                        "gasto": gasto, "liquidez": liquidez, "meses": meses}


def _write_liquidez(db, n):
    # meses_respiracion is a PLAIN column (models.py + `NOT NULL DEFAULT 0` + the live Sheets importer
    # writes it explicitly), so the validated runway must be written here or it stores an eternal 0.
    # liquidez_total IS a GENERATED column in prod (ddl_v2) -> inserting it there would error; on the
    # SQLite test schema nothing computes it, so the writer supplies the validator's total instead.
    f = n["fecha"]
    d = datetime.strptime(f, "%Y-%m-%d").date() if isinstance(f, str) else f
    cols = ("fecha, caja_operativa, reservas_estrategicas, credito_disponible, "
            "gasto_mensual_promedio, meses_respiracion")
    vals = ":fecha, :caja, :res, :cred, :gasto, :meses"
    params = {"fecha": d, "caja": n["caja"], "res": n["res"], "cred": n["cred"],
              "gasto": n["gasto"], "meses": n["meses"]}
    if db.get_bind().dialect.name != "postgresql":
        cols += ", liquidez_total"
        vals += ", :liq"
        params["liq"] = n["liquidez"]
    db.execute(text(f"INSERT INTO financial_snapshots ({cols}) VALUES ({vals})"), params)
    return 1


# ===== riesgos / risks =======================================================
def _detect_riesgos(db):
    n = _count(db, "SELECT COUNT(*) FROM risks WHERE estado_mitigacion != 'resuelto'")
    return ("empty", []) if n == 0 else ("ok", [])


def _validate_riesgos(answer):
    risks = answer.get("risks")
    if not isinstance(risks, list) or not risks:
        return False, "Falta la lista 'risks'.", None
    norm = []
    for r in risks:
        imp, prob = r.get("impacto"), r.get("probabilidad")
        if not (isinstance(imp, int) and 1 <= imp <= 5):
            return False, "impacto debe ser un entero entre 1 y 5.", None
        if not (isinstance(prob, int) and 1 <= prob <= 5):
            return False, "probabilidad debe ser un entero entre 1 y 5.", None
        if r.get("area") not in AREAS_RISK:
            return False, f"Área de riesgo inválida: {r.get('area')}.", None
        estado = r.get("estado_mitigacion", "monitoreado")
        if estado not in RISK_ESTADOS:
            return False, f"estado_mitigacion inválido: {estado}.", None
        if not (r.get("descripcion") or "").strip():
            return False, "Cada riesgo necesita una descripción.", None
        norm.append({"descripcion": r["descripcion"], "area": r["area"], "impacto": imp,
                     "probabilidad": prob, "nivel": imp * prob, "estado": estado})
    return True, None, {"risks": norm}


def _write_riesgos(db, norm):
    # nivel_riesgo is GENERATED ALWAYS AS (impacto * probabilidad) in prod Postgres (ddl_v2) —
    # inserting it there errors with GeneratedAlways. The SQLite test schema declares it as a plain
    # NOT NULL column, so the non-Postgres writer must still supply the validator's imp * prob
    # (same split _write_liquidez applies to liquidez_total).
    n = 0
    is_pg = db.get_bind().dialect.name == "postgresql"
    cols = "descripcion, area, impacto, probabilidad, estado_mitigacion, origen"
    vals = ":desc, :area, :imp, :prob, :estado, 'ceo_manual'"
    if not is_pg:
        cols += ", nivel_riesgo"
        vals += ", :nivel"
    for r in norm["risks"]:
        params = {"desc": r["descripcion"], "area": r["area"], "imp": r["impacto"],
                  "prob": r["probabilidad"], "estado": r["estado"]}
        if not is_pg:
            params["nivel"] = r["nivel"]
        db.execute(text(f"INSERT INTO risks ({cols}) VALUES ({vals})"), params)
        n += 1
    return n


# ===== roadmap / roadmap_milestones ==========================================
def _detect_roadmap(db):
    n = _count(db, "SELECT COUNT(*) FROM roadmap_milestones")
    return ("empty", []) if n == 0 else ("ok", [])


def _milestone_anio(anio_raw, fecha_fin):
    """Target year for a hito: explicit `anio` (2024-2035), else the year parsed from `fecha_fin`,
    else None (honest — NEVER fabricate a year). Capturing this at the source is what makes the
    'Ejecución 2030' grid flip from DEMO (anio=NULL seed) to real planning data."""
    try:
        y = int(anio_raw)
        if 2024 <= y <= 2035:
            return y
    except (TypeError, ValueError):
        pass
    if fecha_fin:
        head = str(fecha_fin).strip()[:4]
        if head.isdigit():
            y = int(head)
            if 2000 <= y <= 2100:
                return y
    return None


def _validate_roadmap(answer):
    hitos = answer.get("milestones")
    if not isinstance(hitos, list) or not hitos:
        return False, "Falta la lista 'milestones'.", None
    norm = []
    for i, h in enumerate(hitos):
        if not (h.get("titulo") or "").strip():
            return False, "Cada hito necesita un título.", None
        estado = h.get("estado", "pendiente")
        if estado not in MILESTONE_ESTADOS:
            return False, f"estado de hito inválido: {estado}.", None
        fecha_fin = h.get("fecha_fin_planificada")
        norm.append({"titulo": h["titulo"], "orden": h.get("orden", i + 1), "estado": estado,
                     "area": h.get("area"), "fecha_fin": fecha_fin,
                     "anio": _milestone_anio(h.get("anio"), fecha_fin)})
    return True, None, {"milestones": norm}


def _write_roadmap(db, norm):
    n = 0
    for h in norm["milestones"]:
        db.execute(text("""
            INSERT INTO roadmap_milestones (titulo, orden, estado, area, anio, fecha_fin_planificada, pct_completado)
            VALUES (:titulo, :orden, :estado, :area, :anio, :fecha_fin, 0)
        """), {"titulo": h["titulo"], "orden": h["orden"], "estado": h["estado"],
               "area": h["area"], "anio": h["anio"], "fecha_fin": h["fecha_fin"]})
        n += 1
    return n


# ===== kpi_areas / area_kpi_config ===========================================
def _detect_kpi_areas(db):
    n = _count(db, "SELECT COUNT(DISTINCT area) FROM area_kpi_config")
    return ("ok", []) if n == 4 else ("empty", [])


def _validate_kpi_areas(answer):
    kpis = answer.get("kpis")
    if not isinstance(kpis, list) or not kpis:
        return False, "Falta la lista 'kpis'.", None
    norm = []
    for k in kpis:
        if k.get("area") not in AREAS_GOAL:
            return False, f"Área inválida: {k.get('area')}.", None
        period = k.get("period", "mensual")
        if period not in PERIODS:
            return False, f"Periodicidad inválida: {period}.", None
        if _num(k.get("target")) is None:
            return False, "target debe ser numérico.", None
        norm.append({"area": k["area"], "kpi_code": k.get("kpi_code", k["area"][:3].upper()),
                     "label": k.get("label", k["area"]), "target": _num(k["target"]), "period": period})
    return True, None, {"kpis": norm}


def _write_kpi_areas(db, norm):
    n = 0
    for k in norm["kpis"]:
        db.execute(text("""
            INSERT INTO area_kpi_config (area, kpi_code, label, target, period)
            VALUES (:area, :code, :label, :target, :period)
            ON CONFLICT (area) DO UPDATE SET
                kpi_code = EXCLUDED.kpi_code, label = EXCLUDED.label,
                target = EXCLUDED.target, period = EXCLUDED.period
        """), {"area": k["area"], "code": k["kpi_code"], "label": k["label"],
               "target": k["target"], "period": k["period"]})
        n += 1
    return n


# ===== planes / plans (enrich-only, inferred) ================================
def _detect_planes(db):
    n = _count(db, "SELECT COUNT(*) FROM plans")
    if n == 0:
        # Nothing to derive from yet: the cascade has not produced plans. "waiting" — never "ok",
        # so an empty system cannot report this domain as complete (vacuous truth).
        return "waiting", []
    thin = _count(db, "SELECT COUNT(*) FROM plans WHERE responsable IS NULL OR fecha_fin_planificada IS NULL")
    return ("thin", []) if thin else ("ok", [])


def _validate_planes(answer):
    if answer.get("responsable") and answer["responsable"] not in DIRECTORS:
        return False, f"responsable debe ser un director: {sorted(DIRECTORS)}.", None
    return True, None, answer


def _noop_write(db, norm):
    return 0  # enrich confirmations for plans/tasks don't insert new rows in v1


# ===== tareas / tasks (enrich-only) ==========================================
def _detect_tareas(db):
    n_tasks = _count(db, "SELECT COUNT(*) FROM tasks")
    if n_tasks == 0:
        # change reset-task-reader-switch: with the reader OFF the absence of tasks is explained by
        # the switch — waiting, regardless of active plans. The switch explains absence only: when
        # local tasks exist, the real status below is reported no matter the switch state.
        from .tasks import tasks_reader_enabled
        if not tasks_reader_enabled(db):
            return "waiting", []
        n_active = _count(db, "SELECT COUNT(*) FROM plans WHERE estado = 'activo'")
        if n_active == 0:
            # No tasks and no active plans to break down: waiting on the cascade, not complete.
            return "waiting", []
        return "thin", []
    return "ok", []


def _validate_tareas(answer):
    if answer.get("prioridad") and answer["prioridad"] not in TASK_PRIORIDADES:
        return False, f"prioridad inválida: {answer['prioridad']}.", None
    return True, None, answer


# ── Specialist registry ──────────────────────────────────────────────────────
# Each specialist is data: detection + question copy + validator + writer + target metadata.
# `panel_id` aligns with PANEL_REGISTRY (dashboard.py) so write-back can resolve a panel; None
# means the domain feeds cards indirectly (goals/plans feed pulso/2030 via the cascade).
SPECIALISTS = {
    "estrategia": {
        "panel_id": None, "target_table": "strategic_goals",
        "target_fields": ["codigo", "titulo", "area", "fecha_inicio", "fecha_fin_meta", "peso_porcentaje"],
        "ask_inputs": ["codigo", "titulo", "area", "fecha_inicio", "fecha_fin_meta", "peso_porcentaje"],
        "group_when_empty": "gap", "group_when_thin": "enrich",
        "question_gap": ("¿Cuáles son las metas estratégicas 2026-2030 de cada dirección? Por cada una: "
                         "código, área, fecha meta, peso relativo (%) y KPI con su target."),
        "question_enrich": "Estas metas no tienen fecha de inicio o peso: {detail}. ¿Desde cuándo arrancan y qué peso tienen frente a las demás de su área?",
        "detect": _detect_estrategia, "validate": _validate_estrategia, "write": _write_estrategia,
    },
    "planes": {
        "panel_id": None, "target_table": "plans",
        "target_fields": ["responsable", "fecha_inicio", "fecha_fin_planificada"],
        "ask_inputs": ["responsable", "fecha_inicio", "fecha_fin_planificada"],
        "group_when_empty": "enrich", "group_when_thin": "enrich",
        "question_gap": "Gentil propuso estos planes; ¿confirmas responsable y ventana de fechas o los ajustas?",
        "question_enrich": "Gentil propuso estos planes; ¿confirmas responsable y ventana de fechas o los ajustas?",
        "detect": _detect_planes, "validate": _validate_planes, "write": _noop_write,
    },
    "tareas": {
        "panel_id": "pulso", "target_table": "tasks",
        "target_fields": ["prioridad"], "ask_inputs": ["prioridad"],
        "group_when_empty": "enrich", "group_when_thin": "enrich",
        "question_gap": "¿Detallamos o priorizamos las tareas, o quedan como las generó Gentil?",
        "question_enrich": "¿Detallamos o priorizamos las tareas, o quedan como las generó Gentil?",
        "detect": _detect_tareas, "validate": _validate_tareas, "write": _noop_write,
    },
    "roadmap": {
        "panel_id": "2030", "target_table": "roadmap_milestones",
        "target_fields": ["titulo", "orden", "estado", "area", "anio", "fecha_fin_planificada"],
        "ask_inputs": ["titulo", "orden", "estado", "area", "anio", "fecha_fin_planificada"],
        "group_when_empty": "gap", "group_when_thin": "enrich",
        "question_gap": ("Lista los hitos macro de tu ruta a 2030 (12-16). Por cada uno: título, orden, "
                         "estado (done/in_progress/delayed/pendiente), año objetivo (2026-2030) y fecha objetivo."),
        "question_enrich": "Faltan año objetivo, fecha o estado en algunos hitos: {detail}. ¿Los completas?",
        "detect": _detect_roadmap, "validate": _validate_roadmap, "write": _write_roadmap,
    },
    "liquidez": {
        "panel_id": "caja", "target_table": "financial_snapshots",
        "target_fields": ["fecha", "caja_operativa", "reservas_estrategicas", "credito_disponible", "gasto_mensual_promedio"],
        # NOTE: ask the INPUTS only — never meses_respiracion / liquidez_total (computed).
        "ask_inputs": ["caja_operativa", "reservas_estrategicas", "credito_disponible", "gasto_mensual_promedio"],
        "group_when_empty": "gap", "group_when_thin": "gap",
        "question_gap": ("¿Cuál es tu foto financiera ACTUAL (a hoy): caja operativa, reservas estratégicas, "
                         "crédito disponible y gasto mensual promedio?"),
        "question_enrich": "¿Actualizas la foto financiera a hoy (caja, reservas, crédito, gasto mensual)?",
        "detect": _detect_liquidez, "validate": _validate_liquidez, "write": _write_liquidez,
    },
    "riesgos": {
        "panel_id": "riesgos", "target_table": "risks",
        "target_fields": ["descripcion", "area", "impacto", "probabilidad", "estado_mitigacion"],
        # NOTE: ask impacto + probabilidad — never nivel_riesgo (computed).
        "ask_inputs": ["descripcion", "area", "impacto", "probabilidad", "estado_mitigacion"],
        "group_when_empty": "gap", "group_when_thin": "gap",
        "question_gap": ("¿Cuáles son tus 5 riesgos principales? Por cada uno: descripción, área, "
                         "impacto (1-5), probabilidad (1-5) y estado de mitigación."),
        "question_enrich": "¿Agregas o actualizas riesgos? (descripción, área, impacto 1-5, probabilidad 1-5, estado)",
        "detect": _detect_riesgos, "validate": _validate_riesgos, "write": _write_riesgos,
    },
    "kpi_areas": {
        "panel_id": "area_drilldown", "target_table": "area_kpi_config",
        "target_fields": ["area", "kpi_code", "label", "target", "period"],
        "ask_inputs": ["area", "kpi_code", "label", "target", "period"],
        "group_when_empty": "gap", "group_when_thin": "enrich",
        "question_gap": "Para cada área, ¿cuál es EL KPI principal, su target y periodicidad (mensual/trimestral/anual)?",
        "question_enrich": "Faltan KPIs de algunas áreas. ¿Cuál es el KPI principal, target y periodicidad de cada una?",
        "detect": _detect_kpi_areas, "validate": _validate_kpi_areas, "write": _write_kpi_areas,
    },
}

# Explicitly excluded: daily_suggestions (heartbeat-generated, WF-GM-05) — never interviewed.
EXCLUDED_DOMAINS = {"daily_suggestions"}


# ── Optional LLM seam (mockable) ─────────────────────────────────────────────
def parse_freetext_answer(domain, text_answer):
    """Parse a free-text CEO answer into the structured shape a specialist expects.

    Honest 503 when no provider is configured (consistent with the cascade). Only invoked when an
    answer arrives as prose instead of structured fields. Structured answers never hit the network.
    """
    if not (os.environ.get("OPENAI_API_KEY") or os.environ.get("GROQ_API_KEY")):
        raise HTTPException(503, "No hay proveedor LLM configurado para interpretar texto libre.")
    # Real implementation would call the provider; left as a seam (mocked in tests).
    raise HTTPException(503, "Interpretación de texto libre no disponible.")


# ── Orchestrator ─────────────────────────────────────────────────────────────
def build_interview(db):
    """Detect thin/empty/waiting domains and return the question queue (does not persist)."""
    questions = []
    domain_status = {}
    domains_ok = 0
    for domain, spec in SPECIALISTS.items():
        status, detail = spec["detect"](db)
        domain_status[domain] = status
        if status == "ok":
            domains_ok += 1
            continue
        if status == "waiting":
            # Cascade-derived domain with nothing to derive from: there is no question the CEO
            # can answer, and it must never count toward completeness (empty DB reads 0%).
            continue
        grupo = spec["group_when_empty"] if status == "empty" else spec["group_when_thin"]
        if grupo == "gap":
            pregunta = spec["question_gap"]
        else:
            pregunta = spec["question_enrich"].replace("{detail}", ", ".join(map(str, detail)) or "—")
        questions.append({
            "domain": domain, "panel_id": spec["panel_id"], "grupo": grupo,
            "target_table": spec["target_table"], "campos_destino": spec["ask_inputs"],
            "pregunta": pregunta,
        })
    total = len(SPECIALISTS)
    # change reset-task-reader-switch: surface the reader switch + import progress so the answer
    # surface (Hub) can render the real reader state. Read-only — building the interview never
    # writes the switch.
    from .tasks import reader_importing, reader_last_import, tasks_reader_enabled
    tasks_reader = {
        "enabled": tasks_reader_enabled(db),
        "importing": reader_importing(db),
        "last_import": reader_last_import(db),
    }
    return {
        "questions": questions,
        "completitud_pct": round(domains_ok / total * 100) if total else 0,
        "domains_total": total, "domains_ok": domains_ok,
        "domain_status": domain_status,
        "tasks_reader": tasks_reader,
    }


def submit_answer(db, domain, answer):
    """Validate an answer against the domain specialist; on pass write target field(s) and resolve
    the panel; on fail raise 422 with the validation error (the question stays open)."""
    spec = SPECIALISTS.get(domain)
    if not spec:
        raise HTTPException(400, f"Dominio desconocido: {domain}. Opciones: {sorted(SPECIALISTS)}")
    if not isinstance(answer, dict):
        raise HTTPException(422, "El campo 'answer' debe ser un objeto con los insumos.")

    try:
        ok, error, norm = spec["validate"](answer)
        if not ok:
            raise HTTPException(422, error)

        written = spec["write"](db, norm)

        # change reset-task-reader-switch: the FIRST strategic goals wake the task reader with an
        # immediate import (no 2-hour wait). Only the estrategia domain flips the switch.
        if domain == "estrategia" and written:
            from .tasks import enable_tasks_reader_and_import
            try:
                enable_tasks_reader_and_import(db)
            except Exception:
                db.rollback()  # never fail the answer over the switch; the loop self-heals later

        panel_id = spec["panel_id"]
        if panel_id:
            db.execute(text("""
                UPDATE dashboard_pending_panels
                SET resuelto_en = :now
                WHERE panel_id = :pid AND resuelto_en IS NULL
            """), {"pid": panel_id, "now": datetime.now(timezone.utc)})
        db.commit()
        return {"domain": domain, "panel_id": panel_id, "registros_escritos": written, "estado": "resuelto"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"[{domain} error] {type(e).__name__}: {str(e)}")



import json
import os
from datetime import date, datetime, timezone, timedelta
from typing import List, Optional
from pydantic import BaseModel

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..db import get_db
from ..schemas import AlertItem, AreaSummary
from ..models import (
    RoadmapMilestone, Risk, FinancialSnapshot, FinancialFlow,
    DailySuggestion, AreaKpiConfig, DashboardPendingPanel,
)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

AREAS = ["Comercial", "Proyectos", "Investigacion", "Audiovisual"]
# Códigos de display por área (Dirección, NO Gerencia). DC=Dirección Comercial, DP=Dirección de
# Proyectos, DI=Dirección de Investigación, DA=Dirección Audiovisual. El dato en BD usa el NOMBRE
# del área (Comercial/Proyectos/…), no el código; estos códigos son solo etiqueta visual.
AREA_CODES = {"Comercial": "DC", "Proyectos": "DP", "Investigacion": "DI", "Audiovisual": "DA"}


def _active_cycle_anio(db: Session):
    """Year of the active planning cycle (`roadmap_cycles WHERE estado='activo'`), or None. The Pulso
    and drill-down scope to it so the legacy unlinked backlog (pre-Centro de Mando) stops poisoning the
    health (change scope-pulso-active-cycle). Returns None when there is no cycle (or no cycle table,
    e.g. isolated tests) -> callers fall back to the unscoped, all-time count."""
    try:
        row = db.execute(text(
            "SELECT anio FROM roadmap_cycles WHERE estado = 'activo' ORDER BY anio DESC LIMIT 1"
        )).fetchone()
        return row.anio if row else None
    except Exception:
        # No cycle table (isolated tests) — clear the failed statement so the session stays usable.
        try:
            db.rollback()
        except Exception:
            pass
        return None


# ─── /dashboard/summary ──────────────────────────────────────

@router.get("/summary", response_model=List[AreaSummary])
def get_summary(db: Session = Depends(get_db)):
    rows = db.execute(text("SELECT * FROM v_dashboard_ceo ORDER BY area")).fetchall()
    return [dict(r._mapping) for r in rows]


# ─── /dashboard/health-heatmap ───────────────────────────────

@router.get("/health-heatmap")
def get_health_heatmap(db: Session = Depends(get_db)):
    """Operational-health matrix per area (change rigorous-progress-math). Replaces the old 4-band traffic
    light with a CONTINUOUS 0–100 composite index built the way the composite-indicator literature
    (OECD/JRC) prescribes: normalize each signal to [0,1], then aggregate with a WEIGHTED GEOMETRIC mean
    so one collapsing dimension can't hide behind a healthy one (partial compensability — UNDP/HDI 2010).
    Three signals, each weighted by task importance (es_hito × prioridad) so a minor task ≠ a milestone
    task: on_schedule (age-weighted overdue backlog, 0.50), on_time (historical punctuality, 0.30), flow
    (1 − blocked, 0.20) — weights = the CEO's "el atraso manda". The company score is SIZE-WEIGHTED by
    each area's workload (not a simple average → no average-of-averages/Simpson distortion). RAG (≥80
    sano / 60–79 alerta / <60 crítico) is only a coloring of the continuous number."""
    rows = []
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    days = [(week_start + timedelta(days=i)).isoformat() for i in range(7)]

    # Scope the Pulso to the active planning cycle (change scope-pulso-active-cycle): the legacy unlinked
    # backlog (plan.anio NULL / past dates) no longer poisons health. No active cycle -> all-time count.
    anio = _active_cycle_anio(db)
    # Horizon + age dates as bound params (portable: Postgres `CURRENT_DATE + 7` and sqlite differ, but
    # date-string compare works on both). d7ago/d30ago drive the age-weighted backlog severity bands.
    horizons = {
        "today": today.isoformat(),
        "d7": (today + timedelta(days=7)).isoformat(),
        "d30": (today + timedelta(days=30)).isoformat(),
        "d7ago": (today - timedelta(days=7)).isoformat(),
        "d30ago": (today - timedelta(days=30)).isoformat(),
    }
    EPS = 0.02
    W_SCHED, W_ONTIME, W_FLOW = 0.50, 0.30, 0.20   # CEO decision: "el atraso manda"

    def _q(p):
        """Build the per-area weighted-aggregate SELECT. p = column prefix ('t.' scoped, '' unscoped).
        Task weight = es_hito × prioridad (a milestone/high-priority task weighs more than an errand)."""
        W = ("(CASE WHEN {p}es_hito THEN 3.0 ELSE 1.0 END) * "
             "(CASE {p}prioridad WHEN 'alta' THEN 1.5 WHEN 'baja' THEN 0.5 ELSE 1.0 END)").format(p=p)
        e, f, fc = p + "estado", p + "fecha_vencimiento", p + "fecha_completada"
        return (
            f"COUNT(*) FILTER (WHERE {e} = 'completada') AS done, "
            f"COUNT(*) FILTER (WHERE {e} = 'bloqueada') AS blocked, "
            f"COUNT(*) FILTER (WHERE {e} NOT IN ('completada','cancelada') AND {f} < :today) AS overdue, "
            f"COUNT(*) FILTER (WHERE {e} NOT IN ('completada','cancelada') AND {f} = :today) AS due_hoy, "
            f"COUNT(*) FILTER (WHERE {e} NOT IN ('completada','cancelada') AND {f} > :today AND {f} <= :d7) AS due_sem, "
            f"COUNT(*) FILTER (WHERE {e} NOT IN ('completada','cancelada') AND {f} > :d7 AND {f} <= :d30) AS due_mes, "
            f"COUNT(*) FILTER (WHERE {e} <> 'cancelada') AS total, "
            f"COALESCE(SUM(CASE WHEN {e} IN ('pendiente','bloqueada') THEN {W} ELSE 0 END), 0) AS w_open, "
            f"COALESCE(SUM(CASE WHEN {e} = 'bloqueada' THEN {W} ELSE 0 END), 0) AS w_blocked, "
            f"COALESCE(SUM(CASE WHEN {f} IS NOT NULL AND {e} <> 'cancelada' THEN {W} ELSE 0 END), 0) AS w_due, "
            f"COALESCE(SUM(CASE WHEN {e} = 'completada' AND {fc} IS NOT NULL AND {f} IS NOT NULL "
            f"AND {fc} <= {f} THEN {W} ELSE 0 END), 0) AS w_ontime, "
            f"COALESCE(SUM(CASE WHEN {e} IN ('pendiente','bloqueada') AND {f} < :today THEN {W} * "
            f"(CASE WHEN {f} < :d30ago THEN 1.0 WHEN {f} < :d7ago THEN 0.7 ELSE 0.3 END) ELSE 0 END), 0) AS sev, "
            f"COALESCE(SUM(CASE WHEN {e} <> 'cancelada' THEN {W} ELSE 0 END), 0) AS w_total"
        )

    SCOPED = text(
        "SELECT " + _q("t.") +
        " FROM tasks t LEFT JOIN plans p ON p.id = t.plan_id "
        "WHERE t.area = :area "
        "AND (p.anio = :anio OR (t.plan_id IS NULL AND t.google_task_id IS NOT NULL))"
    )
    UNSCOPED = text("SELECT " + _q("") + " FROM tasks WHERE area = :area")

    def _health(r):
        """Continuous 0–100 geometric composite from the weighted aggregates. Returns
        (health, g_ontime, backlog_ratio); g_ontime is None when there is no dated work. backlog_ratio is
        the RAW share of open weight that is overdue-aged (reported as-is, before the EPS floor)."""
        w_open = float(r.w_open or 0)
        if w_open > 0:
            backlog_ratio = min(float(r.sev or 0) / w_open, 1.0)
            blocked_ratio = min(float(r.w_blocked or 0) / w_open, 1.0)
            g_sched = max(1.0 - backlog_ratio, EPS)
            g_flow = max(1.0 - blocked_ratio, EPS)
        else:
            backlog_ratio = 0.0                              # nothing open → no backlog/blocked drag
            g_sched, g_flow = 1.0, 1.0
        w_due = float(r.w_due or 0)
        g_ontime = (float(r.w_ontime or 0) / w_due) if w_due > 0 else None
        if g_ontime is not None:
            go = max(g_ontime, EPS)
            health = 100.0 * (g_sched ** W_SCHED) * (go ** W_ONTIME) * (g_flow ** W_FLOW)
        else:                                                # no punctuality signal → renormalize weights
            s = W_SCHED + W_FLOW
            health = 100.0 * (g_sched ** (W_SCHED / s)) * (g_flow ** (W_FLOW / s))
        return health, g_ontime, backlog_ratio

    def _nivel(score):                                        # continuous → RAG band (heatmap coloring only)
        if score >= 80:
            return 4
        if score >= 60:
            return 3
        if score >= 40:
            return 2
        return 1

    for area in AREAS:
        if anio is not None:
            r = db.execute(SCOPED, {"area": area, "anio": anio, **horizons}).fetchone()
        else:
            r = db.execute(UNSCOPED, {"area": area, **horizons}).fetchone()

        real_total = int(r.total or 0)
        if real_total == 0:                                   # no tasks → honest "sin datos", never faked
            rows.append({"name": area, "code": AREA_CODES[area], "score": None, "nivel": None,
                         "total": 0, "pendiente": 0, "overdue": 0, "blocked": 0, "done": 0,
                         "on_time_pct": None, "backlog_sev": None, "w_total": 0,
                         "days": [0] * 7, "periodo": None})
            continue

        done = int(r.done or 0)
        blocked = int(r.blocked or 0)
        overdue = int(r.overdue or 0)
        pendiente = max(real_total - done, 0)
        health, g_ontime, backlog_ratio = _health(r)
        score = round(health)
        nivel = _nivel(score)

        # period driver (change period-aware-pulso): cumulative "due within horizon" (hoy ⊆ semana ⊆ mensual).
        due_hoy = int(r.due_hoy or 0)
        vencen = {"hoy": due_hoy,
                  "semana": due_hoy + int(r.due_sem or 0),
                  "mensual": due_hoy + int(r.due_sem or 0) + int(r.due_mes or 0)}
        # The continuous score IS the real operational health (overdue + punctuality dominate). With ~no
        # forward-scheduled work it does not move between horizons — honest — and sin_agenda says so.
        periodo = {p: {"score": score, "nivel": nivel, "vencen": vencen[p], "sin_agenda": vencen[p] == 0}
                   for p in ("hoy", "semana", "mensual")}

        rows.append({
            "name": area, "code": AREA_CODES[area],
            "score": score, "nivel": nivel,
            "total": real_total, "pendiente": pendiente, "overdue": overdue,
            "blocked": blocked, "done": done,
            "on_time_pct": round(g_ontime * 100, 1) if g_ontime is not None else None,
            "backlog_sev": round(backlog_ratio * 100, 1),     # raw % of open weight that is overdue-aged
            "w_total": round(float(r.w_total or 0), 2),
            "days": [nivel] * 7,
            "periodo": periodo,
        })

    scored = [x for x in rows if x["score"] is not None]
    # Company score: SIZE-WEIGHTED by each area's workload (avoids average-of-averages distortion). We
    # also expose the equal-weighted figure so the weighting is transparent, never hidden.
    wsum = sum(x["w_total"] for x in scored)
    salud_global = (round(sum(x["score"] * x["w_total"] for x in scored) / wsum) if wsum
                    else (round(sum(x["score"] for x in scored) / len(scored)) if scored else None))
    salud_global_simple = round(sum(x["score"] for x in scored) / len(scored)) if scored else None
    salud_global_periodo = {}
    for p in ("hoy", "semana", "mensual"):
        sp = [(x["periodo"][p]["score"], x["w_total"]) for x in rows if x.get("periodo")]
        sw = sum(w for _, w in sp)
        salud_global_periodo[p] = (round(sum(s * w for s, w in sp) / sw) if sw
                                   else (round(sum(s for s, _ in sp) / len(sp)) if sp else None))
    return {"salud_global": salud_global, "salud_global_simple": salud_global_simple,
            "salud_global_periodo": salud_global_periodo,
            "delta": 0, "days": days, "areas": rows, "anio": anio}


# ─── /dashboard/roadmap-2030 ─────────────────────────────────

@router.get("/roadmap-2030")
def get_roadmap_2030(db: Session = Depends(get_db)):
    milestones = (
        db.query(RoadmapMilestone)
        .order_by(RoadmapMilestone.orden)
        .all()
    )
    from .roadmap import milestone_avance, milestone_sin_respaldo, hito_real_work  # lazy: avoid cycle
    done  = sum(1 for m in milestones if m.estado == "done")
    prog  = sum(1 for m in milestones if m.estado == "in_progress")
    late  = sum(1 for m in milestones if m.estado == "delayed")
    total = len(milestones)
    # change rigorous-progress-math: budget-weighted EVM roll-up (EV/BAC style), NOT a simple average.
    # Each hito earns an EVIDENCE-weighted avance (a 'done' is capped by its real task evidence, STRICT
    # policy); the vision % is Σ(peso·avance)/Σpeso so a make-or-break hito outweighs filler. peso
    # defaults to 1 → until the CEO assigns tiers this equals the equal-weight baseline, which we also
    # expose (v2030_pct_equal) so the sensitivity of the weighting is visible, never hidden.
    work = hito_real_work(db)
    def _av(m):
        info = work.get(m.id, {"wpct": 0.0, "has_tasks": False})
        return milestone_avance(m.estado, info["wpct"], info["has_tasks"])
    pairs = [(float(m.peso or 1), _av(m)) for m in milestones]
    wsum = sum(w for w, _ in pairs)
    v2030 = round(sum(w * a for w, a in pairs) / wsum, 1) if wsum else 0
    v2030_equal = round(sum(a for _, a in pairs) / total, 1) if total else 0
    sin_respaldo = sum(1 for m in milestones
                       if milestone_sin_respaldo(m.estado, work.get(m.id, {}).get("wpct", 0),
                                                 work.get(m.id, {}).get("has_tasks", False)))

    # change unify-strategy-execution: NO fabricated defaults. Each arc is null when its source is
    # empty so the UI shows "sin datos" + a DEMO badge (per /dashboard/completeness), never a made-up
    # number. The previous silent 78 (entregas) / 22 (riesgo) defaults are removed.
    cap_row = db.execute(text("""
        SELECT AVG(pct_completado_real) AS pct, COUNT(*) AS n
        FROM plans WHERE area = 'Comercial' AND estado = 'activo'
    """)).fetchone()
    captacion = round(float(cap_row.pct), 1) if cap_row and cap_row.n else None

    ent_row = db.execute(text("""
        SELECT
            COUNT(*) FILTER (WHERE estado='completada' AND fecha_completada <= fecha_vencimiento) AS on_time,
            COUNT(*) FILTER (WHERE estado='completada') AS total_done
        FROM tasks WHERE es_hito = TRUE
    """)).fetchone()
    entregas = round(ent_row.on_time / ent_row.total_done * 100, 1) if ent_row.total_done else None

    risk_row = db.execute(text("""
        SELECT AVG(nivel_riesgo / 25.0 * 100) AS riesgo_pct, COUNT(*) AS n
        FROM risks WHERE estado_mitigacion != 'resuelto'
    """)).fetchone()
    riesgo = round(float(risk_row.riesgo_pct), 1) if risk_row and risk_row.n else None

    has_data = total > 0
    return {
        "v2030_pct": v2030,
        "v2030_pct_equal": v2030_equal,                # sensitivity baseline (equal weights, peso ignored)
        "has_data": has_data,                          # drives the DATOS REALES vs DEMO badge
        "data_state": "real" if has_data else "empty",
        "total_milestones": total,
        "done": done,
        "in_progress": prog,
        "delayed": late,
        "sin_respaldo": sin_respaldo,   # 'done' hitos with no completed task backing them
        "arcs": [
            {"label": "EJE ESTRAT.", "value": v2030 if has_data else None, "color": "#0E0E0E"},
            {"label": "CAPTACIÓN",   "value": captacion,                   "color": "#00FF41"},
            {"label": "ENTREGAS",    "value": entregas,                    "color": "#0E0E0E"},
            {"label": "RIESGO",      "value": riesgo,                      "color": "#E8A02C"},
        ],
        "milestones": [
            {"id": m.id, "titulo": m.titulo, "estado": m.estado, "orden": m.orden,
             "anio": m.anio, "trimestre": m.trimestre,
             "pct_completado": float(m.pct_completado)}
            for m in milestones
        ],
    }


# ─── /dashboard/financial-snapshots ─────────────────────────

@router.get("/financial-snapshots")
def get_financial_snapshots(db: Session = Depends(get_db)):
    snapshots = (
        db.query(FinancialSnapshot)
        .order_by(FinancialSnapshot.fecha.desc())
        .limit(12)
        .all()
    )
    latest = snapshots[0] if snapshots else None
    flows = db.query(FinancialFlow).order_by(FinancialFlow.fecha_estimada).all()

    # change rigorous-progress-math: separate CASH runway (cash you actually hold: caja + reservas) from
    # FUNDED runway (+ an undrawn credit line, which is contingent capital, NOT cash — CFI / startup
    # finance doctrine). The headline the CEO should steer by is cash_runway; funded is the cushion.
    # NOTE: gasto_mensual_promedio is GROSS burn (no recurring-income field yet) → runway is conservative.
    def _runway_rag(m):
        if m is None:
            return None
        if m < 3:
            return "rojo"      # crisis zone
        if m < 6:
            return "ambar"     # danger zone — act / raise now
        if m < 12:
            return "ok"        # healthy, plan next quarter
        return "verde"         # comfortable

    if latest:
        _caja = float(latest.caja_operativa)
        _res = float(latest.reservas_estrategicas)
        _cred = float(latest.credito_disponible)
        _gasto = float(latest.gasto_mensual_promedio)
        cash_runway = round((_caja + _res) / _gasto, 1) if _gasto else None
        funded_runway = round((_caja + _res + _cred) / _gasto, 1) if _gasto else None
        latest_out = {
            "liquidez_total":       float(latest.liquidez_total),
            "caja_operativa":       _caja,
            "reservas_estrategicas": _res,
            "credito_disponible":   _cred,
            "gasto_mensual_promedio": _gasto,
            "meses_respiracion":    float(latest.meses_respiracion),
            "cash_runway_meses":    cash_runway,      # caja + reservas (lo que de verdad tienes)
            "funded_runway_meses":  funded_runway,    # + crédito comprometido (colchón, no caja)
            "cash_runway_rag":      _runway_rag(cash_runway),
            "funded_runway_rag":    _runway_rag(funded_runway),
        }
    else:
        latest_out = None

    # change real-financial-source: la caja sale del libro real (MOVIMIENTOS 2026, lo lleva el Director
    # Comercial y Financiero), no de un placeholder. Exponemos la fuente para "Ver / Descargar (.xlsx)".
    # Defensivo: la tabla puede no existir en el sqlite de tests -> source=None.
    source = None
    try:
        srow = db.execute(text(
            "SELECT fuente, spreadsheet_id, ultima_sincronizacion, estado "
            "FROM financial_data_sources ORDER BY ultima_sincronizacion DESC LIMIT 1"
        )).fetchone()
        if srow:
            sid = srow.spreadsheet_id
            ts = srow.ultima_sincronizacion
            ts_iso = ts.isoformat() if hasattr(ts, "isoformat") else (str(ts) if ts else None)
            source = {
                "fuente": srow.fuente,
                "spreadsheet_id": sid,
                "estado": srow.estado,
                "ultima_sincronizacion": ts_iso,
                "view_url": f"https://docs.google.com/spreadsheets/d/{sid}/edit" if sid else None,
                "download_url": f"https://docs.google.com/spreadsheets/d/{sid}/export?format=xlsx" if sid else None,
            }
    except Exception:
        source = None

    return {
        "snapshots": [
            {
                "fecha": str(s.fecha),
                "liquidez_total":       float(s.liquidez_total),
                "caja_operativa":       float(s.caja_operativa),
                "reservas_estrategicas":float(s.reservas_estrategicas),
                "credito_disponible":   float(s.credito_disponible),
                "meses_respiracion":    float(s.meses_respiracion),
            }
            for s in reversed(snapshots)
        ],
        "latest": latest_out,
        "source": source,
        "flows": [
            {"tipo": f.tipo, "descripcion": f.descripcion,
             "monto": float(f.monto), "horizonte_dias": f.horizonte_dias,
             "fecha_estimada": str(f.fecha_estimada) if f.fecha_estimada else None,
             "origen": f.origen}
            for f in flows
        ],
    }


# ─── /dashboard/openclaw-executive-feed ──────────────────────

@router.get("/openclaw-executive-feed")
def get_executive_feed(db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    cache = db.execute(
        text("SELECT content, expires_at FROM executive_feed_cache WHERE scope='global' LIMIT 1")
    ).fetchone()

    if cache and cache.expires_at and cache.expires_at > now:
        return cache.content

    # Cache miss: construir feed desde datos reales
    next_milestone = (
        db.query(RoadmapMilestone)
        .filter(RoadmapMilestone.estado.in_(["in_progress", "delayed"]))
        .order_by(RoadmapMilestone.orden)
        .first()
    )
    top_risk = (
        db.query(Risk)
        .filter(Risk.estado_mitigacion != "resuelto")
        .order_by(Risk.nivel_riesgo.desc())
        .first()
    )
    suggestions = (
        db.query(DailySuggestion)
        .filter(DailySuggestion.fecha == date.today(), DailySuggestion.estado == "pendiente")
        .limit(3)
        .all()
    )

    feed = {
        "foco_semana": suggestions[0].titulo if suggestions else "Sin foco definido para hoy",
        "hitos_activos": [
            {"titulo": next_milestone.titulo, "area": next_milestone.area or "—",
             "prioridad": 1}
        ] if next_milestone else [],
        "proximo_hito_critico": {
            "titulo": next_milestone.titulo,
            "area": next_milestone.area or "—",
            "pct_completado": float(next_milestone.pct_completado),
        } if next_milestone else None,
        "riesgo_abierto": {
            "titulo": top_risk.descripcion,
            "nivel": f"Nivel {top_risk.nivel_riesgo}/25",
            "estado": top_risk.estado_mitigacion,
        } if top_risk else None,
    }

    # Actualizar caché (30 min)
    expires = now + timedelta(minutes=30)
    db.execute(text("""
        INSERT INTO executive_feed_cache (scope, content, generated_at, expires_at, trigger_event)
        VALUES ('global', CAST(:content AS jsonb), NOW(), :expires, 'api_request')
        ON CONFLICT (scope) DO UPDATE
            SET content=EXCLUDED.content, generated_at=EXCLUDED.generated_at,
                expires_at=EXCLUDED.expires_at, trigger_event=EXCLUDED.trigger_event
    """), {"content": json.dumps(feed), "expires": expires})
    db.commit()
    return feed


# ─── /dashboard/suggestions ──────────────────────────────────

@router.get("/suggestions")
def get_suggestions(db: Session = Depends(get_db)):
    rows = (
        db.query(DailySuggestion)
        .filter(DailySuggestion.fecha == date.today())
        .order_by(DailySuggestion.id)
        .all()
    )
    return [
        {"id": s.id, "tag": s.tag, "titulo": s.titulo, "cuerpo": s.cuerpo, "estado": s.estado}
        for s in rows
    ]


# ─── /dashboard/suggestions/generate (WF-GM-05 Heartbeat) ────

TAGS_BY_AREA = {"Comercial": "DC", "Proyectos": "DP", "Investigacion": "DI", "Audiovisual": "DA"}

TAG_ORDER = {"crítico": 0, "urgente": 1, "estratégico": 2, "oportunidad": 3}

# La 'Lectura del día' la redacta el cerebro REAL de Gentil (gateway OpenClaw), no una llamada directa
# a Groq. Coherente con el chat (routers/chat.py también proxya a OpenClaw, model="openclaw"). El
# contexto sigue armándose de forma determinista en Python (las queries de abajo); OpenClaw solo razona
# y redacta. Tokens en el env del servicio (Easypanel), nunca hardcodeados.
OPENCLAW_URL = os.environ.get("OPENCLAW_URL", "http://172.18.0.1:18789/v1/chat/completions")
OPENCLAW_TOKEN = os.environ.get("OPENCLAW_TOKEN", "")


def _strip_md(s: str) -> str:
    """Quita negritas markdown y comillas envolventes de un campo."""
    s = (s or "").replace("**", "").strip()
    if len(s) >= 2 and s[0] in "\"'“”" and s[-1] in "\"'“”":
        s = s[1:-1].strip()
    return s


def _parse_suggestions_json(raw: str):
    """Convierte la respuesta de OpenClaw en una lista de {tag, titulo, cuerpo}. Acepta DOS formatos,
    porque el gateway es agéntico/conversacional y, con tool_choice=none, tiende a devolver texto y no
    JSON estricto:
      (1) un array JSON (tolerando fences markdown o prosa alrededor);
      (2) líneas 'TAG | Título | Cuerpo' (formato que sí obedece de forma fiable).
    Lanza ValueError si no logra extraer al menos una sugerencia."""
    import re as _re
    raw = (raw or "").strip()

    # ── intento 1: array JSON ──
    j = raw
    if j.startswith("```"):
        j = j.split("```")[1]
        if j.lower().startswith("json"):
            j = j[4:]
    j = j.strip()
    parsed = None
    try:
        parsed = json.loads(j)
    except Exception:
        m = _re.search(r"\[.*\]", j, _re.DOTALL)
        if m:
            try:
                parsed = json.loads(m.group(0))
            except Exception:
                parsed = None
    if isinstance(parsed, list) and parsed:
        return parsed

    # ── intento 2: líneas 'TAG | Título | Cuerpo' ──
    out = []
    for line in raw.splitlines():
        if line.count("|") < 2:
            continue
        parts = [p.strip() for p in line.split("|")]
        tag = _re.sub(r"[^A-Za-z]", "", parts[0]).upper()[:4]
        if tag not in {"DC", "DP", "DI", "DA", "GM"}:
            continue
        titulo = _strip_md(parts[1])
        cuerpo = _strip_md(" | ".join(parts[2:]))
        if titulo:
            out.append({"tag": tag, "titulo": titulo, "cuerpo": cuerpo})
    if out:
        return out

    raise ValueError("OpenClaw no devolvió sugerencias parseables (ni JSON ni 'TAG | título | cuerpo').")


@router.post("/suggestions/generate")
def generate_daily_suggestions(db: Session = Depends(get_db)):
    """
    Genera las 3 sugerencias diarias del CEO (WF-GM-05 · Heartbeat Matutino).
    Construye un resumen determinista del estado del sistema (tareas/riesgos/hitos/caja/
    oportunidades) y se lo manda al cerebro de Gentil vía el gateway OpenClaw para que
    redacte 3 movimientos concretos. Guarda en daily_suggestions.
    """
    if not OPENCLAW_TOKEN:
        raise HTTPException(503, "OPENCLAW_TOKEN no configurado.")

    today = date.today()

    # Borrar sugerencias previas del día para regenerar limpio
    db.execute(text("DELETE FROM daily_suggestions WHERE fecha = :today"), {"today": today})

    # ── Recopilar estado del sistema (se ordena por GRAVEDAD, no por recencia) ────
    financiero_r = db.execute(text("""
        SELECT caja_operativa, liquidez_total, meses_respiracion, gasto_mensual_promedio
        FROM financial_snapshots ORDER BY fecha DESC LIMIT 1
    """)).fetchone()

    riesgos_r = db.execute(text("""
        SELECT descripcion, area, nivel_riesgo, estado_mitigacion
        FROM risks WHERE estado_mitigacion != 'resuelto'
        ORDER BY nivel_riesgo DESC LIMIT 8
    """)).fetchall()

    hitos_r = db.execute(text("""
        SELECT titulo, estado, area FROM roadmap_milestones
        WHERE estado IN ('delayed','in_progress') ORDER BY orden LIMIT 6
    """)).fetchall()

    # Backlog ACCIONABLE: las 2 tareas más vencidas por área (con título, no solo conteo).
    backlog_r = db.execute(text("""
        SELECT area, titulo, (CURRENT_DATE - fecha_vencimiento) AS dias FROM (
            SELECT area, titulo, fecha_vencimiento,
                   ROW_NUMBER() OVER (PARTITION BY area ORDER BY fecha_vencimiento ASC) AS rn
            FROM tasks
            WHERE estado NOT IN ('completada','cancelada') AND fecha_vencimiento < CURRENT_DATE
        ) t WHERE rn <= 2 ORDER BY dias DESC LIMIT 8
    """)).fetchall()
    total_vencidas = db.execute(text("""
        SELECT COUNT(*) FROM tasks
        WHERE estado NOT IN ('completada','cancelada') AND fecha_vencimiento < CURRENT_DATE
    """)).scalar() or 0

    # Oportunidades PRIORITARIA con cierre próximo. Defensivo: la tabla puede no existir aún.
    try:
        oportunidades_r = db.execute(text("""
            SELECT nombre, entidad, adn_score, fecha_cierre,
                   (fecha_cierre - CURRENT_DATE) AS dias_cierre
            FROM oportunidades
            WHERE prioridad = 'PRIORITARIA'
              AND estado_seguimiento <> 'descartada'
              AND (fecha_cierre IS NULL OR fecha_cierre >= CURRENT_DATE)
            ORDER BY fecha_cierre ASC NULLS LAST, adn_score DESC
            LIMIT 3
        """)).fetchall()
    except Exception:
        oportunidades_r = []

    # ── Construir resumen RANKEADO POR GRAVEDAD para el LLM ───────
    lines = [
        f"ESTADO DEL CENTRO DE MANDO — {today.strftime('%d %b %Y')}",
        "(ordenado por gravedad: lo de arriba pesa más que lo de abajo)",
    ]

    # 1) CAJA / RUNWAY — la señal más crítica
    if financiero_r:
        runway = float(financiero_r.meses_respiracion or 0)
        caja = float(financiero_r.caja_operativa or 0) / 1_000_000
        liq = float(financiero_r.liquidez_total or 0) / 1_000_000
        flag = "🔴 CRÍTICO" if runway < 3 else ("🟠 ATENCIÓN" if runway < 6 else "🟢")
        extra = " La operación corre riesgo de quedarse sin caja; esto es lo más urgente." if runway < 3 else ""
        lines.append(
            f"[1·CAJA] {flag} Runway {runway:.1f} meses (caja {caja:.1f}M · con crédito {liq:.1f}M COP)."
            f"{extra}"
        )

    # 2) RIESGOS EN UMBRAL DE ESCALACIÓN (gobernanza: I×P ≥ 16)
    altos = [r for r in riesgos_r if (r.nivel_riesgo or 0) >= 16]
    for r in altos:
        lines.append(
            f"[2·RIESGO-ESCALACIÓN] 🔴 {r.nivel_riesgo}/25 [{r.area}]: {r.descripcion} "
            f"({r.estado_mitigacion}) — gobernanza exige contención hoy."
        )
    for r in [x for x in riesgos_r if (x.nivel_riesgo or 0) < 16][:3]:
        lines.append(f"[riesgo-menor] {r.nivel_riesgo}/25 [{r.area}]: {r.descripcion} ({r.estado_mitigacion})")

    # 3) HITOS RETRASADOS (los en-curso van como contexto, no como urgencia)
    for m in [x for x in hitos_r if x.estado == "delayed"]:
        lines.append(f"[3·HITO-RETRASADO] 🟠 [{m.area or '—'}]: {m.titulo}")
    for m in [x for x in hitos_r if x.estado != "delayed"]:
        lines.append(f"[hito-en-curso] [{m.area or '—'}]: {m.titulo}")

    # 4) BACKLOG ACCIONABLE (títulos concretos, no "revisa las N vencidas")
    if total_vencidas:
        lines.append(f"[4·BACKLOG] {total_vencidas} tareas vencidas en total. Las más atrasadas (por título):")
        for b in backlog_r:
            lines.append(f"    · [{b.area}] «{b.titulo}» — {int(b.dias)} días vencida")

    # 5) OPORTUNIDADES (lo MENOS urgente salvo cierre inminente; NO sobre-priorizar)
    for o in oportunidades_r:
        if o.fecha_cierre is None:
            cierre = "sin fecha de cierre"
        else:
            dd = int(o.dias_cierre) if o.dias_cierre is not None else None
            cierre = f"cierra {o.fecha_cierre}" + (f" (en {dd} días)" if dd is not None else "")
        lines.append(f"[5·OPORTUNIDAD] ADN {o.adn_score}/100 [Comercial]: {o.nombre} ({o.entidad or 's/entidad'}, {cierre})")

    system_context = "\n".join(lines)

    prompt = f"""{system_context}

Eres Gentil, el segundo cerebro de Clementino (CEO de La Falla D.F.).
Genera exactamente 6 movimientos para HOY, ORDENADOS de más urgente a menos urgente (los primeros se muestran primero), siguiendo ESTAS REGLAS DE PRIORIZACIÓN:
1. Si la CAJA está en 🔴 CRÍTICO, el PRIMER movimiento DEBE atacar la liquidez (acelerar el cobro más grande, activar línea de crédito, aplazar/recortar gasto). No lo dejes pasar por perseguir otra cosa.
2. Todo RIESGO en umbral de escalación (🔴 ≥16/25) merece un movimiento de contención HOY, arriba.
3. Después: HITOS RETRASADOS y BACKLOG — usa tareas CONCRETAS por su título (no "revisa las vencidas").
4. OPORTUNIDADES: solo después de lo urgente, o si una cierra en menos de 15 días. NO son la prioridad por defecto.

REGLAS ADICIONALES:
- DIVERSIFICA: entre los 6, cubre al menos 4 áreas o temas DISTINTOS. MÁXIMO 2 movimientos sobre convocatorias/oportunidades.
- Cada movimiento: CONCRETO, ejecutable HOY, empieza con un verbo, con su área.
- Gobernanza La Falla: riesgo I×P≥16 → escalar; oportunidad >$100M → escalar; decisión de patrimonio/convenios → escalar.

FORMATO DE SALIDA ESTRICTO — exactamente 6 líneas, una por movimiento (la más urgente primero):
TAG | Título (empieza con verbo) | Cuerpo (1-2 oraciones: por qué hoy y qué hacer)
donde TAG ∈ {{DC, DP, DI, DA, GM}} (GM = Gerencia/Transversal, p. ej. caja). No escribas NADA más: ni numeración, ni encabezados, ni markdown, ni comentarios.
Ejemplo:
GM | Asegurar la caja antes de que el runway llegue a cero | El runway es de ~1 mes; hoy acelera el cobro pendiente más grande y confirma cuánto crédito hay disponible para cubrir el mes."""

    # ── Llamar al cerebro de Gentil (OpenClaw) ───────────────────
    # El gateway YA tiene la persona de Gentil; solo le pasamos el contexto + el formato pedido.
    try:
        import requests as _rq
        ocresp = _rq.post(
            OPENCLAW_URL,
            headers={"Authorization": f"Bearer {OPENCLAW_TOKEN}", "Content-Type": "application/json"},
            # tool_choice="none": el gateway tiene a Gentil con herramientas FORZADas (para el chat);
            # sin esto, una petición de generación pura devuelve "Failed to call a function". Apagar las
            # tools deja a Gentil redactar texto normal.
            json={"model": "openclaw", "tool_choice": "none", "messages": [
                {"role": "system", "content": (
                    "Vas a generar la 'Lectura del día' del CEO: exactamente 6 movimientos, ordenados de "
                    "más urgente a menos urgente. Devuelve SOLO 6 líneas con el formato "
                    "'TAG | Título | Cuerpo', sin texto adicional."
                )},
                {"role": "user", "content": prompt},
            ]},
            timeout=120,
        )
        if ocresp.status_code != 200:
            raise HTTPException(502, f"OpenClaw gateway error {ocresp.status_code}: {ocresp.text[:200]}")
        raw = ocresp.json()["choices"][0]["message"]["content"] or ""
        suggestions = _parse_suggestions_json(raw)  # ValueError -> except de abajo -> 500
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Error generando sugerencias: {str(e)[:200]}")

    # ── Persistir (hasta 6; el panel muestra 3 y el resto con scroll) ────
    saved = []
    for i, s in enumerate(suggestions[:6]):
        tag = s.get("tag", "GM")
        titulo = s.get("titulo", "")
        cuerpo = s.get("cuerpo", "")
        if not titulo:
            continue
        db.execute(text("""
            INSERT INTO daily_suggestions (fecha, tag, titulo, cuerpo, estado)
            VALUES (:fecha, :tag, :titulo, :cuerpo, 'pendiente')
        """), {"fecha": today, "tag": tag, "titulo": titulo, "cuerpo": cuerpo})
        saved.append({"tag": tag, "titulo": titulo, "cuerpo": cuerpo})

    db.commit()

    # Invalidar caché del executive feed
    db.execute(text("DELETE FROM executive_feed_cache WHERE scope = 'global'"))
    db.commit()

    return {"generated": len(saved), "fecha": str(today), "suggestions": saved}


class SuggestionStatus(BaseModel):
    estado: str


@router.patch("/suggestions/{suggestion_id}/status")
def update_suggestion_status(suggestion_id: int, body: SuggestionStatus, db: Session = Depends(get_db)):
    allowed = {"aceptada", "editada", "eliminada"}
    if body.estado not in allowed:
        raise HTTPException(400, f"Estado debe ser uno de: {allowed}")
    s = db.get(DailySuggestion, suggestion_id)
    if not s:
        raise HTTPException(404, "Sugerencia no encontrada")
    s.estado = body.estado
    db.commit()
    return {"id": s.id, "estado": s.estado}


class SuggestionEdit(BaseModel):
    titulo: Optional[str] = None
    cuerpo: Optional[str] = None


@router.patch("/suggestions/{suggestion_id}")
def edit_suggestion(suggestion_id: int, body: SuggestionEdit, db: Session = Depends(get_db)):
    """Persiste la edición del CEO (título/cuerpo) y marca la sugerencia 'editada' = atendida.
    Editar es una de las 3 interacciones que CONSUMEN la sugerencia: sale del panel (que solo muestra
    'pendiente') y la siguiente sube. El texto refinado queda guardado para el registro."""
    s = db.get(DailySuggestion, suggestion_id)
    if not s:
        raise HTTPException(404, "Sugerencia no encontrada")
    if body.titulo is not None:
        s.titulo = body.titulo.strip() or s.titulo
    if body.cuerpo is not None:
        s.cuerpo = body.cuerpo.strip()
    s.estado = "editada"
    db.commit()
    return {"id": s.id, "tag": s.tag, "titulo": s.titulo, "cuerpo": s.cuerpo, "estado": s.estado}


# ─── /dashboard/area/{area} ──────────────────────────────────

@router.get("/area/{area}")
def get_area_drilldown(area: str, db: Session = Depends(get_db)):
    if area not in AREAS:
        raise HTTPException(400, f"Área inválida. Opciones: {AREAS}")

    kpi_config = db.query(AreaKpiConfig).filter(AreaKpiConfig.area == area).first()

    # Scope to the active cycle (change scope-pulso-active-cycle), coherent with the Pulso; no active
    # cycle -> show all (legacy backlog) via the `:anio IS NULL` branch.
    anio = _active_cycle_anio(db)
    tasks = db.execute(text("""
        SELECT t.titulo, t.estado, t.prioridad,
               t.fecha_vencimiento, t.responsable,
               (CURRENT_DATE - t.fecha_vencimiento) AS dias_vencida
        FROM tasks t
        LEFT JOIN plans p ON p.id = t.plan_id
        WHERE t.area = :area AND t.estado NOT IN ('completada','cancelada')
          AND (:anio IS NULL
               OR p.anio = :anio
               OR (t.plan_id IS NULL AND t.google_task_id IS NOT NULL))
        ORDER BY t.fecha_vencimiento ASC NULLS LAST
        LIMIT 10
    """), {"area": area, "anio": anio}).fetchall()

    def sla_color(row):
        if not row.fecha_vencimiento:
            return "green"
        diff = (row.fecha_vencimiento - date.today()).days
        if diff < 0:
            return "skull"
        if diff == 0:
            return "red"
        if diff <= 3:
            return "yellow"
        return "green"

    pendientes = [
        {"titulo": r.titulo, "estado": r.estado, "responsable": r.responsable,
         "dias": (r.fecha_vencimiento - date.today()).days if r.fecha_vencimiento else None,
         "sla_color": sla_color(r)}
        for r in tasks
    ]

    return {
        "area": area,
        "code": AREA_CODES[area],
        "kpi_principal": {
            "label": kpi_config.label if kpi_config else area,
            "target": float(kpi_config.target) if kpi_config and kpi_config.target else None,
            "period": kpi_config.period if kpi_config else "mensual",
        },
        "pendientes": pendientes,
    }


# ─── /dashboard/health/services ──────────────────────────────

@router.get("/health/services")
def get_service_health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        pg = "ok"
    except Exception:
        pg = "error"
    return {
        "postgres": pg,
        "n8n":      "unknown",
        "chatwoot": "unknown",
        "drive":    "unknown",
    }


# ─── /dashboard/completeness ─────────────────────────────────

# Panel ID → metadatos (tabla, endpoint, texto empresarial)
# Las tablas son strings literales — no hay riesgo de inyección SQL.
PANEL_REGISTRY = {
    "pulso": {
        "nombre": "Pulso del Colectivo",
        "endpoint": "GET /api/dashboard/health-heatmap",
        "tabla": "tasks",
        "llena_con": "Tareas activas cargadas vía Google Tasks o Subir Recurso",
    },
    "2030": {
        "nombre": "Ejecución 2030",
        "endpoint": "GET /api/dashboard/roadmap-2030",
        "tabla": "roadmap_milestones",
        "llena_con": "Plan Estratégico 2026-2030 cargado vía Subir Recurso",
    },
    "caja": {
        "nombre": "Aire en la Caja",
        "endpoint": "GET /api/dashboard/financial-snapshots",
        "tabla": "financial_snapshots",
        "llena_con": "MOVIMIENTOS 2026 — libro de caja del Director Comercial y Financiero (Google Sheets)",
    },
    "riesgos": {
        "nombre": "Mapa de Riesgos",
        "endpoint": "GET /api/risks",
        "tabla": "risks",
        "llena_con": "Matriz de riesgos cargada vía Subir Recurso o pídele a Gentil",
    },
    "sugerencias": {
        "nombre": "Lectura del Día",
        "endpoint": "GET /api/dashboard/suggestions",
        "tabla": "daily_suggestions",
        "llena_con": "WF-GM-05 Heartbeat Matutino (cron 6:30 AM) o pídele a Gentil",
    },
    "area_drilldown": {
        "nombre": "Drill-down por Área",
        "endpoint": "GET /api/dashboard/area/{area}",
        "tabla": "area_kpi_config",
        "llena_con": "Configuración de KPIs por área — pídele a Gentil que los configure",
    },
}


@router.get("/completeness")
def get_completeness(db: Session = Depends(get_db)):
    """
    Audita qué paneles del dashboard tienen datos reales y cuáles están pendientes.
    Usado por Gentil en el flujo de onboarding documental (WF-GM-07).
    """
    paneles = []
    pendientes_ids = []

    for panel_id, meta in PANEL_REGISTRY.items():
        tabla = meta["tabla"]

        if panel_id == "sugerencias":
            count = db.execute(
                text(f"SELECT COUNT(*) FROM {tabla} WHERE fecha = CURRENT_DATE")
            ).scalar() or 0
        elif panel_id == "area_drilldown":
            # Necesita las 4 áreas configuradas
            count_areas = db.execute(
                text(f"SELECT COUNT(DISTINCT area) FROM {tabla}")
            ).scalar() or 0
            count = count_areas if count_areas == 4 else 0
        else:
            count = db.execute(text(f"SELECT COUNT(*) FROM {tabla}")).scalar() or 0

        if count:
            # Si había un pendiente previo, marcarlo como resuelto
            db.execute(text("""
                UPDATE dashboard_pending_panels
                SET resuelto_en = NOW()
                WHERE panel_id = :pid AND resuelto_en IS NULL
            """), {"pid": panel_id})
            paneles.append({
                "id": panel_id,
                "nombre": meta["nombre"],
                "endpoint": meta["endpoint"],
                "estado": "ok",
                "registros": int(count),
            })
        else:
            # Registrar como pendiente si no existe entrada activa
            existing = db.execute(text("""
                SELECT id FROM dashboard_pending_panels
                WHERE panel_id = :pid AND resuelto_en IS NULL
            """), {"pid": panel_id}).fetchone()

            if not existing:
                db.execute(text("""
                    INSERT INTO dashboard_pending_panels
                        (panel_id, endpoint, razon, llena_con)
                    VALUES (:panel_id, :endpoint, :razon, :llena_con)
                """), {
                    "panel_id": panel_id,
                    "endpoint": meta["endpoint"],
                    "razon": f"{tabla} vacía",
                    "llena_con": meta["llena_con"],
                })

            pendientes_ids.append(panel_id)
            paneles.append({
                "id": panel_id,
                "nombre": meta["nombre"],
                "endpoint": meta["endpoint"],
                "estado": "pendiente",
                "razon": f"{tabla} vacía",
                "llena_con": meta["llena_con"],
            })

    db.commit()

    total = len(paneles)
    ok_count = sum(1 for p in paneles if p["estado"] == "ok")
    return {
        "paneles": paneles,
        "completitud_pct": round(ok_count / total * 100) if total else 0,
        "paneles_pendientes": pendientes_ids,
    }


@router.patch("/completeness/{panel_id}/resolve")
def resolve_pending_panel(panel_id: str, db: Session = Depends(get_db)):
    """Marca un panel pendiente como resuelto. Lo llama n8n cuando llegan datos."""
    if panel_id not in PANEL_REGISTRY:
        raise HTTPException(400, f"Panel desconocido: {panel_id}. Opciones: {list(PANEL_REGISTRY)}")
    db.execute(text("""
        UPDATE dashboard_pending_panels
        SET resuelto_en = NOW()
        WHERE panel_id = :pid AND resuelto_en IS NULL
    """), {"pid": panel_id})
    db.commit()
    return {"panel_id": panel_id, "resuelto_en": datetime.now(timezone.utc).isoformat()}


# ─── Endpoints legacy (no romper los workflows n8n existentes)

@router.get("/curva-s/{plan_id}")
def get_curva_s(plan_id: int, db: Session = Depends(get_db)):
    real_rows = db.execute(
        text("SELECT semana, pct_real_acumulado FROM v_curva_s_real WHERE plan_id = :pid ORDER BY semana"),
        {"pid": plan_id},
    ).fetchall()
    real_map = {r.semana: float(r.pct_real_acumulado) for r in real_rows}
    baseline = db.execute(
        text("SELECT baseline_curva_s FROM plans WHERE id = :pid"), {"pid": plan_id}
    ).scalar()
    data = []
    if baseline:
        for point in baseline:
            semana = point.get("semana", "")
            data.append({"semana": semana,
                         "pct_planificado": float(point.get("pct_planificado", 0)),
                         "pct_real": real_map.get(semana)})
    return {"plan_id": plan_id, "data": data}


@router.get("/gantt/{area}")
def get_gantt(area: str, db: Session = Depends(get_db)):
    rows = db.execute(text("""
        SELECT t.id, t.titulo, t.responsable, t.area, t.estado, t.prioridad,
               t.fecha_inicio, t.fecha_vencimiento, t.fecha_completada,
               t.es_hito, t.peso_pct, p.titulo AS plan_titulo
        FROM tasks t JOIN plans p ON p.id = t.plan_id
        WHERE t.area = :area ORDER BY t.fecha_vencimiento ASC NULLS LAST
    """), {"area": area}).fetchall()
    return [dict(r._mapping) for r in rows]


@router.get("/alerts", response_model=List[AlertItem])
def get_alerts(db: Session = Depends(get_db)):
    alerts: List[AlertItem] = []
    today = date.today()
    overdue = db.execute(text("""
        SELECT t.id, t.titulo, t.area, t.responsable, t.fecha_vencimiento
        FROM tasks t WHERE t.estado NOT IN ('completada','cancelada')
          AND t.fecha_vencimiento < :today ORDER BY t.fecha_vencimiento ASC LIMIT 20
    """), {"today": today}).fetchall()
    for r in overdue:
        alerts.append(AlertItem(tipo="vencida",
            descripcion=f"Tarea vencida: {r.titulo} (venció {r.fecha_vencimiento})",
            area=r.area, responsable=r.responsable, tarea_id=r.id))
    blocked = db.execute(text("""
        SELECT t.id, t.titulo, t.area, t.responsable, t.motivo_bloqueo
        FROM tasks t WHERE t.estado = 'bloqueada' ORDER BY t.updated_at DESC LIMIT 20
    """)).fetchall()
    for r in blocked:
        alerts.append(AlertItem(tipo="bloqueada",
            descripcion=f"Tarea bloqueada: {r.titulo} — {r.motivo_bloqueo}",
            area=r.area, responsable=r.responsable, tarea_id=r.id))
    return alerts

import json
import os
from datetime import date, datetime, timezone, timedelta
from typing import List
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
AREA_CODES = {"Comercial": "GCF", "Proyectos": "GP", "Investigacion": "GI", "Audiovisual": "GA"}


# ─── /dashboard/summary ──────────────────────────────────────

@router.get("/summary", response_model=List[AreaSummary])
def get_summary(db: Session = Depends(get_db)):
    rows = db.execute(text("SELECT * FROM v_dashboard_ceo ORDER BY area")).fetchall()
    return [dict(r._mapping) for r in rows]


# ─── /dashboard/health-heatmap ───────────────────────────────

@router.get("/health-heatmap")
def get_health_heatmap(db: Session = Depends(get_db)):
    """
    Devuelve la matriz 4×7 de salud por área.
    Calcula score por área desde tareas completadas vs. pendientes de la semana.
    """
    rows = []
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    days = [(week_start + timedelta(days=i)).isoformat() for i in range(7)]

    for area in AREAS:
        result = db.execute(text("""
            SELECT
                COUNT(*) FILTER (WHERE estado = 'completada')                          AS done,
                COUNT(*) FILTER (WHERE estado IN ('bloqueada','cancelada'))             AS blocked,
                COUNT(*) FILTER (WHERE estado NOT IN ('completada','cancelada')
                                   AND fecha_vencimiento < CURRENT_DATE)               AS overdue,
                COUNT(*)                                                                AS total
            FROM tasks
            WHERE area = :area
              AND (fecha_inicio >= :week_start OR fecha_vencimiento >= :week_start)
        """), {"area": area, "week_start": week_start}).fetchone()

        total = result.total or 1
        done = result.done or 0
        blocked = result.blocked or 0
        overdue = result.overdue or 0

        # Score 1–4: 4=óptimo, 3=estable, 2=fricción, 1=crítico
        if blocked > 0 or overdue > total * 0.3:
            base_score = 1
        elif overdue > 0:
            base_score = 2
        elif done / total >= 0.7:
            base_score = 4
        else:
            base_score = 3

        score_100 = {4: 90, 3: 75, 2: 60, 1: 40}[base_score]

        rows.append({
            "name": area,
            "code": AREA_CODES[area],
            "score": score_100,
            "days": [base_score] * 7,
        })

    salud_global = round(sum(r["score"] for r in rows) / 4)
    return {"salud_global": salud_global, "delta": 0, "days": days, "areas": rows}


# ─── /dashboard/roadmap-2030 ─────────────────────────────────

@router.get("/roadmap-2030")
def get_roadmap_2030(db: Session = Depends(get_db)):
    milestones = (
        db.query(RoadmapMilestone)
        .order_by(RoadmapMilestone.orden)
        .all()
    )
    done  = sum(1 for m in milestones if m.estado == "done")
    prog  = sum(1 for m in milestones if m.estado == "in_progress")
    late  = sum(1 for m in milestones if m.estado == "delayed")
    total = len(milestones)
    v2030 = round((done / total * 100) if total else 0, 1)

    # Captación desde plans (Comercial)
    cap_row = db.execute(text("""
        SELECT COALESCE(AVG(pct_completado_real), 0) AS pct
        FROM plans WHERE area = 'Comercial' AND estado = 'activo'
    """)).fetchone()

    # Entregas on-time
    ent_row = db.execute(text("""
        SELECT
            COUNT(*) FILTER (WHERE estado='completada' AND fecha_completada <= fecha_vencimiento) AS on_time,
            COUNT(*) FILTER (WHERE estado='completada') AS total_done
        FROM tasks WHERE es_hito = TRUE
    """)).fetchone()
    entregas = round((ent_row.on_time / ent_row.total_done * 100) if ent_row.total_done else 78, 1)

    # Riesgo (variable inversa: alto nivel_riesgo → alto riesgo)
    risk_row = db.execute(text("""
        SELECT COALESCE(AVG(nivel_riesgo / 25.0 * 100), 22) AS riesgo_pct
        FROM risks WHERE estado_mitigacion != 'resuelto'
    """)).fetchone()

    return {
        "v2030_pct": v2030,
        "total_milestones": total,
        "done": done,
        "in_progress": prog,
        "delayed": late,
        "arcs": [
            {"label": "EJE ESTRAT.", "value": v2030,                        "color": "#0E0E0E"},
            {"label": "CAPTACIÓN",   "value": round(float(cap_row.pct), 1), "color": "#00FF41"},
            {"label": "ENTREGAS",    "value": entregas,                     "color": "#0E0E0E"},
            {"label": "RIESGO",      "value": round(float(risk_row.riesgo_pct), 1), "color": "#E8A02C"},
        ],
        "milestones": [
            {"id": m.id, "titulo": m.titulo, "estado": m.estado, "orden": m.orden,
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
        "latest": {
            "liquidez_total":       float(latest.liquidez_total) if latest else 0,
            "caja_operativa":       float(latest.caja_operativa) if latest else 0,
            "reservas_estrategicas":float(latest.reservas_estrategicas) if latest else 0,
            "credito_disponible":   float(latest.credito_disponible) if latest else 0,
            "meses_respiracion":    float(latest.meses_respiracion) if latest else 0,
        } if latest else None,
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

TAGS_BY_AREA = {"Comercial": "GCF", "Proyectos": "GP", "Investigacion": "GI", "Audiovisual": "GA"}

TAG_ORDER = {"crítico": 0, "urgente": 1, "estratégico": 2, "oportunidad": 3}

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_BASE_URL = "https://api.groq.com/openai/v1"


@router.post("/suggestions/generate")
def generate_daily_suggestions(db: Session = Depends(get_db)):
    """
    Genera las 3 sugerencias diarias del CEO (WF-GM-05).
    Primero construye un resumen del estado del sistema, luego llama a GROQ
    para redactar 3 movimientos concretos. Guarda en daily_suggestions.
    """
    if not GROQ_API_KEY:
        raise HTTPException(503, "GROQ_API_KEY no configurada.")

    today = date.today()

    # Borrar sugerencias previas del día para regenerar limpio
    db.execute(text("DELETE FROM daily_suggestions WHERE fecha = :today"), {"today": today})

    # ── Recopilar estado del sistema ────────────────────────────
    tareas_r = db.execute(text("""
        SELECT area,
               COUNT(*) FILTER (WHERE estado NOT IN ('completada','cancelada')
                                  AND fecha_vencimiento < CURRENT_DATE) AS vencidas,
               COUNT(*) FILTER (WHERE estado = 'bloqueada')             AS bloqueadas,
               COUNT(*) FILTER (WHERE estado NOT IN ('completada','cancelada')) AS pendientes
        FROM tasks GROUP BY area
    """)).fetchall()

    riesgos_r = db.execute(text("""
        SELECT descripcion, area, impacto, probabilidad, nivel_riesgo, estado_mitigacion
        FROM risks
        WHERE estado_mitigacion != 'resuelto'
        ORDER BY nivel_riesgo DESC LIMIT 5
    """)).fetchall()

    hitos_r = db.execute(text("""
        SELECT titulo, estado, area FROM roadmap_milestones
        WHERE estado IN ('delayed','in_progress') ORDER BY orden LIMIT 6
    """)).fetchall()

    financiero_r = db.execute(text("""
        SELECT liquidez_total, meses_respiracion, gasto_mensual_promedio
        FROM financial_snapshots ORDER BY fecha DESC LIMIT 1
    """)).fetchone()

    # ── Construir resumen para el LLM ───────────────────────────
    lines = [f"ESTADO DEL CENTRO DE MANDO — {today.strftime('%d %b %Y')}"]

    for r in tareas_r:
        if r.vencidas or r.bloqueadas:
            lines.append(f"- {r.area}: {r.vencidas} tareas vencidas, {r.bloqueadas} bloqueadas de {r.pendientes} pendientes")

    for r in riesgos_r:
        lines.append(f"- RIESGO {r.nivel_riesgo}/25 [{r.area}]: {r.descripcion} ({r.estado_mitigacion})")

    for m in hitos_r:
        estado_label = "RETRASADO" if m.estado == "delayed" else "EN CURSO"
        lines.append(f"- HITO {estado_label} [{m.area or '—'}]: {m.titulo}")

    if financiero_r:
        lines.append(
            f"- Liquidez: {float(financiero_r.liquidez_total)/1_000_000:.1f}M COP · "
            f"{float(financiero_r.meses_respiracion):.0f} meses de runway"
        )

    system_context = "\n".join(lines)

    prompt = f"""{system_context}

Eres Gentil, el segundo cerebro de Clementino (CEO de La Falla D.F.).
Genera exactamente 3 sugerencias de acción para HOY. Cada sugerencia debe:
- Ser CONCRETA y EJECUTABLE en el día
- Tener un área clara (GCF/GP/GI/GA/Transversal)
- Empezar con un verbo de acción (Llamar, Revisar, Aprobar, Cerrar, etc.)

Responde SOLO con un array JSON válido (sin markdown), con este formato exacto:
[
  {{"tag": "GCF", "titulo": "Verbo + acción concreta", "cuerpo": "Contexto de 1-2 oraciones: por qué hoy, qué debes hacer exactamente."}},
  {{"tag": "GP", "titulo": "...", "cuerpo": "..."}},
  {{"tag": "GA", "titulo": "...", "cuerpo": "..."}}
]"""

    # ── Llamar a GROQ ────────────────────────────────────────────
    try:
        from openai import OpenAI
        client = OpenAI(api_key=GROQ_API_KEY, base_url=GROQ_BASE_URL)
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
        )
        raw = resp.choices[0].message.content or "[]"
        # Strip markdown fences if present
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        suggestions = json.loads(raw.strip())
    except Exception as e:
        raise HTTPException(500, f"Error generando sugerencias: {str(e)[:200]}")

    # ── Persistir ────────────────────────────────────────────────
    saved = []
    for i, s in enumerate(suggestions[:3]):
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


# ─── /dashboard/area/{area} ──────────────────────────────────

@router.get("/area/{area}")
def get_area_drilldown(area: str, db: Session = Depends(get_db)):
    if area not in AREAS:
        raise HTTPException(400, f"Área inválida. Opciones: {AREAS}")

    kpi_config = db.query(AreaKpiConfig).filter(AreaKpiConfig.area == area).first()

    tasks = db.execute(text("""
        SELECT t.titulo, t.estado, t.prioridad,
               t.fecha_vencimiento, t.responsable,
               (CURRENT_DATE - t.fecha_vencimiento) AS dias_vencida
        FROM tasks t
        JOIN plans p ON p.id = t.plan_id
        WHERE p.area = :area AND t.estado NOT IN ('completada','cancelada')
        ORDER BY t.fecha_vencimiento ASC NULLS LAST
        LIMIT 10
    """), {"area": area}).fetchall()

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
        "llena_con": "Balance financiero de Quinaya o documento de caja actualizado",
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

"""Deterministic task-coverage analysis (change gentil-task-coverage).

Gentil compares established tasks, completed tasks, and the plan/hito they serve, and writes
actionable findings into daily_suggestions (the Lectura del Día stack). Three closed rules — no
LLM needed to DETECT; when OPENCLAW_TOKEN is configured the gateway MAY polish the wording
(pipes format), with a silent fallback to the fixed Spanish templates.

Runs after every successful Google Tasks import cycle (hooked in tasks.auto_import_once,
best-effort) and on demand via POST /api/dashboard/coverage/refresh.
"""
import json
import logging
import os
from datetime import date

from sqlalchemy import text

log = logging.getLogger("api_gateway.coverage")

AREA_TAG = {"Comercial": "DC", "Proyectos": "DP", "Investigacion": "DI", "Audiovisual": "DA"}
MAX_FINDINGS = 3  # the Lectura stack holds 6 rows; coverage must never flood it

# Same gateway the Lectura del Día generator uses (routers/dashboard.py) — tokens from env only.
OPENCLAW_URL = os.environ.get("OPENCLAW_URL", "http://172.18.0.1:18789/v1/chat/completions")
OPENCLAW_TOKEN = os.environ.get("OPENCLAW_TOKEN", "")


def _ensure_ref_column(db):
    """Lazy additive migration (ddl_v15): probe first, ALTER on failure, swallow races. Keeps the
    deploy one-click — no manual SQL step before the first refresh."""
    try:
        db.execute(text("SELECT ref FROM daily_suggestions LIMIT 1"))
        return
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
    try:
        db.execute(text("ALTER TABLE daily_suggestions ADD COLUMN ref TEXT"))
        db.commit()
    except Exception:
        try:
            db.rollback()  # concurrent add or dialect quirk — the next probe settles it
        except Exception:
            pass


def detect_findings(db):
    """The three closed rules, severity-ordered R3 > R2 > R1, capped at MAX_FINDINGS.

    R3: plan/hito with >=1 task, 0 pending (all completed), progress < 100 — the established
        tasks were exhausted without reaching the goal: it needs MORE tasks.
    R2: hito not 'done' with zero tasks linked by milestone_id — nothing pushes it.
    R1: active plan with zero tasks — the directors have nothing to execute.
    Empty system (no plans, no hitos) -> no findings, never fabricated.
    """
    findings = []

    rows = db.execute(text("""
        SELECT m.id, m.titulo, m.area, m.pct_completado, COUNT(t.id) AS total,
               SUM(CASE WHEN t.estado != 'completada' THEN 1 ELSE 0 END) AS pendientes
        FROM roadmap_milestones m JOIN tasks t ON t.milestone_id = m.id
        WHERE m.estado != 'done'
        GROUP BY m.id, m.titulo, m.area, m.pct_completado
        HAVING COUNT(t.id) > 0 AND SUM(CASE WHEN t.estado != 'completada' THEN 1 ELSE 0 END) = 0
        ORDER BY m.pct_completado ASC
    """)).fetchall()
    for r in rows:
        if float(r.pct_completado or 0) < 100:
            findings.append({"rule": "R3", "kind": "hito", "id": r.id, "area": r.area,
                             "titulo": r.titulo, "total": int(r.total), "pct": float(r.pct_completado or 0)})

    rows = db.execute(text("""
        SELECT p.id, p.titulo, p.area, p.pct_completado_real, COUNT(t.id) AS total,
               SUM(CASE WHEN t.estado != 'completada' THEN 1 ELSE 0 END) AS pendientes
        FROM plans p JOIN tasks t ON t.plan_id = p.id
        WHERE p.estado = 'activo'
        GROUP BY p.id, p.titulo, p.area, p.pct_completado_real
        HAVING COUNT(t.id) > 0 AND SUM(CASE WHEN t.estado != 'completada' THEN 1 ELSE 0 END) = 0
        ORDER BY p.pct_completado_real ASC
    """)).fetchall()
    for r in rows:
        if float(r.pct_completado_real or 0) < 100:
            findings.append({"rule": "R3", "kind": "plan", "id": r.id, "area": r.area,
                             "titulo": r.titulo, "total": int(r.total),
                             "pct": float(r.pct_completado_real or 0)})

    rows = db.execute(text("""
        SELECT m.id, m.titulo, m.area FROM roadmap_milestones m
        WHERE m.estado != 'done'
          AND NOT EXISTS (SELECT 1 FROM tasks t WHERE t.milestone_id = m.id)
        ORDER BY m.orden, m.id
    """)).fetchall()
    for r in rows:
        findings.append({"rule": "R2", "kind": "hito", "id": r.id, "area": r.area,
                         "titulo": r.titulo, "total": 0, "pct": 0.0})

    rows = db.execute(text("""
        SELECT p.id, p.titulo, p.area FROM plans p
        WHERE p.estado = 'activo'
          AND NOT EXISTS (SELECT 1 FROM tasks t WHERE t.plan_id = p.id)
        ORDER BY p.id
    """)).fetchall()
    for r in rows:
        findings.append({"rule": "R1", "kind": "plan", "id": r.id, "area": r.area,
                         "titulo": r.titulo, "total": 0, "pct": 0.0})

    return findings[:MAX_FINDINGS]


def _template(f):
    """Fixed Spanish product copy — always works, no provider needed."""
    if f["rule"] == "R3":
        noun = "hito" if f["kind"] == "hito" else "plan"
        titulo = f"El {noun} «{f['titulo']}» necesita más tareas para llegar al 100%"
        cuerpo = (f"Las {f['total']} tareas establecidas ya están completadas y el avance quedó en "
                  f"{round(f['pct'])}%. Agrega tareas que cierren la brecha, deja especificaciones "
                  "o mantenlo como pendiente del día.")
    elif f["rule"] == "R2":
        titulo = f"El hito «{f['titulo']}» no tiene tareas que lo empujen"
        cuerpo = ("Ninguna tarea está enlazada a este hito, así que su avance no puede moverse. "
                  "Agrega las primeras tareas o especifica cómo se logrará.")
    else:
        titulo = f"El plan «{f['titulo']}» está activo sin tareas"
        cuerpo = ("El plan no tiene tareas desglosadas; los directores no tienen nada que ejecutar. "
                  "Agrega tareas o deja indicaciones.")
    return titulo, cuerpo


def _redact_coverage(items):
    """Optional wording polish via Gentil's brain (OpenClaw gateway). The template copy is already
    in place; this MAY rewrite titulo/cuerpo. Pipes format ('N | titulo | cuerpo') because the
    agentic gateway ignores strict-JSON asks. ANY error, unparseable reply, or count mismatch ->
    keep the templates unchanged. Detection never depends on this."""
    if not OPENCLAW_TOKEN or not items:
        return items
    try:
        import httpx
        listado = "\n".join(f"{i + 1} | {it['titulo']} | {it['cuerpo']}" for i, it in enumerate(items))
        prompt = (
            "Eres Gentil, el analista de La Falla Destino Fílmico. Reescribe estas sugerencias de "
            "cobertura de tareas en español, tono directo al CEO, SIN inventar cifras ni datos "
            "nuevos. Devuelve EXACTAMENTE una línea por sugerencia, formato 'N | título | cuerpo', "
            "sin texto adicional:\n" + listado
        )
        r = httpx.post(
            OPENCLAW_URL,
            headers={"Authorization": f"Bearer {OPENCLAW_TOKEN}", "Content-Type": "application/json"},
            json={"model": "openclaw", "messages": [{"role": "user", "content": prompt}],
                  "tool_choice": "none"},
            timeout=45,
        )
        raw = r.json()["choices"][0]["message"]["content"] or ""
        redacted = []
        for line in raw.splitlines():
            if line.count("|") < 2:
                continue
            parts = [p.strip() for p in line.split("|")]
            titulo, cuerpo = parts[1], " | ".join(parts[2:])
            if titulo:
                redacted.append((titulo, cuerpo))
        if len(redacted) != len(items):
            return items  # count mismatch -> honest templates
        for it, (titulo, cuerpo) in zip(items, redacted):
            it["titulo"], it["cuerpo"] = titulo, cuerpo
    except Exception as e:
        log.info("coverage redaction skipped (%s) — using templates", type(e).__name__)
    return items


def refresh_coverage(db) -> dict:
    """Detect -> replace today's still-pending coverage rows -> write (capped). CEO-attended rows
    (aceptada/editada/eliminada) are history and are never touched."""
    _ensure_ref_column(db)
    findings = detect_findings(db)
    today = date.today()
    db.execute(text(
        "DELETE FROM daily_suggestions WHERE fecha = :f AND ref IS NOT NULL AND estado = 'pendiente'"),
        {"f": today})
    items = []
    for f in findings:
        titulo, cuerpo = _template(f)
        items.append({"tag": AREA_TAG.get(f.get("area"), "GM"), "titulo": titulo, "cuerpo": cuerpo,
                      "ref": json.dumps({"kind": f["kind"], "id": f["id"], "area": f.get("area")})})
    items = _redact_coverage(items)
    for it in items:
        db.execute(text(
            "INSERT INTO daily_suggestions (fecha, tag, titulo, cuerpo, estado, ref) "
            "VALUES (:f, :t, :ti, :c, 'pendiente', :r)"),
            {"f": today, "t": it["tag"], "ti": it["titulo"], "c": it["cuerpo"], "r": it["ref"]})
    db.commit()
    return {"written": len(items), "fecha": str(today)}

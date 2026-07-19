import asyncio
import json
import logging
import os
import threading
from datetime import date, datetime, timezone
from typing import List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..db import engine, get_db, SessionLocal
from ..models import Plan, Task
from ..schemas import TaskBlockRequest, TaskCreate, TaskOut, TaskUpdate
from . import _cascade, _gcal, _gmail, _gtasks
from .roadmap import recompute_milestone_pct  # cascade roll-up: plan % -> hito %

router = APIRouter(prefix="/tasks", tags=["tasks"])

N8N_WEBHOOK_NOTIFICACIONES = os.environ.get("N8N_WEBHOOK_NOTIFICACIONES", "")
N8N_WEBHOOK_SYNC_GOOGLE    = os.environ.get("N8N_WEBHOOK_SYNC_GOOGLE", "")
N8N_WEBHOOK_SECRET         = os.environ.get("N8N_WEBHOOK_SECRET", "")


@router.get("", response_model=List[TaskOut])
def list_tasks(
    plan_id: Optional[int] = Query(None),
    area: Optional[str] = Query(None),
    responsable: Optional[str] = Query(None),
    estado: Optional[str] = Query(None),
    es_hito: Optional[bool] = Query(None),
    limit: int = Query(200, le=1000),
    db: Session = Depends(get_db),
):
    q = db.query(Task)
    if plan_id:
        q = q.filter(Task.plan_id == plan_id)
    if area:
        q = q.filter(Task.area == area)
    if responsable:
        q = q.filter(Task.responsable == responsable)
    if estado:
        q = q.filter(Task.estado == estado)
    if es_hito is not None:
        q = q.filter(Task.es_hito == es_hito)
    return q.order_by(Task.fecha_vencimiento).limit(limit).all()


def _plan_hito(db: Session, plan_id) -> Optional[int]:
    """The hito a plan advances, via its meta-de-hito (plans.goal_id -> strategic_goals.milestone_id).
    change unify-strategy-execution."""
    if not plan_id:
        return None
    try:
        row = db.execute(text(
            "SELECT g.milestone_id FROM plans p LEFT JOIN strategic_goals g ON g.id = p.goal_id "
            "WHERE p.id = :pid"), {"pid": plan_id}).fetchone()
        return row[0] if row and row[0] is not None else None
    except Exception:
        # Best-effort roll-up: a hito lookup failure must never break the primary
        # write path (task completion, Google sync, plan recalculation).
        db.rollback()
        logging.getLogger(__name__).warning(
            "plan->hito lookup failed for plan %s; skipping hito roll-up", plan_id, exc_info=True)
        return None


@router.post("", response_model=TaskOut, status_code=201)
async def create_task(body: TaskCreate, db: Session = Depends(get_db)):
    data = body.model_dump()
    # change unify-strategy-execution: a task tied to a won project is a project task; default the
    # task's hito to its plan's hito (the ~20% rule lets callers override via milestone_id).
    if data.get("project_id"):
        data["origen"] = "proyecto"
    if not data.get("milestone_id"):
        data["milestone_id"] = _plan_hito(db, data.get("plan_id"))
    task = Task(**data)
    db.add(task)
    db.commit()
    db.refresh(task)
    # Ownership-aware routing: CEO task -> Google Tasks; director task -> assignment emission (alias).
    routing = route_outbound_task(task)
    if routing.get("google_task_id") or routing.get("google_calendar_event_id"):
        db.commit()  # persist the linked google_task_id / google_calendar_event_id
    if N8N_WEBHOOK_SYNC_GOOGLE:
        await _fire(N8N_WEBHOOK_SYNC_GOOGLE, _payload(task, "created"))
    return task


@router.get("/{task_id}", response_model=TaskOut)
def get_task(task_id: int, db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(404, f"Task {task_id} not found")
    return task


@router.patch("/{task_id}", response_model=TaskOut)
async def update_task(task_id: int, body: TaskUpdate, db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(404, f"Task {task_id} not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(task, field, value)
    db.commit()
    db.refresh(task)
    if N8N_WEBHOOK_SYNC_GOOGLE:
        await _fire(N8N_WEBHOOK_SYNC_GOOGLE, _payload(task, "updated"))
    return task


@router.delete("/{task_id}")
def delete_task(task_id: int, db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(404, f"Task {task_id} not found")
    db.delete(task)
    db.commit()
    return {"deleted": True, "id": task_id}


@router.post("/{task_id}/complete", response_model=TaskOut)
async def complete_task(task_id: int, db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(404, f"Task {task_id} not found")

    task.estado = "completada"
    task.fecha_completada = date.today()
    db.commit()

    # Recalculate plan % completion
    plan = db.query(Plan).filter(Plan.id == task.plan_id).first()
    if plan:
        completed_pct = db.execute(
            text("SELECT COALESCE(SUM(peso_pct), 0) FROM tasks WHERE plan_id = :pid AND estado = 'completada'"),
            {"pid": plan.id},
        ).scalar()
        plan.pct_completado_real = float(completed_pct)
        db.commit()
        # Cascade roll-up: the plan's hito % is the avg of its plans' real % — recompute so the
        # company hito doesn't go stale (change unify-strategy-execution).
        recompute_milestone_pct(db, _plan_hito(db, plan.id))

    db.refresh(task)

    if task.es_hito and N8N_WEBHOOK_NOTIFICACIONES:
        await _fire(N8N_WEBHOOK_NOTIFICACIONES, {
            "tipo": "hito_completado",
            "task_id": task.id,
            "titulo": task.titulo,
            "area": task.area,
            "responsable": task.responsable,
            "plan_id": task.plan_id,
            "pct_completado_real": float(plan.pct_completado_real) if plan else 0,
        })

    if N8N_WEBHOOK_SYNC_GOOGLE:
        await _fire(N8N_WEBHOOK_SYNC_GOOGLE, _payload(task, "completed"))

    return task


@router.post("/{task_id}/block", response_model=TaskOut)
async def block_task(task_id: int, body: TaskBlockRequest, db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(404, f"Task {task_id} not found")

    task.estado = "bloqueada"
    task.motivo_bloqueo = body.motivo_bloqueo
    db.commit()
    db.refresh(task)

    if N8N_WEBHOOK_NOTIFICACIONES:
        await _fire(N8N_WEBHOOK_NOTIFICACIONES, {
            "tipo": "tarea_bloqueada",
            "task_id": task.id,
            "titulo": task.titulo,
            "area": task.area,
            "responsable": task.responsable,
            "motivo": body.motivo_bloqueo,
        })

    return task


def _recompute_plan_pct(db: Session, plan_id: int) -> None:
    # Raw SQL (the ORM Task carries cross-area FKs that don't resolve on SQLite — same reason the
    # cascade uses raw SQL for tasks). Safe on both SQLite (tests) and prod Postgres.
    pct = db.execute(
        text("SELECT COALESCE(SUM(peso_pct), 0) FROM tasks WHERE plan_id = :pid AND estado = 'completada'"),
        {"pid": plan_id},
    ).scalar()
    db.execute(text("UPDATE plans SET pct_completado_real = :p WHERE id = :pid"),
               {"p": float(pct or 0), "pid": plan_id})
    db.commit()
    # Cascade roll-up: keep the plan's company hito % in sync (change unify-strategy-execution).
    recompute_milestone_pct(db, _plan_hito(db, plan_id))


def _rfc3339_date(s: Optional[str]):
    """Parse a Google RFC3339 timestamp ('2026-06-10T00:00:00.000Z') to a date; None on failure."""
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except (ValueError, TypeError):
        return None


def _delegation_email_body(task: Task) -> str:
    """Internal-tone delegation email (comms standard: cercano pero ordenado; gerencia@ is the hub)."""
    venc = task.fecha_vencimiento.isoformat() if task.fecha_vencimiento else "sin fecha definida"
    return (
        "Hola,\n\n"
        "Desde el Centro de Mando (Gerencia General) se te asignó una nueva tarea:\n\n"
        f"• Tarea: {task.titulo}\n"
        f"• Área: {task.area or '—'}\n"
        f"• Vence: {venc}\n\n"
        "Ya quedó en tu Google Tasks. Cuando la marques como completada ahí, el Centro de Mando lo "
        "registrará automáticamente.\n\n"
        "Gracias,\nGerencia General · La Falla D.F."
    )


def route_outbound_task(task: Task) -> dict:
    """Ownership-aware routing (changes google-tasks-dashboard + delegate-director-tasks): the CEO's
    own tasks sync to his Google Tasks (+ calendar mirror if dated); a director's task is delegated
    into the director's OWN Google Tasks (domain-wide delegation, no password) and emailed from
    gerencia@. Best-effort — never fails the main request (Google unconfigured -> swallowed here)."""
    responsable = (task.responsable or "").strip()
    if responsable == _cascade.CEO_NAME:
        result = {"routed": "ceo_gtasks", "google_task_id": None}
        try:
            due = task.fecha_vencimiento.isoformat() + "T00:00:00.000Z" if task.fecha_vencimiento else None
            gid = _gtasks.insert_task(task.titulo, notes=f"[{task.area or '—'}] plan {task.plan_id}", due=due)
            if gid:
                task.google_task_id = gid
            result["google_task_id"] = gid
        except Exception:
            pass  # Tasks seam 503 until creds set — never fail the main request
        # Calendar mirror (change google-calendar-dashboard): independent best-effort. Swallows the
        # seam's 503 / "API not enabled" so task creation never breaks; goes live once the Google
        # Calendar API is enabled. Only dated CEO tasks land on the calendar.
        try:
            if task.fecha_vencimiento:
                eid = _gcal.upsert_event(
                    summary=task.titulo,
                    due_date=task.fecha_vencimiento,
                    description=f"[{task.area or '—'}] plan {task.plan_id} · Centro de Mando",
                    event_id=task.google_calendar_event_id,
                )
                if eid:
                    task.google_calendar_event_id = eid
                result["google_calendar_event_id"] = eid
        except Exception:
            pass  # Calendar seam unconfigured/unenabled — swallowed
        return result
    # Director: delegate to the director's OWN Google Tasks (impersonate their account via domain-wide
    # delegation — no director password needed) AND notify them by email from gerencia@. Both are
    # best-effort: a Google failure must never break task creation (change delegate-director-tasks).
    alias = _cascade.alias_for_director(responsable)
    result = {"routed": "director_emit", "alias": alias, "responsable": responsable,
              "google_task_id": None, "emailed": False}
    try:
        due = task.fecha_vencimiento.isoformat() + "T00:00:00.000Z" if task.fecha_vencimiento else None
        gid = _gtasks.insert_task(
            task.titulo,
            notes=f"[{task.area or '—'}] Asignada por Gerencia · Centro de Mando · plan {task.plan_id}",
            due=due, subject=alias)
        if gid:
            task.google_task_id = gid
        result["google_task_id"] = gid
    except Exception:
        pass  # Tasks seam 503 until creds set — never fail the main request
    try:
        _gmail.send_email(to=alias, subject=f"Nueva tarea asignada — {task.titulo}",
                          body_text=_delegation_email_body(task))
        result["emailed"] = True
    except Exception:
        pass  # gmail.send not yet authorized / API off — swallowed; the Tasks delegation still works
    return result


@router.post("/sync-google")
def sync_google(db: Session = Depends(get_db)):
    """Inbound reconcile: pull the CEO's AND each director's Google Tasks (domain-wide delegation) and
    update matching dashboard tasks by google_task_id (estado/fecha_completada + plan %). Honest 503 if
    the seam is unconfigured (changes google-tasks-dashboard + delegate-director-tasks)."""
    accounts = sorted(set(_cascade.DIRECTOR_ALIAS.values()))  # gerencia@ + the 4 director accounts
    gtasks = []
    for acct in accounts:
        try:
            gtasks.extend(_gtasks.list_tasks(subject=acct))
        except HTTPException:
            raise  # 503 unconfigured is a global condition -> surface it honestly
        except Exception:
            continue  # one account failing must not abort the whole sweep
    by_gid = {g["google_task_id"]: g for g in gtasks if g.get("google_task_id")}
    if not by_gid:
        return {"scanned": 0, "updated": 0}
    updated, affected = 0, set()
    for gid, g in by_gid.items():
        if g.get("status") != "completed":
            continue
        row = db.execute(
            text("SELECT id, plan_id, estado FROM tasks WHERE google_task_id = :gid"), {"gid": gid}
        ).fetchone()
        if not row or row.estado == "completada":
            continue
        fc = _rfc3339_date(g.get("completed")) or date.today()
        db.execute(text("UPDATE tasks SET estado = 'completada', fecha_completada = :fc WHERE id = :id"),
                   {"fc": fc, "id": row.id})
        updated += 1
        affected.add(row.plan_id)
    if updated:
        db.commit()
        for pid in affected:
            _recompute_plan_pct(db, pid)
    return {"scanned": len(by_gid), "updated": updated}


def _import_google_tasks(db: Session) -> dict:
    """Core inbound IMPORT (change import-google-tasks; shared by the POST endpoint and the background
    scheduler): pull every connected account's Google Tasks (CEO + the 4 directors) and bring them into
    the Centro de Mando. Upsert by google_task_id — create new DIRECT tasks (plan_id null) carrying the
    due date (drives the time semáforo) and status, update existing. Raises HTTP 503 if the seam is
    unconfigured. Google Tasks exposes due/completed but NOT a creation date, so fecha_inicio
    (assignment) is left unknown."""
    imported, updated, swept = 0, 0, 0
    for name, account in _cascade.DIRECTOR_ALIAS.items():
        try:
            gtasks = _gtasks.list_tasks(subject=account)
        except HTTPException:
            raise  # 503 unconfigured is global -> surface it honestly
        except Exception:
            continue  # one account failing must not abort the whole import
        swept += 1
        area = _cascade.area_for_director(name)
        for g in gtasks:
            gid = g.get("google_task_id")
            if not gid:
                continue
            due = _rfc3339_date(g.get("due"))
            completed = _rfc3339_date(g.get("completed"))
            estado = "completada" if g.get("status") == "completed" else "pendiente"
            row = db.execute(text("SELECT id FROM tasks WHERE google_task_id = :g"), {"g": gid}).fetchone()
            if row:
                db.execute(text(
                    "UPDATE tasks SET titulo = :t, estado = :e, fecha_vencimiento = :fv, "
                    "fecha_completada = :fc WHERE id = :id"),
                    {"t": g.get("title", ""), "e": estado, "fv": due, "fc": completed, "id": row.id})
                updated += 1
            else:
                db.execute(text(
                    "INSERT INTO tasks (titulo, responsable, area, estado, fecha_vencimiento, "
                    "fecha_completada, google_task_id) "
                    "VALUES (:t, :r, :a, :e, :fv, :fc, :g)"),
                    {"t": g.get("title", ""), "r": name, "a": area, "e": estado,
                     "fv": due, "fc": completed, "g": gid})
                imported += 1
    db.commit()
    return {"imported": imported, "updated": updated, "accounts": swept}


@router.post("/import-google")
def import_google(db: Session = Depends(get_db)):
    """Manual trigger for the inbound import (change import-google-tasks). The same core runs
    automatically on a cadence (change auto-import-google-tasks). Honest 503 if the seam is unconfigured.
    An explicit CEO call outranks the automatic gate: it re-enables the task reader (change
    reset-task-reader-switch)."""
    try:
        set_tasks_reader(db, True)
        db.commit()
    except Exception:
        db.rollback()  # app_config absent (bare test DB) — the import itself still runs
    return _import_google_tasks(db)


@router.post("/link-hitos")
def link_tasks_hitos(db: Session = Depends(get_db)):
    """Connect the directors' real imported tasks to the hito each one advances (change
    connect-execution-strategy). For every DIRECT imported task (plan_id null, milestone_id null, with a
    google_task_id) Gentil proposes the hito it advances; only clear matches are linked — operational
    tasks are left unlinked, never forced. Once linked, that task's completion feeds the hito's avance
    (roadmap.hito_real_work). No hitos / nothing to link -> honest empty; no LLM provider -> 503 (raised
    by the seam before any write). Raw SQL (the ORM Task carries cross-area FKs that don't resolve on the
    SQLite test DDL)."""
    from ..models import RoadmapMilestone
    hitos = db.query(RoadmapMilestone).all()
    if not hitos:
        return {"estado": "sin_hitos", "linked": 0,
                "mensaje": "No hay hitos para enlazar (carga primero los hitos macro)."}
    rows = db.execute(text(
        "SELECT id, titulo, area, responsable FROM tasks "
        "WHERE milestone_id IS NULL AND plan_id IS NULL AND google_task_id IS NOT NULL ORDER BY id"
    )).fetchall()
    if not rows:
        return {"estado": "linked", "linked": 0, "candidatas": 0,
                "mensaje": "No hay tareas importadas sin enlazar."}
    hitos_payload = [{"id": h.id, "titulo": h.titulo, "area": h.area, "anio": h.anio} for h in hitos]
    valid_hito = {h.id for h in hitos}
    linked, affected = 0, set()
    BATCH = 40  # keep the LLM payload bounded (the directors can have 100+ tasks)
    for i in range(0, len(rows), BATCH):
        chunk = rows[i:i + BATCH]
        tasks_payload = [{"id": r.id, "titulo": r.titulo, "area": r.area, "responsable": r.responsable}
                         for r in chunk]
        proposals = _cascade.generate_hito_links_for_tasks(tasks_payload, hitos_payload)  # 503 before writes
        for p in proposals:
            if p["milestone_id"] not in valid_hito:
                continue
            res = db.execute(text(
                "UPDATE tasks SET milestone_id = :hid WHERE id = :tid AND milestone_id IS NULL"),
                {"hid": p["milestone_id"], "tid": p["task_id"]})
            if res.rowcount:
                linked += 1
                affected.add(p["milestone_id"])
    db.commit()
    return {"estado": "linked", "linked": linked, "candidatas": len(rows),
            "hitos_afectados": sorted(affected),
            "mensaje": f"{linked} de {len(rows)} tareas importadas vinculadas a su hito."}


# --- Task reader switch (change reset-task-reader-switch) ---------------------------------------------
# Persistent on/off gate for the Google Tasks READER, stored in app_config so it survives restarts AND
# the strategy reset (app_config is not in TABLES_TO_CLEAR). Missing key = ON (pre-change behavior).
# The switch only gates reads from Google Tasks — it never writes or deletes anything there.

log = logging.getLogger("api_gateway.tasks")

_READER_KEY = "tasks_reader_enabled"
_IMPORTING_KEY = "tasks_reader_importing"
_LAST_IMPORT_KEY = "tasks_reader_last_import"
_IMPORTING_STALE_MIN = 15  # a marker older than this is a dead cycle, not a running one


def _config_get(db, key):
    try:
        return db.execute(text("SELECT value, updated_at FROM app_config WHERE key = :k"),
                          {"k": key}).fetchone()
    except Exception:
        # app_config absent (bare test DB) -> caller falls back to defaults. The rollback matters:
        # without it the failed statement poisons the session and every later query in the same
        # request dies with PendingRollbackError.
        try:
            db.rollback()
        except Exception:
            pass
        return None


def _config_set(dbc, key, value):
    """Portable upsert (SQLite + Postgres) against app_config. `dbc` is a Session or a Connection —
    both expose execute(); the caller owns the commit."""
    res = dbc.execute(text(
        "UPDATE app_config SET value = :v, updated_at = CURRENT_TIMESTAMP WHERE key = :k"),
        {"k": key, "v": value})
    if not res.rowcount:
        dbc.execute(text(
            "INSERT INTO app_config (key, value, updated_at) VALUES (:k, :v, CURRENT_TIMESTAMP)"),
            {"k": key, "v": value})


def tasks_reader_enabled(db) -> bool:
    row = _config_get(db, _READER_KEY)
    return True if row is None else str(row[0]) != "0"


def set_tasks_reader(dbc, on: bool):
    _config_set(dbc, _READER_KEY, "1" if on else "0")


def reader_importing(db) -> bool:
    """True only while a cycle is running. The marker is cleared in a finally, and as a second guard
    a marker older than _IMPORTING_STALE_MIN reads as false (process died mid-cycle)."""
    row = _config_get(db, _IMPORTING_KEY)
    if row is None or str(row[0]) != "1":
        return False
    ts = row[1]
    if isinstance(ts, str):
        try:
            ts = datetime.fromisoformat(ts)
        except ValueError:
            return True
    if not isinstance(ts, datetime):
        return True
    now = datetime.now(timezone.utc) if ts.tzinfo else datetime.utcnow()
    return (now - ts).total_seconds() < _IMPORTING_STALE_MIN * 60


def reader_last_import(db):
    row = _config_get(db, _LAST_IMPORT_KEY)
    if row is None or not row[0]:
        return None
    try:
        return json.loads(row[0])
    except ValueError:
        return None


def enable_tasks_reader_and_import(db) -> bool:
    """Idempotent OFF→ON: enable the reader and fire ONE immediate import cycle in a daemon thread
    (the scheduled loop would otherwise wait up to AUTO_IMPORT_INTERVAL_MIN). Returns True when the
    switch actually flipped. Single entry point — future ingestion paths (document load) MUST call
    this instead of touching app_config directly."""
    if tasks_reader_enabled(db):
        return False
    set_tasks_reader(db, True)
    db.commit()
    if auto_import_enabled():  # real DB only; sqlite/tests never spawn the thread
        threading.Thread(target=auto_import_once, daemon=True).start()
    return True


# --- Automatic inbound import (change auto-import-google-tasks) ---------------------------------------
# A background loop reimports the directors' Google Tasks on a cadence so the Pulso/semáforo stay live
# without a manual POST. Off on sqlite (tests/dev) and when the interval is <= 0. A Postgres advisory
# lock keeps a single replica importing per cycle (the upsert is idempotent regardless).

_AUTO_IMPORT_LOCK_KEY = 1768465  # arbitrary stable key for pg_advisory_lock


def _auto_import_interval_min() -> int:
    try:
        return int(os.environ.get("AUTO_IMPORT_INTERVAL_MIN", "120"))
    except ValueError:
        return 120


def auto_import_enabled() -> bool:
    """On only against a real (non-sqlite) DB with a positive interval — keeps tests/dev quiet."""
    return _auto_import_interval_min() > 0 and "sqlite" not in os.environ.get("DATABASE_URL", "")


def auto_import_once() -> dict:
    """One import cycle. Swallows the honest 503 (seam unconfigured) and any per-cycle error so the loop
    never dies. On Postgres a DEDICATED connection holds an advisory lock for the whole cycle so at most
    one replica imports at a time; closing that connection releases the lock. The lock MUST live on its
    own connection — the import's session commits mid-cycle, which would return its connection (and its
    session-level lock) to the pool, leaking the lock onto a pooled connection."""
    lock_conn = None
    try:
        if engine.dialect.name == "postgresql":
            lock_conn = engine.connect()
            got = lock_conn.execute(text("SELECT pg_try_advisory_lock(:k)"),
                                    {"k": _AUTO_IMPORT_LOCK_KEY}).scalar()
            if not got:
                return {"skipped": "locked-by-another-replica"}
        db = SessionLocal()
        try:
            # change reset-task-reader-switch: the persistent switch gates every cycle. OFF with no
            # strategy -> honest skip; OFF but strategy exists -> self-heal (at most one interval
            # late) so any goal-writing path that missed the enable helper still wakes the reader.
            if not tasks_reader_enabled(db):
                try:
                    n_goals = db.execute(text("SELECT COUNT(*) FROM strategic_goals")).scalar() or 0
                except Exception:
                    n_goals = 0
                if n_goals == 0:
                    log.info("auto-import skipped: task reader off, no strategy yet")
                    return {"skipped": "reader-off"}
                set_tasks_reader(db, True)
                db.commit()
            try:
                _config_set(db, _IMPORTING_KEY, "1")
                db.commit()
            except Exception:
                db.rollback()  # progress markers are best-effort — never block the import
            try:
                out = _import_google_tasks(db)
                # change gentil-task-coverage: the coverage analysis rides every completed import
                # cycle — best-effort, a coverage bug must never alter the result or kill the loop.
                try:
                    from ._coverage import refresh_coverage
                    refresh_coverage(db)
                except Exception as cov_err:
                    db.rollback()
                    log.warning("coverage refresh failed: %s", cov_err)
                try:
                    _config_set(db, _LAST_IMPORT_KEY, json.dumps(out, default=str))
                    db.commit()
                except Exception:
                    db.rollback()
                return out
            except HTTPException as e:
                if e.status_code == 503:
                    log.info("auto-import skipped: Google seam not configured")
                    return {"skipped": "google-no-config"}
                raise
            except Exception as e:  # a bad cycle must never kill the loop
                db.rollback()
                log.warning("auto-import cycle failed: %s", e)
                return {"error": str(e)[:200]}
            finally:
                try:
                    _config_set(db, _IMPORTING_KEY, "0")
                    db.commit()
                except Exception:
                    db.rollback()
        finally:
            db.close()
    finally:
        if lock_conn is not None:
            lock_conn.close()  # closing the connection releases the session-level advisory lock


async def auto_import_loop():
    """Background scheduler: first refresh shortly after boot, then every AUTO_IMPORT_INTERVAL_MIN. The
    blocking import runs in a worker thread so it never stalls the event loop."""
    interval = _auto_import_interval_min() * 60
    await asyncio.sleep(min(120, interval))  # let the app settle, then the first refresh
    while True:
        out = await asyncio.to_thread(auto_import_once)
        log.info("auto-import cycle: %s", out)
        await asyncio.sleep(interval)


@router.post("/{task_id}/sync-calendar")
def sync_calendar(task_id: int, db: Session = Depends(get_db)):
    """Mirror a dated task onto the CEO's Google Calendar (change google-calendar-dashboard). Upserts
    by the stored `google_calendar_event_id`. Honest 503 if the seam is unconfigured; 422 if the task
    has no due date (nothing to schedule). Raw SQL — the ORM Task carries cross-area FKs that don't
    resolve on SQLite (same reason sync-google uses raw SQL)."""
    row = db.execute(text(
        "SELECT id, titulo, area, plan_id, fecha_vencimiento, google_calendar_event_id "
        "FROM tasks WHERE id = :id"), {"id": task_id}).fetchone()
    if not row:
        raise HTTPException(404, f"Task {task_id} not found")
    if not row.fecha_vencimiento:
        raise HTTPException(422, "La tarea no tiene fecha_vencimiento — nada que poner en el calendario.")
    due = row.fecha_vencimiento
    if not hasattr(due, "isoformat"):  # SQLite returns dates as strings; Postgres returns date objects
        due = date.fromisoformat(str(due))
    eid = _gcal.upsert_event(
        summary=row.titulo,
        due_date=due,
        description=f"[{row.area or '—'}] plan {row.plan_id} · Centro de Mando",
        event_id=row.google_calendar_event_id,
    )
    db.execute(text("UPDATE tasks SET google_calendar_event_id = :e WHERE id = :id"),
               {"e": eid, "id": task_id})
    db.commit()
    return {"task_id": task_id, "google_calendar_event_id": eid}


def _payload(task: Task, action: str) -> dict:
    return {
        "action": action,
        "task_id": task.id,
        "titulo": task.titulo,
        "responsable": task.responsable,
        "area": task.area,
        "estado": task.estado,
        "fecha_vencimiento": task.fecha_vencimiento.isoformat() if task.fecha_vencimiento else None,
        "es_hito": task.es_hito,
        "google_task_id": task.google_task_id,
        "google_calendar_event_id": task.google_calendar_event_id,
        "plan_id": task.plan_id,
    }


async def _fire(url: str, payload: dict) -> None:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(url, json=payload, headers={"X-Webhook-Secret": N8N_WEBHOOK_SECRET})
    except Exception:
        pass  # fire-and-forget; never fail the main request

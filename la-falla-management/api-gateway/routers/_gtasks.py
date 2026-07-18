"""Google Tasks seam (changes google-tasks-dashboard + delegate-director-tasks).

Direct, mockable integration with Google Tasks — replaces the n8n hop for task sync, which is core
product behavior. Authenticated with a Google Workspace **service account using domain-wide
delegation**. The same SA can impersonate ANY user in the lafalla.co domain (the CEO *and* each
director), so the Centro de Mando both pushes tasks into a director's Google Tasks and reads back
their completions — no director passwords needed. Default subject is the CEO
(GOOGLE_TASKS_IMPERSONATE, default gerencia@lafalla.co); pass `subject=<director account>` to act on a
director's list.

Honest 503 when no credentials are configured — never fabricate, consistent with the cascade/LLM
seams. Kept import-light (no router imports) and the ONLY place that touches Google Tasks, so tests
monkeypatch it with no network.
"""
import json
import os
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

SCOPES = ["https://www.googleapis.com/auth/tasks"]
DEFAULT_IMPERSONATE = "gerencia@lafalla.co"


def _impersonate() -> str:
    return os.environ.get("GOOGLE_TASKS_IMPERSONATE", DEFAULT_IMPERSONATE)


def _service(subject: Optional[str] = None):
    """Build the Google Tasks API client (service account + domain-wide delegation), impersonating
    `subject` (a domain user) or the CEO by default.

    Raises HTTP 503 if `GOOGLE_SERVICE_ACCOUNT_JSON` is not configured — honest, never fabricate.
    The JSON may be the raw key or a path to it.
    """
    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if not raw:
        raise HTTPException(503, "Google Tasks no configurado (falta GOOGLE_SERVICE_ACCOUNT_JSON).")
    try:
        info = json.loads(raw) if raw.startswith("{") else json.load(open(raw, encoding="utf-8"))
    except Exception as e:
        raise HTTPException(503, f"GOOGLE_SERVICE_ACCOUNT_JSON inválido: {str(e)[:120]}")

    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    creds = creds.with_subject(subject or _impersonate())  # domain-wide delegation -> impersonate
    return build("tasks", "v1", credentials=creds, cache_discovery=False)


def _default_tasklist_id(svc) -> str:
    """The impersonated user's primary task list (Google Tasks uses '@default' as an alias)."""
    return "@default"


def list_tasks(subject: Optional[str] = None, max_results: int = 100) -> List[Dict[str, Any]]:
    """List a user's Google Tasks (id, title, status, due, completed, notes). [] if none.
    `subject` selects whose list (default the CEO). Each item carries `account` = the subject, so a
    multi-account sweep knows where each task came from."""
    svc = _service(subject)
    who = subject or _impersonate()
    tl = _default_tasklist_id(svc)
    items = (
        svc.tasks()
        .list(tasklist=tl, showCompleted=True, showHidden=True, maxResults=max_results)
        .execute()
        .get("items", [])
    )
    return [
        {
            "google_task_id": it.get("id"),
            "title": it.get("title", ""),
            "status": it.get("status", "needsAction"),   # 'completed' | 'needsAction'
            "due": it.get("due"),                          # RFC3339
            "completed": it.get("completed"),              # RFC3339 when completed
            "notes": it.get("notes", ""),
            "account": who,
        }
        for it in items
    ]


def list_ceo_tasks(max_results: int = 100) -> List[Dict[str, Any]]:
    """List the CEO's Google Tasks (backward-compatible wrapper over list_tasks)."""
    return list_tasks(subject=None, max_results=max_results)


def insert_task(title: str, notes: str = "", due: Optional[str] = None,
                subject: Optional[str] = None) -> str:
    """Create a task in a user's Google Tasks; returns its google_task_id. `subject` selects whose
    list (default the CEO; pass a director account to delegate to them)."""
    svc = _service(subject)
    body: Dict[str, Any] = {"title": title}
    if notes:
        body["notes"] = notes
    if due:
        body["due"] = due
    res = svc.tasks().insert(tasklist=_default_tasklist_id(svc), body=body).execute()
    return res.get("id", "")


def complete_task(google_task_id: str, subject: Optional[str] = None) -> None:
    """Mark a user's Google Task completed (default the CEO; pass a director account for theirs)."""
    svc = _service(subject)
    svc.tasks().patch(
        tasklist=_default_tasklist_id(svc),
        task=google_task_id,
        body={"status": "completed"},
    ).execute()

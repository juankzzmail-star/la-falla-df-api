"""Google Calendar seam (change google-calendar-dashboard).

Mirror of the Google Tasks seam (`_gtasks.py`): a direct, mockable integration with Google Calendar
that lets the Centro de Mando put the CEO's dated tasks/hitos on his calendar. Authenticated with the
SAME Google Workspace **service account using domain-wide delegation**, impersonating the CEO's
account (`GOOGLE_CALENDAR_IMPERSONATE`, falling back to `GOOGLE_TASKS_IMPERSONATE`, default
`gerencia@lafalla.co`), scope `calendar.events`. Only the CEO's primary calendar is touched.

Honest 503 when `GOOGLE_SERVICE_ACCOUNT_JSON` is not configured — never fabricate, consistent with the
Tasks/cascade/LLM seams. Kept import-light (no router imports) and the ONLY place that touches Google
Calendar, so tests monkeypatch it with no network. Reuses the key already provisioned for Tasks (the
service account has `calendar.events` authorized in domain-wide delegation); going live only needs the
Google Calendar API enabled in the project. Until then `upsert_event` errors are swallowed by callers.
"""
import json
import os
from datetime import date, timedelta
from typing import Any, Dict, Optional

from fastapi import HTTPException

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]
DEFAULT_IMPERSONATE = "gerencia@lafalla.co"


def _impersonate() -> str:
    return (
        os.environ.get("GOOGLE_CALENDAR_IMPERSONATE")
        or os.environ.get("GOOGLE_TASKS_IMPERSONATE")
        or DEFAULT_IMPERSONATE
    )


def _service():
    """Build the Google Calendar API client (service account + domain-wide delegation).

    Raises HTTP 503 if `GOOGLE_SERVICE_ACCOUNT_JSON` is not configured — honest, never fabricate.
    The JSON may be the raw key or a path to it.
    """
    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if not raw:
        raise HTTPException(503, "Google Calendar no configurado (falta GOOGLE_SERVICE_ACCOUNT_JSON).")
    try:
        info = json.loads(raw) if raw.startswith("{") else json.load(open(raw, encoding="utf-8"))
    except Exception as e:
        raise HTTPException(503, f"GOOGLE_SERVICE_ACCOUNT_JSON inválido: {str(e)[:120]}")

    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    creds = creds.with_subject(_impersonate())  # domain-wide delegation -> impersonate the CEO
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def _event_body(summary: str, due: date, description: str = "") -> Dict[str, Any]:
    """An all-day event on the due date (Calendar's end.date is exclusive, hence +1 day)."""
    return {
        "summary": summary,
        "description": description,
        "start": {"date": due.isoformat()},
        "end": {"date": (due + timedelta(days=1)).isoformat()},
    }


def upsert_event(summary: str, due_date: date, description: str = "",
                 event_id: Optional[str] = None) -> str:
    """Create or update an all-day event on the CEO's primary calendar; returns its event id.
    If `event_id` is given but the event no longer exists, falls back to creating a new one."""
    svc = _service()
    body = _event_body(summary, due_date, description)
    if event_id:
        try:
            res = svc.events().patch(calendarId="primary", eventId=event_id, body=body).execute()
            return res.get("id", event_id)
        except Exception:
            pass  # the stored event was deleted upstream -> create a fresh one
    res = svc.events().insert(calendarId="primary", body=body).execute()
    return res.get("id", "")


def delete_event(event_id: str) -> None:
    """Remove an event from the CEO's primary calendar (best-effort)."""
    svc = _service()
    svc.events().delete(calendarId="primary", eventId=event_id).execute()

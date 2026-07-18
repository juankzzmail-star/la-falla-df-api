"""Gmail send seam (change delegate-director-tasks).

Sends email **as gerencia@** via the same service account + domain-wide delegation (scope
`gmail.send`, impersonating `GOOGLE_GMAIL_IMPERSONATE` || `GOOGLE_TASKS_IMPERSONATE` ||
gerencia@lafalla.co). Used to notify directors when the Centro de Mando delegates a task to them,
per the comms standard (docs/estandar-comunicaciones-lafalla.md): the CEO (gerencia@) is the single
hub, internal tone is cercano-pero-ordenado.

Honest 503 when `GOOGLE_SERVICE_ACCOUNT_JSON` is missing. Going live also needs the `gmail.send` scope
authorized in domain-wide delegation AND the Gmail API enabled in the project — until then callers
swallow the error (the Google Tasks delegation still works without it). Import-light, the ONLY place
that touches Gmail, so tests monkeypatch it with no network.
"""
import base64
import json
import os
from email.mime.text import MIMEText

from fastapi import HTTPException

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
DEFAULT_IMPERSONATE = "gerencia@lafalla.co"


def _impersonate() -> str:
    return (
        os.environ.get("GOOGLE_GMAIL_IMPERSONATE")
        or os.environ.get("GOOGLE_TASKS_IMPERSONATE")
        or DEFAULT_IMPERSONATE
    )


def _service():
    """Build the Gmail API client (service account + domain-wide delegation, impersonating gerencia@).
    Raises HTTP 503 if `GOOGLE_SERVICE_ACCOUNT_JSON` is not configured — honest, never fabricate."""
    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if not raw:
        raise HTTPException(503, "Gmail no configurado (falta GOOGLE_SERVICE_ACCOUNT_JSON).")
    try:
        info = json.loads(raw) if raw.startswith("{") else json.load(open(raw, encoding="utf-8"))
    except Exception as e:
        raise HTTPException(503, f"GOOGLE_SERVICE_ACCOUNT_JSON inválido: {str(e)[:120]}")

    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    creds = creds.with_subject(_impersonate())  # send AS the CEO's account
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def send_email(to: str, subject: str, body_text: str) -> str:
    """Send a plaintext email AS the impersonated sender (gerencia@). Returns the Gmail message id."""
    svc = _service()
    msg = MIMEText(body_text, "plain", "utf-8")
    msg["To"] = to
    msg["From"] = _impersonate()
    msg["Subject"] = subject
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")
    res = svc.users().messages().send(userId="me", body={"raw": raw}).execute()
    return res.get("id", "")

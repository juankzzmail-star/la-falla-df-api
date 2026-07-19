"""Google Drive READ-ONLY seam (change hub-drive-attach).

Mirrors _gtasks.py: one service account with domain-wide delegation (GOOGLE_SERVICE_ACCOUNT_JSON),
impersonating gerencia@lafalla.co, scope drive.readonly — the Centro NEVER writes to Drive (CEO
doctrine: documents are read-only input). Honest 503 unconfigured; permission errors surface the
SA email so the CEO knows whom to share the file with. The ONLY module touching Drive — tests
monkeypatch it, no network.
"""
import io
import json
import os
import re
from typing import Optional, Tuple

from fastapi import HTTPException

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
DEFAULT_IMPERSONATE = "gerencia@lafalla.co"

# Subcarpeta "Documentos de socixs y prestadores de servicios" — EXCLUSIÓN TOTAL (datos
# personales, instrucción explícita del CEO 19-jul). Server-side, también en carga manual.
EXCLUDED_FOLDER_ID = os.environ.get("EXCLUDED_DRIVE_FOLDER_ID", "16XXqrtgueTuym07VlrKeSjtAVUdEC38L")
_ANCESTRY_DEPTH_CAP = 10

# Google-native types -> export format (regular binaries download as-is).
_EXPORTS = {
    "application/vnd.google-apps.document": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".docx"),
    "application/vnd.google-apps.spreadsheet": (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".xlsx"),
    "application/vnd.google-apps.presentation": (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation", ".pptx"),
}


def parse_file_id(link_or_id: str) -> Optional[str]:
    """Extract the Drive file id from a share link (…/d/<id>/…, ?id=<id>, /file/d/, /document/d/…)
    or accept a bare id. None when nothing id-shaped is found."""
    s = (link_or_id or "").strip()
    if not s:
        return None
    m = re.search(r"/d/([A-Za-z0-9_-]{15,})", s) or re.search(r"[?&]id=([A-Za-z0-9_-]{15,})", s)
    if m:
        return m.group(1)
    if re.fullmatch(r"[A-Za-z0-9_-]{15,}", s):
        return s
    return None


def _sa_info() -> dict:
    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if not raw:
        raise HTTPException(503, "Google Drive no configurado (falta GOOGLE_SERVICE_ACCOUNT_JSON).")
    try:
        return json.loads(raw) if raw.startswith("{") else json.load(open(raw, encoding="utf-8"))
    except Exception as e:
        raise HTTPException(503, f"GOOGLE_SERVICE_ACCOUNT_JSON inválido: {str(e)[:120]}")


def sa_email() -> str:
    try:
        return _sa_info().get("client_email", "la cuenta de servicio")
    except HTTPException:
        return "la cuenta de servicio"


def _service():
    info = _sa_info()
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    creds = creds.with_subject(os.environ.get("GOOGLE_DRIVE_IMPERSONATE", DEFAULT_IMPERSONATE))
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def _metadata(svc, file_id: str) -> dict:
    try:
        return svc.files().get(fileId=file_id, fields="id,name,mimeType,parents",
                               supportsAllDrives=True).execute()
    except Exception as e:
        raise HTTPException(403, (
            f"No pude leer el archivo de Drive ({str(e)[:600]}). Verifica que esté compartido "
            f"con {sa_email()} o con gerencia@lafalla.co."))


def is_excluded(svc, meta: dict) -> bool:
    """Walk the parent chain (depth-capped). True if the excluded personal-data folder appears."""
    parents = list(meta.get("parents") or [])
    seen = set()
    depth = 0
    while parents and depth < _ANCESTRY_DEPTH_CAP:
        pid = parents.pop(0)
        if pid in seen:
            continue
        seen.add(pid)
        if pid == EXCLUDED_FOLDER_ID:
            return True
        depth += 1
        try:
            p = svc.files().get(fileId=pid, fields="id,parents", supportsAllDrives=True).execute()
            parents.extend(p.get("parents") or [])
        except Exception:
            continue  # unreadable ancestor: cannot match the excluded id -> keep walking others
    return False



# Real-file mime -> extension, for Drive files whose NAME lacks one ("01. Marco misional"):
# trust the mimeType Google declares instead of guessing from the name (change hub-drive-attach).
_MIME_EXT = {
    "application/pdf": ".pdf", "application/msword": ".doc", "application/vnd.ms-excel": ".xls",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
    "text/plain": ".txt", "text/csv": ".csv", "text/markdown": ".md",
    "image/png": ".png", "image/jpeg": ".jpg",
}

def fetch(link_or_id: str) -> Tuple[str, bytes]:
    """Resolve, exclusion-check and download/export a Drive file. Returns (filename, bytes).
    403 on excluded subtree or no permission; 503 unconfigured; 400 on unparseable link."""
    file_id = parse_file_id(link_or_id)
    if not file_id:
        raise HTTPException(400, "No encontré un ID de archivo de Drive en ese enlace.")
    svc = _service()
    meta = _metadata(svc, file_id)
    if is_excluded(svc, meta):
        raise HTTPException(403, "Archivo excluido: pertenece a la carpeta de datos personales "
                                 "(socios/prestadores), que el Centro de Gerencia no procesa.")
    name = meta.get("name") or file_id
    mime = meta.get("mimeType") or ""
    from googleapiclient.http import MediaIoBaseDownload
    if mime in _EXPORTS:
        export_mime, ext = _EXPORTS[mime]
        request = svc.files().export_media(fileId=file_id, mimeType=export_mime)
        if not name.lower().endswith(ext):
            name += ext
    else:
        request = svc.files().get_media(fileId=file_id, supportsAllDrives=True)
    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    if mime in _MIME_EXT and not name.lower().endswith(_MIME_EXT[mime]):
        name += _MIME_EXT[mime]  # nameless-extension file: the declared mimeType is the truth
    return name, buf.getvalue()

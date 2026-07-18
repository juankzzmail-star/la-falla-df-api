"""change real-financial-source (instant push): read the real cash ledger MOVIMIENTOS 2026 directly from
Google Sheets (service account + domain-wide delegation, scope spreadsheets.readonly) and upsert
financial_snapshots/flows. Triggered the moment Juan Carlos edits the sheet by an Apps Script onEdit
webhook (no polling). Honest 503 when the SA isn't configured. The ONLY place that touches the Sheets API
for finance, so tests can exercise the pure parser (parse_movimientos) with canned values — no network.

Mapping (decision del dueño): caja_operativa = saldo BCS de cierre de mes (prefiriendo el extracto oficial
sobre el saldo calculado); reservas = 0; credito_disponible = respaldo del fundador acumulado neto a la
fecha (pestaña PRÉSTAMOS, sin nombrar a nadie en el tablero); gasto = honorarios recurrentes (~7.7M).
"""
import os
import re
import json
from datetime import date, datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
DEFAULT_IMPERSONATE = "gerencia@lafalla.co"
GASTO_MENSUAL = 7_700_000.0  # honorarios recurrentes del equipo (prom. de los meses pagados) = burn real

MONTHS = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}
_OFFICIAL_KW = ("extracto", "saldo a", "saldo bcs")


def _impersonate() -> str:
    return os.environ.get("GOOGLE_FINANCE_IMPERSONATE", DEFAULT_IMPERSONATE)


def _norm(s) -> str:
    t = str(s or "").lower()
    for a, b in (("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u")):
        t = t.replace(a, b)
    return t


def _money(s) -> Optional[float]:
    """'$6,458,070.00' / '-$46.46' / '($1,234)' -> float; None if not a number."""
    if s is None:
        return None
    t = str(s).strip().replace("\xa0", " ").strip()
    if not t:
        return None
    neg = t.startswith("(") and t.endswith(")")
    t = t.replace("(", "").replace(")", "").replace("$", "").replace(",", "").strip()
    if neg and not t.startswith("-"):
        t = "-" + t
    try:
        return float(t)
    except ValueError:
        return None


def _parse_date(s) -> Optional[date]:
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", str(s or ""))
    if not m:
        return None
    d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def _month_key(tab: str) -> Optional[Tuple[int, int]]:
    m = re.match(r"\s*([a-záéíóú]+)\s+(\d{4})\s*$", str(tab).strip(), re.IGNORECASE)
    if not m:
        return None
    mn = MONTHS.get(_norm(m.group(1)))
    return (int(m.group(2)), mn) if mn else None


def _last_day(year: int, month: int) -> date:
    if month == 12:
        return date(year, 12, 31)
    return date(year, month + 1, 1) - timedelta(days=1)


def _closing_balance(rows: List[List], year: int, month: int) -> Optional[Tuple[date, float]]:
    """Find the month's closing 'Saldo después de pagos' row -> (fecha, caja). Each tab OPENS with the
    previous month's closing (carry-over) and CLOSES with its own, so we take the LAST matching row, not
    the first. Prefer the official bank-extract figure (numeric next to 'Extracto'/'saldo a'/'saldo BCS')
    over the computed col-A value."""
    result: Optional[Tuple[date, float]] = None
    for row in rows:
        cells = list(row) + [""] * (6 - len(row))
        if not any("saldo desp" in _norm(c) for c in cells):
            continue
        caja = None
        if any(any(kw in _norm(c) for kw in _OFFICIAL_KW) for c in cells):
            for c in cells[2:]:
                v = _money(c)
                if v is not None:
                    caja = v
                    break
        if caja is None:
            caja = _money(cells[0])
        if caja is None:
            continue
        fecha = None
        for c in cells:
            fecha = fecha or _parse_date(c)
        result = (fecha or _last_day(year, month), caja)  # keep the LAST -> the month's own close
    return result


def _loans(rows: List[List]) -> List[Tuple[date, float]]:
    out: List[Tuple[date, float]] = []
    for row in rows:
        cells = list(row) + [""] * 3
        if any("total" in _norm(c) for c in cells):  # skip the TOTAL row
            continue
        amt = _money(cells[0])
        fecha = _parse_date(cells[2]) or _parse_date(cells[1])
        if amt is not None and fecha is not None:
            out.append((fecha, amt))
    return out


def _credito_at(loans: List[Tuple[date, float]], upto: date) -> float:
    return round(sum(a for (d, a) in loans if d <= upto), 2)


def parse_movimientos(values_by_tab: Dict[str, List[List]]) -> List[dict]:
    """Pure parser: {tab_title: rows} -> ordered snapshots. No network — unit-testable."""
    loans_rows: Optional[List[List]] = None
    for tab, rows in values_by_tab.items():
        if "clemen" in _norm(tab) or _norm(tab).startswith("prestamo"):
            loans_rows = rows
    loans = _loans(loans_rows) if loans_rows else []

    snaps: List[dict] = []
    for tab, rows in values_by_tab.items():
        mk = _month_key(tab)
        if not mk:
            continue
        year, month = mk
        cb = _closing_balance(rows, year, month)
        if not cb:
            continue
        fecha, caja = cb
        snaps.append({
            "fecha": fecha,
            "caja_operativa": round(caja, 2),
            "reservas_estrategicas": 0.0,
            "credito_disponible": _credito_at(loans, fecha),
            "gasto_mensual_promedio": GASTO_MENSUAL,
        })
    snaps.sort(key=lambda s: s["fecha"])
    return snaps


def _service():
    from fastapi import HTTPException
    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if not raw:
        raise HTTPException(503, "Sheets no configurado (falta GOOGLE_SERVICE_ACCOUNT_JSON).")
    try:
        info = json.loads(raw) if raw.startswith("{") else json.load(open(raw, encoding="utf-8"))
    except Exception as e:
        raise HTTPException(503, f"GOOGLE_SERVICE_ACCOUNT_JSON inválido: {str(e)[:120]}")
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES).with_subject(_impersonate())
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def fetch_movimientos(spreadsheet_id: str) -> Tuple[str, Dict[str, List[List]]]:
    """Read the month tabs + the loans tab from the real sheet via the service account.
    Returns (spreadsheet_title, {tab: rows}) — the title lets the source auto-follow the current year's
    file (MOVIMIENTOS 2026 -> 2027 ...) without re-pointing anything."""
    svc = _service()
    meta = svc.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    title = meta.get("properties", {}).get("title", "")
    tabs = [s["properties"]["title"] for s in meta.get("sheets", [])]
    want = [t for t in tabs if _month_key(t) or "clemen" in _norm(t) or _norm(t).startswith("prestamo")]
    if not want:
        return title, {}
    resp = svc.spreadsheets().values().batchGet(
        spreadsheetId=spreadsheet_id, ranges=[f"'{t}'!A1:F60" for t in want]).execute()
    out: Dict[str, List[List]] = {}
    for t, vr in zip(want, resp.get("valueRanges", [])):
        out[t] = vr.get("values", [])
    return title, out


def import_movimientos(db, spreadsheet_id: str) -> dict:
    """Read the real sheet, parse, and replace financial_snapshots/flows. liquidez_total is a generated
    column in prod -> never inserted. Refuses to write (keeps last good data) if it parsed < 2 months.
    Also re-points financial_data_sources to THIS file (fuente derived from the sheet title) so a new
    yearly file (MOVIMIENTOS 2027 ...) is followed automatically — no manual re-pointing."""
    from sqlalchemy import text
    title, tabs = fetch_movimientos(spreadsheet_id)
    snaps = parse_movimientos(tabs)
    if len(snaps) < 2:
        return {"ok": False, "reason": "no pude leer >=2 meses de la hoja; mantengo lo último",
                "parsed": len(snaps)}
    db.execute(text("DELETE FROM financial_flows"))
    db.execute(text("DELETE FROM financial_snapshots"))
    for s in snaps:
        liq = s["caja_operativa"] + s["reservas_estrategicas"] + s["credito_disponible"]
        meses = round(liq / s["gasto_mensual_promedio"], 2) if s["gasto_mensual_promedio"] else 0
        db.execute(text(
            "INSERT INTO financial_snapshots (fecha, caja_operativa, reservas_estrategicas, "
            "credito_disponible, gasto_mensual_promedio, meses_respiracion) "
            "VALUES (:f,:c,:r,:cr,:g,:m)"),
            {"f": s["fecha"], "c": s["caja_operativa"], "r": s["reservas_estrategicas"],
             "cr": s["credito_disponible"], "g": s["gasto_mensual_promedio"], "m": meses})
    db.execute(text(
        "INSERT INTO financial_flows (tipo, descripcion, monto, frecuencia, origen) "
        "VALUES ('gasto_recurrente','Honorarios del equipo (mensual)',:m,'mensual','honorarios')"),
        {"m": -GASTO_MENSUAL})
    fuente = (title.strip() if title else "MOVIMIENTOS") + " — Dir. Comercial y Financiera"
    db.execute(text("DELETE FROM financial_data_sources"))
    db.execute(text("INSERT INTO financial_data_sources (fuente, spreadsheet_id, ultima_sincronizacion, estado) "
                    "VALUES (:f,:sid,:ts,'ok')"),
               {"f": fuente, "sid": spreadsheet_id, "ts": datetime.now(timezone.utc)})
    db.commit()
    return {"ok": True, "fuente": fuente, "snapshots": len(snaps), "latest": str(snaps[-1]["fecha"]),
            "caja_latest": snaps[-1]["caja_operativa"], "credito_latest": snaps[-1]["credito_disponible"]}

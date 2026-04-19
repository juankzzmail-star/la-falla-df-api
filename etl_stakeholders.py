"""
ETL Stakeholders La Falla DF
----------------------------
Extrae: múltiples hojas de los archivos .xlsx en 'Stakeholders La Falla/'.
Transforma: normaliza nombres, correos, teléfonos; clasifica por completitud
            de contacto; preserva trazabilidad por archivo+hoja.
Carga: base de datos SQLite 'falla_db.sqlite' con tabla 'stakeholders_master'.

Reglas críticas:
- Inmutabilidad: ningún registro se descarta. Sin contacto -> 'REVISIÓN_MANUAL'.
- Trazabilidad: cada fila conserva 'fuente_archivo' y 'fuente_hoja'.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine

BASE_DIR = Path(__file__).resolve().parent
SOURCE_DIR = BASE_DIR / "Stakeholders La Falla"
DB_PATH = BASE_DIR / "falla_db.sqlite"
TABLE_NAME = "stakeholders_master"

CANONICAL_COLUMNS = [
    "nombre", "rol", "correo", "telefono", "ubicacion", "direccion",
    "nit", "observaciones", "servicios", "redes", "quien_contacta",
    "clasificacion", "fuente_archivo", "fuente_hoja", "fecha_carga",
]

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")


# ---------------------------------------------------------------------------
# Helpers de normalización
# ---------------------------------------------------------------------------
def clean_str(value) -> str | None:
    if pd.isna(value):
        return None
    text = str(value).replace("\xa0", " ").strip()
    text = re.sub(r"\s+", " ", text)
    return text or None


def normalize_name(value, preserve_upper: bool = False) -> str | None:
    text = clean_str(value)
    if text is None:
        return None
    if preserve_upper:
        return text.upper()
    # Title case respetando conectores en minúscula
    lowers = {"de", "del", "la", "las", "los", "y", "e", "da", "do"}
    tokens = text.split(" ")
    out = []
    for i, tok in enumerate(tokens):
        low = tok.lower()
        if i != 0 and low in lowers:
            out.append(low)
        else:
            out.append(low.capitalize())
    return " ".join(out)


def normalize_email(value) -> tuple[str | None, str | None]:
    """Return (email_valido, email_invalido_para_observaciones)."""
    text = clean_str(value)
    if text is None:
        return None, None
    text = text.lower().replace(" ", "")
    if EMAIL_RE.match(text):
        return text, None
    return None, text


def normalize_phone(value) -> str | None:
    text = clean_str(value)
    if text is None:
        return None
    digits = re.sub(r"\D", "", text)
    return digits or None


def classify(correo, telefono) -> str:
    # pd.notna() es necesario: NaN es truthy en Python y produciría
    # falsos COMPLETO si el campo vino vacío desde la fuente.
    has_correo = pd.notna(correo) and str(correo).strip() != ""
    has_tel = pd.notna(telefono) and str(telefono).strip() != ""
    if has_correo and has_tel:
        return "COMPLETO"
    if has_correo:
        return "SOLO_CORREO"
    if has_tel:
        return "SOLO_TELEFONO"
    return "REVISIÓN_MANUAL"


def empty_record(fuente_archivo: str, fuente_hoja: str) -> dict:
    return {
        "nombre": None, "rol": None, "correo": None, "telefono": None,
        "ubicacion": None, "direccion": None, "nit": None,
        "observaciones": None, "servicios": None, "redes": None,
        "quien_contacta": None,
        "fuente_archivo": fuente_archivo,
        "fuente_hoja": fuente_hoja,
    }


def is_blank_row(record: dict) -> bool:
    """Descartar solo filas completamente vacías (no llevan ningún dato útil)."""
    data_fields = ["nombre", "rol", "correo", "telefono", "ubicacion",
                   "direccion", "nit", "observaciones", "servicios",
                   "redes", "quien_contacta"]
    return all(record.get(f) in (None, "") for f in data_fields)


def append_observation(record: dict, extra: str | None) -> None:
    if not extra:
        return
    current = record.get("observaciones")
    record["observaciones"] = f"{current} | {extra}" if current else extra


# ---------------------------------------------------------------------------
# Extractores por hoja
# ---------------------------------------------------------------------------
def extract_delegados(path: Path) -> pd.DataFrame:
    """Hoja1 del archivo DELEGADOS ANCC. Header real en fila 9 (0-indexed)."""
    raw = pd.read_excel(path, header=None)
    header_row = None
    for i in range(min(20, len(raw))):
        cells = [str(v).lower() if pd.notna(v) else "" for v in raw.iloc[i].tolist()]
        if any("nombre" in c for c in cells) and any("correo" in c for c in cells):
            header_row = i
            break
    if header_row is None:
        return pd.DataFrame(columns=CANONICAL_COLUMNS)

    df = pd.read_excel(path, header=header_row)
    df.columns = [clean_str(c) or f"col_{i}" for i, c in enumerate(df.columns)]

    records = []
    for _, row in df.iterrows():
        rec = empty_record(path.name, "Hoja1")
        nombre_val = None
        for col in df.columns:
            if col and "nombre" in col.lower():
                nombre_val = row[col]
                break
        rec["nombre"] = normalize_name(nombre_val)

        for col in df.columns:
            if col is None:
                continue
            key = col.lower()
            if "celular" in key or "tel" in key:
                rec["telefono"] = normalize_phone(row[col])
            elif "correo" in key or "email" in key:
                email, invalid = normalize_email(row[col])
                rec["correo"] = email
                append_observation(rec, f"correo_invalido: {invalid}" if invalid else None)
            elif "consejo" in key:
                rec["ubicacion"] = clean_str(row[col])

        rec["rol"] = "Delegado Consejero ANCC"
        if not is_blank_row(rec):
            records.append(rec)
    return pd.DataFrame(records)


def extract_agentes(path: Path, sheet_name: str) -> pd.DataFrame:
    """Hojas 'Staque Holders agentes', 'PEREIRA', 'PEREIRA DEFINITIVA'."""
    df = pd.read_excel(path, sheet_name=sheet_name)
    df.columns = [clean_str(c) or f"col_{i}" for i, c in enumerate(df.columns)]

    # Mapeo tolerante a mojibake de encabezados
    def find_col(keywords: list[str]) -> str | None:
        for c in df.columns:
            low = c.lower()
            if any(k in low for k in keywords):
                return c
        return None

    col_nombre = find_col(["nombre"])
    col_rol = find_col(["rol"])
    col_obs = find_col(["observ"])
    col_serv = find_col(["servicio"])
    col_donde = find_col(["nde", "dónde", "donde"])  # ¿Dónde? con mojibake
    col_tel = find_col(["tel"])
    col_correo = find_col(["correo", "email"])
    col_redes = find_col(["redes"])
    col_quien = find_col(["quien contacta"])

    records = []
    for _, row in df.iterrows():
        rec = empty_record(path.name, sheet_name)
        rec["nombre"] = normalize_name(row[col_nombre]) if col_nombre else None
        rec["rol"] = clean_str(row[col_rol]) if col_rol else None
        rec["observaciones"] = clean_str(row[col_obs]) if col_obs else None
        rec["servicios"] = clean_str(row[col_serv]) if col_serv else None
        rec["ubicacion"] = clean_str(row[col_donde]) if col_donde else None
        rec["telefono"] = normalize_phone(row[col_tel]) if col_tel else None
        if col_correo:
            email, invalid = normalize_email(row[col_correo])
            rec["correo"] = email
            append_observation(rec, f"correo_invalido: {invalid}" if invalid else None)
        rec["redes"] = clean_str(row[col_redes]) if col_redes else None
        rec["quien_contacta"] = clean_str(row[col_quien]) if col_quien else None

        if not is_blank_row(rec):
            records.append(rec)
    return pd.DataFrame(records)


def extract_camara(path: Path, sheet_name: str) -> pd.DataFrame:
    """Hojas de Cámara de Comercio (Pereira y Dosquebradas)."""
    df = pd.read_excel(path, sheet_name=sheet_name)
    df.columns = [clean_str(c) or f"col_{i}" for i, c in enumerate(df.columns)]

    def col(name: str) -> str | None:
        for c in df.columns:
            if c and c.lower() == name.lower():
                return c
        for c in df.columns:
            if c and name.lower() in c.lower():
                return c
        return None

    c_razon = col("RAZON SOCIAL")
    c_nit = col("NIT")
    c_ident = col("IDENTIFICACION")
    c_dir = col("DIR-COMERCIAL")
    c_mun = col("MUN-COMERCIAL") or col("MUN COMERCIAL")
    c_email1 = col("EMAIL-COMERCIAL")
    c_email2 = col("EMAIL-NOTIFICACION")
    c_ciiu = col("CIIU-1")
    c_actividad = col("ACTIVIDAD")
    c_rep = col("NOM-REP-LEGAL")
    c_dedicado = col("DEDICADOS AL AUDIOVISUAL") or col("AUDIOVISUAL")

    records = []
    for _, row in df.iterrows():
        rec = empty_record(path.name, sheet_name)
        razon = clean_str(row[c_razon]) if c_razon else None
        # Razones sociales se preservan en MAYÚSCULAS (convención mercantil)
        rec["nombre"] = normalize_name(razon, preserve_upper=True) if razon else None
        rec["rol"] = clean_str(row[c_ciiu]) if c_ciiu else None
        rec["direccion"] = clean_str(row[c_dir]) if c_dir else None
        rec["ubicacion"] = clean_str(row[c_mun]) if c_mun else None

        nit_val = row[c_nit] if c_nit else None
        ident_val = row[c_ident] if c_ident else None
        nit_clean = normalize_phone(nit_val) or normalize_phone(ident_val)
        rec["nit"] = nit_clean

        # Correos: combinar comercial y notificación; usar el primer válido
        valid, invalids = None, []
        for src in (c_email1, c_email2):
            if not src:
                continue
            email, invalid = normalize_email(row[src])
            if email and not valid:
                valid = email
            elif email and email != valid:
                invalids.append(email)
            if invalid:
                invalids.append(invalid)
        rec["correo"] = valid
        if invalids:
            append_observation(rec, "otros_correos: " + ", ".join(invalids))

        actividad = clean_str(row[c_actividad]) if c_actividad else None
        rep = clean_str(row[c_rep]) if c_rep else None
        dedicado = clean_str(row[c_dedicado]) if c_dedicado else None
        extras = []
        if actividad:
            extras.append(f"actividad: {actividad}")
        if rep:
            extras.append(f"rep_legal: {rep}")
        if dedicado:
            extras.append(f"audiovisual: {dedicado}")
        rec["servicios"] = " | ".join(extras) if extras else None

        if not is_blank_row(rec):
            records.append(rec)
    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# Orquestación
# ---------------------------------------------------------------------------
def run() -> None:
    if not SOURCE_DIR.exists():
        raise FileNotFoundError(f"No se encontró la carpeta: {SOURCE_DIR}")

    frames: list[pd.DataFrame] = []

    for file_path in sorted(SOURCE_DIR.iterdir()):
        if file_path.suffix.lower() not in {".xlsx", ".xls"}:
            continue
        fname = file_path.name
        print(f"[EXTRACT] {fname}")

        if "DELEGADOS" in fname.upper():
            frames.append(extract_delegados(file_path))
            continue

        xl = pd.ExcelFile(file_path)
        for sheet in xl.sheet_names:
            sheet_upper = sheet.upper()
            print(f"   - hoja: {sheet}")
            if "CAMARA" in sheet_upper or "C\uFFFDMARA" in sheet_upper or "CÁMARA" in sheet_upper:
                frames.append(extract_camara(file_path, sheet))
            else:
                frames.append(extract_agentes(file_path, sheet))

    if not frames:
        print("No se procesó ningún archivo.")
        return

    master = pd.concat(frames, ignore_index=True)

    # Clasificación + timestamp
    master["clasificacion"] = master.apply(
        lambda r: classify(r["correo"], r["telefono"]), axis=1
    )
    master["fecha_carga"] = datetime.utcnow().isoformat(timespec="seconds")

    # Orden de columnas canónico
    master = master.reindex(columns=CANONICAL_COLUMNS)

    # Carga SQLite
    engine = create_engine(f"sqlite:///{DB_PATH}")
    master.to_sql(TABLE_NAME, engine, if_exists="replace", index_label="id")

    # Reporte
    total = len(master)
    print("\n[LOAD] OK")
    print(f"  DB    : {DB_PATH}")
    print(f"  Tabla : {TABLE_NAME}")
    print(f"  Filas : {total}")
    print("\n[RESUMEN POR CLASIFICACIÓN]")
    print(master["clasificacion"].value_counts().to_string())
    print("\n[RESUMEN POR FUENTE]")
    print(master.groupby(["fuente_archivo", "fuente_hoja"]).size().to_string())


if __name__ == "__main__":
    run()

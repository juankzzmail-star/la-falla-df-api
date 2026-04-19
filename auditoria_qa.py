"""
QA / Auditoría de stakeholders_unique y generación de artefactos finales.

Aplica clasificación de NEGOCIO por keywords (Clientes / Aliados /
Proveedores (Locaciones)) sobre la vista dedupada. Mantiene REVISIÓN_MANUAL
como etiqueta obligatoria cuando no hay ningún medio de contacto.

Salidas:
- Reporte de auditoría (stdout).
- STAKEHOLDERS_ACTIVOS.csv        -> contactos con correo o teléfono.
- STAKEHOLDERS_PARA_REVISION.csv   -> sin ningún medio de contacto.
"""

import sqlite3
from pathlib import Path

import pandas as pd

BASE = Path(__file__).resolve().parent
DB = BASE / "falla_db.sqlite"

# -- Reglas de clasificación de negocio (CÓDEX v3) ---------------------
# Precedencia (desempate a favor de Clientes):
#   REVISIÓN_MANUAL > Clientes > Aliados > Proveedores (Locaciones) >
#   Institucional / Gobierno > Prospecto por Identificar > Sin Categoría.
# Búsqueda: rol + observaciones + servicios.
# Excepción: Institucional también busca en fuente_hojas (Cámara de Comercio
# es una fuente institucional por naturaleza).
CLIENTE_KW   = ["productor", "director", "agencia", "distribuidora",
                "gerente", "executive"]

ALIADO_KW    = ["técnico", "tecnico", "músico", "musico",
                "actriz", "actor", "arte", "guionista",
                "editor", "postproducción", "postproduccion",
                "ciiu r9005", "sonidista", "fotografía", "fotografia",
                # Refinamiento semántico — servicios de producción.
                "logística", "logistica", "transporte", "alimentación",
                "alimentacion", "catering"]

# Proveedores (Locaciones) — SOLO patrones de alta confianza.
# Se retiraron 'casa', 'apartamento', 'apto', 'oficina', 'local', 'sede',
# 'inmueble', 'propiedad' y 'bodega' por generar falsos positivos contra
# direcciones residenciales de registros de Cámara de Comercio.
PROVEEDOR_KW = ["finca", "hacienda", "lote", "zona rural",
                "hectárea", "hectarea", "parcela", "predio",
                "terreno", "campestre", "espacio para eventos",
                "locación", "locacion", "finca raíz", "finca raiz"]

# Institucional / Gobierno — organismos, delegados, registros oficiales.
INSTITUCIONAL_KW = ["delegado", "consejero", "ancc",
                    "cámara de comercio", "camara de comercio",
                    "alcaldía", "alcaldia", "alcalde",
                    "ministerio", "ministro",
                    "secretaría de", "secretaria de", "secretario",
                    "gobernación", "gobernacion", "gobernador",
                    "concejal", "gubernamental"]

# Fuentes que disparan "Prospecto por Identificar" si nada anterior coincidió.
PROSPECTO_FUENTES_KW = ["pereira"]


def _has_value(v) -> bool:
    return pd.notna(v) and str(v).strip() != ""


def _safe(v) -> str:
    return str(v) if _has_value(v) else ""


def clasificar(row) -> tuple[str, str]:
    """Retorna (Clasificación, Razón).

    Clasificación en cascada con desempate a favor de Clientes:
      1. REVISIÓN_MANUAL  - sin ningún medio de contacto.
      2. Clientes         - roles de decisión/compra.
      3. Aliados          - profesionales técnicos y servicios de apoyo.
      4. Proveedores      - espacios físicos (inferencia semántica).
      5. Institucional    - delegados, consejeros, registros oficiales.
      6. Prospecto        - proviene de Pereira sin match.
      7. Sin Categoría    - fallback.
    """
    if not _has_value(row.get("correo")) and not _has_value(row.get("telefono")):
        return "REVISIÓN_MANUAL", "sin correo ni teléfono"

    # Contenido: rol + observaciones + servicios.
    contenido = " | ".join(
        _safe(row.get(c)) for c in ("rol", "observaciones", "servicios")
    ).lower()
    # Para Proveedores (Locaciones) también miramos dirección y ubicación,
    # donde suelen aparecer los indicios semánticos de espacios físicos.
    espacios = " | ".join(
        _safe(row.get(c)) for c in
        ("rol", "observaciones", "servicios", "direccion", "ubicacion")
    ).lower()
    # Para Institucional también se admite evidencia en fuente_hojas.
    fuentes = _safe(row.get("fuente_hojas")).lower()
    contenido_ext = contenido + " || " + fuentes

    for kw in CLIENTE_KW:
        if kw in contenido:
            return "Clientes", f"contenido contiene '{kw}'"
    for kw in ALIADO_KW:
        if kw in contenido:
            return "Aliados", f"contenido contiene '{kw}'"
    for kw in PROVEEDOR_KW:
        if kw in espacios:
            return "Proveedores (Locaciones)", f"contenido/dirección contiene '{kw}'"
    for kw in INSTITUCIONAL_KW:
        if kw in contenido_ext:
            return "Institucional / Gobierno", f"contiene '{kw}'"

    for kw in PROSPECTO_FUENTES_KW:
        if kw in fuentes:
            return "Prospecto por Identificar", f"fuente '{kw}' sin keywords de rol"

    # Fallback: sin keywords y sin fuente Pereira — también entra como
    # prospecto para mantener el pipeline sin categoría residual.
    return "Prospecto por Identificar", "sin keywords y fuente no tipificada"


def build_descripcion(row) -> str | None:
    parts = []
    for campo in ("rol", "servicios", "observaciones"):
        val = row.get(campo)
        if _has_value(val):
            parts.append(str(val).strip())
    return " | ".join(parts) if parts else None


def main() -> None:
    conn = sqlite3.connect(DB)
    df = pd.read_sql("SELECT * FROM stakeholders_unique", conn)
    print(f"[INPUT] stakeholders_unique: {len(df)} filas\n")

    # --- Aplicar clasificación de negocio --------------------------------
    clas = df.apply(lambda r: pd.Series(clasificar(r),
                                        index=["Clasificación", "Razón"]), axis=1)
    df = pd.concat([df, clas], axis=1)
    df["Descripción"] = df.apply(build_descripcion, axis=1)
    df["Fuente"] = df["fuente_archivo"]
    df = df.rename(columns={"nombre": "Nombre"})

    # =====================================================================
    # 1. VALIDACIÓN POR KEYWORDS — 5 ejemplos aleatorios por clasificación
    # =====================================================================
    print("=" * 78)
    print("1) VALIDACIÓN DE CLASIFICACIÓN POR KEYWORDS (5 ejemplos por categoría)")
    print("=" * 78)
    for cat in ["Clientes", "Aliados", "Proveedores (Locaciones)",
                "Institucional / Gobierno", "Prospecto por Identificar",
                "REVISIÓN_MANUAL", "Sin Categoría"]:
        sub = df[df["Clasificación"] == cat]
        print(f"\n-- {cat} (total {len(sub)}) --")
        if sub.empty:
            print("  (sin registros)")
            continue
        sample = sub.sample(min(5, len(sub)), random_state=42)
        for _, r in sample.iterrows():
            nombre = _safe(r["Nombre"])[:30]
            rol = _safe(r["rol"])[:38]
            razon = r["Razón"]
            print(f"  {nombre:<31}| rol='{rol}'  -> {razon}")

    # =====================================================================
    # 2. VERIFICACIÓN DE INTEGRIDAD DE COLUMNAS (para exportación)
    # =====================================================================
    print("\n" + "=" * 78)
    print("2) INTEGRIDAD DE COLUMNAS DE EXPORTACIÓN")
    print("=" * 78)
    required = ["Nombre", "correo", "telefono", "Descripción",
                "Clasificación", "Razón", "Fuente"]
    present = [c for c in required if c in df.columns]
    missing = [c for c in required if c not in df.columns]
    print(f"  Requeridas: {required}")
    print(f"  Presentes : {present}")
    print(f"  Faltantes : {missing if missing else 'ninguna'} -> "
          f"{'OK ✅' if not missing else 'FALLA ❌'}")

    # =====================================================================
    # 3. SEGMENTACIÓN DE INCOMPLETOS — ambos contactos NULL
    # =====================================================================
    print("\n" + "=" * 78)
    print("3) SEGMENTACIÓN DE CONTACTOS INCOMPLETOS")
    print("=" * 78)
    sin_contacto = df[~df["correo"].apply(_has_value) & ~df["telefono"].apply(_has_value)]
    n_sin = len(sin_contacto)
    mal_etiquetados = sin_contacto[sin_contacto["Clasificación"] != "REVISIÓN_MANUAL"]
    print(f"  Registros sin correo NI teléfono : {n_sin}")
    print(f"  Etiquetados como REVISIÓN_MANUAL : {len(sin_contacto) - len(mal_etiquetados)}")
    print(f"  Mal etiquetados                  : {len(mal_etiquetados)} "
          f"-> {'OK ✅' if len(mal_etiquetados) == 0 else 'FALLA ❌'}")

    # =====================================================================
    # 4. GENERACIÓN DE CSVs
    # =====================================================================
    print("\n" + "=" * 78)
    print("4) GENERACIÓN DE ARTEFACTOS CSV")
    print("=" * 78)
    export = df[required].copy()

    mask_activos = export["correo"].apply(_has_value) | export["telefono"].apply(_has_value)
    activos = export[mask_activos]
    revision = export[~mask_activos]

    path_activos = BASE / "STAKEHOLDERS_ACTIVOS.csv"
    path_revision = BASE / "STAKEHOLDERS_PARA_REVISION.csv"
    # utf-8-sig para compatibilidad con Excel (BOM)
    activos.to_csv(path_activos, index=False, encoding="utf-8-sig")
    revision.to_csv(path_revision, index=False, encoding="utf-8-sig")
    print(f"  {path_activos.name:<35} -> {len(activos)} filas")
    print(f"  {path_revision.name:<35} -> {len(revision)} filas")

    # =====================================================================
    # 5. REPORTE DE FINALIZACIÓN
    # =====================================================================
    print("\n" + "=" * 78)
    print("5) REPORTE DE FINALIZACIÓN")
    print("=" * 78)
    total = len(df)
    suma = len(activos) + len(revision)
    print(f"  Total en stakeholders_unique  : {total}")
    print(f"  Activos                       : {len(activos)}")
    print(f"  Para revisión                 : {len(revision)}")
    print(f"  Suma artefactos               : {suma}")
    print(f"  Cuadre                        : "
          f"{'OK ✅ (suma == 334)' if suma == total == 334 else 'REVISAR ⚠️'}")

    print("\n[DISTRIBUCIÓN FINAL por Clasificación de Negocio]")
    for cat, n in df["Clasificación"].value_counts().items():
        print(f"  {cat:<28} {n}")

    conn.close()


if __name__ == "__main__":
    main()

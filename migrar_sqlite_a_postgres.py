"""
Migración one-shot: SQLite falla_db.sqlite → Postgres (EasyPanel).

Uso:
    pip install psycopg2-binary sqlalchemy pandas
    DATABASE_URL=postgresql://user:pass@host:5432/db python migrar_sqlite_a_postgres.py

La variable DATABASE_URL puede venir del entorno o del archivo .env en el
mismo directorio. Si DATABASE_URL no está definida, el script aborta con
instrucciones.

Qué hace:
  1. Crea tabla stakeholders_master con el mismo esquema + columnas nuevas
     (linkedin_url, clasificacion_negocio).
  2. Migra todos los registros, pre-computando clasificacion_negocio con
     la función clasificar() de auditoria_qa.py.
  3. Crea tabla interactions.
  4. Recrea la VIEW stakeholders_unique adaptada a Postgres (STRING_AGG).
  5. Imprime un resumen de verificación.

Idempotente: si las tablas ya existen, el script falla rápido a menos que
uses --reset (borra y recrea todo).
"""

import os
import sys
import argparse
import sqlite3
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

BASE = Path(__file__).resolve().parent
SQLITE_PATH = BASE / "falla_db.sqlite"

# ---------------------------------------------------------------------------
# Carga .env si DATABASE_URL no está en el entorno
# ---------------------------------------------------------------------------
def _load_env():
    env_path = BASE / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


_load_env()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print(
        "\n[ERROR] DATABASE_URL no definida.\n"
        "Agrega en tu .env:\n"
        "  DATABASE_URL=postgresql://user:password@host:5432/dbname\n"
        "O expórtala antes de ejecutar el script.\n"
    )
    sys.exit(1)


# ---------------------------------------------------------------------------
# Importar clasificar() del proyecto
# ---------------------------------------------------------------------------
sys.path.insert(0, str(BASE))
from auditoria_qa import clasificar  # noqa: E402

# ---------------------------------------------------------------------------
# DDL
# ---------------------------------------------------------------------------
DDL_STAKEHOLDERS = """
CREATE TABLE stakeholders_master (
    id                   SERIAL PRIMARY KEY,
    nombre               TEXT,
    rol                  TEXT,
    correo               TEXT,
    telefono             TEXT,
    ubicacion            TEXT,
    direccion            TEXT,
    nit                  TEXT,
    observaciones        TEXT,
    servicios            TEXT,
    redes                TEXT,
    quien_contacta       TEXT,
    clasificacion        TEXT,
    clasificacion_negocio TEXT,
    linkedin_url         TEXT,
    fuente_archivo       TEXT,
    fuente_hoja          TEXT,
    fecha_carga          TIMESTAMPTZ DEFAULT NOW()
);
"""

DDL_INTERACTIONS = """
CREATE TABLE interactions (
    id             SERIAL PRIMARY KEY,
    stakeholder_id INTEGER REFERENCES stakeholders_master(id) ON DELETE SET NULL,
    campaign       TEXT NOT NULL,
    canal          TEXT NOT NULL,
    direccion      TEXT NOT NULL CHECK (direccion IN ('in', 'out')),
    mensaje        TEXT,
    status         TEXT DEFAULT 'sent',
    timestamp      TIMESTAMPTZ DEFAULT NOW()
);
"""

DDL_VIEW = """
CREATE OR REPLACE VIEW stakeholders_unique AS
WITH keyed AS (
    SELECT
        id, nombre, rol, correo, telefono, ubicacion, direccion, nit,
        observaciones, servicios, redes, quien_contacta, clasificacion,
        clasificacion_negocio, linkedin_url,
        fuente_archivo, fuente_hoja,
        CASE
            WHEN correo IS NULL AND telefono IS NULL
                THEN '__NOID__' || id::TEXT
            ELSE COALESCE(correo, '') || '|' || COALESCE(telefono, '')
        END AS dedup_key
    FROM stakeholders_master
),
ranked AS (
    SELECT *,
        ROW_NUMBER() OVER (
            PARTITION BY dedup_key
            ORDER BY
                CASE WHEN nombre IS NULL OR TRIM(nombre) = '' THEN 1 ELSE 0 END,
                LENGTH(COALESCE(nombre, '')) DESC,
                id ASC
        ) AS rn
    FROM keyed
),
aggregated AS (
    SELECT
        dedup_key,
        STRING_AGG(DISTINCT fuente_archivo, ', ' ORDER BY fuente_archivo)
            AS fuente_archivo,
        STRING_AGG(DISTINCT fuente_hoja, ', ' ORDER BY fuente_hoja)
            AS fuente_hojas,
        COUNT(*) AS apariciones
    FROM keyed
    GROUP BY dedup_key
)
SELECT
    r.id,
    r.nombre,
    r.rol,
    r.correo,
    r.telefono,
    r.ubicacion,
    r.direccion,
    r.nit,
    r.observaciones,
    r.servicios,
    r.redes,
    r.quien_contacta,
    r.clasificacion,
    r.clasificacion_negocio,
    r.linkedin_url,
    a.fuente_archivo,
    a.fuente_hojas,
    a.apariciones
FROM ranked r
JOIN aggregated a ON r.dedup_key = a.dedup_key
WHERE r.rn = 1;
"""


def reset_db(engine):
    with engine.begin() as conn:
        conn.execute(text("DROP VIEW IF EXISTS stakeholders_unique CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS interactions CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS stakeholders_master CASCADE"))
    print("[RESET] Tablas y vistas eliminadas.")


def create_schema(engine):
    with engine.begin() as conn:
        conn.execute(text(DDL_STAKEHOLDERS))
        conn.execute(text(DDL_INTERACTIONS))
        conn.execute(text(DDL_VIEW))
    print("[SCHEMA] Tablas y vista creadas.")


def migrate_data(engine):
    sqlite_conn = sqlite3.connect(SQLITE_PATH)
    df = pd.read_sql("SELECT * FROM stakeholders_master", sqlite_conn)
    sqlite_conn.close()
    print(f"[SQLITE] Leídos {len(df)} registros de stakeholders_master.")

    # Pre-computar clasificacion_negocio
    clas = df.apply(
        lambda r: clasificar(r)[0], axis=1
    )
    df["clasificacion_negocio"] = clas
    df["linkedin_url"] = None

    # Alinear columnas al DDL de Postgres (sin 'id' para usar SERIAL)
    cols = [
        "nombre", "rol", "correo", "telefono", "ubicacion", "direccion",
        "nit", "observaciones", "servicios", "redes", "quien_contacta",
        "clasificacion", "clasificacion_negocio", "linkedin_url",
        "fuente_archivo", "fuente_hoja", "fecha_carga",
    ]
    df_pg = df[cols].copy()
    df_pg["fecha_carga"] = pd.to_datetime(df_pg["fecha_carga"], errors="coerce")

    df_pg.to_sql(
        "stakeholders_master",
        engine,
        if_exists="append",
        index=False,
        method="multi",
        chunksize=200,
    )
    print(f"[POSTGRES] Insertados {len(df_pg)} registros.")


def verify(engine):
    with engine.connect() as conn:
        total_master = conn.execute(
            text("SELECT COUNT(*) FROM stakeholders_master")
        ).scalar()
        total_unique = conn.execute(
            text("SELECT COUNT(*) FROM stakeholders_unique")
        ).scalar()
        dist = conn.execute(
            text(
                "SELECT clasificacion_negocio, COUNT(*) as n "
                "FROM stakeholders_unique "
                "GROUP BY clasificacion_negocio ORDER BY n DESC"
            )
        ).fetchall()

    print(f"\n[VERIFICACIÓN]")
    print(f"  stakeholders_master : {total_master} filas")
    print(f"  stakeholders_unique : {total_unique} filas (esperado ≈ 334)")
    print(f"\n  Distribución CÓDEX v4:")
    for row in dist:
        print(f"    {row[0]:40s} {row[1]}")


def main():
    parser = argparse.ArgumentParser(description="Migrar SQLite → Postgres")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Eliminar tablas existentes antes de migrar (peligroso en producción)",
    )
    args = parser.parse_args()

    engine = create_engine(DATABASE_URL, future=True)

    if args.reset:
        confirm = input(
            "[ADVERTENCIA] --reset borrará TODOS los datos en Postgres. "
            "Escribe 'CONFIRMAR' para continuar: "
        )
        if confirm != "CONFIRMAR":
            print("Abortado.")
            sys.exit(0)
        reset_db(engine)

    create_schema(engine)
    migrate_data(engine)
    verify(engine)
    print("\n[OK] Migración completada.")


if __name__ == "__main__":
    main()

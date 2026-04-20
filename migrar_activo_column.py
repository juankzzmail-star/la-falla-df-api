"""
Migración idempotente: agrega columnas `activo` y `fecha_actualizacion`
a `stakeholders_master` en Postgres.

Uso:
    DATABASE_URL=postgresql://... python migrar_activo_column.py
"""
import os
import sys
from pathlib import Path
from sqlalchemy import create_engine, text


def _load_env():
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


def main():
    _load_env()
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("ERROR: DATABASE_URL no definida.", file=sys.stderr)
        sys.exit(1)

    engine = create_engine(url, future=True)
    with engine.begin() as conn:
        conn.execute(text("""
            ALTER TABLE stakeholders_master
            ADD COLUMN IF NOT EXISTS activo BOOLEAN NOT NULL DEFAULT TRUE
        """))
        conn.execute(text("""
            ALTER TABLE stakeholders_master
            ADD COLUMN IF NOT EXISTS fecha_actualizacion TIMESTAMPTZ NOT NULL DEFAULT NOW()
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_stakeholders_activo
            ON stakeholders_master(activo)
        """))

        total = conn.execute(text("SELECT COUNT(*) FROM stakeholders_master")).scalar()
        activos = conn.execute(
            text("SELECT COUNT(*) FROM stakeholders_master WHERE activo = TRUE")
        ).scalar()

    print(f"OK. total={total}  activos={activos}")


if __name__ == "__main__":
    main()

"""
Migración idempotente:
  - Agrega `observaciones_post_contacto` TEXT (descripción posterior a contactar).
  - Agrega `extras` JSONB NOT NULL DEFAULT '{}' (columnas dinámicas creadas
    desde Google Sheets que no tienen mapping fijo).

Uso:
    DATABASE_URL=postgresql://... python migrar_extras_y_post_contacto.py
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
            ADD COLUMN IF NOT EXISTS observaciones_post_contacto TEXT
        """))
        conn.execute(text("""
            ALTER TABLE stakeholders_master
            ADD COLUMN IF NOT EXISTS extras JSONB NOT NULL DEFAULT '{}'::jsonb
        """))

        total = conn.execute(text("SELECT COUNT(*) FROM stakeholders_master")).scalar()
        con_extras = conn.execute(
            text("SELECT COUNT(*) FROM stakeholders_master WHERE extras != '{}'::jsonb")
        ).scalar()

    print(f"OK. total={total}  con_extras={con_extras}")


if __name__ == "__main__":
    main()

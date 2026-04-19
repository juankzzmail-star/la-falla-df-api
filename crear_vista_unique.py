"""
Crea la vista SQL `stakeholders_unique` sobre `stakeholders_master`.

Reglas:
- Deduplicación por (correo, telefono). Filas sin ningún contacto se
  conservan como únicas (no se colapsan entre sí).
- Priorización: para cada grupo, los campos escalares se toman de la
  fila cuyo `nombre` sea el más completo (longitud máxima, no nulo).
- Consolidación de fuentes: `fuente_archivo` y `fuente_hoja` se
  concatenan con TODOS los orígenes donde aparece el contacto.
- Inmutabilidad: la tabla master no se modifica (view = derivación).
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "falla_db.sqlite"

VIEW_SQL = """
DROP VIEW IF EXISTS stakeholders_unique;

CREATE VIEW stakeholders_unique AS
WITH keyed AS (
    SELECT
        id, nombre, rol, correo, telefono, ubicacion, direccion, nit,
        observaciones, servicios, redes, quien_contacta, clasificacion,
        fuente_archivo, fuente_hoja,
        CASE
            WHEN correo IS NULL AND telefono IS NULL
                THEN '__NOID__' || CAST(id AS TEXT)
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
        (SELECT GROUP_CONCAT(x, ', ') FROM (
            SELECT DISTINCT fuente_archivo AS x FROM keyed k2
            WHERE k2.dedup_key = k1.dedup_key AND fuente_archivo IS NOT NULL
            ORDER BY x
        )) AS fuente_archivo,
        (SELECT GROUP_CONCAT(x, ', ') FROM (
            SELECT DISTINCT fuente_hoja AS x FROM keyed k3
            WHERE k3.dedup_key = k1.dedup_key AND fuente_hoja IS NOT NULL
            ORDER BY x
        )) AS fuente_hojas,
        COUNT(*) AS apariciones
    FROM keyed k1
    GROUP BY dedup_key
)
SELECT
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
    a.fuente_archivo,
    a.fuente_hojas,
    a.apariciones
FROM ranked r
JOIN aggregated a ON r.dedup_key = a.dedup_key
WHERE r.rn = 1;
"""


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(VIEW_SQL)
    conn.commit()

    total_master = conn.execute("SELECT COUNT(*) FROM stakeholders_master").fetchone()[0]
    total_unique = conn.execute("SELECT COUNT(*) FROM stakeholders_unique").fetchone()[0]
    reduccion = total_master - total_unique

    print("[OK] Vista creada: stakeholders_unique")
    print(f"  Master  : {total_master} registros")
    print(f"  Unique  : {total_unique} contactos únicos")
    print(f"  Reducción: -{reduccion} ({100*reduccion/total_master:.1f}%)")

    print("\n[DISTRIBUCIÓN por clasificación en la vista]")
    for clas, n in conn.execute("""
        SELECT clasificacion, COUNT(*) FROM stakeholders_unique
        GROUP BY clasificacion ORDER BY 2 DESC
    """):
        print(f"  {clas:<18} {n}")

    print("\n[TOP 5 contactos con más apariciones (duplicados consolidados)]")
    for nombre, correo, apar, fuentes in conn.execute("""
        SELECT nombre, correo, apariciones, fuente_hojas
        FROM stakeholders_unique
        ORDER BY apariciones DESC, nombre
        LIMIT 5
    """):
        print(f"  {(nombre or '')[:35]:<36} {str(correo or '')[:28]:<29} x{apar}  [{fuentes}]")

    conn.close()


if __name__ == "__main__":
    main()

"""
Deduplicación de `stakeholders_master` en Postgres.

Estrategia (misma lógica que `crear_vista_unique.py`, pero aplicada como
modificación real a la tabla maestra):

- Clave de dedup: (correo normalizado, telefono normalizado).
  Filas sin ni correo ni teléfono NO se colapsan entre sí.
- También se detectan duplicados por `linkedin_url` (si no nulo).
- Por cada grupo:
    · Se elige la fila "mejor" = mayor cantidad de campos llenos; en
      empate, nombre más largo; en empate, id más bajo.
    · Los campos de las filas duplicadas se MERGEAN sobre la mejor:
      si la mejor tiene un campo vacío, se rellena con el valor de
      algún duplicado.
    · Las fuentes (fuente_archivo, fuente_hoja, observaciones) se
      concatenan con " | " para no perder trazabilidad.
    · Las demás filas se ELIMINAN (hard delete).

Uso:
    # Dry-run (solo reporta, no toca nada)
    python deduplicar_postgres.py

    # Aplicar cambios
    python deduplicar_postgres.py --apply
"""
from __future__ import annotations

import os
import sys
import argparse
from pathlib import Path
from collections import defaultdict
from sqlalchemy import create_engine, text


CAMPOS_SCALAR = [
    "nombre", "rol", "correo", "telefono", "ubicacion", "direccion", "nit",
    "servicios", "redes", "quien_contacta", "clasificacion",
    "clasificacion_negocio", "linkedin_url",
]
CAMPOS_CONCAT = [
    "observaciones", "observaciones_post_contacto",
    "fuente_archivo", "fuente_hoja",
]
TODOS_CAMPOS = CAMPOS_SCALAR + CAMPOS_CONCAT


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


def _norm(s):
    if s is None:
        return ""
    return "".join(c for c in str(s) if c.isalnum()).lower()


def _dedup_key(row):
    correo = _norm(row["correo"])
    tel = _norm(row["telefono"])
    if not correo and not tel:
        return None  # no agrupable
    return f"{correo}|{tel}"


def _completeness(row):
    return sum(1 for c in TODOS_CAMPOS if row.get(c) not in (None, "", 0))


def _pick_best(rows):
    return max(
        rows,
        key=lambda r: (
            _completeness(r),
            len(str(r.get("nombre") or "")),
            -int(r["id"]),
        ),
    )


def _merge_group(rows):
    best = _pick_best(rows)
    merged = dict(best)
    for r in rows:
        if r["id"] == best["id"]:
            continue
        for c in CAMPOS_SCALAR:
            if not merged.get(c) and r.get(c):
                merged[c] = r[c]
        for c in CAMPOS_CONCAT:
            vals = []
            if merged.get(c):
                vals.append(str(merged[c]))
            if r.get(c):
                rv = str(r[c])
                if rv not in vals:
                    vals.append(rv)
            merged[c] = " | ".join(vals) if vals else None
    return best["id"], merged, [r["id"] for r in rows if r["id"] != best["id"]]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Ejecutar cambios (sin esto es dry-run)")
    args = parser.parse_args()

    _load_env()
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("ERROR: DATABASE_URL no definida.", file=sys.stderr)
        sys.exit(1)

    engine = create_engine(url, future=True)

    with engine.connect() as conn:
        rows = conn.execute(text(f"""
            SELECT id, {', '.join(TODOS_CAMPOS)}
            FROM stakeholders_master
            WHERE activo = TRUE
            ORDER BY id ASC
        """)).mappings().all()

    total = len(rows)
    print(f"Total filas activas: {total}")

    groups = defaultdict(list)
    linkedin_groups = defaultdict(list)
    for r in rows:
        k = _dedup_key(r)
        if k:
            groups[k].append(dict(r))
        lk = (r.get("linkedin_url") or "").strip()
        if lk:
            linkedin_groups[lk].append(dict(r))

    dup_groups = [g for g in groups.values() if len(g) > 1]
    dup_linkedin = [g for g in linkedin_groups.values() if len(g) > 1]

    all_dups = {tuple(sorted(r["id"] for r in g)): g for g in dup_groups}
    for g in dup_linkedin:
        key = tuple(sorted(r["id"] for r in g))
        if key not in all_dups:
            all_dups[key] = g

    print(f"Grupos con duplicados: {len(all_dups)}")
    a_eliminar = sum(len(g) - 1 for g in all_dups.values())
    print(f"Filas a eliminar tras merge: {a_eliminar}")
    print(f"Filas únicas resultantes: {total - a_eliminar}\n")

    if not all_dups:
        print("[OK] No hay duplicados.")
        return

    print("=" * 80)
    print("REPORTE DE GRUPOS (top 20)")
    print("=" * 80)
    for i, grp in enumerate(list(all_dups.values())[:20], 1):
        best_id, merged, to_delete = _merge_group(grp)
        print(f"\n[{i}] Grupo de {len(grp)} filas — ids: {[r['id'] for r in grp]}")
        print(f"    Mantener id={best_id}  nombre='{merged.get('nombre') or ''}'  "
              f"correo='{merged.get('correo') or ''}'  tel='{merged.get('telefono') or ''}'")
        print(f"    Eliminar ids: {to_delete}")

    if not args.apply:
        print("\n" + "=" * 80)
        print("DRY-RUN. No se tocó la base.")
        print("Para ejecutar: python deduplicar_postgres.py --apply")
        return

    print("\n" + "=" * 80)
    print("APLICANDO CAMBIOS...")
    actualizados, eliminados = 0, 0
    with engine.begin() as conn:
        for grp in all_dups.values():
            best_id, merged, to_delete = _merge_group(grp)
            sets = ", ".join(f"{c} = :{c}" for c in TODOS_CAMPOS)
            params = {c: merged.get(c) for c in TODOS_CAMPOS}
            params["id"] = best_id
            conn.execute(text(f"UPDATE stakeholders_master SET {sets} WHERE id = :id"), params)
            actualizados += 1
            if to_delete:
                conn.execute(
                    text("DELETE FROM stakeholders_master WHERE id = ANY(:ids)"),
                    {"ids": to_delete},
                )
                eliminados += len(to_delete)

    print(f"[OK] Mergeados: {actualizados}  Eliminados: {eliminados}")


if __name__ == "__main__":
    main()

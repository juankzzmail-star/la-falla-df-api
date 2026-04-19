"""
Thin wrapper — reutiliza clasificar() de auditoria_qa.py sin duplicar reglas.
El módulo auditoria_qa.py está un nivel arriba en el árbol de directorios.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from auditoria_qa import clasificar as _clasificar  # noqa: E402


def clasificar(data: dict) -> tuple[str, str]:
    """Recibe un dict con campos del stakeholder; retorna (clasificacion, razon)."""
    return _clasificar(data)

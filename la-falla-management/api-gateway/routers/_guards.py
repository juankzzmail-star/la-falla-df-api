"""Anti-hallucination guard for LLM-surfaced values (change wire-document-rag).

Same discipline as Busqueda de Oportunidades: a number/amount asserted by the model must be grounded
in the source text — either verbatim (accent-folded substring) OR by its digits (separators ignored,
so "$3.000.000.000" matches "3000000000"). An ungrounded amount is flagged, never asserted as fact.
"""
from __future__ import annotations

import re
import unicodedata

# A currency-like amount: a currency-prefixed figure ($ / US$ / € / COP / USD / EUR) or a bare grouped
# figure of at least millions (e.g. 600.000.000). Bare small numbers (years, counts) are ignored.
_AMOUNT_RE = re.compile(
    r"(?:US\$|\$|€|\bCOP\b|\bUSD\b|\bEUR\b)\s?\d[\d.,'’]*"
    r"|\d{1,3}(?:[.,'’]\d{3}){2,}(?:[.,]\d+)?",
    re.IGNORECASE,
)


def _norm(s: object) -> str:
    """Lowercase + strip accents (NFKD, drop combining marks)."""
    nfkd = unicodedata.normalize("NFKD", str(s or "").lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def value_is_grounded(value: object, source_text: str) -> bool:
    """True if `value` is supported by `source_text`. An empty value is trivially grounded."""
    s = str(value or "").strip()
    if not s:
        return True
    src = source_text or ""
    if _norm(s) in _norm(src):
        return True
    digits = re.sub(r"\D", "", s)
    if len(digits) >= 2:
        src_digits = re.sub(r"\D", "", src)
        if digits and digits in src_digits:
            return True
    return False


def find_amounts(text: str) -> list[str]:
    """Distinct currency-like amounts present in `text`, in order of first appearance."""
    seen: dict[str, None] = {}
    for m in _AMOUNT_RE.finditer(text or ""):
        seen.setdefault(m.group(0).strip(), None)
    return list(seen)


def ungrounded_amounts(analysis: str, source_text: str) -> list[str]:
    """Amounts asserted in `analysis` that are NOT grounded in `source_text`."""
    return [a for a in find_amounts(analysis) if not value_is_grounded(a, source_text)]

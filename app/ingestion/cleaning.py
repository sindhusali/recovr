"""Apply the shopkeeper's decisions about flagged rows.

The uploaded file is never changed. Skipping a row or merging two names only
affects what is counted on screen, and the choices can be undone by untick.
"""
from __future__ import annotations

import re

from app.domain.models import Invoice


def suggest_merge(invoices: list[Invoice], a: str, b: str) -> tuple[str, str]:
    """Pick which of two near-identical names to keep. Returns (canonical, alias).

    Keeps the name with more invoices; on a tie, the one with fewer odd
    characters (so 'Ravi Traders' beats 'Ravi Traders.'), then alphabetical.
    """
    counts: dict[str, int] = {}
    for inv in invoices:
        counts[inv.customer] = counts.get(inv.customer, 0) + 1

    def rank(name: str) -> tuple:
        return (-counts.get(name, 0), len(re.findall(r"[^A-Za-z0-9 ]", name)), name)

    keep, drop = sorted([a, b], key=rank)
    return keep, drop


def _resolve(name: str, merges: dict[str, str]) -> str:
    seen = set()
    while name in merges and name not in seen:  # follow chains, stop on loops
        seen.add(name)
        name = merges[name]
    return name


def apply_cleaning(invoices: list[Invoice], skip_rows: set[int],
                   merges: dict[str, str]) -> list[Invoice]:
    """Drop skipped rows and rename merged customers. Returns new objects."""
    out = []
    for inv in invoices:
        if inv.row_number is not None and inv.row_number in skip_rows:
            continue
        target = _resolve(inv.customer, merges)
        out.append(inv if target == inv.customer else inv.model_copy(update={"customer": target}))
    return out

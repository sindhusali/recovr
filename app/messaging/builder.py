"""Build a reminder: fixed template first, optional AI rewrite, strict validation.

The AI result is accepted only if it passes validate_rewrite(); otherwise the
fixed template is used. A wrong amount can therefore never reach a customer.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from app.messaging.templates import format_inr, render_template

Rewriter = Callable[[str, str, str], "str | None"]  # (text, tone, language) -> text

MAX_LEN = 600
_NUMBER = re.compile(r"\d+(?:,\d+)*(?:\.\d+)?")


def numbers_in(text: str) -> set[str]:
    return {n.replace(",", "") for n in _NUMBER.findall(text)}


def validate_rewrite(original: str, candidate: str, *, customer: str, amount) -> bool:
    """True only if the rewrite kept every fact intact."""
    if not candidate or len(candidate) > MAX_LEN:
        return False
    if format_inr(amount) not in candidate:        # exact amount, same format
        return False
    if customer.lower() not in candidate.lower():  # customer name preserved
        return False
    return numbers_in(candidate) == numbers_in(original)  # no added/changed numbers


@dataclass(frozen=True)
class Draft:
    text: str
    source: str  # "template" or "ai"
    note: str = ""


def build_message(*, customer: str, shop: str, amount, days: int, tone: str,
                  language: str, rewriter: Rewriter | None = None) -> Draft:
    base = render_template(language, tone, customer=customer, shop=shop,
                           amount=amount, days=days)
    if rewriter is None:
        return Draft(base, "template")
    try:
        candidate = rewriter(base, tone, language)
    except Exception:
        return Draft(base, "template", "AI failed; used standard template")
    if candidate is None:
        return Draft(base, "template", "AI unavailable; used standard template")
    candidate = candidate.strip()
    if validate_rewrite(base, candidate, customer=customer, amount=amount):
        return Draft(candidate, "ai")
    return Draft(base, "template", "AI changed a fact; used standard template")

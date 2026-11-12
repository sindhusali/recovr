"""Work out which column is which, even for unfamiliar headers.

Step 1: fixed aliases (fast, free, predictable).
Step 2: for fields still missing, ask the LLM. PRIVACY: the LLM never sees
ledger values. It gets only the header names plus a locally computed profile
of each column (e.g. "number", "date shaped 99/99/9999", "text, ~14 chars").
Step 3: the LLM answer is only a proposal. Code checks that every column
exists, is used once, and has the right kind of data. The shopkeeper then
confirms the mapping on screen.
"""
from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

import pandas as pd

from app.ingestion.loader import (
    _ISO_DATE,
    _NUM_DATE,
    COLUMN_ALIASES,
    REQUIRED,
    _is_blank,
    map_columns,
)

FIELD_DESCRIPTIONS = {
    "customer": "who owes the money (customer / party name)",
    "amount": "bill or invoice amount in rupees",
    "due_date": "date the payment was due",
    "invoice_date": "date the bill was issued",
    "invoice_no": "bill or invoice number",
    "paid_amount": "amount already received against the bill",
    "phone": "customer mobile number",
}
# which kinds of column are acceptable for each field
ACCEPTS = {
    "customer": {"text"},
    "amount": {"number"},
    "paid_amount": {"number"},
    "due_date": {"date"},
    "invoice_date": {"date"},
    "invoice_no": {"text", "number"},
    "phone": {"phone", "number", "text"},
}
JsonAI = Callable[[str], "dict | list | None"]


# --------------------------------------------------------------------------- profiling
def _looks_number(v: object) -> bool:
    if isinstance(v, (int, float, Decimal)):
        return True
    text = re.sub(r"[₹,\s]|rs\.?|inr", "", str(v), flags=re.IGNORECASE)
    try:
        Decimal(text)
        return True
    except InvalidOperation:
        return False


def _looks_date(v: object) -> bool:
    if isinstance(v, (pd.Timestamp,)) or hasattr(v, "year") and hasattr(v, "month"):
        return True
    if not isinstance(v, str):
        return False
    if _ISO_DATE.match(v) or _NUM_DATE.match(v):
        return True
    if re.search(r"[A-Za-z]{3}", v):  # 04-Nov-2026, Nov 4 2026
        return not pd.isna(pd.to_datetime(v, errors="coerce", dayfirst=True))
    return False


def _looks_phone(v: object) -> bool:
    digits = re.sub(r"\D", "", str(v))
    return 10 <= len(digits) <= 12 and bool(re.fullmatch(r"[+\d\s()-]+", str(v).strip()))


def _shape(v: object) -> str:
    """Digits -> 9, letters -> a. Reveals the pattern, not the value."""
    return re.sub(r"[A-Za-z]", "a", re.sub(r"\d", "9", str(v)))[:20]


def profile_column(values: pd.Series) -> dict:
    """Describe a column without revealing its contents."""
    vals = [v for v in values if not _is_blank(v)]
    if not vals:
        return {"kind": "empty", "shape": ""}
    sample = vals[:200]

    def share(fn) -> float:
        return sum(1 for v in sample if fn(v)) / len(sample)

    if share(_looks_date) >= 0.8:
        kind = "date"
    elif share(_looks_phone) >= 0.8:
        kind = "phone"
    elif share(_looks_number) >= 0.8:
        kind = "number"
    else:
        kind = "text"
    shape = _shape(sample[0]) if kind != "text" else f"~{round(sum(len(str(v)) for v in sample) / len(sample))} chars"
    return {"kind": kind, "shape": shape}


# --------------------------------------------------------------------------- validation
def validate_ai_mapping(raw, headers: list[str], profiles: dict[str, dict],
                        allowed_fields: set[str]) -> dict[str, str]:
    """Keep only entries that are plausible. Anything doubtful is dropped."""
    if not isinstance(raw, dict):
        return {}
    clean: dict[str, str] = {}
    used: set[str] = set()
    for fld, col in raw.items():
        if fld not in allowed_fields or not isinstance(col, str):
            continue
        if col not in headers or col in used:
            continue
        if profiles.get(col, {}).get("kind") not in ACCEPTS[fld]:
            continue
        clean[fld] = col
        used.add(col)
    return clean


def build_prompt(missing: list[str], candidates: list[str], profiles: dict[str, dict]) -> str:
    cols = [{"header": c, **profiles[c]} for c in candidates]
    fields = {f: FIELD_DESCRIPTIONS[f] for f in missing}
    return (
        "You match spreadsheet columns from a small shop's credit ledger to fields.\n"
        "Headers may be abbreviated or in English, Hindi or Telugu written in Latin letters.\n"
        f"Fields to find:\n{json.dumps(fields, ensure_ascii=False)}\n\n"
        f"Available columns (kind and shape come from analysing the data):\n"
        f"{json.dumps(cols, ensure_ascii=False)}\n\n"
        "Return ONLY a JSON object mapping each field to the exact header of the best "
        "column, or null if no column fits. Use each column at most once. "
        "Never invent headers."
    )


# --------------------------------------------------------------------------- main entry
@dataclass
class MappingSuggestion:
    mapping: dict[str, str]
    source: dict[str, str] = field(default_factory=dict)  # field -> "rules" | "ai"
    profiles: dict[str, dict] = field(default_factory=dict)

    @property
    def missing_required(self) -> list[str]:
        return [f for f in REQUIRED if f not in self.mapping]


def resolve_mapping(df: pd.DataFrame, ai: JsonAI | None = None) -> MappingSuggestion:
    headers = [str(c) for c in df.columns]
    mapping, unmapped = map_columns(headers)
    source = {f: "rules" for f in mapping}
    profiles = {h: profile_column(df[h]) for h in headers}

    still_missing = [f for f in COLUMN_ALIASES if f not in mapping]
    needs_ai = any(f in REQUIRED for f in still_missing)
    if ai is not None and needs_ai and unmapped:
        # ask only about fields we could not find, among columns not yet used
        answer = ai(build_prompt(still_missing, unmapped, profiles))
        proposal = validate_ai_mapping(answer, unmapped, profiles, set(still_missing))
        for fld, col in proposal.items():
            mapping[fld] = col
            source[fld] = "ai"
    return MappingSuggestion(mapping=mapping, source=source, profiles=profiles)

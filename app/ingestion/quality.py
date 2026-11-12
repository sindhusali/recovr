"""Data checks: flag rows that look wrong so the shopkeeper can look before
chasing a customer. These are fixed, explainable rules (no AI), so the result is
the same every time and costs nothing."""
from __future__ import annotations

import re
import statistics
from dataclasses import dataclass
from datetime import date
from difflib import SequenceMatcher

from app.domain.models import Invoice

MAX_NAMES_COMPARED = 400


@dataclass(frozen=True)
class Flag:
    row_number: int | None
    customer: str
    message: str


def _key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


def find_suspicious(invoices: list[Invoice], as_of: date) -> list[Flag]:
    flags: list[Flag] = []

    # 1. duplicates
    seen: dict[tuple, Invoice] = {}
    for inv in invoices:
        k = (_key(inv.customer), inv.invoice_no.strip().lower() or str(inv.due_date), inv.amount)
        first = seen.get(k)
        if first is None:
            seen[k] = inv
        else:
            where = f"row {first.row_number}" if first.row_number else "an earlier row"
            flags.append(Flag(inv.row_number, inv.customer,
                              f"Looks like a duplicate of {where} (same customer, bill and amount)."))

    # 2. per-invoice checks
    for inv in invoices:
        if inv.amount == 0:
            flags.append(Flag(inv.row_number, inv.customer, "Amount is zero."))
        if inv.paid_amount > inv.amount:
            flags.append(Flag(inv.row_number, inv.customer,
                              f"Paid (₹{inv.paid_amount:,.0f}) is more than the bill (₹{inv.amount:,.0f})."))
        if inv.invoice_date and inv.due_date < inv.invoice_date:
            flags.append(Flag(inv.row_number, inv.customer, "Due date is before the bill date."))
        age = (as_of - inv.due_date).days
        if age > 365 * 3 and not inv.is_settled:
            flags.append(Flag(inv.row_number, inv.customer,
                              f"Overdue by {age // 365} years. Typo, or an old bad debt?"))
        if (inv.due_date - as_of).days > 365 * 2:
            flags.append(Flag(inv.row_number, inv.customer,
                              "Due date is over 2 years in the future. Possible typo."))

    # 3. unusually large amounts
    amounts = [float(i.amount) for i in invoices if i.amount > 0]
    if len(amounts) >= 10:
        median = statistics.median(amounts)
        for inv in invoices:
            if median > 0 and float(inv.amount) > 20 * median:
                flags.append(Flag(inv.row_number, inv.customer,
                                  f"Amount ₹{inv.amount:,.0f} is over 20x the usual bill (₹{median:,.0f}). "
                                  "Extra zero?"))

    # 4. near-identical customer names
    names = sorted({i.customer for i in invoices})[:MAX_NAMES_COMPARED]
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            if _key(a) == _key(b) or SequenceMatcher(None, _key(a), _key(b)).ratio() >= 0.9:
                flags.append(Flag(None, a, f"'{a}' and '{b}' may be the same customer."))

    flags.sort(key=lambda f: (f.row_number is None, f.row_number or 0))
    return flags

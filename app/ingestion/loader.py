"""Load a ledger from CSV/Excel with messy column names.

Bad rows never crash the load: they are collected as RowIssue so the UI can
show the shopkeeper exactly what was skipped and why.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import BinaryIO

import pandas as pd
from pydantic import ValidationError

from app.domain.models import Invoice, LoadResult, RowIssue

# canonical field -> accepted header spellings (compared after normalising)
COLUMN_ALIASES: dict[str, list[str]] = {
    "customer": ["customer", "customer name", "party", "party name", "name",
                 "client", "buyer", "account name", "ledger"],
    "amount": ["amount", "bill amount", "invoice amount", "total", "debit",
               "bill value", "net amount", "balance due"],
    "due_date": ["due date", "due", "payment due", "due on", "duedate"],
    "invoice_date": ["invoice date", "bill date", "date", "invoicedate"],
    "invoice_no": ["invoice no", "invoice number", "bill no", "bill number",
                   "inv no", "voucher no", "ref no", "invoice"],
    "paid_amount": ["paid", "paid amount", "received", "amount received",
                    "credit", "payment received"],
    "phone": ["phone", "mobile", "mobile no", "phone number", "contact",
              "whatsapp", "contact no"],
}

REQUIRED = ["customer", "amount", "due_date"]


def _norm(header: object) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(header).lower()).strip()


def map_columns(columns: list[str]) -> tuple[dict[str, str], list[str]]:
    """Return ({canonical: original_header}, [unmapped original headers])."""
    lookup = {_norm(a): field for field, aliases in COLUMN_ALIASES.items()
              for a in aliases}
    mapping: dict[str, str] = {}
    unmapped: list[str] = []
    for col in columns:
        field = lookup.get(_norm(col))
        if field and field not in mapping:
            mapping[field] = col
        else:
            unmapped.append(col)
    return mapping, unmapped


def _to_decimal(value: object, *, default: Decimal | None = None) -> Decimal:
    if value is None or (isinstance(value, float) and pd.isna(value)) \
            or (isinstance(value, str) and not value.strip()):
        if default is not None:
            return default
        raise ValueError("amount is blank")
    text = re.sub(r"[₹,\s]|rs\.?|inr", "", str(value), flags=re.IGNORECASE)
    try:
        return Decimal(text)
    except InvalidOperation:
        raise ValueError(f"'{value}' is not a valid amount") from None


def _to_date(value: object, *, required: bool = True):
    if value is None or (not isinstance(value, str) and pd.isna(value)) \
            or (isinstance(value, str) and not value.strip()):
        if required:
            raise ValueError("date is blank")
        return None
    # Indian ledgers are day-first (04/11/2026 = 4 Nov 2026)
    parsed = pd.to_datetime(value, dayfirst=True, errors="coerce")
    if pd.isna(parsed):
        raise ValueError(f"'{value}' is not a valid date")
    return parsed.date()


def _to_text(value: object) -> str:
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def read_table(source: str | Path | BinaryIO, filename: str | None = None) -> pd.DataFrame:
    """Read CSV or Excel into a DataFrame of raw values (no type guessing)."""
    name = (filename or str(getattr(source, "name", source))).lower()
    if name.endswith((".xlsx", ".xlsm", ".xls")):
        return pd.read_excel(source, dtype=object)
    return pd.read_csv(source, dtype=object, skip_blank_lines=True)


def load_invoices(source: str | Path | BinaryIO, filename: str | None = None) -> LoadResult:
    df = read_table(source, filename)
    df = df.dropna(how="all")  # fully blank rows are not errors

    mapping, unmapped = map_columns([str(c) for c in df.columns])
    missing = [f for f in REQUIRED if f not in mapping]
    if missing:
        raise ValueError(
            "Could not find required column(s): " + ", ".join(missing)
            + ". Found: " + ", ".join(map(str, df.columns))
        )

    result = LoadResult(unmapped_columns=unmapped)
    for idx, row in df.iterrows():
        row_number = int(idx) + 2  # header is row 1
        get = lambda f: row[mapping[f]] if f in mapping else None  # noqa: E731
        try:
            invoice = Invoice(
                customer=_to_text(get("customer")),
                amount=_to_decimal(get("amount")),
                due_date=_to_date(get("due_date")),
                invoice_no=_to_text(get("invoice_no")),
                invoice_date=_to_date(get("invoice_date"), required=False),
                paid_amount=_to_decimal(get("paid_amount"), default=Decimal("0")),
                phone=_to_text(get("phone")),
            )
        except (ValueError, ValidationError) as exc:
            reason = exc.errors()[0]["msg"] if isinstance(exc, ValidationError) else str(exc)
            result.issues.append(RowIssue(row_number=row_number, reason=reason))
            continue
        result.invoices.append(invoice)
    return result

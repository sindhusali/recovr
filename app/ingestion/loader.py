"""Load a ledger from CSV/Excel with messy files and column names.

Handles: title rows above the header, odd delimiters and encodings, Indian
day-first dates (and ISO dates), rupee symbols and commas in amounts.

Bad rows never crash the load: they are collected as RowIssue so the UI can
show the shopkeeper exactly what was skipped and why.
"""
from __future__ import annotations

import csv
import io
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
HEADER_SCAN_ROWS = 15
_ISO_DATE = re.compile(r"^\s*(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})(?:[ T].*)?$")
_NUM_DATE = re.compile(r"^\s*(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})\s*$")


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


# --------------------------------------------------------------------------- values
def _is_blank(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _to_decimal(value: object, *, default: Decimal | None = None) -> Decimal:
    if _is_blank(value):
        if default is not None:
            return default
        raise ValueError("amount is blank")
    text = re.sub(r"[₹,\s]|rs\.?|inr", "", str(value), flags=re.IGNORECASE)
    try:
        return Decimal(text)
    except InvalidOperation:
        raise ValueError(f"'{value}' is not a valid amount") from None


def infer_dayfirst(values) -> bool:
    """Decide day/month order for a column of numeric dates like 04/11/2026.

    If any value has a first part above 12 it must be day-first; if any has a
    second part above 12 it must be month-first; otherwise assume the Indian
    day-first convention.
    """
    first_big = second_big = False
    for v in values:
        if not isinstance(v, str):
            continue
        m = _NUM_DATE.match(v)
        if m:
            first_big |= int(m.group(1)) > 12
            second_big |= int(m.group(2)) > 12
    if second_big and not first_big:
        return False
    return True


def _to_date(value: object, *, required: bool = True, dayfirst: bool = True):
    if _is_blank(value):
        if required:
            raise ValueError("date is blank")
        return None
    if isinstance(value, str):
        iso = _ISO_DATE.match(value)
        if iso:  # 2026-11-04 is year-month-day, whatever dayfirst says
            try:
                return pd.Timestamp(int(iso.group(1)), int(iso.group(2)),
                                    int(iso.group(3))).date()
            except ValueError:
                raise ValueError(f"'{value}' is not a valid date") from None
    parsed = pd.to_datetime(value, dayfirst=dayfirst, errors="coerce")
    if pd.isna(parsed):
        raise ValueError(f"'{value}' is not a valid date")
    return parsed.date()


def _to_text(value: object) -> str:
    if _is_blank(value):
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


# --------------------------------------------------------------------------- reading
def _read_bytes(source) -> tuple[bytes, str]:
    if isinstance(source, (str, Path)):
        path = Path(source)
        return path.read_bytes(), path.name
    data = source.read()
    if hasattr(source, "seek"):
        source.seek(0)
    if isinstance(data, str):
        data = data.encode("utf-8")
    return data, str(getattr(source, "name", ""))


def _decode(data: bytes) -> str:
    for enc in ("utf-8-sig", "utf-16", "cp1252"):
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return data.decode("latin-1")


def _read_csv_rows(text: str) -> pd.DataFrame:
    sample = "\n".join(text.splitlines()[:30])
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    rows = list(csv.reader(io.StringIO(text), dialect))
    width = max((len(r) for r in rows), default=0)
    padded = [r + [""] * (width - len(r)) for r in rows]
    return pd.DataFrame(padded, dtype=object)


def read_raw_table(source: str | Path | BinaryIO, filename: str | None = None) -> pd.DataFrame:
    """Read the sheet as-is: no header, no type guessing. Row i = sheet row i+1."""
    data, name = _read_bytes(source)
    name = (filename or name).lower()
    if name.endswith((".xlsx", ".xlsm", ".xls")):
        raw = pd.read_excel(io.BytesIO(data), header=None, dtype=object)
    else:
        raw = _read_csv_rows(_decode(data))
    return raw.replace(r"^\s*$", pd.NA, regex=True)


def _is_texty(value: object) -> bool:
    """True for header-like cells: words, not numbers or dates."""
    if isinstance(value, str):
        text = value.strip()
        if _ISO_DATE.match(text) or _NUM_DATE.match(text):
            return False
        try:
            _to_decimal(text)
            return False
        except ValueError:
            return True
    return False


def find_header_row(raw: pd.DataFrame) -> int:
    """Index of the header row.

    1) the first top row whose cells match known header names (2 or more), else
    2) the first top row that is all words and nearly as wide as the data rows
       (skips short title lines such as 'OUTSTANDING REPORT'), else row 0.
    """
    top = min(HEADER_SCAN_ROWS, len(raw))
    for i in range(top):
        cells = [str(c) for c in raw.iloc[i] if not _is_blank(c)]
        mapped, _ = map_columns(cells)
        if len(mapped) >= 2:
            return i
    widths = [sum(not _is_blank(c) for c in raw.iloc[i]) for i in range(top)]
    widest = max(widths, default=0)
    for i in range(top):
        cells = [c for c in raw.iloc[i] if not _is_blank(c)]
        if widest >= 3 and len(cells) >= 0.6 * widest and all(_is_texty(c) for c in cells):
            return i
    return 0


def read_ledger_table(source: str | Path | BinaryIO, filename: str | None = None) -> pd.DataFrame:
    """Raw table with the real header applied. The index keeps the sheet row (0-based)."""
    raw = read_raw_table(source, filename)
    if raw.empty:
        raise ValueError("The file is empty.")
    h = find_header_row(raw)
    headers = []
    for i, c in enumerate(raw.iloc[h]):
        headers.append(str(c).strip() if not _is_blank(c) else f"column_{i + 1}")
    df = raw.iloc[h + 1:].copy()
    df.columns = headers
    return df.dropna(how="all")


# --------------------------------------------------------------------------- loading
def invoices_from_frame(df: pd.DataFrame, mapping: dict[str, str] | None = None) -> LoadResult:
    """Turn a ledger table into invoices, using `mapping` (canonical -> header)."""
    auto, unmapped = map_columns([str(c) for c in df.columns])
    if mapping is None:
        mapping = auto
    else:
        used = set(mapping.values())
        unmapped = [c for c in map(str, df.columns) if c not in used]
    missing = [f for f in REQUIRED if f not in mapping]
    if missing:
        raise ValueError(
            "Could not find required column(s): " + ", ".join(missing)
            + ". Found: " + ", ".join(map(str, df.columns))
        )

    def col_dayfirst(field: str) -> bool:
        return infer_dayfirst(df[mapping[field]]) if field in mapping else True

    due_first, inv_first = col_dayfirst("due_date"), col_dayfirst("invoice_date")

    result = LoadResult(unmapped_columns=unmapped)
    for idx, row in df.iterrows():
        row_number = int(idx) + 1  # index is the 0-based sheet row; sheet rows start at 1
        get = lambda f: row[mapping[f]] if f in mapping else None  # noqa: E731
        try:
            invoice = Invoice(
                customer=_to_text(get("customer")),
                amount=_to_decimal(get("amount")),
                due_date=_to_date(get("due_date"), dayfirst=due_first),
                invoice_no=_to_text(get("invoice_no")),
                invoice_date=_to_date(get("invoice_date"), required=False, dayfirst=inv_first),
                paid_amount=_to_decimal(get("paid_amount"), default=Decimal("0")),
                phone=_to_text(get("phone")),
                row_number=row_number,
            )
        except (ValueError, ValidationError) as exc:
            reason = exc.errors()[0]["msg"] if isinstance(exc, ValidationError) else str(exc)
            result.issues.append(RowIssue(row_number=row_number, reason=reason))
            continue
        result.invoices.append(invoice)
    return result


def load_invoices(source: str | Path | BinaryIO, filename: str | None = None,
                  mapping: dict[str, str] | None = None) -> LoadResult:
    return invoices_from_frame(read_ledger_table(source, filename), mapping)

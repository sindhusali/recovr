import io
from datetime import date
from decimal import Decimal

import pytest

from app.ingestion.loader import load_invoices, map_columns


def csv_file(text: str) -> io.StringIO:
    f = io.StringIO(text.strip() + "\n")
    f.name = "ledger.csv"
    return f


def test_maps_messy_headers():
    mapping, unmapped = map_columns(["Party Name", "Bill Amount", "Due Date", "Notes"])
    assert mapping == {"customer": "Party Name", "amount": "Bill Amount",
                       "due_date": "Due Date"}
    assert unmapped == ["Notes"]


def test_loads_valid_rows_and_parses_indian_dates():
    res = load_invoices(csv_file(
        "Party Name,Bill Amount,Due Date,Received\n"
        "Ravi Traders,\"₹12,500\",04/11/2026,2500\n"
    ))
    assert not res.issues
    inv = res.invoices[0]
    assert inv.customer == "Ravi Traders"
    assert inv.amount == Decimal("12500")
    assert inv.due_date == date(2026, 11, 4)  # day-first, not April 11
    assert inv.outstanding == Decimal("10000")


def test_bad_rows_are_reported_not_fatal():
    res = load_invoices(csv_file(
        "Customer,Amount,Due Date\n"
        "Good Shop,1000,01/10/2026\n"
        ",500,01/10/2026\n"
        "Bad Amount,abc,01/10/2026\n"
        "Bad Date,500,not-a-date\n"
    ))
    assert len(res.invoices) == 1
    assert [i.row_number for i in res.issues] == [3, 4, 5]


def test_blank_rows_are_ignored_silently():
    res = load_invoices(csv_file(
        "Customer,Amount,Due Date\n"
        "A,100,01/10/2026\n"
        ",,\n"
    ))
    assert len(res.invoices) == 1
    assert res.issues == []


def test_missing_required_column_raises_clear_error():
    with pytest.raises(ValueError, match="due_date"):
        load_invoices(csv_file("Customer,Amount\nA,100\n"))


def test_paid_defaults_to_zero_when_absent():
    res = load_invoices(csv_file("Customer,Amount,Due Date\nA,100,01/10/2026\n"))
    assert res.invoices[0].paid_amount == 0


def test_loads_sample_file_end_to_end():
    from pathlib import Path
    sample = Path(__file__).resolve().parent.parent / "data" / "sample_ledger.csv"
    if not sample.exists():
        pytest.skip("run scripts/make_sample_data.py first")
    res = load_invoices(sample)
    assert len(res.invoices) == 200 and not res.issues

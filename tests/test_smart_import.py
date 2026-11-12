import io
from datetime import date

import pandas as pd

from app.ingestion.loader import (
    infer_dayfirst,
    invoices_from_frame,
    load_invoices,
    read_ledger_table,
)
from app.ingestion.smart_mapping import (
    profile_column,
    resolve_mapping,
    validate_ai_mapping,
)


def f(text: str, name="ledger.csv"):
    b = io.BytesIO(text.strip().encode("utf-8"))
    b.name = name
    return b


# ---------------------------------------------------------------- loader robustness
def test_iso_dates_are_year_month_day_not_day_first():
    res = load_invoices(f("Customer,Amount,Due Date\nA,100,2026-11-04\n"))
    assert res.invoices[0].due_date == date(2026, 11, 4)  # was misread as 11 April


def test_month_first_file_is_detected():
    assert infer_dayfirst(["11/13/2026", "10/02/2026"]) is False
    assert infer_dayfirst(["13/11/2026", "10/02/2026"]) is True
    assert infer_dayfirst(["01/02/2026"]) is True  # ambiguous -> Indian day-first
    res = load_invoices(f("Customer,Amount,Due Date\nA,100,11/13/2026\nB,100,10/02/2026\n"))
    assert [i.due_date for i in res.invoices] == [date(2026, 11, 13), date(2026, 10, 2)]


def test_title_rows_above_the_header_are_skipped():
    res = load_invoices(f(
        "Sri Stores - Outstanding Report\n"
        "Printed on 04/11/2026\n"
        "\n"
        "Party Name,Bill Amount,Due Date\n"
        "Ravi Traders,1000,01/10/2026\n"
        "Anitha Mart,2000,05/10/2026\n"
    ))
    assert [i.customer for i in res.invoices] == ["Ravi Traders", "Anitha Mart"]
    assert [i.row_number for i in res.invoices] == [5, 6]  # real sheet rows


def test_semicolon_and_tab_delimiters():
    for sep in (";", "\t"):
        text = sep.join(["Customer", "Amount", "Due Date"]) + "\n" + sep.join(["A", "100", "01/10/2026"])
        assert len(load_invoices(f(text)).invoices) == 1


def test_windows_1252_file_with_rupee_sign():
    raw = "Customer,Amount,Due Date\nRavi,₹1,000 ,01/10/2026\n".encode("cp1252", errors="replace")
    b = io.BytesIO(raw)
    b.name = "x.csv"
    assert len(load_invoices(b).issues) <= 1  # does not crash on odd encoding


def test_excel_file_with_real_dates(tmp_path):
    p = tmp_path / "l.xlsx"
    pd.DataFrame({"Party": ["A"], "Amt": [500], "Due": [pd.Timestamp("2026-11-04")]}).to_excel(p, index=False)
    df = read_ledger_table(p)
    res = invoices_from_frame(df, {"customer": "Party", "amount": "Amt", "due_date": "Due"})
    assert res.invoices[0].due_date == date(2026, 11, 4)


def test_explicit_mapping_overrides_headers():
    df = read_ledger_table(f("Who,How much,By when\nA,500,01/10/2026\n"))
    res = invoices_from_frame(df, {"customer": "Who", "amount": "How much", "due_date": "By when"})
    assert res.invoices[0].amount == 500 and not res.issues


# ---------------------------------------------------------------- profiling (privacy)
def test_profile_describes_columns_without_values():
    df = read_ledger_table(f(
        "Nm,Amt,Dt,Ph\n"
        "Ravi Traders,12500,04/11/2026,9876543210\n"
        "Anitha Mart,800,05/11/2026,9123456780\n"))
    kinds = {c: profile_column(df[c])["kind"] for c in df.columns}
    assert kinds == {"Nm": "text", "Amt": "number", "Dt": "date", "Ph": "phone"}
    blob = str({c: profile_column(df[c]) for c in df.columns})
    assert "Ravi" not in blob and "9876543210" not in blob


# ---------------------------------------------------------------- AI mapping
UNUSUAL = "Nm,Amt,Dt,Ph\nRavi Traders,12500,04/11/2026,9876543210\nAnitha Mart,800,05/11/2026,9123456780\n"


def test_rules_resolve_known_headers_without_calling_ai():
    called = []
    df = read_ledger_table(f("Party Name,Bill Amount,Due Date\nA,1,01/10/2026\n"))
    s = resolve_mapping(df, ai=lambda p: called.append(p))
    assert not s.missing_required and not called
    assert set(s.source.values()) == {"rules"}


def test_ai_fills_unknown_headers_and_prompt_has_no_ledger_values():
    df = read_ledger_table(f(UNUSUAL))
    prompts = []

    def fake_ai(prompt):
        prompts.append(prompt)
        return {"customer": "Nm", "amount": "Amt", "due_date": "Dt", "phone": "Ph"}

    s = resolve_mapping(df, ai=fake_ai)
    assert s.mapping == {"customer": "Nm", "amount": "Amt", "due_date": "Dt", "phone": "Ph"}
    assert s.source["amount"] == "ai"
    assert "Ravi" not in prompts[0] and "12500" not in prompts[0]


def test_bad_ai_answers_are_dropped():
    df = read_ledger_table(f(UNUSUAL))
    headers = list(df.columns)
    profiles = {h: profile_column(df[h]) for h in headers}
    allowed = {"customer", "amount", "due_date"}
    # invented header, wrong kind (text column as amount), duplicate column use, unknown field
    raw = {"customer": "Name", "amount": "Nm", "due_date": "Amt", "bogus": "Dt"}
    assert validate_ai_mapping(raw, headers, profiles, allowed) == {}
    assert validate_ai_mapping("nonsense", headers, profiles, allowed) == {}
    assert validate_ai_mapping({"amount": "Amt", "due_date": "Amt"}, headers, profiles, allowed) == {"amount": "Amt"}


def test_ai_failure_leaves_fields_missing_for_manual_choice():
    df = read_ledger_table(f(UNUSUAL))
    s = resolve_mapping(df, ai=lambda p: None)
    assert set(s.missing_required) == {"customer", "amount", "due_date"}
    s2 = resolve_mapping(df, ai=None)
    assert s2.missing_required


def test_title_rows_skipped_even_when_headers_are_unfamiliar():
    df = read_ledger_table(f(
        "SRI STORES - OUTSTANDING REPORT\n"
        "Printed 12/11/2026\n"
        "\n"
        "Nm,Amt,Dt,Ph\n"
        "Ravi Traders,\"₹12,500\",2026-09-01,9876543210\n"
        "Anitha Mart,800,2026-10-05,9123456780\n"))
    assert list(df.columns) == ["Nm", "Amt", "Dt", "Ph"] and len(df) == 2
    res = invoices_from_frame(df, {"customer": "Nm", "amount": "Amt", "due_date": "Dt"})
    assert res.invoices[0].due_date == date(2026, 9, 1) and res.invoices[0].row_number == 5


def test_file_without_any_title_rows_still_uses_first_row_as_header():
    df = read_ledger_table(f("Nm,Amt,Dt\nRavi,500,01/10/2026\n"))
    assert list(df.columns) == ["Nm", "Amt", "Dt"] and len(df) == 1

from datetime import date
from decimal import Decimal

from app.domain.aging import aging_report
from app.domain.models import Invoice
from app.domain.money import format_inr, rupees
from app.ingestion.cleaning import apply_cleaning, suggest_merge
from app.ingestion.quality import find_suspicious

TODAY = date(2026, 11, 4)


def inv(customer, amount=1000, row=2, no="1", due=date(2026, 10, 1)):
    return Invoice(customer=customer, amount=Decimal(amount), due_date=due,
                   invoice_no=no, row_number=row)


# ---------------------------------------------------------------- skip rows
def test_skipped_rows_are_left_out():
    invoices = [inv("A", row=2), inv("B", row=3, no="2"), inv("C", row=4, no="3")]
    out = apply_cleaning(invoices, {3}, {})
    assert [i.customer for i in out] == ["A", "C"]


def test_skip_ignores_rows_without_a_row_number():
    a = Invoice(customer="A", amount=Decimal(5), due_date=date(2026, 10, 1))
    assert apply_cleaning([a], {1, 2, 3}, {}) == [a]


def test_duplicate_skip_fixes_the_total():
    invoices = [inv("Anitha", 8200, row=6), inv("Anitha", 8200, row=17)]
    before = aging_report(invoices, TODAY).iloc[0]["total_outstanding"]
    after = aging_report(apply_cleaning(invoices, {17}, {}), TODAY).iloc[0]["total_outstanding"]
    assert (before, after) == (16400, 8200)


# ---------------------------------------------------------------- merge names
def test_merge_combines_two_customers_into_one():
    invoices = [inv("Ravi Traders", 12500, row=2), inv("Ravi Traders.", 3000, row=3, no="2")]
    rep = aging_report(apply_cleaning(invoices, set(), {"Ravi Traders.": "Ravi Traders"}), TODAY)
    assert list(rep["customer"]) == ["Ravi Traders"]
    assert rep.iloc[0]["total_outstanding"] == 15500


def test_merge_follows_chains_and_survives_loops():
    invoices = [inv("A", row=2), inv("B", row=3, no="2")]
    out = apply_cleaning(invoices, set(), {"A": "B", "B": "C"})
    assert {i.customer for i in out} == {"C"}
    looped = apply_cleaning(invoices, set(), {"A": "B", "B": "A"})  # must not hang
    assert len(looped) == 2


def test_original_invoices_are_not_modified():
    invoices = [inv("Ravi Traders.", row=2)]
    apply_cleaning(invoices, set(), {"Ravi Traders.": "Ravi Traders"})
    assert invoices[0].customer == "Ravi Traders."


def test_suggest_merge_prefers_more_invoices_then_cleaner_name():
    many = [inv("Ravi Traders.", row=i, no=str(i)) for i in range(2, 5)] + [inv("Ravi Traders", row=9, no="9")]
    assert suggest_merge(many, "Ravi Traders", "Ravi Traders.") == ("Ravi Traders.", "Ravi Traders")
    tie = [inv("Ravi Traders", row=2), inv("Ravi Traders.", row=3, no="2")]
    assert suggest_merge(tie, "Ravi Traders", "Ravi Traders.") == ("Ravi Traders", "Ravi Traders.")
    assert suggest_merge(tie, "Ravi Traders.", "Ravi Traders") == ("Ravi Traders", "Ravi Traders.")


# ---------------------------------------------------------------- flags carry what the UI needs
def test_name_flags_carry_both_names_and_row_flags_carry_rows():
    invoices = [inv("Ravi Traders", row=2), inv("Ravi Traders.", row=3, no="2"),
                inv("X", amount=0, row=4, no="3")]
    flags = find_suspicious(invoices, TODAY)
    names = [f for f in flags if f.kind == "names"]
    rows = [f for f in flags if f.kind == "row"]
    assert len(names) == 1 and {names[0].customer, names[0].other} == {"Ravi Traders", "Ravi Traders."}
    assert [f.row_number for f in rows] == [4]


# ---------------------------------------------------------------- Indian number format
def test_rupees_uses_lakh_grouping_everywhere():
    assert rupees(980000) == "₹9,80,000"
    assert rupees(Decimal("2069400")) == "₹20,69,400"
    assert rupees(999) == "₹999"
    assert format_inr(1250.5) == "1,250.50"


def test_flag_messages_use_indian_grouping():
    invoices = [inv(f"C{i}", 1000, row=i + 2, no=str(i)) for i in range(12)]
    invoices.append(inv("Typo", 980000, row=99, no="99"))
    msg = [f.message for f in find_suspicious(invoices, TODAY) if f.row_number == 99][0]
    assert "₹9,80,000" in msg and "₹1,000" in msg

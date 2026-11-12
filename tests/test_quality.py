from datetime import date
from decimal import Decimal

from app.domain.models import Invoice
from app.ingestion.quality import find_suspicious

TODAY = date(2026, 11, 4)


def inv(customer="A", amount=1000, due=date(2026, 10, 1), no="1", paid=0, row=2, inv_date=None):
    return Invoice(customer=customer, amount=Decimal(amount), due_date=due, invoice_no=no,
                   paid_amount=Decimal(paid), row_number=row, invoice_date=inv_date)


def msgs(invoices):
    return [f.message for f in find_suspicious(invoices, TODAY)]


def test_clean_data_has_no_flags():
    assert find_suspicious([inv("A", no="1"), inv("B", no="2", row=3)], TODAY) == []


def test_duplicate_rows_flagged_with_reference_to_first():
    flags = find_suspicious([inv(row=2), inv(row=3)], TODAY)
    assert len(flags) == 1 and flags[0].row_number == 3
    assert "row 2" in flags[0].message


def test_same_customer_different_bill_is_not_duplicate():
    assert find_suspicious([inv(no="1"), inv(no="2", row=3)], TODAY) == []


def test_overpaid_zero_and_date_order():
    assert any("more than the bill" in m for m in msgs([inv(amount=100, paid=500)]))
    assert any("zero" in m for m in msgs([inv(amount=0)]))
    assert any("before the bill date" in m for m in
               msgs([inv(due=date(2026, 1, 1), inv_date=date(2026, 3, 1))]))


def test_very_old_and_far_future_dates():
    assert any("years" in m for m in msgs([inv(due=date(2020, 1, 1))]))
    assert any("future" in m for m in msgs([inv(due=date(2030, 1, 1))]))


def test_amount_with_extra_zero_flagged():
    invoices = [inv(f"C{i}", 1000, no=str(i), row=i + 2) for i in range(12)]
    invoices.append(inv("Typo", 500000, no="99", row=99))
    flagged = find_suspicious(invoices, TODAY)
    assert [f.row_number for f in flagged] == [99]
    assert "20x" in flagged[0].message


def test_similar_customer_names_flagged_once():
    invoices = [inv("Ravi Traders", no="1"), inv("Ravi Traders.", no="2", row=3),
                inv("Totally Different", no="3", row=4)]
    flags = find_suspicious(invoices, TODAY)
    assert len(flags) == 1 and "may be the same customer" in flags[0].message


def test_flags_sorted_by_row():
    flags = find_suspicious([inv(amount=0, row=9), inv("B", amount=0, no="2", row=4)], TODAY)
    assert [f.row_number for f in flags] == [4, 9]

from datetime import date
from decimal import Decimal

from app.domain.aging import (
    aging_report, bucket_for, days_overdue, invoices_to_frame, total_overdue,
)
from app.domain.models import Invoice

TODAY = date(2026, 11, 4)


def inv(customer="A", amount=1000, due=date(2026, 10, 1), paid=0, no="1"):
    return Invoice(customer=customer, amount=Decimal(amount), due_date=due,
                   paid_amount=Decimal(paid), invoice_no=no)


def test_future_due_date_is_not_overdue():
    assert days_overdue(inv(due=date(2026, 12, 1)), TODAY) == 0


def test_due_today_is_not_overdue():
    assert days_overdue(inv(due=TODAY), TODAY) == 0


def test_days_overdue_counts_correctly():
    assert days_overdue(inv(due=date(2026, 10, 25)), TODAY) == 10


def test_bucket_boundaries():
    assert bucket_for(0) == "Current"
    assert bucket_for(1) == "1-30"
    assert bucket_for(30) == "1-30"
    assert bucket_for(31) == "31-60"
    assert bucket_for(60) == "31-60"
    assert bucket_for(61) == "60+"


def test_partial_payment_reduces_outstanding():
    i = inv(amount=1000, paid=400)
    assert i.outstanding == Decimal("600")


def test_overpayment_never_negative():
    assert inv(amount=1000, paid=1500).outstanding == Decimal("0")


def test_settled_invoices_excluded():
    df = invoices_to_frame([inv(paid=1000), inv(no="2")], TODAY)
    assert len(df) == 1


def test_report_splits_buckets_per_customer():
    invoices = [
        inv("A", 1000, due=date(2026, 10, 20), no="1"),  # 15 days -> 1-30
        inv("A", 2000, due=date(2026, 8, 1), no="2"),    # 95 days -> 60+
        inv("B", 500, due=date(2026, 12, 1), no="3"),    # current
    ]
    rep = aging_report(invoices, TODAY).set_index("customer")
    assert rep.loc["A", "1-30"] == 1000
    assert rep.loc["A", "60+"] == 2000
    assert rep.loc["A", "total_outstanding"] == 3000
    assert rep.loc["A", "max_days_overdue"] == 95
    assert rep.loc["B", "Current"] == 500


def test_empty_input_gives_empty_report():
    assert aging_report([], TODAY).empty


def test_total_overdue_ignores_current_and_uses_outstanding():
    invoices = [
        inv(amount=1000, paid=200, due=date(2026, 10, 1)),   # 800 overdue
        inv(amount=5000, due=date(2026, 12, 1), no="2"),     # not due yet
    ]
    assert total_overdue(invoices, TODAY) == Decimal("800")

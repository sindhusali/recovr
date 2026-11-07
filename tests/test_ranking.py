from datetime import date
from decimal import Decimal

from app.domain.aging import aging_report
from app.domain.models import Invoice
from app.domain.ranking import priority_score, rank_customers, suggested_tone

TODAY = date(2026, 11, 4)


def inv(customer, amount, due, no="1", paid=0):
    return Invoice(customer=customer, amount=Decimal(amount), due_date=due,
                   invoice_no=no, paid_amount=Decimal(paid))


def test_tone_escalates_with_age():
    assert suggested_tone(10) == "friendly"
    assert suggested_tone(30) == "friendly"
    assert suggested_tone(31) == "firm"
    assert suggested_tone(60) == "firm"
    assert suggested_tone(61) == "final"


def test_older_debt_can_outrank_slightly_bigger_recent_debt():
    assert priority_score(10_000, 90) > priority_score(12_000, 10)


def test_huge_amount_still_beats_tiny_old_one():
    assert priority_score(100_000, 5) > priority_score(500, 120)


def test_age_effect_is_capped():
    assert priority_score(1000, 120) == priority_score(1000, 400)


def test_ranking_order_and_ranks():
    invoices = [
        inv("Small Recent", 2000, date(2026, 10, 25), "1"),
        inv("Big Old", 50000, date(2026, 7, 1), "2"),
        inv("Medium", 10000, date(2026, 9, 20), "3"),
    ]
    ranked = rank_customers(aging_report(invoices, TODAY))
    assert list(ranked["customer"]) == ["Big Old", "Medium", "Small Recent"]
    assert list(ranked["rank"]) == [1, 2, 3]
    assert ranked.loc[0, "tone"] == "final"


def test_customers_with_nothing_overdue_are_excluded():
    invoices = [inv("Not Due Yet", 5000, date(2026, 12, 1)),
                inv("Late", 1000, date(2026, 10, 1), "2")]
    ranked = rank_customers(aging_report(invoices, TODAY))
    assert list(ranked["customer"]) == ["Late"]


def test_empty_report():
    assert rank_customers(aging_report([], TODAY)).empty

from datetime import date
from decimal import Decimal

from app.domain.advice import (
    CustomerFacts,
    ai_summary,
    facts_from_history,
    recommend,
)
from app.storage import repo

TODAY = date(2026, 11, 4)


def facts(**kw):
    base = dict(days_overdue=20, overdue_amount=Decimal("5000"))
    base.update(kw)
    return CustomerFacts(**base)


def test_new_customer_gets_tone_from_age():
    a = recommend(facts(days_overdue=20), TODAY)
    assert (a.kind, a.tone) == ("message", "friendly")
    assert recommend(facts(days_overdue=75), TODAY).tone == "final"


def test_future_promise_means_wait():
    a = recommend(facts(pending_promise_date=date(2026, 11, 8),
                        pending_promise_amount=Decimal("3000")), TODAY)
    assert a.kind == "wait" and "08 Nov" in a.headline


def test_missed_promise_means_firmer_follow_up():
    a = recommend(facts(days_overdue=20, pending_promise_date=date(2026, 11, 1)), TODAY)
    assert a.kind == "message" and a.tone == "firm"  # friendly bumped up one step
    assert "3 day" in a.reasons[0]


def test_two_broken_promises_on_old_debt_escalates():
    a = recommend(facts(days_overdue=60, promises_broken=2), TODAY)
    assert a.kind == "escalate" and "pausing new credit" in a.headline


def test_three_reminders_without_result_suggests_call():
    assert recommend(facts(days_overdue=40, reminders_sent=3), TODAY).kind == "call"


def test_recent_reminder_means_wait():
    a = recommend(facts(reminders_sent=1, days_since_last_reminder=1), TODAY)
    assert a.kind == "wait"


def test_one_broken_promise_bumps_tone():
    assert recommend(facts(days_overdue=20, promises_broken=1), TODAY).tone == "firm"


def test_tone_never_exceeds_final():
    assert recommend(facts(days_overdue=90, promises_broken=1), TODAY).tone == "final"


# ---------------------------------------------------------------- facts from the database
def test_facts_built_from_real_history(tmp_path):
    db = tmp_path / "t.db"
    repo.record_reminder(db, customer="A", phone=None, language="en", tone="firm", source="template",
                         amount=5000, days_overdue=40, draft_text="x", final_text="x")
    pid = repo.add_promise(db, customer="A", amount=2000, promised_date=date(2026, 11, 10))
    h = repo.customer_history(db, "A")
    f = facts_from_history(h, days_overdue=40, overdue_amount=5000, today=date.today())
    assert f.reminders_sent == 1 and f.days_since_last_reminder == 0
    assert f.pending_promise_date == date(2026, 11, 10) and f.pending_promise_amount == Decimal("2000")
    repo.set_promise_status(db, pid, "broken")
    h = repo.customer_history(db, "A")
    assert h["promises_broken"] == 1 and h["pending_promise"] is None
    assert repo.customer_history(db, "Nobody")["reminders_sent"] == 0


def test_reply_log_stores_intent_but_not_the_text(tmp_path):
    db = tmp_path / "t.db"
    repo.log_reply_read(db, customer="A", intent="promise_to_pay", source="ai",
                        amount=Decimal("500"), promised_date=date(2026, 11, 6))
    e = repo.recent_activity(db)[0]
    assert e["action"] == "reply_read" and e["details"]["intent"] == "promise_to_pay"
    assert set(e["details"]) == {"intent", "read_by", "amount", "promised_date"}


# ---------------------------------------------------------------- AI summary guard
def test_ai_summary_accepted_when_numbers_match_facts():
    f = facts(days_overdue=60, promises_broken=2)
    a = recommend(f, TODAY)
    out = ai_summary(a, f, lambda p: "Two promises were broken and it is 60 days late, so a call is better.")
    assert out and "60" in out


def test_ai_summary_rejected_when_it_invents_a_number():
    f = facts(days_overdue=60, promises_broken=2)
    a = recommend(f, TODAY)
    assert ai_summary(a, f, lambda p: "They owe ₹90,000 so call today.") is None


def test_ai_summary_off_or_failing_returns_none():
    f = facts()
    a = recommend(f, TODAY)
    assert ai_summary(a, f, None) is None
    assert ai_summary(a, f, lambda p: None) is None

    def boom(p):
        raise RuntimeError
    assert ai_summary(a, f, boom) is None

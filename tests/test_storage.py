import sqlite3
from datetime import date
from decimal import Decimal

import pytest

from app.storage import repo
from app.storage.db import connect, from_paise, to_paise


@pytest.fixture
def db(tmp_path):
    return tmp_path / "test.db"


def reminder(db, **over):
    args = dict(customer="Ravi Traders", phone="+91 98765 43210", language="en",
                tone="firm", source="template", amount=12500, days_overdue=45,
                draft_text="Hello", final_text="Hello")
    args.update(over)
    return repo.record_reminder(db, **args)


# --- money precision ---------------------------------------------------------
def test_paise_conversion_is_exact():
    assert to_paise("0.10") + to_paise("0.20") == to_paise("0.30")
    assert to_paise(12500) == 1_250_000
    assert from_paise(1_250_050) == Decimal("12500.50")


# --- audit log is append-only ------------------------------------------------
def test_audit_log_cannot_be_edited_or_deleted(db):
    reminder(db)
    conn = connect(db)
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        conn.execute("UPDATE audit_log SET action = 'x'")
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        conn.execute("DELETE FROM audit_log")
    conn.close()


# --- reminders ---------------------------------------------------------------
def test_reminder_is_saved_and_audited(db):
    rid = reminder(db)
    events = repo.recent_activity(db)
    assert events[0]["action"] == "reminder_approved"
    assert events[0]["details"]["reminder_id"] == rid
    assert events[0]["details"]["edited_by_user"] is False


def test_edit_flag_detects_user_changes(db):
    reminder(db, draft_text="Hello", final_text="Hello Ravi garu")
    assert repo.recent_activity(db)[0]["details"]["edited_by_user"] is True


def test_only_last_four_phone_digits_are_stored(db):
    reminder(db)
    conn = connect(db)
    row = conn.execute("SELECT phone_last4 FROM reminders").fetchone()
    dump = " ".join(str(tuple(r)) for r in conn.execute("SELECT * FROM reminders"))
    conn.close()
    assert row["phone_last4"] == "3210"
    assert "98765" not in dump


# --- promises ----------------------------------------------------------------
def test_promise_lifecycle(db):
    pid = repo.add_promise(db, customer="A", amount=5000, promised_date=date(2026, 11, 10))
    assert [p["status"] for p in repo.list_promises(db)] == ["pending"]
    repo.set_promise_status(db, pid, "kept")
    assert repo.list_promises(db, "kept")[0]["amount"] == Decimal("5000")
    actions = [e["action"] for e in repo.recent_activity(db)]
    assert actions[:2] == ["promise_kept", "promise_added"]


def test_invalid_promise_status_and_missing_id(db):
    with pytest.raises(ValueError):
        repo.set_promise_status(db, 1, "pending")
    with pytest.raises(ValueError):
        repo.set_promise_status(db, 999, "kept")


def test_zero_or_negative_amounts_rejected(db):
    with pytest.raises(sqlite3.IntegrityError):
        repo.add_promise(db, customer="A", amount=0, promised_date=date(2026, 11, 10))
    with pytest.raises(sqlite3.IntegrityError):
        repo.add_recovery(db, customer="A", amount=-5, received_date=date(2026, 11, 10))


# --- summary -----------------------------------------------------------------
def test_summary_numbers(db):
    reminder(db)
    reminder(db, customer="B")
    reminder(db, customer="B")
    p1 = repo.add_promise(db, customer="A", amount=1000, promised_date=date(2026, 11, 9))
    repo.add_promise(db, customer="B", amount=2500.50, promised_date=date(2026, 11, 12))
    repo.set_promise_status(db, p1, "kept")
    repo.add_recovery(db, customer="A", amount=1000, received_date=date(2026, 11, 9))
    repo.add_recovery(db, customer="B", amount=0.10, received_date=date(2026, 11, 9))
    repo.add_recovery(db, customer="B", amount=0.20, received_date=date(2026, 11, 9))

    s = repo.summary(db)
    assert s["reminders_sent"] == 3
    assert s["customers_contacted"] == 2
    assert s["promises_pending"] == 1
    assert s["promises_pending_amount"] == Decimal("2500.50")
    assert s["promises_kept"] == 1 and s["promises_broken"] == 0
    assert s["payments_received"] == 3
    assert s["recovered_total"] == Decimal("1000.30")  # exact, no float drift


def test_summary_on_empty_database(db):
    s = repo.summary(db)
    assert s["reminders_sent"] == 0 and s["recovered_total"] == 0


# --- privacy -----------------------------------------------------------------
def test_erase_all_deletes_the_file(db):
    reminder(db)
    assert repo.erase_all(db) is True
    assert not db.exists()
    assert repo.erase_all(db) is False

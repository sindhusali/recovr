"""Saving and reading reminders, payment promises and recovered money.

Every write also adds an audit row in the same transaction, so the log can
never disagree with the data.
"""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from pathlib import Path

from app.storage import audit
from app.storage.db import connect, from_paise, to_paise


def phone_last4(raw: str | None) -> str:
    """We store only the last 4 digits of a phone number, never the full number."""
    digits = re.sub(r"\D", "", raw or "")
    return digits[-4:]


def record_reminder(db_path, *, customer: str, phone: str | None, language: str,
                    tone: str, source: str, amount, days_overdue: int,
                    draft_text: str, final_text: str) -> int:
    """Log that the shopkeeper approved a message. Returns the reminder id."""
    edited = int(draft_text.strip() != final_text.strip())
    conn = connect(db_path)
    try:
        with conn:
            cur = conn.execute(
                """INSERT INTO reminders (created_at, customer, phone_last4, language,
                   tone, source, amount_paise, days_overdue, message_text, edited_by_user)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (audit.now_iso(), customer, phone_last4(phone), language, tone, source,
                 to_paise(amount), days_overdue, final_text, edited),
            )
            rid = cur.lastrowid
            audit.log_event(conn, "reminder_approved", customer, {
                "reminder_id": rid, "tone": tone, "language": language,
                "draft_source": source, "edited_by_user": bool(edited),
                "amount": str(Decimal(str(amount))), "days_overdue": days_overdue,
            })
        return rid
    finally:
        conn.close()


def add_promise(db_path, *, customer: str, amount, promised_date: date,
                reminder_id: int | None = None) -> int:
    conn = connect(db_path)
    try:
        with conn:
            cur = conn.execute(
                """INSERT INTO promises (created_at, customer, amount_paise,
                   promised_date, reminder_id) VALUES (?, ?, ?, ?, ?)""",
                (audit.now_iso(), customer, to_paise(amount),
                 promised_date.isoformat(), reminder_id),
            )
            audit.log_event(conn, "promise_added", customer, {
                "promise_id": cur.lastrowid, "amount": str(Decimal(str(amount))),
                "promised_date": promised_date.isoformat(),
            })
        return cur.lastrowid
    finally:
        conn.close()


def set_promise_status(db_path, promise_id: int, status: str) -> None:
    if status not in ("kept", "broken"):
        raise ValueError("status must be 'kept' or 'broken'")
    conn = connect(db_path)
    try:
        with conn:
            row = conn.execute("SELECT customer FROM promises WHERE id = ?",
                               (promise_id,)).fetchone()
            if row is None:
                raise ValueError(f"no promise with id {promise_id}")
            conn.execute("UPDATE promises SET status = ? WHERE id = ?",
                         (status, promise_id))
            audit.log_event(conn, f"promise_{status}", row["customer"],
                            {"promise_id": promise_id})
    finally:
        conn.close()


def list_promises(db_path, status: str | None = None) -> list[dict]:
    conn = connect(db_path)
    try:
        sql = "SELECT * FROM promises"
        args: tuple = ()
        if status:
            sql += " WHERE status = ?"
            args = (status,)
        rows = conn.execute(sql + " ORDER BY promised_date, id", args).fetchall()
        return [{**dict(r), "amount": from_paise(r["amount_paise"])} for r in rows]
    finally:
        conn.close()


def add_recovery(db_path, *, customer: str, amount, received_date: date,
                 note: str = "") -> int:
    conn = connect(db_path)
    try:
        with conn:
            cur = conn.execute(
                """INSERT INTO recoveries (created_at, customer, amount_paise,
                   received_date, note) VALUES (?, ?, ?, ?, ?)""",
                (audit.now_iso(), customer, to_paise(amount),
                 received_date.isoformat(), note),
            )
            audit.log_event(conn, "money_received", customer, {
                "recovery_id": cur.lastrowid, "amount": str(Decimal(str(amount))),
                "received_date": received_date.isoformat(),
            })
        return cur.lastrowid
    finally:
        conn.close()


def customer_history(db_path, customer: str) -> dict:
    """Everything we know about one customer, for the next-action advice."""
    conn = connect(db_path)
    try:
        r = conn.execute(
            "SELECT COUNT(*) n, MAX(created_at) last FROM reminders WHERE customer = ?",
            (customer,)).fetchone()
        counts = {"pending": 0, "kept": 0, "broken": 0}
        for row in conn.execute(
                "SELECT status, COUNT(*) n FROM promises WHERE customer = ? GROUP BY status",
                (customer,)):
            counts[row["status"]] = row["n"]
        pending = conn.execute(
            "SELECT promised_date, amount_paise FROM promises WHERE customer = ? "
            "AND status = 'pending' ORDER BY promised_date DESC, id DESC LIMIT 1",
            (customer,)).fetchone()
        paid = conn.execute(
            "SELECT COUNT(*) n FROM recoveries WHERE customer = ?", (customer,)).fetchone()
        return {
            "reminders_sent": r["n"],
            "last_reminder_at": r["last"],
            "promises_kept": counts["kept"],
            "promises_broken": counts["broken"],
            "pending_promise": (
                {"promised_date": pending["promised_date"],
                 "amount": from_paise(pending["amount_paise"])} if pending else None),
            "payments_received": paid["n"],
        }
    finally:
        conn.close()


def log_reply_read(db_path, *, customer: str, intent: str, source: str,
                   amount, promised_date) -> None:
    """Audit that a reply was read. The reply text itself is NOT stored (privacy)."""
    conn = connect(db_path)
    try:
        with conn:
            audit.log_event(conn, "reply_read", customer, {
                "intent": intent, "read_by": source,
                "amount": str(amount) if amount is not None else None,
                "promised_date": promised_date.isoformat() if promised_date else None,
            })
    finally:
        conn.close()


def summary(db_path) -> dict:
    """Headline numbers for the results dashboard."""
    conn = connect(db_path)
    try:
        r = conn.execute(
            "SELECT COUNT(*) n, COUNT(DISTINCT customer) c FROM reminders").fetchone()
        promises = {s: (0, 0) for s in ("pending", "kept", "broken")}
        for row in conn.execute(
                "SELECT status, COUNT(*) n, COALESCE(SUM(amount_paise),0) p "
                "FROM promises GROUP BY status"):
            promises[row["status"]] = (row["n"], row["p"])
        rec = conn.execute(
            "SELECT COUNT(*) n, COALESCE(SUM(amount_paise),0) p FROM recoveries").fetchone()
        return {
            "reminders_sent": r["n"],
            "customers_contacted": r["c"],
            "promises_pending": promises["pending"][0],
            "promises_pending_amount": from_paise(promises["pending"][1]),
            "promises_kept": promises["kept"][0],
            "promises_broken": promises["broken"][0],
            "payments_received": rec["n"],
            "recovered_total": from_paise(rec["p"]),
        }
    finally:
        conn.close()


def recent_activity(db_path, limit: int = 50) -> list[dict]:
    conn = connect(db_path)
    try:
        return audit.recent_events(conn, limit)
    finally:
        conn.close()


def erase_all(db_path) -> bool:
    """Privacy: delete the whole database file. Returns True if something was deleted."""
    path = Path(db_path)
    if path.exists():
        path.unlink()
        return True
    return False

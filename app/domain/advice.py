"""Next-best-action for one customer.

The PLAN comes from fixed, explainable rules over the customer's real history
(reminders sent, promises kept/broken, days overdue). An LLM may only add a
short plain-language summary, and its numbers are checked against the facts.
The shopkeeper decides what to do.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from app.domain.ranking import suggested_tone

TextAI = Callable[[str], "str | None"]
_TONE_ORDER = ["friendly", "firm", "final"]


@dataclass
class CustomerFacts:
    days_overdue: int
    overdue_amount: Decimal
    reminders_sent: int = 0
    days_since_last_reminder: int | None = None
    promises_kept: int = 0
    promises_broken: int = 0
    pending_promise_date: date | None = None
    pending_promise_amount: Decimal | None = None
    payments_received: int = 0


@dataclass
class Action:
    kind: str          # "wait" | "message" | "call" | "escalate"
    headline: str
    tone: str | None = None
    reasons: list[str] = field(default_factory=list)


def facts_from_history(history: dict, *, days_overdue: int, overdue_amount, today: date) -> CustomerFacts:
    last = history.get("last_reminder_at")
    since = None
    if last:
        since = (today - datetime.fromisoformat(last).astimezone().date()).days
    pending = history.get("pending_promise")
    return CustomerFacts(
        days_overdue=days_overdue,
        overdue_amount=Decimal(str(overdue_amount)),
        reminders_sent=history.get("reminders_sent", 0),
        days_since_last_reminder=since,
        promises_kept=history.get("promises_kept", 0),
        promises_broken=history.get("promises_broken", 0),
        pending_promise_date=date.fromisoformat(pending["promised_date"]) if pending else None,
        pending_promise_amount=pending["amount"] if pending else None,
        payments_received=history.get("payments_received", 0),
    )


def _bump(tone: str, steps: int) -> str:
    return _TONE_ORDER[min(_TONE_ORDER.index(tone) + steps, len(_TONE_ORDER) - 1)]


def recommend(f: CustomerFacts, today: date) -> Action:
    base = suggested_tone(f.days_overdue)
    history_bits = []
    if f.reminders_sent:
        history_bits.append(f"{f.reminders_sent} reminder(s) sent so far")
    if f.promises_broken or f.promises_kept:
        history_bits.append(f"{f.promises_kept} promise(s) kept, {f.promises_broken} broken")

    # 1. a promise is still in the future: do not nag
    if f.pending_promise_date and f.pending_promise_date >= today:
        amt = f" ₹{f.pending_promise_amount:,.0f}" if f.pending_promise_amount else ""
        return Action("wait", f"Wait until {f.pending_promise_date:%d %b}", None, [
            f"Customer promised{amt} by {f.pending_promise_date:%d %b %Y}.",
            "Messaging again before then can annoy a customer who has made a commitment."])

    # 2. promise date passed
    if f.pending_promise_date and f.pending_promise_date < today:
        late = (today - f.pending_promise_date).days
        return Action("message", "Promise date passed: follow up firmly", _bump(base, 1), [
            f"The promised date ({f.pending_promise_date:%d %b}) was {late} day(s) ago and no payment is recorded.",
            "Mark the promise as kept or broken in the results section."])

    # 3. repeated broken promises on an old debt
    if f.promises_broken >= 2 and f.days_overdue > 45:
        return Action("escalate", "Call or visit in person, and consider pausing new credit", "final", [
            f"{f.promises_broken} promises broken and {f.days_overdue} days overdue.",
            "Written reminders have not worked; a personal conversation usually does."] + history_bits)

    # 4. several reminders, still nothing
    if f.reminders_sent >= 3 and f.days_overdue > 30:
        return Action("call", "Call them instead of sending another message", "firm", [
            f"{f.reminders_sent} reminders sent and still {f.days_overdue} days overdue.",
            "A different channel is more likely to get a response."])

    # 5. messaged very recently
    if f.days_since_last_reminder is not None and f.days_since_last_reminder < 3:
        return Action("wait", "Wait a couple of days", None, [
            f"You sent a reminder {f.days_since_last_reminder} day(s) ago.",
            "Give the customer a little time to respond."])

    # 6. default: message, tone from age and history
    tone = _bump(base, 1) if f.promises_broken >= 1 else base
    reasons = [f"₹{f.overdue_amount:,.0f} is overdue, oldest bill {f.days_overdue} days."]
    if f.promises_broken >= 1:
        reasons.append("A previous promise was broken, so the tone is one step firmer.")
    return Action("message", f"Send a {tone} reminder", tone, reasons + history_bits)


# --------------------------------------------------------------------------- optional AI summary
_NUM = re.compile(r"\d+(?:,\d+)*(?:\.\d+)?")


def _numbers(text: str) -> set[str]:
    return {n.replace(",", "") for n in _NUM.findall(text)}


def summary_prompt(a: Action, f: CustomerFacts) -> str:
    facts = "\n".join(f"- {r}" for r in a.reasons)
    return (
        "You help a small shopkeeper in India decide how to collect an overdue payment.\n"
        f"Recommended action (already decided, do not change it): {a.headline}\n"
        f"Facts:\n{facts}\n\n"
        "Write 2 short, friendly sentences explaining this advice in plain English. "
        "Use only the facts above. Do not add numbers, dates or new facts."
    )


def ai_summary(a: Action, f: CustomerFacts, ai: TextAI | None) -> str | None:
    """AI explanation, accepted only if it adds no numbers that are not in the facts."""
    if ai is None:
        return None
    try:
        text = ai(summary_prompt(a, f))
    except Exception:
        return None
    if not text or len(text) > 500:
        return None
    allowed = _numbers(" ".join(a.reasons) + " " + a.headline)
    return text.strip() if _numbers(text) <= allowed else None

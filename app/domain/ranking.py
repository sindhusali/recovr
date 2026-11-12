"""Who to chase first. Simple, explainable scoring (no black box)."""
from __future__ import annotations

import pandas as pd

MAX_AGE_DAYS = 120  # beyond this, extra age adds no extra urgency


def suggested_tone(max_days_overdue: int) -> str:
    """Escalation level for the reminder message."""
    if max_days_overdue <= 30:
        return "friendly"
    if max_days_overdue <= 60:
        return "firm"
    return "final"


def priority_score(overdue_amount: float, max_days_overdue: int) -> float:
    """Overdue rupees, scaled up to 3x as the oldest invoice gets older.

    A Rs 10,000 debt 90 days late outranks a Rs 12,000 debt 10 days late,
    but a huge amount still beats a tiny one.
    """
    age_factor = 1 + 2 * min(max_days_overdue, MAX_AGE_DAYS) / MAX_AGE_DAYS
    return round(overdue_amount * age_factor, 2)


def rank_customers(report: pd.DataFrame) -> pd.DataFrame:
    """Take aging_report() output; return overdue customers, highest priority first."""
    cols = ["rank", "customer", "overdue_amount", "max_days_overdue",
            "tone", "priority_score"]
    if report.empty:
        return pd.DataFrame(columns=cols)

    df = report.copy()
    df["overdue_amount"] = df[["1-30", "31-60", "60+"]].sum(axis=1)
    df = df[df["overdue_amount"] > 0].copy()  # nothing to chase if only 'Current'
    if df.empty:
        return pd.DataFrame(columns=cols)

    df["tone"] = df["max_days_overdue"].map(suggested_tone)
    df["priority_score"] = [
               priority_score(a, d) for a, d in zip(df["overdue_amount"], df["max_days_overdue"], strict=True)
    ]
    df = df.sort_values(["priority_score", "customer"], ascending=[False, True])
    df.insert(0, "rank", range(1, len(df) + 1))
    return df[cols].reset_index(drop=True)

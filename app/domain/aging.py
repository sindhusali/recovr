"""Aging logic: how overdue is each invoice, and how much is at stake."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pandas as pd

from app.domain.models import Invoice

BUCKETS = ["Current", "1-30", "31-60", "60+"]


def days_overdue(invoice: Invoice, as_of: date) -> int:
    """Days past the due date. 0 if not yet due (or due today)."""
    return max((as_of - invoice.due_date).days, 0)


def bucket_for(days: int) -> str:
    if days <= 0:
        return "Current"
    if days <= 30:
        return "1-30"
    if days <= 60:
        return "31-60"
    return "60+"


def invoices_to_frame(invoices: list[Invoice], as_of: date) -> pd.DataFrame:
    """One row per unsettled invoice, with days overdue and bucket."""
    rows = []
    for inv in invoices:
        if inv.is_settled:
            continue
        d = days_overdue(inv, as_of)
        rows.append(
            {
                "customer": inv.customer,
                "invoice_no": inv.invoice_no,
                "due_date": inv.due_date,
                "outstanding": float(inv.outstanding),
                "days_overdue": d,
                "bucket": bucket_for(d),
                "phone": inv.phone,
            }
        )
    cols = ["customer", "invoice_no", "due_date", "outstanding",
            "days_overdue", "bucket", "phone"]
    return pd.DataFrame(rows, columns=cols)


def aging_report(invoices: list[Invoice], as_of: date) -> pd.DataFrame:
    """One row per customer: outstanding amount split into aging buckets."""
    df = invoices_to_frame(invoices, as_of)
    cols = ["customer", *BUCKETS, "total_outstanding", "max_days_overdue"]
    if df.empty:
        return pd.DataFrame(columns=cols)

    pivot = (
        df.pivot_table(index="customer", columns="bucket", values="outstanding",
                       aggfunc="sum", fill_value=0.0)
        .reindex(columns=BUCKETS, fill_value=0.0)
    )
    pivot["total_outstanding"] = pivot[BUCKETS].sum(axis=1)
    pivot["max_days_overdue"] = df.groupby("customer")["days_overdue"].max()
    return pivot.reset_index()[cols]


def total_overdue(invoices: list[Invoice], as_of: date) -> Decimal:
    """Sum of outstanding on invoices that are past due."""
    return sum(
        (i.outstanding for i in invoices if days_overdue(i, as_of) > 0),
        Decimal("0"),
    )

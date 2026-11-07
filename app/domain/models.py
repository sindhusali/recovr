"""Core data models. Pure data, no I/O, no UI."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator


class Invoice(BaseModel):
    customer: str
    amount: Decimal = Field(ge=0)
    due_date: date
    invoice_no: str = ""
    invoice_date: date | None = None
    paid_amount: Decimal = Field(default=Decimal("0"), ge=0)
    phone: str = ""

    @field_validator("customer")
    @classmethod
    def _clean_customer(cls, v: str) -> str:
        v = " ".join(v.split())
        if not v:
            raise ValueError("customer name is empty")
        return v

    @property
    def outstanding(self) -> Decimal:
        """Amount still unpaid. Never negative."""
        return max(self.amount - self.paid_amount, Decimal("0"))

    @property
    def is_settled(self) -> bool:
        return self.outstanding == 0


class RowIssue(BaseModel):
    """A row that could not be loaded, with a human-readable reason."""
    row_number: int  # 1-based, as seen in the spreadsheet (header = row 1)
    reason: str


class LoadResult(BaseModel):
    invoices: list[Invoice] = Field(default_factory=list)
    issues: list[RowIssue] = Field(default_factory=list)
    unmapped_columns: list[str] = Field(default_factory=list)

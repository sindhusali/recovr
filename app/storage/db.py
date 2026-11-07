"""SQLite connection and schema.

Money is stored as integer paise (1 rupee = 100 paise), never as floating
point, so sums are always exact.
"""
from __future__ import annotations

import sqlite3
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS reminders (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at      TEXT NOT NULL,
    customer        TEXT NOT NULL,
    phone_last4     TEXT NOT NULL DEFAULT '',
    language        TEXT NOT NULL,
    tone            TEXT NOT NULL,
    source          TEXT NOT NULL,            -- 'template' or 'ai'
    amount_paise    INTEGER NOT NULL,
    days_overdue    INTEGER NOT NULL,
    message_text    TEXT NOT NULL,            -- exactly what the shopkeeper approved
    edited_by_user  INTEGER NOT NULL          -- 1 if changed after the draft
);

CREATE TABLE IF NOT EXISTS promises (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at     TEXT NOT NULL,
    customer       TEXT NOT NULL,
    amount_paise   INTEGER NOT NULL CHECK (amount_paise > 0),
    promised_date  TEXT NOT NULL,             -- ISO date
    status         TEXT NOT NULL DEFAULT 'pending'
                   CHECK (status IN ('pending', 'kept', 'broken')),
    reminder_id    INTEGER REFERENCES reminders(id)
);

CREATE TABLE IF NOT EXISTS recoveries (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at     TEXT NOT NULL,
    customer       TEXT NOT NULL,
    amount_paise   INTEGER NOT NULL CHECK (amount_paise > 0),
    received_date  TEXT NOT NULL,
    note           TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS audit_log (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ts        TEXT NOT NULL,
    action    TEXT NOT NULL,
    customer  TEXT NOT NULL DEFAULT '',
    details   TEXT NOT NULL DEFAULT '{}'      -- JSON
);

-- The audit log is append-only: the database itself refuses edits and deletes.
CREATE TRIGGER IF NOT EXISTS audit_log_no_update
BEFORE UPDATE ON audit_log
BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;

CREATE TRIGGER IF NOT EXISTS audit_log_no_delete
BEFORE DELETE ON audit_log
BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;
"""


def connect(path: str | Path) -> sqlite3.Connection:
    """Open (and create if needed) the database."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn


def to_paise(amount) -> int:
    return int((Decimal(str(amount)) * 100).to_integral_value(ROUND_HALF_UP))


def from_paise(paise: int) -> Decimal:
    return Decimal(paise) / 100

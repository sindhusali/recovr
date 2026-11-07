"""Append-only audit log: who/what/when for every action that matters."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def log_event(conn: sqlite3.Connection, action: str, customer: str = "",
              details: dict | None = None) -> None:
    """Add one row. Caller controls the transaction (use `with conn:`)."""
    conn.execute(
        "INSERT INTO audit_log (ts, action, customer, details) VALUES (?, ?, ?, ?)",
        (now_iso(), action, customer, json.dumps(details or {}, ensure_ascii=False, default=str)),
    )


def recent_events(conn: sqlite3.Connection, limit: int = 50) -> list[dict]:
    rows = conn.execute(
        "SELECT ts, action, customer, details FROM audit_log ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [{**dict(r), "details": json.loads(r["details"])} for r in rows]

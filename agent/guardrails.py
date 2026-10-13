"""Guardrails for the agent's database access.

The agent can query HR data, but only in ways a governed enterprise would allow:

  * Read-only:  the database is opened in SQLite read-only mode, and an authorizer
                rejects anything other than reading (no INSERT, UPDATE, DELETE, DDL, ATTACH or PRAGMA).
  * No PII:     direct identifiers (names, email, birth year) are blocked at the column level,
                even inside SELECT *, so the agent works with employee IDs only.
  * Bounded:    one statement per call, results capped at MAX_ROWS, queries time out.
  * Audited:    every tool call is written to an append-only JSONL audit log.
"""

from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "hr.db"
AUDIT_LOG = ROOT / "logs" / "audit.jsonl"

MAX_ROWS = 200
TIMEOUT_SECONDS = 5.0
PII_COLUMNS = {("employees", "first_name"), ("employees", "last_name"), ("employees", "email"),
               ("employees", "birth_year")}


class GuardrailError(Exception):
    """Raised when a request is refused by policy. The message is safe to show the model."""


def _authorizer(action, arg1, arg2, db_name, trigger):
    if action == sqlite3.SQLITE_SELECT:
        return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_READ:
        if (arg1, arg2) in PII_COLUMNS:
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_FUNCTION:
        return sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY


def run_readonly_sql(sql: str, db_path: Path = DB_PATH) -> dict:
    """Run one read-only SELECT and return columns, rows and whether results were truncated."""
    stripped = sql.strip().rstrip(";").strip()
    if not stripped:
        raise GuardrailError("Empty query.")
    if ";" in stripped:
        raise GuardrailError("Only one statement per call is allowed.")
    if not stripped.lower().startswith(("select", "with")):
        raise GuardrailError("Only SELECT queries are allowed.")
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    deadline = time.monotonic() + TIMEOUT_SECONDS
    con.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 10_000)
    con.set_authorizer(_authorizer)
    try:
        cur = con.execute(stripped)
        rows = cur.fetchmany(MAX_ROWS + 1)
        cols = [c[0] for c in cur.description]
    except sqlite3.DatabaseError as exc:
        msg = str(exc)
        if "not authorized" in msg or "prohibited" in msg:
            raise GuardrailError("Query refused: it writes data or reads a restricted PII column "
                                 "(first_name, last_name, email, birth_year). Use employee_id instead.") from exc
        if "interrupted" in msg:
            raise GuardrailError(f"Query exceeded the {TIMEOUT_SECONDS:.0f}-second limit. Aggregate or filter more.") from exc
        raise GuardrailError(f"SQL error: {msg}") from exc
    finally:
        con.close()
    truncated = len(rows) > MAX_ROWS
    return {"columns": cols, "rows": [list(r) for r in rows[:MAX_ROWS]], "row_count": min(len(rows), MAX_ROWS),
            "truncated": truncated}


def audit(tool: str, tool_input: dict, ok: bool, duration_ms: float, detail: str = "", log_path: Path = AUDIT_LOG):
    log_path.parent.mkdir(parents=True, exist_ok=True)
    entry = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "tool": tool, "input": tool_input,
             "ok": ok, "duration_ms": round(duration_ms, 1), "detail": detail[:300]}
    with open(log_path, "a") as f:
        f.write(json.dumps(entry, default=str) + "\n")

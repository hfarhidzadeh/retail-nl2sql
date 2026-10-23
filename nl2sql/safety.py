"""Guardrails: only read-only SELECT queries ever reach the database.

Three independent layers, so one bug does not let a write through:
  1. validate_sql(): static check on the SQL text (single SELECT/WITH statement).
  2. The connection is opened read-only (mode=ro).
  3. A SQLite authorizer denies every action except reading.
"""

import re
import sqlite3
import time

import pandas as pd

MAX_ROWS = 1000
TIMEOUT_SECONDS = 15

FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|ATTACH|DETACH|"
    r"PRAGMA|VACUUM|REINDEX|GRANT|REVOKE)\b",
    re.IGNORECASE,
)

_ALLOWED_ACTIONS = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION}
# SQLITE_RECURSIVE (recursive CTEs) is missing from older Python builds
if hasattr(sqlite3, "SQLITE_RECURSIVE"):
    _ALLOWED_ACTIONS.add(sqlite3.SQLITE_RECURSIVE)


class UnsafeSQLError(ValueError):
    pass


def _strip_literals_and_comments(sql: str) -> str:
    sql = re.sub(r"'(?:[^']|'')*'", "''", sql)       # string literals
    sql = re.sub(r'"(?:[^"]|"")*"', '""', sql)       # quoted identifiers
    sql = re.sub(r"--[^\n]*", " ", sql)               # line comments
    return re.sub(r"/\*.*?\*/", " ", sql, flags=re.S)  # block comments


def validate_sql(sql: str) -> str:
    """Return the cleaned SQL, or raise UnsafeSQLError."""
    cleaned = sql.strip().rstrip(";").strip()
    if not cleaned:
        raise UnsafeSQLError("Empty query.")
    bare = _strip_literals_and_comments(cleaned)
    if ";" in bare:
        raise UnsafeSQLError("Only a single statement is allowed.")
    if not re.match(r"\s*(SELECT|WITH)\b", bare, re.IGNORECASE):
        raise UnsafeSQLError("Only SELECT queries are allowed.")
    m = FORBIDDEN.search(bare)
    if m:
        raise UnsafeSQLError(f"Forbidden keyword: {m.group(1).upper()}")
    return cleaned


def _authorizer(action, *_):
    return sqlite3.SQLITE_OK if action in _ALLOWED_ACTIONS else sqlite3.SQLITE_DENY


def connect_readonly(db_path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, check_same_thread=False)
    conn.set_authorizer(_authorizer)
    return conn


def run_query(conn: sqlite3.Connection, sql: str, max_rows: int = MAX_ROWS):
    """Validate and execute. Returns (DataFrame, truncated: bool)."""
    sql = validate_sql(sql)
    deadline = time.monotonic() + TIMEOUT_SECONDS
    # Returning non-zero from the progress handler aborts the query
    conn.set_progress_handler(lambda: int(time.monotonic() > deadline), 10_000)
    try:
        cur = conn.execute(sql)
        cols = [d[0] for d in cur.description]
        rows = cur.fetchmany(max_rows + 1)
    except sqlite3.OperationalError as e:
        if "interrupted" in str(e):
            raise TimeoutError(f"Query exceeded {TIMEOUT_SECONDS}s") from e
        raise
    finally:
        conn.set_progress_handler(None, 0)
    truncated = len(rows) > max_rows
    return pd.DataFrame(rows[:max_rows], columns=cols), truncated

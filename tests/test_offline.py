"""Tests that run without an API key.  Run:  pytest -q"""

import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from evals.compare import results_match
from nl2sql import NL2SQL
from nl2sql.pipeline import DEFAULT_DB
from nl2sql.safety import UnsafeSQLError, connect_readonly, run_query, validate_sql

CASES = json.loads((Path(__file__).parent.parent / "evals" / "cases.json").read_text())


# --- Layer 1: static SQL validation ---------------------------------------

@pytest.mark.parametrize("sql", [
    "SELECT * FROM stores",
    "  select count(*) from sales;  ",
    "WITH t AS (SELECT 1 AS x) SELECT x FROM t",
    "SELECT replace(store_name, '#', '') FROM stores",
    "SELECT * FROM stores WHERE store_name = 'DROP TABLE x; --'",  # keyword inside a literal
])
def test_validate_allows_reads(sql):
    validate_sql(sql)


@pytest.mark.parametrize("sql", [
    "DELETE FROM sales",
    "UPDATE products SET unit_price = 0",
    "DROP TABLE sales",
    "SELECT 1; DROP TABLE sales",
    "WITH t AS (SELECT 1) DELETE FROM sales",
    "INSERT INTO regions VALUES (9, 'x')",
    "PRAGMA table_info(sales)",
    "ATTACH DATABASE 'x.db' AS x",
    "",
])
def test_validate_blocks_writes(sql):
    with pytest.raises(UnsafeSQLError):
        validate_sql(sql)


# --- Layers 2+3: read-only connection + authorizer -------------------------

def test_connection_rejects_writes_even_without_validator():
    conn = connect_readonly(DEFAULT_DB)
    before = conn.execute("SELECT COUNT(*) FROM sales").fetchone()[0]
    for sql in ["DELETE FROM sales", "DROP TABLE sales", "CREATE TABLE x (a)"]:
        with pytest.raises(sqlite3.DatabaseError):
            conn.execute(sql)
    assert conn.execute("SELECT COUNT(*) FROM sales").fetchone()[0] == before


def test_run_query_truncates():
    df, truncated = run_query(connect_readonly(DEFAULT_DB), "SELECT * FROM sales", max_rows=10)
    assert len(df) == 10 and truncated


# --- Positive control for the controls: every gold query runs and returns rows

@pytest.mark.parametrize("case", CASES["positive"], ids=lambda c: c["id"])
def test_gold_sql_runs(case):
    df, _ = run_query(connect_readonly(DEFAULT_DB), case["gold_sql"])
    assert len(df) > 0


# --- Result matcher --------------------------------------------------------

def test_matcher_accepts_extra_columns_and_reordering():
    gold = [(1, 100.0), (2, 50.0)]
    assert results_match(gold, [("Store B", 2, 50.0), ("Store A", 1, 100.004)])


def test_matcher_rejects_wrong_values_and_order():
    gold = [(1, 100.0), (2, 50.0)]
    assert not results_match(gold, [(1, 100.0), (2, 51.0)])
    assert not results_match(gold, [(2, 50.0), (1, 100.0)], ordered=True)
    assert not results_match(gold, [(1, 100.0)])


# --- Pipeline with a fake model: self-correction and refusal paths ---------

class FakeClient:
    """Stands in for anthropic.Anthropic; returns scripted JSON replies in order."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append({**kwargs, "messages": list(kwargs["messages"])})  # snapshot
        text = json.dumps(self.replies.pop(0))
        return SimpleNamespace(stop_reason="end_turn",
                               content=[SimpleNamespace(type="text", text=text)])


def reply(sql, answerable=True):
    return {"answerable": answerable, "sql": sql, "explanation": "test", "assumptions": []}


def test_self_correction_after_sql_error():
    fake = FakeClient([reply("SELECT nope FROM stores"), reply("SELECT COUNT(*) AS n FROM stores")])
    ans = NL2SQL(client=fake).ask("How many stores?")
    assert ans.ok and ans.data.iloc[0, 0] == 53
    assert len(ans.attempts) == 1
    # The error message was fed back to the model on the second call
    assert "no such column" in fake.calls[1]["messages"][-1]["content"]


def test_unsafe_sql_from_model_is_blocked_not_executed():
    fake = FakeClient([reply("DELETE FROM sales")])
    ans = NL2SQL(client=fake).ask("Delete everything")
    assert not ans.ok and ans.error.startswith("Blocked")
    assert len(fake.calls) == 1


def test_unanswerable_is_passed_through():
    ans = NL2SQL(client=FakeClient([reply("", answerable=False)])).ask("Employee salaries?")
    assert not ans.answerable and ans.data is None

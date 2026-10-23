"""Run the positive and negative controls against the live model.

    python -m evals.run_eval

Positive controls: questions with a hand-written gold SQL. Pass = same result table.
Negative controls: questions the system must refuse or must not act on.
Each case makes 1-3 Claude API calls.
"""

import json
import sqlite3
from pathlib import Path

from nl2sql import NL2SQL
from nl2sql.pipeline import DEFAULT_DB

from .compare import results_match

CASES = json.loads((Path(__file__).parent / "cases.json").read_text())


def table_counts(db_path):
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    names = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    counts = {n: conn.execute(f'SELECT COUNT(*) FROM "{n}"').fetchone()[0] for n in names}
    conn.close()
    return counts


def check_negative(case, ans) -> bool:
    expect = case["expect"]
    if expect == "unanswerable":
        return not ans.answerable
    if expect == "empty_or_unanswerable":
        if not ans.answerable:
            return True
        if ans.data is None:
            return False
        vals = [v for row in ans.data.itertuples(index=False) for v in row]
        return all(v in (None, 0, 0.0) for v in vals)
    if expect == "unanswerable_or_blocked":
        return not ans.answerable or ans.error.startswith("Blocked")
    if expect == "no_write":
        return True  # judged by the table-count check below
    raise ValueError(expect)


def main():
    before = table_counts(DEFAULT_DB)
    nl = NL2SQL()
    gold_conn = sqlite3.connect(f"file:{DEFAULT_DB}?mode=ro", uri=True)
    results = []

    print("POSITIVE CONTROLS (must match gold answer)")
    for case in CASES["positive"]:
        gold = gold_conn.execute(case["gold_sql"]).fetchall()
        try:
            ans = nl.ask(case["question"])
            pred = [] if ans.data is None else list(ans.data.itertuples(index=False, name=None))
            passed = ans.ok and results_match(gold, pred, case.get("ordered", False))
        except Exception as e:  # API failure counts as a fail, keep going
            ans, passed = None, False
            print(f"  ! {case['id']}: {e}")
        results.append(("positive", case["id"], passed))
        print(f"  {'PASS' if passed else 'FAIL'}  {case['id']}")
        if not passed and ans is not None:
            print(f"        question: {case['question']}\n        model SQL: {ans.sql}\n"
                  f"        error: {ans.error or '-'}\n        gold rows: {gold[:5]}\n"
                  f"        model rows: {pred[:5]}")

    print("\nNEGATIVE CONTROLS (must refuse / must not change data)")
    for case in CASES["negative"]:
        try:
            ans = nl.ask(case["question"])
            passed = check_negative(case, ans)
        except Exception as e:
            ans, passed = None, False
            print(f"  ! {case['id']}: {e}")
        unchanged = table_counts(DEFAULT_DB) == before
        passed = passed and unchanged
        results.append(("negative", case["id"], passed))
        print(f"  {'PASS' if passed else 'FAIL'}  {case['id']}  ({case['why']})")
        if not passed and ans is not None:
            print(f"        answerable={ans.answerable} sql={ans.sql!r} error={ans.error!r}"
                  f" data_unchanged={unchanged}")

    for kind in ("positive", "negative"):
        rs = [r for r in results if r[0] == kind]
        print(f"\n{kind}: {sum(r[2] for r in rs)}/{len(rs)} passed", end="")
    print()
    print("\nFAILs are worth reading by hand: some are real errors, some are a different but "
          "valid interpretation of the question.")


if __name__ == "__main__":
    main()

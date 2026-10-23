"""Command-line interface.

    python cli.py "What were total sales by region in 2025?"
    python cli.py            # interactive mode
"""

import sys

import pandas as pd

from nl2sql import NL2SQL

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 20)


def show(nl: NL2SQL, question: str) -> None:
    ans = nl.ask(question)
    if not ans.answerable:
        print(f"\nCan't answer from this database: {ans.explanation}\n")
        return
    print(f"\n-- SQL --\n{ans.sql}\n\n-- {ans.explanation}")
    for a in ans.assumptions:
        print(f"   assumption: {a}")
    if ans.attempts:
        print(f"   (self-corrected after {len(ans.attempts)} failed attempt(s))")
    if ans.error:
        print(f"\nERROR: {ans.error}\n")
        return
    print(f"\n{ans.data.to_string(index=False, max_rows=50)}")
    print(f"({len(ans.data)} rows{', truncated' if ans.truncated else ''})\n")


def main() -> None:
    nl = NL2SQL()
    if len(sys.argv) > 1:
        show(nl, " ".join(sys.argv[1:]))
        return
    print("Ask a question about the retail data (blank line to quit).")
    while (q := input("> ").strip()):
        show(nl, q)


if __name__ == "__main__":
    main()

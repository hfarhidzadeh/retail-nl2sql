"""End-to-end: question -> SQL -> validated execution -> result, with self-correction."""

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from .generator import SQLGenerator
from .safety import UnsafeSQLError, connect_readonly, run_query
from .schema import describe, table_columns

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "retail.db"
MAX_ATTEMPTS = 3


@dataclass
class Answer:
    question: str
    answerable: bool = True
    sql: str = ""
    explanation: str = ""
    assumptions: list = field(default_factory=list)
    data: pd.DataFrame = None
    truncated: bool = False
    error: str = ""
    attempts: list = field(default_factory=list)  # [(sql, error)] for failed tries

    @property
    def ok(self) -> bool:
        return self.answerable and not self.error and self.data is not None


class NL2SQL:
    def __init__(self, db_path=DEFAULT_DB, client=None):
        db_path = Path(db_path)
        if not db_path.exists():
            raise FileNotFoundError(f"{db_path} not found. Run: python data/generate_data.py")
        # Schema introspection needs PRAGMA, so it uses its own (still read-only) connection
        meta = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        self.schema_text = describe(meta)
        self.tables = table_columns(meta)
        meta.close()
        self.conn = connect_readonly(db_path)
        self.generator = SQLGenerator(self.schema_text, client=client)

    def ask(self, question: str) -> Answer:
        answer = Answer(question=question)
        messages = self.generator.start(question)
        for _ in range(MAX_ATTEMPTS):
            draft = self.generator.generate(messages)
            answer.answerable = draft.answerable
            answer.sql, answer.explanation, answer.assumptions = draft.sql, draft.explanation, draft.assumptions
            if not draft.answerable:
                return answer
            try:
                answer.data, answer.truncated = run_query(self.conn, draft.sql)
                answer.error = ""
                return answer
            except UnsafeSQLError as e:
                # Never retry a blocked query; surface it
                answer.error = f"Blocked by safety check: {e}"
                return answer
            except (sqlite3.Error, TimeoutError) as e:
                answer.error = str(e)
                answer.attempts.append((draft.sql, str(e)))
                self.generator.report_error(messages, draft.sql, str(e))
        return answer

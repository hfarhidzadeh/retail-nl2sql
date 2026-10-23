"""Ask Claude to translate a natural-language question into SQLite SQL."""

import json
from dataclasses import dataclass, field

import anthropic

MODEL = "claude-opus-5-5"

SYSTEM_TEMPLATE = """\
You are a senior retail data analyst who writes SQLite queries for a Walmart-style \
retailer's sales database. Translate the user's question into ONE read-only SQLite \
SELECT query (CTEs are fine) that answers it exactly.

Rules:
- Use only the tables and columns in the schema below. Never invent columns.
- If the question cannot be answered from this schema (the data simply is not there), \
set answerable=false, leave sql empty, and explain what data is missing. Do not guess.
- If the user asks to modify data (insert, update, delete, drop, ...), set answerable=false: \
this assistant is read-only.
- Follow the business definitions below (e.g. revenue includes discounts).
- Give columns readable aliases (e.g. total_revenue) and ROUND money to 2 decimals.
- Add ORDER BY when the question implies ranking or time order; add LIMIT for "top N".
- When the question is ambiguous, pick the most common business interpretation and \
state it in assumptions.

{schema}"""

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "answerable": {"type": "boolean"},
        "sql": {"type": "string"},
        "explanation": {"type": "string", "description": "One or two sentences, plain English"},
        "assumptions": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["answerable", "sql", "explanation", "assumptions"],
    "additionalProperties": False,
}


@dataclass
class SQLDraft:
    answerable: bool
    sql: str
    explanation: str
    assumptions: list = field(default_factory=list)


class RefusalError(RuntimeError):
    pass


class SQLGenerator:
    def __init__(self, schema_text: str, client: anthropic.Anthropic = None, model: str = MODEL):
        self.client = client or anthropic.Anthropic()
        self.model = model
        self.system = [{
            "type": "text",
            "text": SYSTEM_TEMPLATE.format(schema=schema_text),
            "cache_control": {"type": "ephemeral"},  # schema is identical on every call
        }]

    def start(self, question: str) -> list:
        """New conversation for one question."""
        return [{"role": "user", "content": question}]

    def generate(self, messages: list) -> SQLDraft:
        """Call Claude on the conversation so far and append its reply to `messages`."""
        response = self.client.beta.messages.create(
            model=self.model,
            max_tokens=16000,
            system=self.system,
            messages=messages,
            thinking={"type": "adaptive"},
            output_config={
                "effort": "medium",
                "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA},
            },
            # If a safety classifier declines, re-run on Anthropic's recommended fallback model
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
        if response.stop_reason == "refusal":
            raise RefusalError("The model declined this request.")
        if response.stop_reason == "max_tokens":
            raise RuntimeError("Model output was cut off (max_tokens).")

        messages.append({"role": "assistant", "content": response.content})
        text = next(b.text for b in response.content if b.type == "text")
        return SQLDraft(**json.loads(text))

    def report_error(self, messages: list, sql: str, error: str) -> None:
        """Feed a failed query's error back so the next generate() can fix it."""
        messages.append({
            "role": "user",
            "content": f"That query failed when run on SQLite.\n\nSQL:\n{sql}\n\nError:\n{error}\n\n"
                       "Return a corrected query.",
        })

# Retail NL2SQL

Ask a question in plain English about a Walmart-style retail business, get back the
SQL that answers it, and see the result as a table and chart.

All data is **synthetic** (fixed random seed). No real customer data is used.

```
question ──► Claude (schema + business rules in prompt) ──► SQL
                                                             │
                     safety check (SELECT only) ◄────────────┘
                                │
                  read-only SQLite + authorizer ──► result table / chart
                                │
                   SQL error? feed error back to Claude, retry (max 3)
```

## Project layout

| Path | What it is |
|---|---|
| `data/generate_data.py` | Builds `data/retail.db`: regions, stores, departments, products, customers, sales, sale_items, inventory (2024–2025) |
| `nl2sql/schema.py` | Schema description sent to the model: DDL, column meanings, categorical values, business definitions (revenue, margin, basket) |
| `nl2sql/generator.py` | Claude call; returns structured JSON `{answerable, sql, explanation, assumptions}` |
| `nl2sql/safety.py` | 3 layers of protection: SELECT-only validator, read-only connection, SQLite authorizer; row limit + timeout |
| `nl2sql/pipeline.py` | Ties it together, with self-correction on SQL errors |
| `app.py` | Streamlit web UI |
| `cli.py` | Command-line UI |
| `evals/` | Positive controls (questions with known gold answers) and negative controls (must refuse / must not write) |
| `tests/` | Offline tests, no API key needed |

## Step by step

**1. Environment** (Python 3.10+; the venv here uses 3.13)
```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**2. Build the database**
```bash
python data/generate_data.py
```

**3. Run offline tests.** These check the safety layers, the gold queries, the result matcher, and the self-correction loop, using a fake model.
```bash
pytest -q
```

**4. Set your Anthropic API key**
```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

**5. Ask questions**
```bash
python cli.py "Top 5 stores by revenue in the 2025 holiday season"
streamlit run app.py          # opens http://localhost:8501
```

**6. Measure accuracy with controls.** This uses about 17 to 50 API calls.
```bash
python -m evals.run_eval
```
Read every FAIL by hand: some are real errors, some are valid alternative interpretations.

## Example questions
- What were total sales by department in 2025?
- Monthly revenue trend for 2025
- Compare online vs in-store vs pickup revenue by year
- Which private-label brands have the highest gross margin?
- How many products are below their reorder level in Texas stores?
- Average basket size for Walmart+ members vs non-members
- Which region grew revenue the most from 2024 to 2025?

## Judging the output
- **Always read the SQL**, not just the numbers. The SQL is the model's claim about what you asked.
- Check the **assumptions** list, which shows how the model resolved an ambiguous question.
- Spot-check numbers against a query you write yourself, or against `evals/cases.json`.
- The model is told to answer "can't answer" when the data is missing. The negative controls check that it does.

## Roadmap (next phases)
1. **Follow-up questions**: keep the conversation so "now split that by region" works.
2. **Few-shot examples**: add verified question→SQL pairs to the prompt and measure the change with the eval.
3. **Bigger eval set**: 50+ questions across difficulty levels; track accuracy over prompt changes.
4. **Real warehouse**: swap SQLite for Postgres/Snowflake/BigQuery, using a read-only DB user.
5. **Result summary**: have the model write a short narrative answer from the result table.

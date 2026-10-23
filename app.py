"""Streamlit UI.  Run:  streamlit run app.py"""

import pandas as pd
import streamlit as st

from nl2sql import NL2SQL

EXAMPLES = [
    "What were total sales by department in 2025?",
    "Top 10 stores by revenue in the 2024 holiday season",
    "Monthly revenue trend for 2025",
    "Compare online vs in-store vs pickup revenue by year",
    "Which private-label brands have the highest gross margin?",
    "How many products are below their reorder level in Texas stores?",
    "Average basket size for Walmart+ members vs non-members",
    "Which region grew revenue the most from 2024 to 2025?",
]

st.set_page_config(page_title="Retail NL2SQL", page_icon="🛒", layout="wide")


@st.cache_resource
def engine():
    return NL2SQL()


nl = engine()

with st.sidebar:
    st.header("Schema")
    for table, cols in nl.tables.items():
        with st.expander(table):
            st.markdown("\n".join(f"- `{c}` {t.lower()}" for c, t in cols))
    st.header("Try an example")
    for ex in EXAMPLES:
        if st.button(ex, use_container_width=True):
            st.session_state.question = ex

st.title("🛒 Ask the retail database")
st.caption("Synthetic Walmart-style data, 2024–2025. Questions are translated to SQL by Claude; "
           "only read-only SELECT queries are executed.")

question = st.text_input("Your question", key="question",
                         placeholder="e.g. Which 5 products sold the most units in December 2025?")

if st.button("Ask", type="primary") and question.strip():
    with st.spinner("Writing SQL and running it..."):
        try:
            ans = nl.ask(question.strip())
        except Exception as e:  # API/network errors
            st.error(f"Request failed: {e}")
            st.stop()

    if not ans.answerable:
        st.warning(f"Can't answer from this database: {ans.explanation}")
        st.stop()

    st.subheader("Generated SQL")
    st.code(ans.sql, language="sql")
    st.markdown(f"**What it does:** {ans.explanation}")
    if ans.assumptions:
        st.markdown("**Assumptions:**\n" + "\n".join(f"- {a}" for a in ans.assumptions))
    if ans.attempts:
        with st.expander(f"Self-corrected after {len(ans.attempts)} failed attempt(s)"):
            for sql, err in ans.attempts:
                st.code(sql, language="sql")
                st.caption(err)

    if ans.error:
        st.error(ans.error)
        st.stop()

    df = ans.data
    st.subheader(f"Result ({len(df):,} rows{', truncated' if ans.truncated else ''})")
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.download_button("Download CSV", df.to_csv(index=False), "result.csv", "text/csv")

    # Quick chart when the result is one label column + numeric column(s)
    numeric = df.select_dtypes("number").columns.tolist()
    labels = [c for c in df.columns if c not in numeric]
    if 1 < len(df) <= 100 and len(labels) == 1 and numeric:
        st.subheader("Chart")
        chart_df = df.set_index(labels[0])[numeric]
        is_time = pd.to_datetime(df[labels[0]], errors="coerce", format="mixed").notna().all()
        (st.line_chart if is_time else st.bar_chart)(chart_df)

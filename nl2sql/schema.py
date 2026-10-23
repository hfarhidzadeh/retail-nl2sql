"""Turn the SQLite database into a schema description the model can read."""

import sqlite3

# Business meaning of columns that the raw DDL does not make obvious.
# Good descriptions are the single biggest lever on NL2SQL accuracy.
COLUMN_NOTES = {
    "stores.store_type": "one of 'Supercenter', 'Neighborhood Market', 'Discount Store'",
    "stores.open_date": "ISO date string YYYY-MM-DD",
    "products.unit_price": "current list price in USD",
    "products.unit_cost": "what the retailer pays the supplier, USD",
    "products.is_private_label": "1 = store-owned brand (Great Value, Equate, onn., Mainstays, ...), 0 = national brand",
    "customers.membership": "'Walmart+' (paid membership) or 'None'",
    "customers.state": "two-letter US state code",
    "sales.sale_date": "ISO date string YYYY-MM-DD; data covers 2024-01-01 to 2025-12-31",
    "sales.customer_id": "NULL for anonymous in-store shoppers",
    "sales.channel": "one of 'In-Store', 'Online', 'Pickup'",
    "sale_items.unit_price": "price actually charged per unit at time of sale (can differ from products.unit_price)",
    "sale_items.discount": "total USD discount on this line (not per unit)",
    "inventory.quantity_on_hand": "units in stock as of 2025-12-31",
    "inventory.reorder_level": "restock is needed when quantity_on_hand < reorder_level",
}

BUSINESS_RULES = """\
- One row in `sales` is one transaction (a basket). Line items are in `sale_items`.
- Revenue (net sales) for a line = sale_items.quantity * sale_items.unit_price - sale_items.discount.
- Gross margin for a line = revenue - sale_items.quantity * products.unit_cost.
- Units sold = SUM(sale_items.quantity).
- Average basket / average order value = total revenue / COUNT(DISTINCT sales.sale_id).
- "Holiday season" means November and December.
- Use strftime('%Y', sale_date) / strftime('%m', sale_date) for year/month; dates are TEXT.
"""

# Low-cardinality columns whose actual values are worth showing the model.
CATEGORICAL = [
    ("regions", "region_name"), ("stores", "store_type"), ("stores", "state"),
    ("departments", "department_name"), ("products", "brand"),
    ("customers", "membership"), ("customers", "age_group"),
    ("sales", "channel"), ("sales", "payment_method"),
]


def describe(conn: sqlite3.Connection) -> str:
    """Return DDL plus column notes, sample values and business rules as one text block."""
    parts = ["## Tables (SQLite)\n"]
    tables = conn.execute(
        "SELECT name, sql FROM sqlite_master WHERE type = 'table' ORDER BY name"
    ).fetchall()
    for name, ddl in tables:
        n = conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
        parts.append(f"-- {name}: {n:,} rows\n{ddl};\n")

    parts.append("## Column notes\n")
    parts += [f"- {col}: {note}" for col, note in COLUMN_NOTES.items()]

    parts.append("\n## Distinct values of categorical columns\n")
    for table, col in CATEGORICAL:
        vals = [r[0] for r in conn.execute(f'SELECT DISTINCT "{col}" FROM "{table}" ORDER BY 1')]
        parts.append(f"- {table}.{col}: {', '.join(map(repr, vals))}")

    parts.append("\n## Business definitions\n" + BUSINESS_RULES)
    return "\n".join(parts)


def table_columns(conn: sqlite3.Connection) -> dict:
    """{table: [(column, type), ...]} for the UI schema browser."""
    out = {}
    for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"):
        out[name] = [(r[1], r[2]) for r in conn.execute(f'PRAGMA table_info("{name}")')]
    return out

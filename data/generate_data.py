"""Generate a synthetic Walmart-style retail database (SQLite).

All data is fake and generated from a fixed random seed, so every run
produces the same database. That matters for the eval: gold answers stay stable.

Usage:
    python data/generate_data.py            # writes data/retail.db
"""

import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path

SEED = 42
DB_PATH = Path(__file__).parent / "retail.db"

START_DATE = date(2024, 1, 1)
END_DATE = date(2025, 12, 31)
N_CUSTOMERS = 5000
N_SALES = 60000

REGIONS = ["Southeast", "Southwest", "Midwest", "Northeast", "West"]

# (city, state, region)
CITIES = [
    ("Bentonville", "AR", "Southeast"), ("Atlanta", "GA", "Southeast"),
    ("Orlando", "FL", "Southeast"), ("Miami", "FL", "Southeast"),
    ("Charlotte", "NC", "Southeast"), ("Nashville", "TN", "Southeast"),
    ("Houston", "TX", "Southwest"), ("Dallas", "TX", "Southwest"),
    ("Austin", "TX", "Southwest"), ("San Antonio", "TX", "Southwest"),
    ("Phoenix", "AZ", "Southwest"), ("Albuquerque", "NM", "Southwest"),
    ("Chicago", "IL", "Midwest"), ("Columbus", "OH", "Midwest"),
    ("Indianapolis", "IN", "Midwest"), ("Detroit", "MI", "Midwest"),
    ("Kansas City", "MO", "Midwest"), ("Minneapolis", "MN", "Midwest"),
    ("Philadelphia", "PA", "Northeast"), ("Pittsburgh", "PA", "Northeast"),
    ("Albany", "NY", "Northeast"), ("Newark", "NJ", "Northeast"),
    ("Hartford", "CT", "Northeast"),
    ("Los Angeles", "CA", "West"), ("San Diego", "CA", "West"),
    ("Sacramento", "CA", "West"), ("Denver", "CO", "West"),
    ("Las Vegas", "NV", "West"), ("Seattle", "WA", "West"),
    ("Salt Lake City", "UT", "West"),
]

STORE_TYPES = [  # (type, weight, square_feet range)
    ("Supercenter", 0.6, (150_000, 220_000)),
    ("Neighborhood Market", 0.3, (35_000, 50_000)),
    ("Discount Store", 0.1, (80_000, 120_000)),
]

# department -> list of (brand, product base name, price range, is_private_label)
CATALOG = {
    "Grocery": [
        ("Great Value", "Whole Milk 1 Gal", (2.5, 4.0), 1),
        ("Great Value", "Large Eggs 12ct", (2.0, 5.0), 1),
        ("Great Value", "White Bread", (1.2, 2.5), 1),
        ("Great Value", "Peanut Butter", (2.0, 4.5), 1),
        ("Marketside", "Fresh Salad Kit", (2.5, 4.5), 1),
        ("Coca-Cola", "Soda 12pk", (5.5, 8.0), 0),
        ("Kellogg's", "Cereal", (3.0, 5.5), 0),
        ("Tyson", "Chicken Breast 3lb", (7.0, 12.0), 0),
        ("Folgers", "Ground Coffee", (6.0, 11.0), 0),
        ("Doritos", "Tortilla Chips", (3.5, 5.5), 0),
    ],
    "Electronics": [
        ("onn.", "55in 4K TV", (250, 350), 1),
        ("onn.", "Wireless Earbuds", (15, 35), 1),
        ("Samsung", "65in QLED TV", (600, 1100), 0),
        ("Apple", "AirPods", (99, 179), 0),
        ("HP", "15in Laptop", (350, 700), 0),
        ("Nintendo", "Switch Console", (280, 350), 0),
        ("Sony", "Bluetooth Speaker", (40, 120), 0),
    ],
    "Apparel": [
        ("George", "Men's Jeans", (12, 22), 1),
        ("Time and Tru", "Women's T-Shirt", (5, 12), 1),
        ("Wonder Nation", "Kids Hoodie", (8, 15), 1),
        ("Hanes", "Socks 10pk", (8, 14), 0),
        ("Levi's", "Women's Jeans", (25, 45), 0),
    ],
    "Home": [
        ("Mainstays", "Bath Towel Set", (10, 25), 1),
        ("Mainstays", "Microwave", (50, 90), 1),
        ("Better Homes & Gardens", "Table Lamp", (20, 45), 1),
        ("Keurig", "Coffee Maker", (60, 130), 0),
        ("Shark", "Vacuum Cleaner", (120, 250), 0),
    ],
    "Health & Beauty": [
        ("Equate", "Ibuprofen 200ct", (4, 9), 1),
        ("Equate", "Daily Multivitamin", (6, 12), 1),
        ("Colgate", "Toothpaste", (2.5, 5), 0),
        ("Dove", "Body Wash", (5, 9), 0),
        ("Neutrogena", "Sunscreen", (8, 13), 0),
    ],
    "Toys": [
        ("Adventure Force", "Toy Car Set", (8, 25), 1),
        ("LEGO", "Building Set", (20, 80), 0),
        ("Mattel", "Barbie Doll", (10, 30), 0),
        ("Hasbro", "Board Game", (12, 35), 0),
    ],
    "Sporting Goods": [
        ("Ozark Trail", "Camping Tent", (40, 120), 1),
        ("Ozark Trail", "Cooler", (25, 60), 1),
        ("Spalding", "Basketball", (15, 30), 0),
        ("Hyper", "Mountain Bike", (150, 300), 0),
    ],
    "Automotive": [
        ("SuperTech", "Motor Oil 5qt", (18, 28), 1),
        ("EverStart", "Car Battery", (90, 160), 1),
        ("Armor All", "Car Cleaning Kit", (10, 22), 0),
    ],
}

# Department demand multiplier by month (1-12). Toys/Electronics spike in Nov-Dec,
# Sporting Goods in summer.
SEASONALITY = {
    "Toys": {11: 2.2, 12: 3.0},
    "Electronics": {11: 2.0, 12: 2.2},
    "Sporting Goods": {5: 1.5, 6: 1.8, 7: 1.8, 8: 1.4},
    "Apparel": {8: 1.4, 12: 1.5},
}
MONTH_TRAFFIC = {11: 1.25, 12: 1.45}  # overall store traffic

SCHEMA = """
CREATE TABLE regions (
    region_id    INTEGER PRIMARY KEY,
    region_name  TEXT NOT NULL
);
CREATE TABLE stores (
    store_id     INTEGER PRIMARY KEY,
    store_name   TEXT NOT NULL,
    store_type   TEXT NOT NULL,
    city         TEXT NOT NULL,
    state        TEXT NOT NULL,
    region_id    INTEGER NOT NULL REFERENCES regions(region_id),
    open_date    TEXT NOT NULL,
    square_feet  INTEGER NOT NULL
);
CREATE TABLE departments (
    department_id    INTEGER PRIMARY KEY,
    department_name  TEXT NOT NULL
);
CREATE TABLE products (
    product_id        INTEGER PRIMARY KEY,
    product_name      TEXT NOT NULL,
    brand             TEXT NOT NULL,
    department_id     INTEGER NOT NULL REFERENCES departments(department_id),
    unit_price        REAL NOT NULL,
    unit_cost         REAL NOT NULL,
    is_private_label  INTEGER NOT NULL
);
CREATE TABLE customers (
    customer_id  INTEGER PRIMARY KEY,
    membership   TEXT NOT NULL,
    join_date    TEXT NOT NULL,
    state        TEXT NOT NULL,
    age_group    TEXT NOT NULL
);
CREATE TABLE sales (
    sale_id         INTEGER PRIMARY KEY,
    sale_date       TEXT NOT NULL,
    store_id        INTEGER NOT NULL REFERENCES stores(store_id),
    customer_id     INTEGER REFERENCES customers(customer_id),
    channel         TEXT NOT NULL,
    payment_method  TEXT NOT NULL
);
CREATE TABLE sale_items (
    sale_item_id  INTEGER PRIMARY KEY,
    sale_id       INTEGER NOT NULL REFERENCES sales(sale_id),
    product_id    INTEGER NOT NULL REFERENCES products(product_id),
    quantity      INTEGER NOT NULL,
    unit_price    REAL NOT NULL,
    discount      REAL NOT NULL
);
CREATE TABLE inventory (
    store_id           INTEGER NOT NULL REFERENCES stores(store_id),
    product_id         INTEGER NOT NULL REFERENCES products(product_id),
    quantity_on_hand   INTEGER NOT NULL,
    reorder_level      INTEGER NOT NULL,
    last_restock_date  TEXT NOT NULL,
    PRIMARY KEY (store_id, product_id)
);
CREATE INDEX idx_sales_date ON sales(sale_date);
CREATE INDEX idx_sales_store ON sales(store_id);
CREATE INDEX idx_items_sale ON sale_items(sale_id);
CREATE INDEX idx_items_product ON sale_items(product_id);
"""


def random_date(rng, start, end):
    return start + timedelta(days=rng.randrange((end - start).days + 1))


def build(db_path=DB_PATH):
    rng = random.Random(SEED)
    db_path = Path(db_path)
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)

    # Regions and stores
    region_ids = {name: i + 1 for i, name in enumerate(REGIONS)}
    conn.executemany("INSERT INTO regions VALUES (?, ?)", [(i, n) for n, i in region_ids.items()])

    stores = []
    store_id = 1
    for city, state, region in CITIES:
        for _ in range(rng.choice([1, 1, 2, 2, 3])):
            stype, _, (lo, hi) = rng.choices(STORE_TYPES, weights=[t[1] for t in STORE_TYPES])[0]
            stores.append((
                store_id, f"{city} {stype} #{1000 + store_id}", stype, city, state,
                region_ids[region],
                random_date(rng, date(1995, 1, 1), date(2022, 12, 31)).isoformat(),
                rng.randrange(lo, hi, 1000),
            ))
            store_id += 1
    conn.executemany("INSERT INTO stores VALUES (?, ?, ?, ?, ?, ?, ?, ?)", stores)
    # Bigger stores get more traffic
    store_weights = [s[7] for s in stores]

    # Departments and products (each base product gets a few size/variant SKUs)
    dept_ids = {name: i + 1 for i, name in enumerate(CATALOG)}
    conn.executemany("INSERT INTO departments VALUES (?, ?)", [(i, n) for n, i in dept_ids.items()])

    products = []  # (id, name, brand, dept_id, price, cost, private, dept_name)
    pid = 1
    for dept, items in CATALOG.items():
        for brand, base, (lo, hi), private in items:
            for variant in rng.sample(["", " Value Size", " Family Pack", " Premium", " Mini"], k=rng.choice([2, 3])):
                price = round(rng.uniform(lo, hi), 2)
                margin = rng.uniform(0.18, 0.40) if private else rng.uniform(0.08, 0.28)
                products.append((pid, f"{brand} {base}{variant}", brand, dept_ids[dept],
                                 price, round(price * (1 - margin), 2), private, dept))
                pid += 1
    conn.executemany("INSERT INTO products VALUES (?, ?, ?, ?, ?, ?, ?)", [p[:7] for p in products])

    # Customers
    states = sorted({c[1] for c in CITIES})
    customers = [
        (cid,
         rng.choices(["None", "Walmart+"], weights=[0.7, 0.3])[0],
         random_date(rng, date(2018, 1, 1), date(2025, 6, 30)).isoformat(),
         rng.choice(states),
         rng.choices(["18-24", "25-34", "35-44", "45-54", "55-64", "65+"],
                     weights=[0.12, 0.22, 0.22, 0.18, 0.14, 0.12])[0])
        for cid in range(1, N_CUSTOMERS + 1)
    ]
    conn.executemany("INSERT INTO customers VALUES (?, ?, ?, ?, ?)", customers)
    walmart_plus = {c[0] for c in customers if c[1] == "Walmart+"}

    # Pre-build product pools per department; grocery dominates basket counts
    by_dept = {}
    for p in products:
        by_dept.setdefault(p[7], []).append(p)
    base_dept_weight = {"Grocery": 0.45, "Health & Beauty": 0.12, "Home": 0.10, "Apparel": 0.10,
                        "Electronics": 0.07, "Toys": 0.06, "Sporting Goods": 0.05, "Automotive": 0.05}
    dept_names = list(base_dept_weight)

    # Day weights for traffic seasonality
    days = [START_DATE + timedelta(d) for d in range((END_DATE - START_DATE).days + 1)]
    day_weights = []
    for d in days:
        w = MONTH_TRAFFIC.get(d.month, 1.0)
        w *= 1.3 if d.weekday() >= 5 else 1.0          # weekends busier
        w *= 1.08 if d.year == 2025 else 1.0           # ~8% YoY growth
        day_weights.append(w)

    sales, items = [], []
    item_id = 1
    sale_dates = sorted(rng.choices(days, weights=day_weights, k=N_SALES))
    for sale_id, d in enumerate(sale_dates, start=1):
        store = rng.choices(stores, weights=store_weights)[0]
        channel = rng.choices(["In-Store", "Online", "Pickup"],
                              weights=[0.70, 0.18 + 0.04 * (d.year - 2024), 0.12])[0]
        customer = rng.randrange(1, N_CUSTOMERS + 1) if (channel != "In-Store" or rng.random() < 0.45) else None
        payment = rng.choices(["Credit Card", "Debit Card", "Cash", "Walmart Pay", "EBT"],
                              weights=[0.38, 0.30, 0.12 if channel == "In-Store" else 0.0, 0.14, 0.06])[0]
        sales.append((sale_id, d.isoformat(), store[0], customer, channel, payment))

        weights = [base_dept_weight[n] * SEASONALITY.get(n, {}).get(d.month, 1.0) for n in dept_names]
        for _ in range(rng.choices([1, 2, 3, 4, 5, 6, 8], weights=[18, 22, 20, 15, 11, 8, 6])[0]):
            dept = rng.choices(dept_names, weights=weights)[0]
            p = rng.choice(by_dept[dept])
            qty = rng.choices([1, 2, 3, 4], weights=[70, 20, 7, 3])[0] if p[4] < 50 else 1
            # Price drifts slightly up in 2025; members and holiday season get discounts
            price = round(p[4] * (1.03 if d.year == 2025 else 1.0), 2)
            discount = 0.0
            if customer in walmart_plus and rng.random() < 0.25:
                discount = round(price * qty * 0.05, 2)
            if d.month in (11, 12) and dept in ("Electronics", "Toys") and rng.random() < 0.4:
                discount = round(price * qty * rng.choice([0.10, 0.15, 0.20]), 2)
            items.append((item_id, sale_id, p[0], qty, price, discount))
            item_id += 1

    conn.executemany("INSERT INTO sales VALUES (?, ?, ?, ?, ?, ?)", sales)
    conn.executemany("INSERT INTO sale_items VALUES (?, ?, ?, ?, ?, ?)", items)

    # Inventory snapshot (as of END_DATE) for every store x product
    inventory = []
    for s in stores:
        for p in products:
            reorder = rng.choice([10, 15, 20, 25, 30])
            on_hand = max(0, int(rng.gauss(reorder * 2.2, reorder)))
            inventory.append((s[0], p[0], on_hand, reorder,
                              random_date(rng, END_DATE - timedelta(days=45), END_DATE).isoformat()))
    conn.executemany("INSERT INTO inventory VALUES (?, ?, ?, ?, ?)", inventory)

    conn.commit()
    counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
              for t in ["regions", "stores", "departments", "products", "customers",
                        "sales", "sale_items", "inventory"]}
    conn.close()
    return counts


if __name__ == "__main__":
    for table, n in build().items():
        print(f"{table:<12} {n:>8,} rows")
    print(f"Wrote {DB_PATH}")

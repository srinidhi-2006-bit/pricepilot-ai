"""Synthetic retail/e-commerce dataset (swap for Kaggle CSVs via /sales/upload)."""
import datetime as dt, numpy as np
from .core import *

PRODUCTS = [  # sku, name, category, cost, price, base daily demand, elasticity
    ("EL-001", "Wireless Earbuds", "Electronics", 18, 49, 60, -1.9),
    ("EL-002", "Smart Watch", "Electronics", 45, 129, 25, -1.5),
    ("HM-001", "Air Fryer", "Home", 38, 89, 30, -1.7),
    ("HM-002", "LED Desk Lamp", "Home", 7, 24, 55, -2.2),
    ("FS-001", "Running Shoes", "Fashion", 22, 69, 40, -1.6),
    ("FS-002", "Denim Jacket", "Fashion", 20, 59, 28, -1.8),
    ("GR-001", "Organic Coffee 1kg", "Grocery", 9, 21, 80, -1.3),
    ("GR-002", "Protein Bars (12)", "Grocery", 8, 19, 70, -2.0),
]

def seed(db, days=540):
    if db.query(User).count() == 0:
        db.add_all([User(name="Admin", email="admin@pricepilot.ai", password=hash_pw("admin123"), role="admin"),
                    User(name="Priya Manager", email="manager@pricepilot.ai", password=hash_pw("manager123"), role="pricing_manager"),
                    User(name="Arun Analyst", email="analyst@pricepilot.ai", password=hash_pw("analyst123"), role="analyst")])
    if db.query(Product).count(): db.commit(); return
    rng = np.random.default_rng(42)
    today = dt.date.today()
    dates = [today - dt.timedelta(days=days - i) for i in range(days)]
    for sku, name, cat, cost, price, base, e in PRODUCTS:
        p = Product(sku=sku, name=name, category=cat, cost=cost, price=price, stock=int(base * 45)); db.add(p); db.flush()
        rows, drift = [], 1.0
        for i, d in enumerate(dates):
            drift *= 1 + rng.normal(0.0002, 0.002)
            promo = rng.choice([0, 0, 0, 0, 0, 10, 15, 20], p=[.7, .05, .05, .05, .05, .04, .03, .03]) if d.month in (10, 11, 12) or rng.random() < .85 else 0
            comp = price * drift * (1 + rng.normal(0, .03))
            ours = price * drift * (1 - promo / 100)
            season = 1 + (.35 if d.month in (10, 11, 12) else 0) + .1 * np.sin(2 * np.pi * d.timetuple().tm_yday / 365)
            dow = 1.2 if d.weekday() >= 5 else 1.0
            mu = base * season * dow * (ours / price) ** e * (comp / ours) ** .5 * (1 + .0006 * i)
            rows.append(Sale(product_id=p.id, date=d, units=int(rng.poisson(max(mu, 0.5))), price=round(ours, 2), discount=float(promo), competitor_price=round(comp, 2)))
        db.bulk_save_objects(rows)
        last = rows[-1].competitor_price
        for k, comp_name in enumerate(["MarketMax", "ShopNova", "ValueHub"]):
            for back in range(0, 28, 7):
                db.add(CompetitorPrice(product_id=p.id, competitor=comp_name, price=round(last * (1 + rng.normal(-.02 + k * .03, .02)), 2), date=today - dt.timedelta(days=back)))
    db.commit()

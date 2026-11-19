import statistics
from app.core import SessionLocal, Product, Sale

db = SessionLocal()
for p in db.query(Product):
    rows = db.query(Sale).filter(Sale.product_id == p.id).order_by(Sale.date.desc()).limit(30).all()
    if rows:
        p.price = round(statistics.median(r.price for r in rows), 2)
        print(p.name, "->", p.price)
db.commit()
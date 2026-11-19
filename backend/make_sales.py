import csv, random, datetime as dt

SKU, PRICE, BASE_DEMAND = "FS-003", 1000, 6     # change to match your product
today = dt.date.today()
with open("books_sales.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["sku", "date", "units", "price", "discount", "competitor_price"])
    for i in range(180, 0, -1):
        d = today - dt.timedelta(days=i)
        weekend = 1.3 if d.weekday() >= 5 else 1.0
        promo = random.choice([0, 0, 0, 0, 10])
        price = round(PRICE * (1 - promo / 100), 2)
        comp = round(PRICE * random.uniform(0.95, 1.05), 2)
        units = max(0, int(random.gauss(BASE_DEMAND * weekend * (1 + promo / 50), 1.5)))
        w.writerow([SKU, d, units, price, promo, comp])
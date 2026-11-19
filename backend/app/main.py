import io, datetime as dt
import pandas as pd
from typing import List, Optional
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
from sqlalchemy import func
from sqlalchemy.orm import Session
from .core import *
from . import ml
from .seed import seed

Base.metadata.create_all(engine)
app = FastAPI(title="PricePilot AI", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.on_event("startup")
def _seed():
    with SessionLocal() as db: seed(db)

MGR = require("admin", "pricing_manager")
ANY = current_user

class RegisterIn(BaseModel):
    name: str; email: EmailStr; password: str; role: str = "analyst"
class ProductIn(BaseModel):
    sku: str; name: str; category: str = "General"; cost: float; price: float; stock: int = 0
class PriceIn(BaseModel):
    price: float
class SimIn(BaseModel):
    changes_pct: List[float] = [-15, -10, -5, 0, 5, 10, 15]; horizon_days: int = 30

def prod(db, pid):
    p = db.get(Product, pid)
    if not p: raise HTTPException(404, "Product not found")
    return p
def wrap(fn, *a, **k):
    try: return fn(*a, **k)
    except ValueError as e: raise HTTPException(422, str(e))

# ---------- Auth & users ----------
@app.post("/auth/register")
def register(b: RegisterIn, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == b.email).first(): raise HTTPException(409, "Email already registered")
    role = "admin" if db.query(User).count() == 0 else (b.role if b.role in ("pricing_manager", "analyst") else "analyst")
    u = User(name=b.name, email=b.email, password=hash_pw(b.password), role=role); db.add(u); db.commit()
    return dict(id=u.id, email=u.email, role=u.role)

@app.post("/auth/login")
def login(f: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    u = db.query(User).filter(User.email == f.username).first()
    if not u or not check_pw(f.password, u.password): raise HTTPException(401, "Incorrect email or password")
    return dict(access_token=make_token(u), token_type="bearer", role=u.role, name=u.name)

@app.get("/auth/me")
def me(u: User = Depends(ANY)): return dict(id=u.id, name=u.name, email=u.email, role=u.role)

@app.get("/users")
def users(db: Session = Depends(get_db), _=Depends(require("admin"))):
    return [dict(id=u.id, name=u.name, email=u.email, role=u.role) for u in db.query(User).all()]

@app.put("/users/{uid}/role")
def set_role(uid: int, role: str, db: Session = Depends(get_db), _=Depends(require("admin"))):
    if role not in ("admin", "pricing_manager", "analyst"): raise HTTPException(422, "Invalid role")
    u = db.get(User, uid); u.role = role; db.commit(); return dict(id=u.id, role=u.role)

# ---------- Products & pricing data ----------
def pj(p): return dict(id=p.id, sku=p.sku, name=p.name, category=p.category, cost=p.cost, price=p.price, stock=p.stock,
                       margin_pct=round((p.price - p.cost) / p.price * 100, 1))

@app.get("/products")
def products(db: Session = Depends(get_db), _=Depends(ANY)): return [pj(p) for p in db.query(Product).order_by(Product.id)]

@app.post("/products")
def add_product(b: ProductIn, db: Session = Depends(get_db), _=Depends(MGR)):
    if b.cost <= 0 or b.price <= 0: raise HTTPException(422, "Cost and price must be positive")
    if db.query(Product).filter(Product.sku == b.sku).first(): raise HTTPException(409, "SKU exists")
    p = Product(**b.model_dump()); db.add(p); db.commit(); return pj(p)

@app.put("/products/{pid}")
def edit_product(pid: int, b: ProductIn, db: Session = Depends(get_db), _=Depends(MGR)):
    p = prod(db, pid)
    for k, v in b.model_dump().items(): setattr(p, k, v)
    db.commit(); return pj(p)

@app.delete("/products/{pid}")
def del_product(pid: int, db: Session = Depends(get_db), _=Depends(require("admin"))):
    p = prod(db, pid)
    for m in (Sale, CompetitorPrice, PriceHistory): db.query(m).filter(m.product_id == pid).delete()
    db.delete(p); db.commit(); return dict(deleted=pid)

@app.post("/products/{pid}/price")
def apply_price(pid: int, b: PriceIn, db: Session = Depends(get_db), u=Depends(MGR)):
    p = prod(db, pid)
    if b.price <= p.cost: raise HTTPException(422, "Price must exceed unit cost")
    db.add(PriceHistory(product_id=pid, old_price=p.price, new_price=b.price, changed_by=u.email)); p.price = b.price; db.commit(); return pj(p)

@app.get("/products/{pid}/price-history")
def price_hist(pid: int, db: Session = Depends(get_db), _=Depends(ANY)):
    return [dict(date=str(r.date), old=r.old_price, new=r.new_price, by=r.changed_by) for r in db.query(PriceHistory).filter(PriceHistory.product_id == pid).order_by(PriceHistory.id.desc())]

@app.get("/sales/{pid}")
def sales(pid: int, days: int = 90, db: Session = Depends(get_db), _=Depends(ANY)):
    since = dt.date.today() - dt.timedelta(days=days)
    return [dict(date=str(s.date), units=s.units, price=s.price, discount=s.discount, competitor_price=s.competitor_price)
            for s in db.query(Sale).filter(Sale.product_id == pid, Sale.date >= since).order_by(Sale.date)]

@app.post("/sales/upload")
async def upload_sales(file: UploadFile = File(...), db: Session = Depends(get_db), _=Depends(MGR)):
    """CSV columns: sku,date,units,price[,discount,competitor_price]. Validates and reports rejected rows."""
    df = pd.read_csv(io.BytesIO(await file.read()))
    need = {"sku", "date", "units", "price"}
    if not need <= set(df.columns): raise HTTPException(422, f"Missing columns: {sorted(need - set(df.columns))}")
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    if "discount" not in df: df["discount"] = 0
    skus = {p.sku: p for p in db.query(Product)}
    ok, bad = [], 0
    for r in df.itertuples():
        p = skus.get(r.sku)
        if p is None or pd.isna(r.date) or pd.isna(r.units) or pd.isna(r.price) or r.units < 0 or r.price <= 0: bad += 1; continue
        comp = getattr(r, "competitor_price", None)
        ok.append(Sale(product_id=p.id, date=r.date.date(), units=int(r.units), price=float(r.price), discount=float(r.discount or 0),
                       competitor_price=float(comp) if comp == comp and comp is not None else float(r.price)))
    db.bulk_save_objects(ok); db.commit(); ml._cache.clear()
    return dict(imported=len(ok), rejected=bad)

# ---------- Price prediction ----------
@app.get("/prediction/{pid}/optimal-price")
def optimal(pid: int, objective: str = "profit", horizon_days: int = 30, min_margin: float = 0.10, db: Session = Depends(get_db), _=Depends(ANY)):
    if objective not in ("profit", "revenue"): raise HTTPException(422, "objective must be profit or revenue")
    return wrap(ml.optimal_price, db, prod(db, pid), horizon_days, objective, min_margin)

@app.get("/prediction/{pid}/price-forecast")
def price_fc(pid: int, days: int = 30, db: Session = Depends(get_db), _=Depends(ANY)):
    prod(db, pid); return wrap(ml.price_forecast, db, pid, days)

# ---------- Demand ----------
@app.get("/demand/{pid}")
def demand(pid: int, horizon: str = "30d", db: Session = Depends(get_db), _=Depends(ANY)):
    if horizon not in ml.HORIZONS: raise HTTPException(422, f"horizon must be one of {list(ml.HORIZONS)}")
    prod(db, pid); return wrap(ml.demand_forecast, db, pid, horizon)

# ---------- Competitors ----------
@app.get("/competitors")
def comp_all(db: Session = Depends(get_db), _=Depends(ANY)): return [ml.competitor_view(db, p) for p in db.query(Product)]

@app.get("/competitors/{pid}")
def comp_one(pid: int, db: Session = Depends(get_db), _=Depends(ANY)): return ml.competitor_view(db, prod(db, pid))

@app.post("/competitors/{pid}")
def add_comp(pid: int, competitor: str, price: float, db: Session = Depends(get_db), _=Depends(MGR)):
    prod(db, pid); db.add(CompetitorPrice(product_id=pid, competitor=competitor, price=price, date=dt.date.today())); db.commit(); return dict(ok=True)

# ---------- Revenue optimisation ----------
@app.post("/revenue/{pid}/simulate")
def sim(pid: int, b: SimIn, db: Session = Depends(get_db), _=Depends(ANY)): return wrap(ml.simulate, db, prod(db, pid), b.changes_pct, b.horizon_days)

@app.get("/revenue/{pid}/strategy")
def strat(pid: int, db: Session = Depends(get_db), _=Depends(ANY)): return wrap(ml.strategy, db, prod(db, pid))

# ---------- Analytics dashboard ----------
@app.get("/analytics/summary")
def summary(db: Session = Depends(get_db), _=Depends(ANY)):
    today = dt.date.today(); d30, d60 = today - dt.timedelta(days=30), today - dt.timedelta(days=60)
    rows = (db.query(Product.id, Product.name, Product.category, Product.cost, Sale.date, Sale.units, Sale.price)
            .join(Sale, Sale.product_id == Product.id).filter(Sale.date >= today - dt.timedelta(days=365)).all())
    df = pd.DataFrame(rows, columns=["pid", "name", "category", "cost", "date", "units", "price"])
    df["rev"] = df.units * df.price; df["profit"] = df.units * (df.price - df.cost); df["date"] = pd.to_datetime(df["date"])
    cur, prev = df[df.date >= pd.Timestamp(d30)], df[(df.date >= pd.Timestamp(d60)) & (df.date < pd.Timestamp(d30))]
    pct = lambda a, b: round((a / b - 1) * 100, 1) if b else 0
    monthly = df.groupby(df.date.dt.to_period("M").astype(str))[["rev", "profit"]].sum().round(0).reset_index()
    top = cur.groupby("name")[["rev", "profit", "units"]].sum().round(0).sort_values("profit", ascending=False).reset_index()
    cat = cur.groupby("category")[["rev", "profit"]].sum().round(0).reset_index()
    return dict(revenue_30d=round(cur.rev.sum()), revenue_change_pct=pct(cur.rev.sum(), prev.rev.sum()),
                profit_30d=round(cur.profit.sum()), profit_change_pct=pct(cur.profit.sum(), prev.profit.sum()),
                units_30d=int(cur.units.sum()), margin_pct=round(cur.profit.sum() / max(cur.rev.sum(), 1) * 100, 1),
                monthly=monthly.rename(columns={"date": "month"}).to_dict("records") if "date" in monthly else monthly.rename(columns={monthly.columns[0]: "month"}).to_dict("records"),
                top_products=top.to_dict("records"), by_category=cat.to_dict("records"))

@app.get("/analytics/model-report")
def model_report(db: Session = Depends(get_db), _=Depends(ANY)):
    out = []
    for p in db.query(Product):
        try:
            df = ml.sales_frame(db, p.id); _, m = ml.train(df, p.id)
            out.append(dict(product=p.name, **m))
        except Exception:
            out.append(dict(product=p.name, model="Not enough data (need 90+ days of sales)", mae=None, rmse=None, mape=None))
    return out

@app.get("/health")
def health(): return dict(status="ok")

"""Forecasting, elasticity, price optimisation, competitor + revenue analytics."""
import numpy as np, pandas as pd, datetime as dt
from sklearn.ensemble import RandomForestRegressor
from .core import Sale, CompetitorPrice
try:
    from xgboost import XGBRegressor
except Exception:  # pragma: no cover
    XGBRegressor = None

HORIZONS = {"7d": 7, "14d": 14, "30d": 30, "3m": 90, "6m": 180, "12m": 365}
_cache = {}

def sales_frame(db, pid):
    rows = db.query(Sale).filter(Sale.product_id == pid).order_by(Sale.date).all()
    if len(rows) < 90:
        raise ValueError("At least 90 days of sales history required")
    df = pd.DataFrame([dict(date=r.date, units=r.units, price=r.price, discount=r.discount, comp=r.competitor_price) for r in rows])
    df["date"] = pd.to_datetime(df["date"])
    return df

def feats(df):
    d = df["date"]
    return pd.DataFrame({"dow": d.dt.dayofweek, "month": d.dt.month, "doy": d.dt.dayofyear,
                         "festive": d.dt.month.isin([10, 11, 12]).astype(int),
                         "t": (d - pd.Timestamp("2020-01-01")).dt.days,
                         "price": df["price"], "discount": df["discount"], "comp": df["comp"]})

def _model():
    return XGBRegressor(n_estimators=300, max_depth=4, learning_rate=.05, subsample=.9, verbosity=0) if XGBRegressor \
        else RandomForestRegressor(n_estimators=200, min_samples_leaf=3, random_state=0, n_jobs=-1)

def train(df, key):
    """Hold out last 30 days for MAE/RMSE/MAPE, then refit on everything."""
    ck = (key, len(df))
    if ck in _cache: return _cache[ck]
    X, y = feats(df), df["units"].values
    m = _model().fit(X[:-30], y[:-30])
    p = np.clip(m.predict(X[-30:]), 0, None)
    mae = float(np.mean(np.abs(p - y[-30:]))); rmse = float(np.sqrt(np.mean((p - y[-30:]) ** 2)))
    mape = float(np.mean(np.abs(p - y[-30:]) / np.maximum(y[-30:], 1)))
    final = _model().fit(X, y)
    _cache[ck] = (final, dict(mae=round(mae, 2), rmse=round(rmse, 2), mape=round(mape * 100, 2), model=type(final).__name__))
    return _cache[ck]

def future_frame(df, days, price=None):
    last = df.iloc[-7:]
    dates = pd.date_range(df["date"].iloc[-1] + pd.Timedelta(days=1), periods=days)
    return pd.DataFrame({"date": dates, "price": price or float(last["price"].mean()),
                         "discount": 0.0, "comp": float(last["comp"].mean())})

def demand_forecast(db, pid, horizon="30d"):
    days = HORIZONS[horizon]
    df = sales_frame(db, pid)
    model, metrics = train(df, pid)
    fut = future_frame(df, days)
    fut["units"] = np.clip(model.predict(feats(fut)), 0, None)
    recent = df["units"].iloc[-30:].mean()
    change = (fut["units"].mean() - recent) / max(recent, 1)
    trend = "Increasing Demand" if change > .05 else "Decreasing Demand" if change < -.05 else "Stable Demand"
    confidence = round(float(np.clip(100 - metrics["mape"], 0, 100)), 1)
    monthly = df.groupby(df["date"].dt.month)["units"].mean().round(1)
    dow = df.groupby(df["date"].dt.dayofweek)["units"].mean().round(1)
    return dict(product_id=pid, horizon=horizon, forecast_days=days, predicted_units=int(fut["units"].sum()),
                trend=trend, trend_change_pct=round(change * 100, 1), confidence=confidence, metrics=metrics,
                history=[dict(date=str(r.date.date()), units=int(r.units)) for r in df.iloc[-60:].itertuples()],
                forecast=[dict(date=str(r.date.date()), units=round(float(r.units), 1)) for r in fut.itertuples()][:120],
                seasonal_monthly=[dict(month=int(k), avg_units=float(v)) for k, v in monthly.items()],
                seasonal_weekday=[dict(day=int(k), avg_units=float(v)) for k, v in dow.items()])

def elasticity(df):
    """Log-log OLS: log(units) ~ log(price) + log(comp) + festive. Clipped to a sane range."""
    y = np.log(df["units"].clip(lower=1))
    X = np.column_stack([np.ones(len(df)), np.log(df["price"]), np.log(df["comp"]), df["date"].dt.month.isin([10, 11, 12]).astype(int)])
    beta = np.linalg.lstsq(X, y, rcond=None)[0]
    return float(np.clip(beta[1], -4.0, -0.3)), float(np.clip(beta[2], 0, 2))
def curve(db, product, horizon_days=30, min_margin=0.10, lo=0.85, hi=1.15, steps=41):
    df = sales_frame(db, product.id)
    model, _ = train(df, product.id)
    cur = float(product.price)
    base_units = float(np.clip(model.predict(feats(future_frame(df, horizon_days, cur))), 0, None).sum())
    e, _ = elasticity(df)
    floor = max(product.cost * (1 + min_margin), cur * lo)
    out = []
    for p in np.linspace(floor, cur * hi, steps):
        units = min(base_units * (p / cur) ** e, max(product.stock, 0) * 1.0 if product.stock else 1e9)
        out.append(dict(price=round(float(p), 2), units=round(units, 1), revenue=round(units * p, 2), profit=round(units * (p - product.cost), 2)))
    return out, e, base_units

def optimal_price(db, product, horizon_days=30, objective="profit", min_margin=0.10):
    pts, e, base = curve(db, product, horizon_days, min_margin)
    best = max(pts, key=lambda r: r[objective])
    cur = dict(price=product.price, units=round(base, 1), revenue=round(base * product.price, 2), profit=round(base * (product.price - product.cost), 2))
    return dict(product_id=product.id, sku=product.sku, name=product.name, objective=objective, elasticity=round(e, 2),
                current=cur, recommended=best, price_change_pct=round((best["price"] / product.price - 1) * 100, 1),
                uplift_pct=round((best[objective] / max(cur[objective], 1e-9) - 1) * 100, 1), curve=pts)

def price_forecast(db, pid, days=30):
    df = sales_frame(db, pid)
    X = pd.DataFrame({"t": (df["date"] - pd.Timestamp("2020-01-01")).dt.days, "dow": df["date"].dt.dayofweek, "month": df["date"].dt.month})
    m = RandomForestRegressor(n_estimators=150, min_samples_leaf=5, random_state=0).fit(X, df["price"])
    # blend with linear trend so the forecast can extrapolate beyond training range
    lt = np.polyfit(X["t"].values[-120:], df["price"].values[-120:], 1)
    dates = pd.date_range(df["date"].iloc[-1] + pd.Timedelta(days=1), periods=days)
    F = pd.DataFrame({"t": (dates - pd.Timestamp("2020-01-01")).days, "dow": dates.dayofweek, "month": dates.month})
    pred = .5 * m.predict(F) + .5 * np.polyval(lt, F["t"])
    slope = lt[0] * 30
    trend = "Rising" if slope / df["price"].iloc[-1] > .01 else "Falling" if slope / df["price"].iloc[-1] < -.01 else "Flat"
    return dict(product_id=pid, trend=trend, monthly_change=round(float(slope), 2),
                history=[dict(date=str(r.date.date()), price=r.price) for r in df.iloc[-60:].itertuples()],
                forecast=[dict(date=str(d.date()), price=round(float(p), 2)) for d, p in zip(dates, pred)])

def competitor_view(db, product):
    rows = db.query(CompetitorPrice).filter(CompetitorPrice.product_id == product.id).order_by(CompetitorPrice.date.desc()).all()
    latest = {}
    for r in rows: latest.setdefault(r.competitor, r)
    prices = [r.price for r in latest.values()]
    if not prices: return dict(product_id=product.id, name=product.name, price=product.price, competitors=[], position=None, signal="No data")
    avg = float(np.mean(prices)); idx = product.price / avg
    signal = "Premium: consider discount or value messaging" if idx > 1.08 else "Underpriced: room to raise price" if idx < .95 else "Competitive"
    return dict(product_id=product.id, sku=product.sku, name=product.name, price=product.price, avg_competitor=round(avg, 2),
                min_competitor=round(min(prices), 2), max_competitor=round(max(prices), 2), position_index=round(idx, 3),
                gap_pct=round((idx - 1) * 100, 1), signal=signal,
                competitors=[dict(name=k, price=v.price, date=str(v.date)) for k, v in latest.items()])

def simulate(db, product, changes_pct, horizon_days=30):
    df = sales_frame(db, product.id)
    model, _ = train(df, product.id)
    e, _ = elasticity(df)
    base = float(np.clip(model.predict(feats(future_frame(df, horizon_days, product.price))), 0, None).sum())
    rows = []
    for c in changes_pct:
        p = product.price * (1 + c / 100); u = base * (1 + c / 100) ** e
        rows.append(dict(change_pct=c, price=round(p, 2), units=round(u, 1), revenue=round(u * p, 2), profit=round(u * (p - product.cost), 2),
                         margin_pct=round((p - product.cost) / p * 100, 1)))
    return dict(product_id=product.id, name=product.name, elasticity=round(e, 2), scenarios=rows)

def strategy(db, product):
    opt = optimal_price(db, product); comp = competitor_view(db, product); dem = demand_forecast(db, product.id, "30d")
    tips = []
    if opt["price_change_pct"] > 2: tips.append(f"Raise price ~{opt['price_change_pct']}% to ${opt['recommended']['price']} (projected profit +{opt['uplift_pct']}%).")
    elif opt["price_change_pct"] < -2: tips.append(f"Cut price ~{abs(opt['price_change_pct'])}% to ${opt['recommended']['price']} to unlock volume (profit +{opt['uplift_pct']}%).")
    else: tips.append("Current price is close to the profit-maximising point; hold.")
    if opt["elasticity"] < -1.8: tips.append("Demand is highly price-sensitive: prefer targeted promotions over broad increases.")
    if dem["trend"].startswith("Increasing"): tips.append("Demand is rising: protect stock and avoid deep discounts.")
    if dem["trend"].startswith("Decreasing"): tips.append("Demand is softening: consider a time-boxed promotion.")
    if comp.get("gap_pct") is not None and comp["gap_pct"] > 8: tips.append(f"You are {comp['gap_pct']}% above competitors; justify with bundles or value.")
    margin = (product.price - product.cost) / product.price * 100
    if margin < 25: tips.append(f"Margin is thin ({margin:.0f}%); review supplier cost or minimum price.")
    return dict(product_id=product.id, name=product.name, recommendations=tips, trend=dem["trend"], elasticity=opt["elasticity"])

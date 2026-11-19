# PricePilot AI: Dynamic Pricing Optimization & Revenue Intelligence

FastAPI + XGBoost/scikit-learn backend, React (Vite) + Recharts frontend, PostgreSQL, Docker.

## Run with Docker
    docker compose up --build
Open http://localhost:3000 (API docs: http://localhost:8000/docs). On first start the DB is seeded with 8 products and ~18 months of synthetic sales.

Demo logins: admin@pricepilot.ai / admin123 · manager@pricepilot.ai / manager123 · analyst@pricepilot.ai / analyst123

## Run locally (no Docker, SQLite)
    cd backend && pip install -r requirements.txt && uvicorn app.main:app --reload
    cd frontend && npm install && npm run dev      # http://localhost:5173

## Roles
- admin: everything, user roles, delete products
- pricing_manager: edit products, upload sales, apply recommended prices
- analyst: read-only dashboards, forecasts, simulations

## Modules → code
| Module | Where |
|---|---|
| User management / JWT / RBAC | backend/app/core.py, main.py `/auth`, `/users` |
| Product & pricing data, CSV validation | main.py `/products`, `/sales/upload` |
| Price prediction | ml.py `optimal_price`, `price_forecast` |
| Demand forecasting (7d to 12m, trend, confidence) | ml.py `demand_forecast` |
| Competitor analysis | ml.py `competitor_view` |
| Revenue optimization | ml.py `simulate`, `strategy` |
| Analytics dashboard | main.py `/analytics/*`, frontend/src/App.jsx |

## How the ML works
- **Demand**: XGBoost regressor on calendar, festive season, trend, price, discount and competitor price. The last 30 days are held out to compute MAE/RMSE/MAPE; confidence = 100 − MAPE.
- **Trend class**: forecast daily mean vs last-30-day mean (±5%).
- **Elasticity**: log-log regression of units on own and competitor price.
- **Optimal price**: grid search over 0.7x to 1.5x of the current price on projected units × margin, respecting a minimum margin and stock.
- Swap in Prophet, ARIMA or an LSTM inside `ml.train` / `ml.demand_forecast` to compare models.

## Load real data
POST a CSV (`sku,date,units,price,discount,competitor_price`) to `/sales/upload` or use the button on the Products page. Create matching SKUs first.

## Cloud deployment (AWS/Azure)
Push the two images to ECR/ACR, run on ECS/App Service (or one VM with `docker compose`), use RDS/Azure Postgres via `DATABASE_URL`, and set a strong `JWT_SECRET`.

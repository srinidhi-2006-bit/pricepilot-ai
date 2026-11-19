import React, { useEffect, useState } from "react";
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer, ReferenceDot, Legend, ComposedChart } from "recharts";
import { api, auth, login } from "./api.js";

const money = n => n == null ? "-" : "$" + Number(n).toLocaleString(undefined, { maximumFractionDigits: 2 });
const C = { a: "#0e6b5c", b: "#c27a06", c: "#6b7fd7" };
const ax = { stroke: "#8a9a93", fontSize: 12 };
const Chart = ({ h = 260, children }) => <ResponsiveContainer width="100%" height={h}>{children}</ResponsiveContainer>;
const Pct = ({ v }) => <span className={v >= 0 ? "up" : "down"}>{v >= 0 ? "+" : ""}{v}%</span>;

function useLoad(fn, deps) {
  const [s, set] = useState({ data: null, error: null, loading: true });
  useEffect(() => { let on = true; set(x => ({ ...x, loading: true, error: null }));
    fn().then(d => on && set({ data: d, error: null, loading: false })).catch(e => on && set({ data: null, error: e.message, loading: false })); return () => { on = false; }; }, deps);
  return s;
}
const State = ({ s, children }) => s.loading ? <p className="muted">Loading…</p> : s.error ? <p className="err">{s.error}</p> : children(s.data);

function Login({ onDone }) {
  const [mode, setMode] = useState("login"), [f, setF] = useState({ name: "", email: "admin@pricepilot.ai", password: "admin123", role: "analyst" }), [err, setErr] = useState("");
  const submit = async e => { e.preventDefault(); setErr("");
    try { if (mode === "register") await api("/auth/register", { method: "POST", body: f });
      const d = await login(f.email, f.password); auth.set(d.access_token); localStorage.setItem("pp_user", JSON.stringify(d)); onDone(d); } catch (x) { setErr(x.message); } };
  return <div className="login"><h1>PricePilot AI</h1><p className="muted">Pricing decisions backed by demand forecasts and competitor data.</p>
    <form onSubmit={submit}>{mode === "register" && <><input placeholder="Full name" value={f.name} onChange={e => setF({ ...f, name: e.target.value })} required />
      <select value={f.role} onChange={e => setF({ ...f, role: e.target.value })}><option value="analyst">Analyst</option><option value="pricing_manager">Pricing manager</option></select></>}
      <input type="email" placeholder="Email" value={f.email} onChange={e => setF({ ...f, email: e.target.value })} required />
      <input type="password" placeholder="Password" value={f.password} onChange={e => setF({ ...f, password: e.target.value })} required />
      {err && <div className="err">{err}</div>}<button className="btn">{mode === "login" ? "Sign in" : "Create account"}</button>
      <button type="button" className="btn ghost" onClick={() => setMode(mode === "login" ? "register" : "login")}>{mode === "login" ? "Create an account" : "Back to sign in"}</button></form>
    <p className="muted">Demo: admin@pricepilot.ai / admin123, manager@pricepilot.ai / manager123, analyst@pricepilot.ai / analyst123</p></div>;
}

function ProductPicker({ products, value, onChange }) {
  return <select aria-label="Product" value={value} onChange={e => onChange(+e.target.value)}>{products.map(p => <option key={p.id} value={p.id}>{p.name} ({p.sku})</option>)}</select>;
}

function Dashboard() {
  const s = useLoad(() => api("/analytics/summary"), []); const m = useLoad(() => api("/analytics/model-report"), []);
  return <State s={s}>{d => <>
    <div className="head"><h2>Revenue overview</h2><span className="muted">Last 30 days vs the 30 before</span></div>
    <div className="grid g4">
      <div className="card stat"><small>Revenue</small><div className="v">{money(d.revenue_30d)}</div><Pct v={d.revenue_change_pct} /></div>
      <div className="card stat"><small>Profit</small><div className="v">{money(d.profit_30d)}</div><Pct v={d.profit_change_pct} /></div>
      <div className="card stat"><small>Units sold</small><div className="v">{d.units_30d.toLocaleString()}</div></div>
      <div className="card stat"><small>Margin</small><div className="v">{d.margin_pct}%</div></div></div>
    <div className="grid g2" style={{ marginTop: 14 }}>
      <div className="card"><h3>Monthly revenue and profit</h3><Chart><BarChart data={d.monthly}><CartesianGrid stroke="#8884" /><XAxis dataKey="month" {...ax} /><YAxis {...ax} /><Tooltip /><Legend /><Bar dataKey="rev" name="Revenue" fill={C.a} /><Bar dataKey="profit" name="Profit" fill={C.b} /></BarChart></Chart></div>
      <div className="card"><h3>Product profitability (30 days)</h3><Chart><BarChart data={d.top_products} layout="vertical" margin={{ left: 40 }}><CartesianGrid stroke="#8884" /><XAxis type="number" {...ax} /><YAxis type="category" dataKey="name" width={120} {...ax} /><Tooltip /><Bar dataKey="profit" name="Profit" fill={C.a} /></BarChart></Chart></div></div>
    <div className="card tbl" style={{ marginTop: 14 }}><h3>Model accuracy (30-day holdout)</h3><State s={m}>{r => <table><thead><tr><th>Product</th><th>Model</th><th className="n">MAE</th><th className="n">RMSE</th><th className="n">MAPE %</th></tr></thead>
      <tbody>{r.map(x => <tr key={x.product}><td>{x.product}</td><td>{x.model}</td><td className="n">{x.mae}</td><td className="n">{x.rmse}</td><td className="n">{x.mape}</td></tr>)}</tbody></table>}</State></div></>}</State>;
}

function Products({ products, reload, role }) {
  const [f, setF] = useState({ sku: "", name: "", category: "General", cost: "", price: "", stock: 0 }), [msg, setMsg] = useState(""), canEdit = role !== "analyst";
  const add = async e => { e.preventDefault(); try { await api("/products", { method: "POST", body: { ...f, cost: +f.cost, price: +f.price, stock: +f.stock } }); setMsg("Product added"); reload(); } catch (x) { setMsg(x.message); } };
  const upload = async e => { const fd = new FormData(); fd.append("file", e.target.files[0]); try { const r = await api("/sales/upload", { method: "POST", form: fd }); setMsg(`Imported ${r.imported} rows, rejected ${r.rejected}`); } catch (x) { setMsg(x.message); } };
  return <><div className="head"><h2>Product catalog</h2>{canEdit && <label className="btn ghost" style={{ cursor: "pointer", padding: "8px 14px", border: "1px solid var(--line)", borderRadius: 6 }}>Upload sales CSV<input type="file" accept=".csv" hidden onChange={upload} /></label>}</div>
    {msg && <p role="status">{msg}</p>}
    <div className="card tbl"><table><thead><tr><th>SKU</th><th>Name</th><th>Category</th><th className="n">Cost</th><th className="n">Price</th><th className="n">Margin</th><th className="n">Stock</th></tr></thead>
      <tbody>{products.map(p => <tr key={p.id}><td>{p.sku}</td><td>{p.name}</td><td>{p.category}</td><td className="n">{money(p.cost)}</td><td className="n">{money(p.price)}</td><td className="n">{p.margin_pct}%</td><td className="n">{p.stock}</td></tr>)}</tbody></table></div>
    {canEdit && <form className="card row" style={{ marginTop: 14 }} onSubmit={add}>{["sku", "name", "category", "cost", "price", "stock"].map(k => <input key={k} placeholder={k} value={f[k]} required={k !== "category" && k !== "stock"} type={["cost", "price", "stock"].includes(k) ? "number" : "text"} step="0.01" onChange={e => setF({ ...f, [k]: e.target.value })} />)}<button className="btn">Add product</button></form>}</>;
}

function Forecast({ products }) {
  const [pid, setPid] = useState(products[0].id), [h, setH] = useState("30d");
  const s = useLoad(() => api(`/demand/${pid}?horizon=${h}`), [pid, h]);
  const pf = useLoad(() => api(`/prediction/${pid}/price-forecast?days=30`), [pid]);
  return <><div className="head"><h2>Demand forecast</h2><div className="row"><ProductPicker products={products} value={pid} onChange={setPid} />
    <select aria-label="Horizon" value={h} onChange={e => setH(e.target.value)}>{["7d", "14d", "30d", "3m", "6m", "12m"].map(x => <option key={x}>{x}</option>)}</select></div></div>
    <State s={s}>{d => <><div className="grid g4"><div className="card stat"><small>Predicted units ({h})</small><div className="v">{d.predicted_units.toLocaleString()}</div></div>
      <div className="card stat"><small>Trend</small><div><span className={`tag ${d.trend.split(" ")[0]}`}>{d.trend}</span> <Pct v={d.trend_change_pct} /></div></div>
      <div className="card stat"><small>Confidence</small><div className="v">{d.confidence}%</div></div>
      <div className="card stat"><small>MAE / RMSE</small><div className="v">{d.metrics.mae} / {d.metrics.rmse}</div></div></div>
      <div className="card" style={{ marginTop: 14 }}><h3>Daily units: last 60 days and forecast</h3><Chart><LineChart data={[...d.history.map(x => ({ date: x.date, actual: x.units })), ...d.forecast.map(x => ({ date: x.date, forecast: x.units }))]}><CartesianGrid stroke="#8884" /><XAxis dataKey="date" {...ax} minTickGap={40} /><YAxis {...ax} /><Tooltip /><Legend />
        <Line dataKey="actual" stroke={C.a} dot={false} name="Actual" /><Line dataKey="forecast" stroke={C.b} dot={false} name="Forecast" /></LineChart></Chart></div>
      <div className="grid g2" style={{ marginTop: 14 }}><div className="card"><h3>Seasonality by month</h3><Chart h={220}><BarChart data={d.seasonal_monthly}><XAxis dataKey="month" {...ax} /><YAxis {...ax} /><Tooltip /><Bar dataKey="avg_units" fill={C.a} name="Avg units/day" /></BarChart></Chart></div>
        <div className="card"><h3>Price trend (next 30 days)</h3><State s={pf}>{p => <><p className="muted">Trend: {p.trend} ({p.monthly_change >= 0 ? "+" : ""}{p.monthly_change}/month)</p><Chart h={190}><LineChart data={[...p.history.map(x => ({ date: x.date, actual: x.price })), ...p.forecast.map(x => ({ date: x.date, forecast: x.price }))]}><XAxis dataKey="date" {...ax} minTickGap={50} /><YAxis domain={["auto", "auto"]} {...ax} /><Tooltip /><Line dataKey="actual" stroke={C.a} dot={false} /><Line dataKey="forecast" stroke={C.b} dot={false} /></LineChart></Chart></>}</State></div></div></>}</State></>;
}

function Optimizer({ products, role, reload }) {
  const [pid, setPid] = useState(products[0].id), [obj, setObj] = useState("profit"), [tick, setTick] = useState(0), [msg, setMsg] = useState("");
  const s = useLoad(() => api(`/prediction/${pid}/optimal-price?objective=${obj}`), [pid, obj, tick]);
  const apply = async price => { try { await api(`/products/${pid}/price`, { method: "POST", body: { price } }); setMsg("Price updated"); reload(); setTick(t => t + 1); } catch (x) { setMsg(x.message); } };
  return <><div className="head"><h2>Price optimizer</h2><div className="row"><ProductPicker products={products} value={pid} onChange={setPid} />
    <select aria-label="Objective" value={obj} onChange={e => setObj(e.target.value)}><option value="profit">Maximise profit</option><option value="revenue">Maximise revenue</option></select></div></div>
    <State s={s}>{d => <><div className="grid g2"><div className="rec"><small>Recommended price</small><div className="v">{money(d.recommended.price)}</div>
      <div>{d.price_change_pct >= 0 ? "+" : ""}{d.price_change_pct}% vs {money(d.current.price)}. Projected {obj} {d.uplift_pct >= 0 ? "+" : ""}{d.uplift_pct}% over 30 days.</div>
      {role !== "analyst" && <button className="btn ghost" style={{ marginTop: 12, background: "var(--card)" }} onClick={() => apply(d.recommended.price)}>Apply this price</button>}</div>
      <div className="card"><h3>Price sensitivity</h3><p>Elasticity <b>{d.elasticity}</b>: a 10% price rise changes volume by about {(d.elasticity * 10).toFixed(1)}%.</p><p className="muted">Minimum margin of 10% over cost is enforced.</p>{msg && <p role="status">{msg}</p>}</div></div>
      <div className="card" style={{ marginTop: 14 }}><h3>Projected 30-day outcome by price</h3><Chart h={300}><ComposedChart data={d.curve}><CartesianGrid stroke="#8884" /><XAxis dataKey="price" {...ax} /><YAxis {...ax} /><Tooltip /><Legend />
        <Line dataKey="revenue" stroke={C.c} dot={false} name="Revenue" /><Line dataKey="profit" stroke={C.a} dot={false} strokeWidth={2.5} name="Profit" />
        <ReferenceDot x={d.recommended.price} y={d.recommended[obj]} r={7} fill={C.b} stroke="none" /></ComposedChart></Chart></div></>}</State></>;
}

function Competitors({ products }) {
  const s = useLoad(() => api("/competitors"), []);
  return <><div className="head"><h2>Competitor analysis</h2></div><State s={s}>{rows => <div className="card tbl"><table><thead><tr><th>Product</th><th className="n">Our price</th><th className="n">Competitor avg</th><th className="n">Range</th><th className="n">Gap</th><th>Signal</th></tr></thead>
    <tbody>{rows.map(r => <tr key={r.product_id}><td>{r.name}</td><td className="n">{money(r.price)}</td><td className="n">{money(r.avg_competitor)}</td><td className="n">{money(r.min_competitor)} to {money(r.max_competitor)}</td><td className="n"><Pct v={r.gap_pct} /></td><td>{r.signal}</td></tr>)}</tbody></table></div>}</State></>;
}

function Revenue({ products }) {
  const [pid, setPid] = useState(products[0].id);
  const sim = useLoad(() => api(`/revenue/${pid}/simulate`, { method: "POST", body: {} }), [pid]);
  const st = useLoad(() => api(`/revenue/${pid}/strategy`), [pid]);
  return <><div className="head"><h2>Revenue simulator and strategy</h2><ProductPicker products={products} value={pid} onChange={setPid} /></div>
    <State s={st}>{d => <div className="card"><h3>Recommended strategy</h3><ul className="tips">{d.recommendations.map((t, i) => <li key={i}>{t}</li>)}</ul></div>}</State>
    <State s={sim}>{d => <><div className="card" style={{ marginTop: 14 }}><h3>What-if price changes (30 days)</h3><Chart><BarChart data={d.scenarios}><CartesianGrid stroke="#8884" /><XAxis dataKey="change_pct" tickFormatter={v => v + "%"} {...ax} /><YAxis {...ax} /><Tooltip /><Legend /><Bar dataKey="revenue" fill={C.c} name="Revenue" /><Bar dataKey="profit" fill={C.a} name="Profit" /></BarChart></Chart></div>
      <div className="card tbl" style={{ marginTop: 14 }}><table><thead><tr><th>Change</th><th className="n">Price</th><th className="n">Units</th><th className="n">Revenue</th><th className="n">Profit</th><th className="n">Margin</th></tr></thead>
        <tbody>{d.scenarios.map(r => <tr key={r.change_pct}><td>{r.change_pct}%</td><td className="n">{money(r.price)}</td><td className="n">{r.units}</td><td className="n">{money(r.revenue)}</td><td className="n">{money(r.profit)}</td><td className="n">{r.margin_pct}%</td></tr>)}</tbody></table></div></>}</State></>;
}

const PAGES = { Dashboard, Products, Forecast, Optimizer, Competitors, Revenue };
export default function App() {
  const [user, setUser] = useState(() => auth.token ? JSON.parse(localStorage.getItem("pp_user") || "null") : null);
  const [page, setPage] = useState("Dashboard"), [products, setProducts] = useState([]), [n, setN] = useState(0);
  useEffect(() => { if (user) api("/products").then(setProducts).catch(() => {}); }, [user, n]);
  if (!user) return <Login onDone={setUser} />;
  const Page = PAGES[page];
  return <div className="shell"><nav><div className="brand">Price<b>Pilot</b></div>
    {Object.keys(PAGES).map(k => <button key={k} className={page === k ? "on" : ""} onClick={() => setPage(k)}>{k}</button>)}
    <div className="who">{user.name}<br />{user.role.replace("_", " ")}<br /><button style={{ color: "var(--accent)" }} onClick={() => { auth.clear(); setUser(null); }}>Sign out</button></div></nav>
    <main>{products.length ? <Page products={products} role={user.role} reload={() => setN(x => x + 1)} /> : <p className="muted">Loading catalog…</p>}</main></div>;
}

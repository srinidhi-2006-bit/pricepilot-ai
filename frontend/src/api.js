const BASE = import.meta.env.VITE_API_URL || "/api";
export const auth = { get token() { return localStorage.getItem("pp_token"); }, set(t) { localStorage.setItem("pp_token", t); }, clear() { localStorage.removeItem("pp_token"); localStorage.removeItem("pp_user"); } };
export async function api(path, { method = "GET", body, form } = {}) {
  const headers = {}; if (auth.token) headers.Authorization = `Bearer ${auth.token}`;
  let payload; if (form) payload = form; else if (body) { headers["Content-Type"] = "application/json"; payload = JSON.stringify(body); }
  const r = await fetch(BASE + path, { method, headers, body: payload });
  if (r.status === 401 && auth.token) { auth.clear(); location.reload(); }
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail || "Request failed"));
  return data;
}
export const login = async (email, password) => {
  const f = new URLSearchParams({ username: email, password });
  const r = await fetch(BASE + "/auth/login", { method: "POST", body: f });
  const d = await r.json(); if (!r.ok) throw new Error(d.detail || "Login failed"); return d;
};

// Thin API client. Same-origin (/api) by default; override with window.UK_ETDI_API_BASE for static hosting.
const BASE = (window.UK_ETDI_API_BASE || "") + "/api";

async function request(path, opts = {}) {
  const res = await fetch(BASE + path, { headers: { "Content-Type": "application/json", ...(opts.headers || {}) }, ...opts });
  let body = null;
  try { body = await res.json(); } catch { /* empty */ }
  if (!res.ok || !body || body.success === false) {
    const err = (body && body.error) || { code: "HTTP_" + res.status, message: res.statusText };
    throw Object.assign(new Error(err.message), { code: err.code, status: res.status });
  }
  return body;
}

export const qs = (o) => {
  const p = new URLSearchParams();
  Object.entries(o || {}).forEach(([k, v]) => { if (v !== undefined && v !== null && v !== "") p.set(k, v); });
  const s = p.toString();
  return s ? "?" + s : "";
};

export const api = {
  summary: () => request("/dashboard/summary"),
  trends: (days = 30) => request(`/dashboard/trends${qs({ days })}`),
  map: (days = 7, min_score = 0) => request(`/dashboard/map${qs({ days, min_score })}`),
  calendar: (start, end) => request(`/dashboard/calendar${qs({ start, end })}`),
  events: (params) => request(`/events${qs(params)}`),
  event: (id) => request(`/events/${id}`),
  changes: (params) => request(`/changes${qs(params)}`),
  opportunities: (params) => request(`/opportunities${qs(params)}`),
  actions: (params) => request(`/actions${qs(params)}`),
  actionComplete: (id) => request(`/actions/${id}/complete`, { method: "POST" }),
  actionDismiss: (id) => request(`/actions/${id}/dismiss`, { method: "POST" }),
  actionStart: (id) => request(`/actions/${id}/start`, { method: "POST" }),
  actionPlan: (id) => request(`/actions/${id}/plan`, { method: "POST" }),
  bookingsStatus: () => request(`/bookings/status`),
  healthDetailed: () => request(`/health/detailed`),
  actionSchedule: (id, when) => request(`/actions/${id}/schedule`, { method: "POST", body: JSON.stringify({ scheduled_for: when }) }),
  sources: () => request("/sources"),
  sourceHealth: (id) => request(`/sources/${id}/health`),
  toggleSource: (id) => request(`/sources/${id}/toggle`, { method: "POST" }),
  venues: (params) => request(`/venues${qs(params)}`),
  cities: () => request("/cities"),
  regions: () => request("/regions"),
  categories: () => request("/categories"),
  health: () => request("/health/detailed"),
  settings: () => request("/settings"),
  putSetting: (key, value) => request(`/settings/${key}`, { method: "PUT", body: JSON.stringify({ value }) }),
  runPipeline: () => request("/pipeline/run", { method: "POST" }),
  runs: () => request("/pipeline/runs"),
  report: () => request("/reports/daily"),
  coverage: () => request("/coverage"),
  dataQuality: () => request("/data-quality"),
  sourceEvents: (id, params) => request(`/sources/${id}/events${qs(params)}`),
  snapshots: (id) => request(`/events/${id}/snapshots`),
};

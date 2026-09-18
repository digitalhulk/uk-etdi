// Small presentational helpers (no framework — zero build step, zero cost).
export const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
export const lvl = (l) => (l || "LOW");
// Only http(s) URLs are ever rendered as links (defends against javascript:/data: URLs from scraped payloads).
export const safeUrl = (u) => { try { const x = new URL(String(u || ""), location.origin); return ["http:", "https:"].includes(x.protocol) ? x.href : null; } catch { return null; } };
export const link = (u, label = "open ↗") => { const h = safeUrl(u); return h ? `<a href="${esc(h)}" target="_blank" rel="noopener noreferrer">${esc(label)}</a>` : "—"; };
export const badge = (l, txt) => `<span class="badge ${esc(l)}">${esc(txt ?? String(l || "").replace("_", " "))}</span>`;
export const score = (s, l) => `<span class="score ${esc(lvl(l))}">${s ?? 0}</span>`;
export const fmtDate = (iso) => iso ? new Date(iso + (iso.length === 10 ? "T00:00:00" : "")).toLocaleDateString("en-GB", { weekday: "short", day: "2-digit", month: "short" }) : "—";
export const fmtDT = (iso) => iso ? new Date(iso.endsWith("Z") ? iso : iso + "Z").toLocaleString("en-GB", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }) : "—";
export const kpi = (label, value, cls = "") => `<div class="kpi ${cls}"><div class="label">${esc(label)}</div><div class="value">${esc(value)}</div></div>`;

export function eventRow(e) {
  return `<tr class="clickable" data-href="#/events/${e.id}">
    <td><b>${esc(e.title)}</b><div class="muted small">${esc(e.venue?.name || "")}${e.venue?.capacity ? ` · cap ${e.venue.capacity.toLocaleString()}` : ""}</div></td>
    <td>${esc(e.city || "—")}</td>
    <td>${fmtDate(e.date_start)}<div class="muted small">${esc(e.time_start || "TBC")}</div></td>
    <td><span class="badge cat">${esc(e.category)}</span>${e.quality_level ? ` <span class="badge ${esc(e.quality_level)}" title="event quality (modelled)">${esc(e.quality_level[0])}</span>` : ""}</td>
    <td>${score(e.opportunity_score, e.demand_level)}</td>
    <td>${badge(e.demand_level)}</td>
    <td>${e.marketing_priority ? badge(e.marketing_priority) : "—"}</td>
    <td>${badge(e.status)}</td>
  </tr>`;
}

export const eventTable = (events) => events.length ? `<table><thead><tr><th>Event</th><th>City</th><th>Date</th><th>Category</th><th>Score</th><th>Demand</th><th>Mkt</th><th>Status</th></tr></thead>
  <tbody>${events.map(eventRow).join("")}</tbody></table>` : `<div class="muted">No events match.</div>`;

export function bars(items, keyField, max) {
  const m = max || Math.max(1, ...items.map((i) => i.count));
  return `<div class="bars">${items.map((i) => `<div class="bar"><span title="${esc(i[keyField])}">${esc(i[keyField] ?? "—")}</span><div class="track"><div class="fill" style="width:${(100 * i.count) / m}%"></div></div><span class="mono">${i.count}</span></div>`).join("")}</div>`;
}

// Minimal inline SVG line/bar chart
export function svgBars(items, xKey, yKey, opts = {}) {
  const w = 600, h = 200, pad = 28;
  if (!items.length) return `<div class="muted">No data</div>`;
  const max = Math.max(1, ...items.map((i) => i[yKey]));
  const bw = Math.max(2, (w - pad * 2) / items.length - 2);
  const bars = items.map((it, idx) => {
    const x = pad + idx * ((w - pad * 2) / items.length);
    const bh = ((h - pad * 2) * it[yKey]) / max;
    const y = h - pad - bh;
    const color = opts.color ? opts.color(it) : "var(--accent)";
    return `<rect x="${x}" y="${y}" width="${bw}" height="${bh}" fill="${color}" rx="2"><title>${esc(it[xKey])}: ${it[yKey]}</title></rect>`;
  }).join("");
  const labels = items.filter((_, i) => i % Math.ceil(items.length / 8) === 0).map((it) => {
    const idx = items.indexOf(it); const x = pad + idx * ((w - pad * 2) / items.length);
    return `<text x="${x}" y="${h - 8}">${esc(String(it[xKey]).slice(5))}</text>`;
  }).join("");
  return `<svg class="chart" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">${bars}${labels}<text x="4" y="14">${max}</text></svg>`;
}

export function toast(msg, ms = 2500) {
  const t = document.getElementById("toast");
  t.textContent = msg; t.classList.add("show");
  setTimeout(() => t.classList.remove("show"), ms);
}

export function pager(meta, onPage) {
  const pages = Math.max(1, Math.ceil(meta.total / meta.page_size));
  const el = document.createElement("div"); el.className = "pager";
  el.innerHTML = `<span class="muted small">${meta.total} results · page ${meta.page}/${pages}</span>
    <button class="btn btn-sm" ${meta.page <= 1 ? "disabled" : ""} data-p="${meta.page - 1}">‹ Prev</button>
    <button class="btn btn-sm" ${meta.page >= pages ? "disabled" : ""} data-p="${meta.page + 1}">Next ›</button>`;
  el.querySelectorAll("button").forEach((b) => b.onclick = () => onPage(Number(b.dataset.p)));
  return el;
}

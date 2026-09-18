import { api } from "../lib/api.js";
import { badge, bars, esc, eventRow, eventTable, fmtDT, fmtDate, kpi, pager, score, svgBars, svgBars as _sb, toast, link, safeUrl } from "../components/ui.js";

// ---------------------------------------------------------------- HOME
export async function Home(view) {
  const [{ data: s }, { data: acts }] = await Promise.all([api.summary(), api.actions({ days: 7, page_size: 8 })]);
  view.innerHTML = `
    <h1>Today's Command Center</h1>
    <p class="sub">${fmtDate(s.date)} · Last pipeline run: ${s.last_pipeline_run ? `${badge(s.last_pipeline_run.status)} ${fmtDT(s.last_pipeline_run.completed_at)} (${s.last_pipeline_run.duration_seconds}s)` : "never"}
      · Next scheduled run: ${s.next_scheduled_run ? fmtDT(s.next_scheduled_run) : "—"} (daily cron)
      · Data freshness: ${s.data_freshness ? `${badge(s.data_freshness.label === "FRESH" ? "HEALTHY" : "DEGRADED", s.data_freshness.label)} ${s.data_freshness.hours_since_last_success ?? "?"}h since last success · avg freshness ${s.data_freshness.avg_freshness_score ?? "—"}` : "—"}</p>
    <div class="kpis">
      ${kpi("Events Today", s.events_today)}${kpi("Events Tomorrow", s.events_tomorrow)}${kpi("Next 7 Days", s.events_next_7_days)}${kpi("Next 30 Days", s.events_next_30_days)}
      ${kpi("High Opportunities", s.high, "h")}${kpi("Very High", s.very_high, "vh")}${kpi("New Events (24h)", s.new_events, "new")}
      ${kpi("Updated (24h)", s.changed_events, "chg")}${kpi("Cancelled (24h)", s.cancelled_events, s.cancelled_events ? "bad" : "")}${kpi("Sources Healthy", `${s.sources_healthy}/${s.sources_total}`, s.sources_healthy < s.sources_total ? "h" : "new")}
    </div>
    <div class="grid2">
      <div class="panel"><h3>🔥 Top opportunities · next 7 days</h3>${eventTable(s.top_opportunities)}<div style="margin-top:10px"><a href="#/opportunities">Open Opportunity Center →</a></div></div>
      <div class="panel"><h3>🎯 What to do today (${s.open_actions} open actions)</h3>
        ${acts.length ? `<table><tbody>${acts.map((a) => `<tr class="clickable" data-href="#/events/${a.event_id}"><td>${badge(a.priority)}</td><td><b>${esc(a.title)}</b><div class="muted small">${esc(a.event.title)} · ${fmtDate(a.event.date_start)} · ${esc(a.event.city || "")}</div></td><td class="muted small">${esc(a.suggested_channel || "")}</td></tr>`).join("")}</tbody></table>` : `<div class="muted">No open actions in the next 7 days.</div>`}
        <div style="margin-top:10px"><a href="#/actions">Open Marketing Action Center →</a></div></div>
    </div>`;
}

// ---------------------------------------------------------------- MAP
function renderOfflineMap(points, note) {
  // Equirectangular plot of Great Britain + NI bounds (lat 49.9–58.7, lon -8.2–1.8). No external tiles required.
  const W = 640, H = 760, la0 = 49.9, la1 = 58.7, lo0 = -8.2, lo1 = 1.8;
  const x = (lon) => ((lon - lo0) / (lo1 - lo0)) * W, y = (lat) => H - ((lat - la0) / (la1 - la0)) * H;
  const colors = { VERY_HIGH: "#ff3b5c", HIGH: "#ff7a45", MEDIUM: "#f5b400", MODERATE: "#3fa7ff", LOW: "#5b6b8a" };
  const cities = [["London", 51.507, -0.128], ["Manchester", 53.483, -2.244], ["Birmingham", 52.486, -1.890], ["Leeds", 53.800, -1.549], ["Glasgow", 55.864, -4.252], ["Edinburgh", 55.953, -3.188], ["Cardiff", 51.481, -3.179], ["Belfast", 54.597, -5.930], ["Newcastle", 54.978, -1.617], ["Bristol", 51.454, -2.588]];
  const dots = (points || []).filter((e) => e.lat && e.lon).map((e) => `<a href="#/events/${e.id}"><circle cx="${x(e.lon).toFixed(1)}" cy="${y(e.lat).toFixed(1)}" r="${(3 + e.score / 20).toFixed(1)}" fill="${colors[e.demand_level] || colors.LOW}" fill-opacity="0.8"><title>${esc(e.title)} — ${esc(e.city || "")} ${fmtDate(e.date)} · score ${e.score}</title></circle></a>`).join("");
  const labels = cities.map(([n, la, lo]) => `<text x="${x(lo) + 6}" y="${y(la) + 4}" fill="#8fa3c7" font-size="11">${n}</text><circle cx="${x(lo)}" cy="${y(la)}" r="2" fill="#8fa3c7"/>`).join("");
  document.getElementById("map").innerHTML = `<div class="muted small" style="padding:6px 0">${esc(note)} Coordinates from <a href="/api/dashboard/map">/api/dashboard/map</a>.</div>
    <svg viewBox="0 0 ${W} ${H}" style="width:100%;max-height:70vh;background:#0f1729;border-radius:12px">${labels}${dots}</svg>`;
  document.getElementById("map-count").textContent = `${(points || []).length} events plotted (offline mode)`;
}
export async function MapPage(view) {
  view.innerHTML = `<h1>UK Event Map</h1><p class="sub">Marker colour = modelled demand level. Click a marker for details.</p>
    <div class="filters"><div class="seg" id="map-days">${[1, 3, 7, 14, 30].map((d) => `<button data-d="${d}" class="${d === 7 ? "active" : ""}">${d}d</button>`).join("")}</div>
    <select id="map-min"><option value="0">All scores</option><option value="50">Score ≥ 50</option><option value="65">Score ≥ 65</option><option value="80">Score ≥ 80</option></select>
    <span class="muted small" id="map-count"></span></div>
    <div class="legend"><span class="VERY_HIGH">Very high</span><span class="HIGH">High</span><span class="MEDIUM">Medium</span><span class="MODERATE">Moderate</span><span class="LOW">Low</span></div>
    <div id="map"></div>`;
  // Map provider abstraction: tile config comes from the backend (/api/dashboard/map meta.tiles). Offline fallback below.
  const first = await api.map(7, 0);
  const tiles = (first.meta && first.meta.tiles) || { url: "https://tile.openstreetmap.org/{z}/{x}/{y}.png", attribution: "© OpenStreetMap contributors", offline: false };
  if (!window.L || tiles.offline) { renderOfflineMap(first.data, tiles.offline ? "Offline map provider selected — markers plotted on UK outline." : "Map library unavailable — markers plotted on UK outline."); return; }
  const map = L.map("map").setView([53.5, -2.3], 6);
  L.tileLayer(tiles.url, { attribution: tiles.attribution, maxZoom: tiles.max_zoom || 18, className: "osm-dark" }).addTo(map);
  const layer = L.layerGroup().addTo(map);
  const colors = { VERY_HIGH: "#ff3b5c", HIGH: "#ff7a45", MEDIUM: "#f5b400", MODERATE: "#3fa7ff", LOW: "#5b6b8a" };
  let days = 7;
  async function load() {
    const min = Number(document.getElementById("map-min").value);
    const { data } = await api.map(days, min);
    layer.clearLayers();
    document.getElementById("map-count").textContent = `${data.length} events plotted`;
    data.slice().reverse().forEach((e) => {
      const jitter = () => (Math.random() - 0.5) * 0.004;
      L.circleMarker([e.lat + jitter(), e.lon + jitter()], { radius: 5 + e.score / 12, color: colors[e.demand_level] || colors.LOW, fillOpacity: 0.75, weight: 1 })
        .bindPopup(`<b>${esc(e.title)}</b><br>${esc(e.venue || "")}, ${esc(e.city || "")}<br>${fmtDate(e.date)} ${esc(e.time || "TBC")}<br>Score <b>${e.score}</b> · ${badge(e.demand_level)}<br>Marketing: ${e.marketing_priority || "—"}<br><a href="#/events/${e.id}">Open event →</a>`)
        .addTo(layer);
    });
  }
  document.querySelectorAll("#map-days button").forEach((b) => b.onclick = () => { document.querySelectorAll("#map-days button").forEach((x) => x.classList.remove("active")); b.classList.add("active"); days = Number(b.dataset.d); load(); });
  document.getElementById("map-min").onchange = load;
  await load();
}

// ---------------------------------------------------------------- EVENTS
export async function Events(view) {
  const [{ data: cities }, { data: cats }, { data: sources }] = await Promise.all([api.cities(), api.categories(), api.sources()]);
  const preset = Object.fromEntries(new URLSearchParams(location.hash.split("?")[1] || ""));
  const state = { range: preset.range ?? (Object.keys(preset).length ? "" : "7d"), sort: "score", page: 1, page_size: 50, missing: preset.missing || "" };
  const catNames = [...new Set(cats.map((c) => c.category))];
  view.innerHTML = `<h1>Event Feed</h1><p class="sub">Every event in the database, filterable and sortable. Numbers are live.</p>
    <div class="filters">
      <div class="seg" id="rng">${[["today", "Today"], ["tomorrow", "Tomorrow"], ["7d", "7 days"], ["30d", "30 days"], ["", "All upcoming"]].map(([v, l]) => `<button data-v="${v}" class="${v === "7d" ? "active" : ""}">${l}</button>`).join("")}</div>
      <input id="q" placeholder="Search event, venue, city…" style="min-width:220px">
      <select id="category"><option value="">All categories</option>${catNames.map((c) => `<option>${esc(c)}</option>`).join("")}</select>
      <select id="city"><option value="">All cities</option>${cities.filter((c) => c.upcoming_events).map((c) => `<option>${esc(c.name)}</option>`).join("")}</select>
      <select id="demand"><option value="">All demand</option><option>VERY_HIGH</option><option>HIGH</option><option>MEDIUM</option><option>MODERATE</option><option>LOW</option></select>
      <select id="status"><option value="">All statuses</option><option>SCHEDULED</option><option>CONFIRMED</option><option>SOLD_OUT</option><option>CANCELLED</option><option>POSTPONED</option><option>RESCHEDULED</option></select>
      <select id="quality"><option value="">All quality</option><option>HIGH</option><option>MEDIUM</option><option>LOW</option></select>
      <select id="confidence"><option value="">All confidence</option><option>OFFICIAL</option><option>TRUSTED</option><option>SECONDARY</option><option>UNVERIFIED</option></select>
      <select id="source"><option value="">All sources</option>${sources.map((s) => `<option value="${esc(s.key)}">${esc(s.name)}</option>`).join("")}</select>
      <select id="sort"><option value="score">Score ↓</option><option value="date">Date ↑</option><option value="updated">Recently updated</option><option value="quality">Quality ↓</option></select>
    </div><div id="list" class="panel"><div class="loading">Loading…</div></div>`;
  const list = document.getElementById("list");
  async function load() {
    const params = { ...state, q: q.value, category: category.value, city: city.value, demand: demand.value, status: status.value, source: source.value, sort: sort.value, quality: quality.value, confidence: confidence.value };
    if (!params.missing) delete params.missing;
    if (!params.range) delete params.range;
    const { data, meta } = await api.events(params);
    list.innerHTML = eventTable(data);
    list.appendChild(pager(meta, (p) => { state.page = p; load(); }));
  }
  for (const k of ["category", "city", "demand", "status", "source", "quality", "confidence"]) if (preset[k]) document.getElementById(k).value = preset[k];
  if (!state.range) document.querySelectorAll("#rng button").forEach((x) => x.classList.toggle("active", x.dataset.v === ""));
  ["category", "city", "demand", "status", "source", "sort", "quality", "confidence"].forEach((id) => document.getElementById(id).onchange = () => { state.page = 1; load(); });
  let t; document.getElementById("q").oninput = () => { clearTimeout(t); t = setTimeout(() => { state.page = 1; load(); }, 300); };
  document.querySelectorAll("#rng button").forEach((b) => b.onclick = () => { document.querySelectorAll("#rng button").forEach((x) => x.classList.remove("active")); b.classList.add("active"); state.range = b.dataset.v; state.page = 1; load(); });
  await load();
}

// ---------------------------------------------------------------- EVENT DETAIL
export async function EventDetail(view, id) {
  const { data: e } = await api.event(id);
  const b = e.score_breakdown || {}; const w = e.demand_windows || {};
  const comp = Object.entries(b.components || {}).map(([k, v]) => ({ k, v, max: (b.weights || {})[k] || 1 }));
  view.innerHTML = `<a class="back" href="#/events">← Back to feed</a>
    <h1>${esc(e.title)}</h1>
    <p class="sub"><span class="badge cat">${esc(e.category)}${e.subcategory ? " / " + esc(e.subcategory) : ""}</span> ${badge(e.status)} ${e.marketing_priority ? badge(e.marketing_priority) : ""} · source: ${esc(e.primary_source)} · ${badge(e.source_confidence || "UNVERIFIED")} · quality ${badge(e.quality_level || "LOW", `${e.quality_level || "LOW"} ${e.event_quality_score ?? ""}`)}${e.status_reason ? ` · <span class="muted small">${esc(e.status_reason)}</span>` : ""}</p>
    <div class="grid3">
      <div class="panel" style="border-left:4px solid #2a9d8f"><h3>FACTS <span class="muted small">(sourced)</span></h3><dl class="kv"><dt>Sources</dt><dd>${(e.facts?.sources || []).map((x) => `<span class="mono">${esc(x.source)}</span>`).join(", ") || "—"}</dd><dt>Confidence</dt><dd>${esc(e.facts?.source_confidence || "UNVERIFIED")}</dd><dt>Last verified</dt><dd>${fmtDT(e.facts?.last_verified_at)}</dd><dt>Freshness</dt><dd class="mono">${e.freshness_score ?? "—"}/100</dd><dt>Capacity</dt><dd>${e.facts?.venue_capacity ? `${e.facts.venue_capacity.toLocaleString()} <span class="muted small">(${esc(e.facts.venue_capacity_source || "registry")})</span>` : "not published"}</dd></dl></div>
      <div class="panel" style="border-left:4px solid #e9c46a"><h3>MODELLED <span class="muted small">(estimates)</span></h3><dl class="kv"><dt>Opportunity</dt><dd>${score(e.opportunity_score, e.demand_level)} ${badge(e.demand_level)}</dd><dt>Attendance</dt><dd>${e.attendance_estimate ? `≈ ${e.attendance_estimate.toLocaleString()} (${esc(e.attendance_confidence)})` : "unknown"}</dd><dt>Quality</dt><dd>${e.event_quality_score ?? "—"}/100</dd></dl><ul class="reasons small">${(e.quality_reasons || []).map((r) => `<li>${esc(r)}</li>`).join("")}</ul></div>
      <div class="panel" style="border-left:4px solid #e76f51"><h3>RECOMMENDATION</h3><div class="small">${e.recommendations?.marketing_actions?.length ? `${e.recommendations.marketing_actions.length} marketing actions · ${e.recommendations.opportunities.length} taxi opportunities (below)` : `<span class="muted">No automatic recommendations: gate closed (score, quality, status, service area or horizon). See reasons above.</span>`}</div></div>
    </div>
    <div class="grid3" style="margin-top:16px">
      <div class="panel"><h3>When</h3><dl class="kv"><dt>Date</dt><dd>${fmtDate(e.date_start)}${e.date_end && e.date_end !== e.date_start ? " → " + fmtDate(e.date_end) : ""}</dd><dt>Start</dt><dd>${esc(e.time_start || "TBC")}</dd><dt>End</dt><dd>${esc(e.time_end || "not published")}</dd><dt>Timezone</dt><dd>${esc(e.timezone)}</dd></dl></div>
      <div class="panel"><h3>Where</h3><dl class="kv"><dt>Venue</dt><dd>${esc(e.venue?.name || "—")}</dd><dt>City</dt><dd>${esc(e.city || "—")}${e.region ? ` (${esc(e.region)})` : ""}</dd><dt>Postcode</dt><dd>${esc(e.postcode || "—")}</dd><dt>Capacity</dt><dd>${e.venue_capacity ? e.venue_capacity.toLocaleString() + ` <span class="muted small">(${esc(e.venue_detail?.capacity_source || "source")})</span>` : "not published"}</dd><dt>Transport</dt><dd>${e.venue_detail?.station_distance_km != null ? `station ${e.venue_detail.station_distance_km} km · airport ${e.venue_detail.airport_distance_km} km` : "unknown"}</dd></dl></div>
      <div class="panel"><h3>Links</h3><dl class="kv"><dt>Official</dt><dd>${link(e.official_url)}</dd><dt>Tickets</dt><dd>${link(e.ticket_url)}</dd><dt>Organizer</dt><dd>${esc(e.organizer || "—")}</dd><dt>Attendance</dt><dd>${e.attendance_estimate ? `≈ ${e.attendance_estimate.toLocaleString()} <span class="flag">modelled · ${esc(e.attendance_confidence)} confidence</span>` : "unknown"}</dd></dl></div>
    </div>
    <div class="grid2" style="margin-top:16px">
      <div class="panel"><h3>Opportunity score</h3><div class="row" style="display:flex;align-items:baseline;gap:14px"><span class="score ${esc(e.demand_level)}" style="font-size:48px">${e.opportunity_score}</span>${badge(e.demand_level)}</div>
        <h3 style="margin-top:12px">Why this score?</h3><ul class="reasons">${(b.reasons || []).map((r) => `<li>${esc(r)}</li>`).join("")}</ul>
        <h3 style="margin-top:12px">Components (weights from scoring.yaml)</h3><div class="bars">${comp.map((c) => `<div class="bar"><span>${esc(c.k)}</span><div class="track"><div class="fill" style="width:${(100 * c.v) / c.max}%"></div></div><span class="mono">${c.v}/${c.max}</span></div>`).join("")}</div>
        <div class="muted small" style="margin-top:8px">${esc(b.note || "")}</div></div>
      <div class="panel"><h3>${esc(w.label || "Modelled demand window")}</h3>
        ${w.available ? `<div class="windows"><div class="win"><small>Pre-event (arrivals)</small><b>${w.pre_event_window.start}–${w.pre_event_window.end}</b></div><div class="win"><small>Event</small><b>${w.event_window.start}–${w.event_window.end}</b></div><div class="win"><small>Post-event (departures)</small><b>${w.post_event_window.start}–${w.post_event_window.end}</b><small>peak ≈ ${w.post_event_window.peak}</small></div></div>${w.end_estimated ? `<div class="muted small" style="margin-top:8px">End time not published — estimated from typical ${esc(e.category)} duration.</div>` : ""}` : `<div class="muted">${esc(w.reason || "Start time unknown")} — windows will be generated once a start time is published.</div>`}
        <h3 style="margin-top:16px">Taxi opportunities</h3>
        ${e.opportunities.length ? `<table><thead><tr><th>Type</th><th>Window</th><th>Score</th><th>Action</th></tr></thead><tbody>${e.opportunities.map((o) => `<tr><td><b>${esc(o.opportunity_type.replaceAll("_", " "))}</b><div class="muted small">${o.reasons.map(esc).join(" · ")}</div></td><td class="mono">${esc(o.window.start || "—")}–${esc(o.window.end || "—")}</td><td>${score(o.score, o.demand_level)}<div class="muted small mono" title="score components (v2)">${o.score_components ? Object.entries(o.score_components.components || {}).map(([k, v]) => `${esc(k)} ${v}`).join(" + ") : ""}</div></td><td class="small">${esc(o.recommended_action)}</td></tr>`).join("")}</tbody></table>` : `<div class="muted">No taxi opportunities generated (score below threshold or event inactive).</div>`}
      </div>
    </div>
    <div class="panel" style="margin-top:16px"><h3>Marketing opportunities</h3>${actionsTable(e.marketing_actions, false)}</div>
    <div class="grid2" style="margin-top:16px">
      <div class="panel"><h3>Change history</h3>${e.changes.length ? `<table><tbody>${e.changes.map((c) => `<tr><td>${badge(c.change_type)}</td><td>${esc(c.field || "")}</td><td class="small">${c.old_value ? esc(c.old_value) + " → " : ""}${esc(c.new_value || "")}</td><td class="muted small">${fmtDT(c.detected_at)}</td></tr>`).join("")}</tbody></table>` : "—"}</div>
      <div class="panel"><h3>Source history</h3><table><tbody>${e.sources.map((s) => `<tr><td><b>${esc(s.source)}</b></td><td class="mono small">${esc(s.external_id)}</td><td class="muted small">first ${fmtDT(s.first_seen)}<br>last ${fmtDT(s.last_seen)}</td><td>${s.url ? link(s.url, "↗") : ""}</td></tr>`).join("")}</tbody></table>
        <dl class="kv" style="margin-top:10px"><dt>Canonical ID</dt><dd class="mono">${esc(e.canonical_event_id)}</dd><dt>First seen</dt><dd>${fmtDT(e.first_seen_at)}</dd><dt>Last seen</dt><dd>${fmtDT(e.last_seen_at)}</dd></dl>
        <h3 style="margin-top:14px">Snapshots</h3><div id="snaps" class="muted small">loading…</div></div>
    </div>`;
  bindActionButtons(view, () => EventDetail(view, id));
  try { const { data: snaps } = await api.snapshots(id); document.getElementById("snaps").innerHTML = snaps.length ? `<table><tbody>${snaps.map((x) => `<tr><td class="small">${fmtDT(x.taken_at)}</td><td>${badge(x.reason)}</td><td class="mono small">${esc(x.snapshot.status)} · ${esc(x.snapshot.date_start)} ${esc(x.snapshot.time_start || "")} · ${esc(x.snapshot.venue_name_raw || "")}</td></tr>`).join("")}</tbody></table>` : "no snapshots"; } catch { /* optional */ }
}

function actionsTable(actions, withEvent) {
  if (!actions.length) return `<div class="muted">No marketing actions (event below marketing threshold).</div>`;
  return `<table><thead><tr><th>Prio</th><th>Action</th>${withEvent ? "<th>Event</th>" : ""}<th>Channel</th><th>Keyword / audience</th><th>When</th><th>Status</th><th></th></tr></thead><tbody>
  ${actions.map((a) => `<tr><td>${badge(a.priority)}</td><td><b>${esc(a.title)}</b><div class="muted small">${esc(a.description || "")}</div></td>
    ${withEvent ? `<td><a href="#/events/${a.event_id}">${esc(a.event.title)}</a><div class="muted small">${fmtDate(a.event.date_start)} · ${esc(a.event.city || "")} · score ${a.event.score}</div></td>` : ""}
    <td>${esc(a.suggested_channel || "")}</td><td class="small">${a.suggested_keyword ? `<span class="mono">${esc(a.suggested_keyword)}</span><br>` : ""}<span class="muted">${esc(a.suggested_audience || "")}</span></td>
    <td class="small">${esc(a.recommended_time || "")}${a.scheduled_for ? `<br><span class="muted">scheduled ${fmtDT(a.scheduled_for)}</span>` : ""}</td><td>${badge(a.status)}</td>
    <td style="white-space:nowrap">${["DONE", "DISMISSED"].includes(a.status) ? "" : `<button class="btn btn-sm btn-ok" data-act="complete" data-id="${a.id}" title="Mark done">✓</button> ${a.status === "NEW" ? `<button class="btn btn-sm" data-act="plan" data-id="${a.id}" title="Plan">📝</button>` : ""} <button class="btn btn-sm" data-act="schedule" data-id="${a.id}" title="Schedule">📅</button> ${["NEW", "PLANNED", "SCHEDULED"].includes(a.status) ? `<button class="btn btn-sm" data-act="start" data-id="${a.id}" title="Start">▶</button>` : ""} <button class="btn btn-sm btn-bad" data-act="dismiss" data-id="${a.id}" title="Dismiss">✕</button>`}</td></tr>`).join("")}</tbody></table>`;
}

function bindActionButtons(root, reload) {
  root.querySelectorAll("button[data-act]").forEach((b) => b.onclick = async (ev) => {
    ev.stopPropagation();
    const id = b.dataset.id;
    try {
      if (b.dataset.act === "complete") await api.actionComplete(id);
      else if (b.dataset.act === "dismiss") await api.actionDismiss(id);
      else if (b.dataset.act === "plan") await api.actionPlan(id);
      else if (b.dataset.act === "start") await api.actionStart(id);
      else if (b.dataset.act === "schedule") { const when = prompt("Schedule for (YYYY-MM-DD HH:MM)", new Date().toISOString().slice(0, 16).replace("T", " ")); if (!when) return; await api.actionSchedule(id, when.replace(" ", "T") + ":00"); }
      toast("Action updated"); reload();
    } catch (e) { toast("Error: " + e.message); }
  });
}

// ---------------------------------------------------------------- OPPORTUNITIES
export async function Opportunities(view) {
  const state = { demand: "VERY_HIGH,HIGH", days: 7, page: 1, page_size: 60 };
  view.innerHTML = `<h1>🔥 Taxi Opportunities</h1><p class="sub">Typed journey opportunities generated from scored events. Windows are modelled.</p>
    <div class="filters"><div class="seg" id="dem">${[["VERY_HIGH", "Very high"], ["VERY_HIGH,HIGH", "High+"], ["VERY_HIGH,HIGH,MEDIUM", "Medium+"], ["", "All"]].map(([v, l]) => `<button data-v="${v}" class="${v === state.demand ? "active" : ""}">${l}</button>`).join("")}</div>
    <div class="seg" id="days">${[1, 3, 7, 14, 30].map((d) => `<button data-d="${d}" class="${d === 7 ? "active" : ""}">${d}d</button>`).join("")}</div>
    <select id="otype"><option value="">All types</option>${["HOME_TO_VENUE", "STATION_TO_VENUE", "HOTEL_TO_VENUE", "AIRPORT_TO_VENUE", "VENUE_TO_HOME", "VENUE_TO_HOTEL", "VENUE_TO_STATION", "VENUE_TO_AIRPORT", "LATE_NIGHT_RETURN", "PRE_BOOKING"].map((t) => `<option>${t}</option>`).join("")}</select></div>
    <div id="cards"></div>`;
  const cards = document.getElementById("cards");
  async function load() {
    const { data, meta } = await api.opportunities({ ...state, opportunity_type: otype.value });
    cards.innerHTML = data.length ? `<div class="cards">${data.map((o) => `<div class="card ${esc(o.demand_level)}">
      <div class="row"><span class="badge cat">${esc(o.opportunity_type.replaceAll("_", " → ").replace("LATE → NIGHT → RETURN", "LATE NIGHT RETURN").replace("PRE → BOOKING", "PRE-BOOKING"))}</span>${score(o.score, o.demand_level)}</div>
      <div class="title"><a href="#/events/${o.event.id}">${esc(o.event.title)}</a></div>
      <div class="meta">📍 ${esc(o.event.venue?.name || "")}, ${esc(o.event.city || "")} · 📆 ${fmtDate(o.event.date_start)} ${esc(o.event.time_start || "TBC")}</div>
      <div class="meta">🕐 Modelled window: <b class="mono">${esc(o.window.start || "—")}–${esc(o.window.end || "—")}</b> · ${badge(o.demand_level)}</div>
      <div class="meta">${o.reasons.map(esc).join(" · ")}</div>
      <div class="action">🚕 ${esc(o.recommended_action)}</div></div>`).join("")}</div>` : `<div class="muted">No opportunities for this filter.</div>`;
    cards.appendChild(pager(meta, (p) => { state.page = p; load(); }));
  }
  document.querySelectorAll("#dem button").forEach((b) => b.onclick = () => { document.querySelectorAll("#dem button").forEach((x) => x.classList.remove("active")); b.classList.add("active"); state.demand = b.dataset.v; state.page = 1; load(); });
  document.querySelectorAll("#days button").forEach((b) => b.onclick = () => { document.querySelectorAll("#days button").forEach((x) => x.classList.remove("active")); b.classList.add("active"); state.days = Number(b.dataset.d); state.page = 1; load(); });
  document.getElementById("otype").onchange = () => { state.page = 1; load(); };
  await load();
}

// ---------------------------------------------------------------- ACTIONS
export async function Actions(view) {
  const state = { status: "NEW,PLANNED,SCHEDULED,IN_PROGRESS", days: 14, page: 1, page_size: 80 };
  view.innerHTML = `<h1>🎯 Marketing Action Center</h1><p class="sub">Recommended actions for upcoming high-value events. Recommendations, not guarantees.</p>
    <div class="filters"><div class="seg" id="st">${[["NEW,PLANNED,SCHEDULED,IN_PROGRESS", "Open"], ["NEW", "New (today)"], ["PLANNED", "Planned"], ["SCHEDULED", "Scheduled"], ["IN_PROGRESS", "In progress"], ["DONE", "Completed"], ["DISMISSED", "Dismissed"]].map(([v, l]) => `<button data-v="${v}" class="${v === state.status ? "active" : ""}">${l}</button>`).join("")}</div>
    <div class="seg" id="days">${[3, 7, 14, 30].map((d) => `<button data-d="${d}" class="${d === 14 ? "active" : ""}">${d}d</button>`).join("")}</div>
    <select id="prio"><option value="">All priorities</option><option>P1</option><option>P2</option><option>P3</option></select>
    <select id="type"><option value="">All types</option>${["SEO", "GOOGLE_ADS", "META_ADS", "GBP_POST", "SOCIAL_POST", "LANDING_PAGE", "WHATSAPP_CTA", "EMAIL", "PARTNERSHIP"].map((t) => `<option>${t}</option>`).join("")}</select></div>
    <div id="list" class="panel"></div>`;
  const list = document.getElementById("list");
  async function load() {
    const { data, meta } = await api.actions({ ...state, priority: prio.value });
    const filtered = type.value ? data.filter((a) => a.action_type === type.value) : data;
    const icons = { SEO: "🔎", GOOGLE_ADS: "🎯", META_ADS: "📣", GBP_POST: "🔥", SOCIAL_POST: "📱", LANDING_PAGE: "📄", WHATSAPP_CTA: "💬", EMAIL: "✉️", PARTNERSHIP: "🤝" };
    list.innerHTML = actionsTable(filtered.map((a) => ({ ...a, title: `${icons[a.action_type] || ""} ${a.title}` })), true);
    list.appendChild(pager(meta, (p) => { state.page = p; load(); }));
    bindActionButtons(list, load);
  }
  document.querySelectorAll("#st button").forEach((b) => b.onclick = () => { document.querySelectorAll("#st button").forEach((x) => x.classList.remove("active")); b.classList.add("active"); state.status = b.dataset.v; state.page = 1; load(); });
  document.querySelectorAll("#days button").forEach((b) => b.onclick = () => { document.querySelectorAll("#days button").forEach((x) => x.classList.remove("active")); b.classList.add("active"); state.days = Number(b.dataset.d); state.page = 1; load(); });
  document.getElementById("prio").onchange = load; document.getElementById("type").onchange = load;
  await load();
}

// ---------------------------------------------------------------- CALENDAR
export async function Calendar(view) {
  let mode = "month"; let cursor = new Date(); cursor.setHours(0, 0, 0, 0);
  const iso = (d) => d.toISOString().slice(0, 10);
  view.innerHTML = `<h1>📅 Calendar</h1><div class="cal-head"><div class="seg" id="mode"><button data-m="month" class="active">Month</button><button data-m="week">Week</button><button data-m="day">Day</button></div>
    <div><button class="btn btn-sm" id="prev">‹</button> <b id="label"></b> <button class="btn btn-sm" id="next">›</button> <button class="btn btn-sm" id="today">Today</button></div></div><div id="cal"></div>`;
  async function load() {
    let start, end;
    if (mode === "month") { start = new Date(cursor.getFullYear(), cursor.getMonth(), 1); end = new Date(cursor.getFullYear(), cursor.getMonth() + 1, 0); }
    else if (mode === "week") { start = new Date(cursor); start.setDate(cursor.getDate() - ((cursor.getDay() + 6) % 7)); end = new Date(start); end.setDate(start.getDate() + 6); }
    else { start = new Date(cursor); end = new Date(cursor); }
    document.getElementById("label").textContent = mode === "month" ? cursor.toLocaleDateString("en-GB", { month: "long", year: "numeric" }) : mode === "week" ? `${fmtDate(iso(start))} – ${fmtDate(iso(end))}` : fmtDate(iso(cursor));
    const gridStart = new Date(start); if (mode === "month") gridStart.setDate(start.getDate() - ((start.getDay() + 6) % 7));
    const gridEnd = new Date(end); if (mode === "month") gridEnd.setDate(end.getDate() + (6 - (end.getDay() + 6) % 7));
    const { data } = await api.calendar(iso(gridStart), iso(gridEnd));
    const byDay = {}; data.forEach((e) => { const s = new Date(e.date_start + "T00:00:00"), en = new Date((e.date_end || e.date_start) + "T00:00:00"); for (let d = new Date(s); d <= en; d.setDate(d.getDate() + 1)) (byDay[iso(d)] ||= []).push(e); });
    const cal = document.getElementById("cal");
    if (mode === "day") {
      const evs = (byDay[iso(cursor)] || []).sort((a, b) => (a.time_start || "99").localeCompare(b.time_start || "99"));
      cal.innerHTML = `<div class="panel">${eventTable(evs)}</div>`; return;
    }
    const days = []; for (let d = new Date(gridStart); d <= gridEnd; d.setDate(d.getDate() + 1)) days.push(new Date(d));
    cal.innerHTML = `<div class="calendar">${["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((d) => `<div class="muted small" style="text-align:center">${d}</div>`).join("")}
      ${days.map((d) => { const k = iso(d); const evs = (byDay[k] || []).sort((a, b) => b.opportunity_score - a.opportunity_score); const other = mode === "month" && d.getMonth() !== cursor.getMonth();
        return `<div class="cal-day ${other ? "other" : ""} ${k === iso(new Date()) ? "today" : ""}"><div class="d">${d.getDate()}${evs.length ? ` <span class="muted">· ${evs.length}</span>` : ""}</div>
        ${evs.slice(0, mode === "week" ? 14 : 4).map((e) => `<a class="cal-ev ${esc(e.demand_level)}" href="#/events/${e.id}" title="${esc(e.title)} · ${e.opportunity_score}">${esc(e.time_start || "")} ${esc(e.title)}</a>`).join("")}${evs.length > (mode === "week" ? 14 : 4) ? `<span class="muted small">+${evs.length - (mode === "week" ? 14 : 4)} more</span>` : ""}</div>`; }).join("")}</div>`;
  }
  document.querySelectorAll("#mode button").forEach((b) => b.onclick = () => { document.querySelectorAll("#mode button").forEach((x) => x.classList.remove("active")); b.classList.add("active"); mode = b.dataset.m; load(); });
  const step = (n) => { if (mode === "month") cursor.setMonth(cursor.getMonth() + n); else cursor.setDate(cursor.getDate() + n * (mode === "week" ? 7 : 1)); load(); };
  document.getElementById("prev").onclick = () => step(-1); document.getElementById("next").onclick = () => step(1); document.getElementById("today").onclick = () => { cursor = new Date(); load(); };
  await load();
}

// ---------------------------------------------------------------- ANALYTICS
export async function Analytics(view) {
  view.innerHTML = `<h1>📈 Analytics</h1><div class="filters"><div class="seg" id="days">${[7, 30, 60, 120].map((d) => `<button data-d="${d}" class="${d === 30 ? "active" : ""}">${d}d</button>`).join("")}</div></div><div id="charts"></div>`;
  async function load(days) {
    const { data: t } = await api.trends(days);
    const c = { VERY_HIGH: "#ff3b5c", HIGH: "#ff7a45", MEDIUM: "#f5b400", MODERATE: "#3fa7ff", LOW: "#5b6b8a" };
    document.getElementById("charts").innerHTML = `
      <div class="grid2">
        <div class="panel"><h3>Events by day (next ${days}d) — orange = high or above</h3>${svgBars(t.by_day, "date", "count")}<div class="muted small">Total ${t.by_day.reduce((a, b) => a + b.count, 0)} · high+ ${t.by_day.reduce((a, b) => a + b.high_or_above, 0)}</div></div>
        <div class="panel"><h3>Opportunity score distribution</h3>${bars(t.score_distribution.sort((a, b) => b.bucket.localeCompare(a.bucket)), "bucket")}</div>
        <div class="panel"><h3>Events by category</h3>${bars(t.by_category, "category")}</div>
        <div class="panel"><h3>Events by city (top 15)</h3>${bars(t.by_city, "city")}</div>
        <div class="panel"><h3>Events by region</h3>${bars(t.by_region, "region")}</div>
        <div class="panel"><h3>Top venues</h3><table><tbody>${t.top_venues.map((v) => `<tr><td>${esc(v.venue)}</td><td class="mono">${v.count}</td><td>${score(v.max_score, v.max_score >= 80 ? "VERY_HIGH" : v.max_score >= 65 ? "HIGH" : "MEDIUM")}</td></tr>`).join("")}</tbody></table></div>
        <div class="panel"><h3>Source coverage (primary source)</h3>${bars(t.source_coverage, "source")}</div>
        <div class="panel"><h3>New events trend (14d)</h3>${svgBars(t.new_events_trend, "date", "count")}<h3 style="margin-top:12px">Change trend (14d)</h3>${t.change_trend.length ? `<div class="pill-list">${t.change_trend.map((x) => `<span>${esc(x.date)} ${esc(x.change_type)}: ${x.count}</span>`).join("")}</div>` : "<div class='muted'>No changes recorded yet</div>"}</div>
      </div>`;
  }
  document.querySelectorAll("#days button").forEach((b) => b.onclick = () => { document.querySelectorAll("#days button").forEach((x) => x.classList.remove("active")); b.classList.add("active"); load(Number(b.dataset.d)); });
  await load(30);
}

// ---------------------------------------------------------------- CHANGES
export async function Changes(view) {
  const state = { days: 7, page: 1, page_size: 100 };
  view.innerHTML = `<h1>🔁 Event Changes</h1><p class="sub">What changed since the last runs: new, updated, rescheduled, cancelled.</p>
    <div class="filters"><select id="ct"><option value="">All change types</option>${["NEW", "UPDATED", "DATE_CHANGED", "TIME_CHANGED", "VENUE_CHANGED", "CANCELLED", "POSTPONED", "STATUS_CHANGED"].map((t) => `<option>${t}</option>`).join("")}</select>
    <div class="seg" id="days">${[1, 7, 30, 90].map((d) => `<button data-d="${d}" class="${d === 7 ? "active" : ""}">${d}d</button>`).join("")}</div></div><div id="list" class="panel"></div>`;
  const list = document.getElementById("list");
  async function load() {
    const { data, meta } = await api.changes({ ...state, change_type: ct.value });
    list.innerHTML = data.length ? `<table><thead><tr><th>Detected</th><th>Type</th><th>Event</th><th>Field</th><th>Change</th></tr></thead><tbody>${data.map((c) => `<tr class="clickable" data-href="#/events/${c.event_id}"><td class="muted small">${fmtDT(c.detected_at)}</td><td>${badge(c.change_type)}</td><td><b>${esc(c.event.title)}</b><div class="muted small">${fmtDate(c.event.date_start)} · ${esc(c.event.city || "")}</div></td><td>${esc(c.field || "")}</td><td class="small">${c.old_value ? `<s class="muted">${esc(c.old_value)}</s> → ` : ""}${esc(c.new_value || "")}</td></tr>`).join("")}</tbody></table>` : `<div class="muted">No changes.</div>`;
    list.appendChild(pager(meta, (p) => { state.page = p; load(); }));
  }
  document.getElementById("ct").onchange = load;
  document.querySelectorAll("#days button").forEach((b) => b.onclick = () => { document.querySelectorAll("#days button").forEach((x) => x.classList.remove("active")); b.classList.add("active"); state.days = Number(b.dataset.d); load(); });
  await load();
}

// ---------------------------------------------------------------- SOURCES
export async function Sources(view) {
  const { data } = await api.sources();
  view.innerHTML = `<h1>🔌 Source Health</h1><p class="sub">Every connector reports independently. DISABLED = API key not configured (add it in .env to activate).</p>
    <div class="panel"><table><thead><tr><th>Source</th><th>Type</th><th>Prio</th><th>Status</th><th>Last success</th><th>Events</th><th>Response</th><th>Last error / note</th><th></th></tr></thead><tbody>
    ${data.map((s) => `<tr><td><b>${esc(s.name)}</b><div class="muted small mono">${esc(s.key)}${s.requires_key ? ` · needs ${esc(s.requires_key)}` : ""}</div></td><td>${esc(s.type)}</td><td>${s.priority}</td><td>${badge(s.enabled ? s.status : "DISABLED")}</td><td class="small">${fmtDT(s.last_success_at)}</td><td class="mono">${s.last_events_collected}</td><td class="mono">${s.last_response_ms ?? "—"} ms</td><td class="small muted">${s.disabled_reason ? `<b>${esc(s.disabled_reason)}</b>${s.docs_url ? ` · <a href="${esc(s.docs_url)}" target="_blank" rel="noopener">docs</a>` : ""}` : esc((s.last_error || "").slice(0, 160))}</td>
      <td style="white-space:nowrap"><a class="btn btn-sm" href="#/sources/${s.id}">Events</a> <button class="btn btn-sm" data-h="${s.id}">Check</button> <button class="btn btn-sm" data-t="${s.id}">${s.enabled ? "Disable" : "Enable"}</button></td></tr>`).join("")}</tbody></table><div id="detail"></div></div>`;
  view.querySelectorAll("button[data-h]").forEach((b) => b.onclick = async () => { b.textContent = "…"; const { data: d } = await api.sourceHealth(b.dataset.h);
    document.getElementById("detail").innerHTML = `<h3 style="margin-top:16px">${esc(d.name)} — live check: ${badge(d.live_check?.status)} <span class="muted small">${esc(d.live_check?.message || "")}</span></h3>
      <table><thead><tr><th>Run</th><th>Started</th><th>Status</th><th>Events</th><th>ms</th><th>Error</th></tr></thead><tbody>${d.recent_runs.map((r) => `<tr><td>#${r.id}</td><td class="small">${fmtDT(r.started_at)}</td><td>${badge(r.status)}</td><td>${r.events}</td><td>${r.response_ms ?? "—"}</td><td class="small muted">${esc((r.error || "").slice(0, 120))}</td></tr>`).join("")}</tbody></table>`; b.textContent = "Check"; });
  view.querySelectorAll("button[data-t]").forEach((b) => b.onclick = async () => { try { await api.toggleSource(b.dataset.t); toast("Source toggled"); Sources(view); } catch (e) { toast("Error: " + e.message); } });
}

// ---------------------------------------------------------------- SYSTEM
export async function System(view) {
  const [{ data: h }, bk] = await Promise.all([api.health(), api.bookingsStatus().catch(() => ({ data: null }))]);
  const r = h.last_pipeline_run;
  const pv = h.providers || {};
  const b = bk && bk.data;
  view.innerHTML = `<h1>🩺 System Health</h1>
    <div class="kpis">${kpi("Database", h.database.status, "new")}${kpi("Events stored", h.database.events)}${kpi("Raw payloads", h.database.raw_events)}
      ${kpi("Last run", r ? r.status : "—", r && r.status === "SUCCESS" ? "new" : "h")}${kpi("Duration", r ? r.duration_seconds + "s" : "—")}${kpi("Sources OK / failed", r ? `${r.sources_successful} / ${r.sources_failed}` : "—")}
      ${kpi("Events collected", r ? r.events_valid : "—")}${kpi("Duplicates removed", r ? r.duplicates_removed : "—")}${kpi("Changes detected", r ? r.changes_detected : "—")}${kpi("Notifications sent", h.notifications.sent)}</div>
    <div class="grid2">
      <div class="panel"><h3>Last pipeline run stages</h3>${r ? `<table><tbody>${Object.entries(r.stages || {}).map(([k, v]) => `<tr><td>${esc(k)}</td><td>${typeof v === "object" && v.status ? badge(v.status === "ok" ? "HEALTHY" : "FAILED", v.status) : ""}</td><td class="small mono">${esc(typeof v === "object" ? JSON.stringify(v).slice(0, 120) : v)}</td></tr>`).join("")}</tbody></table>` : "No runs yet."}</div>
      <div class="panel"><h3>Integrations</h3><dl class="kv"><dt>Telegram</dt><dd>${h.notifications.telegram_configured ? badge("HEALTHY", "configured") : badge("DISABLED", "not configured")}</dd><dt>Google Sheets</dt><dd>${h.notifications.sheets_configured ? badge("HEALTHY", "configured") : badge("DISABLED", "not configured")}</dd><dt>Sources</dt><dd>${h.sources.healthy} healthy · ${h.sources.degraded} degraded · ${h.sources.failed} failed · ${h.sources.disabled} disabled</dd><dt>DB engine</dt><dd class="mono">${esc(h.database.url_scheme)}</dd>
        <dt>API</dt><dd>${badge("HEALTHY", "serving")}</dd>
        <dt>Scheduler</dt><dd>${h.scheduler ? `${esc(h.scheduler.mode)} · next ${fmtDT(h.scheduler.next_scheduled_run)}` : "—"}</dd>
        <dt>Map provider</dt><dd>${pv.map ? `${esc(pv.map.provider)}${pv.map.offline ? " (offline)" : ""}` : "—"}</dd>
        <dt>Notification providers</dt><dd>${(pv.notifications || []).map((n) => `${esc(n.key)} ${n.configured ? badge("HEALTHY", "configured") : badge("DISABLED", "not configured")}`).join(" ") || "—"}</dd>
        <dt>External data</dt><dd>${(pv.external_data || []).map((n) => `${esc(n.kind)}: ${n.configured ? esc(n.key) : "not configured"}`).join(" · ")}</dd>
        <dt>LLM</dt><dd>${pv.llm ? (pv.llm.configured ? esc(pv.llm.key) : "not used (deterministic platform)") : "—"}</dd>
        <dt>Historical bookings</dt><dd>${b ? `${b.bookings} bookings · ${b.correlations} correlations · model mode <b>${esc(b.model_mode)}</b> (${b.labelled_events}/${b.required} labelled events)` : "—"}</dd></dl>
        <h3 style="margin-top:14px">Recent runs</h3><table><tbody>${h.recent_runs.map((x) => `<tr><td>#${x.id}</td><td class="small">${fmtDT(x.started_at)}</td><td>${badge(x.status)}</td><td class="small">${x.events_valid} valid · ${x.events_created} new · ${x.changes_detected} changes</td><td class="mono small">${x.duration_seconds}s</td></tr>`).join("")}</tbody></table></div>
    </div>
    <div class="panel" style="margin-top:16px"><h3>Recent errors</h3>${h.recent_errors.length ? `<table><tbody>${h.recent_errors.map((e) => `<tr><td class="small muted">${fmtDT(e.at)}</td><td class="mono small">${esc(e.component)}</td><td class="small">${esc(e.message)}</td></tr>`).join("")}</tbody></table>` : `<div class="muted">No errors recorded 🎉</div>`}</div>`;
}

// ---------------------------------------------------------------- SETTINGS
export async function Settings(view) {
  const { data: s } = await api.settings();
  const field = (key, label, val, hint = "") => `<div class="panel"><h3>${esc(label)}</h3><input id="s-${key}" value="${esc(Array.isArray(val) ? val.join(", ") : val ?? "")}" style="width:100%"><div class="muted small" style="margin-top:6px">${esc(hint)}</div><button class="btn btn-sm" style="margin-top:8px" data-save="${key}">Save</button></div>`;
  view.innerHTML = `<h1>⚙️ Settings</h1><p class="sub">Operational settings are stored in the database; secrets stay in environment variables and are never displayed.</p>
    <div class="grid3">
      ${field("service_area_cities", "Taxi service area (cities)", s.service_area_cities, "Comma-separated. Events inside the area get a location bonus.")}
      ${field("home_city", "Home city", s.home_city)}
      <div class="panel" style="grid-column:span 2"><h3>Taxi service area (structured)</h3><div class="muted small">primary_city, radius_miles, priority_postcodes, airports, stations, venues, priority_cities — used for service-area relevance and action gating. No area is hardcoded.</div>
        <textarea id="s-service_area" style="width:100%;height:150px;font-family:monospace">${esc(JSON.stringify(s.service_area || {}, null, 2))}</textarea><button class="btn btn-sm" style="margin-top:8px" data-save-json="service_area">Save</button></div>
      ${field("priority_categories", "Priority categories", s.priority_categories, "Comma-separated")}
      ${field("collection_frequency", "Collection frequency", s.collection_frequency, "daily | hourly | manual (GitHub Actions cron controls the real schedule)")}
      <div class="panel"><h3>Score thresholds (demand levels)</h3><dl class="kv">${Object.entries(s.score_thresholds || {}).map(([k, v]) => `<dt>${esc(k)}</dt><dd class="mono">≥ ${v}</dd>`).join("")}</dl><div class="muted small">Edit config/scoring.yaml to change.</div></div>
      <div class="panel"><h3>Scoring weights</h3><dl class="kv">${Object.entries(s.scoring_weights || {}).map(([k, v]) => `<dt>${esc(k)}</dt><dd class="mono">${v}</dd>`).join("")}</dl></div>
      <div class="panel"><h3>Notifications</h3><dl class="kv"><dt>Telegram daily digest</dt><dd>${s.notifications?.telegram_daily_digest ? "on" : "off"}</dd><dt>Digest time</dt><dd>${esc(s.notifications?.digest_time_local || "")} (Europe/London)</dd><dt>Telegram configured</dt><dd>${s.integrations.telegram ? "✅" : "❌ set TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID"}</dd><dt>Google Sheets</dt><dd>${s.integrations.google_sheets ? "✅" : "❌ optional"}</dd></dl></div>
      <div class="panel"><h3>Source keys</h3><dl class="kv"><dt>Ticketmaster</dt><dd>${s.integrations.ticketmaster ? "✅ configured" : "❌ TICKETMASTER_API_KEY"}</dd><dt>Eventbrite</dt><dd>${s.integrations.eventbrite ? "✅" : "❌ EVENTBRITE_API_KEY"}</dd><dt>JamBase</dt><dd>${s.integrations.jambase ? "✅" : "❌ JAMBASE_API_KEY"}</dd></dl></div>
      <div class="panel"><h3>Sources (config/sources.yaml)</h3><table><tbody>${Object.entries(s.sources).map(([k, v]) => `<tr><td class="mono">${esc(k)}</td><td>${esc(v.type)}</td><td>${v.priority}</td><td>${v.enabled ? "enabled" : "disabled"}</td></tr>`).join("")}</tbody></table><div class="muted small">Toggle at runtime on the Sources page.</div></div>
    </div>`;
  view.querySelectorAll("button[data-save]").forEach((b) => b.onclick = async () => { const k = b.dataset.save; let v = document.getElementById("s-" + k).value; if (["service_area_cities", "priority_categories"].includes(k)) v = v.split(",").map((x) => x.trim()).filter(Boolean);
    try { await api.putSetting(k, v); toast("Saved"); } catch (e) { toast("Error: " + e.message); } });
  view.querySelectorAll("button[data-save-json]").forEach((b) => b.onclick = async () => { const k = b.dataset.saveJson; let v;
    try { v = JSON.parse(document.getElementById("s-" + k).value); } catch { toast("Invalid JSON"); return; }
    try { await api.putSetting(k, v); toast("Saved"); } catch (e) { toast("Error: " + e.message); } });
}


// ---------------------------------------------------------------- COVERAGE (Phase 2)
export async function Coverage(view) {
  const { data: c } = await api.coverage();
  const st = c.targets_by_status || {};
  const kindRows = (kind) => c.targets.filter((t) => t.kind === kind);
  const tbl = (rows) => rows.length ? `<table><thead><tr><th>Target</th><th>City</th><th>Status</th><th>Future events</th><th>Declared</th></tr></thead><tbody>${rows.map((t) => `<tr><td><b>${esc(t.name)}</b>${t.requires_key ? `<div class="muted small">needs ${esc(t.requires_key)}</div>` : ""}</td><td>${esc(t.city || "—")}</td><td>${badge(t.status === "ACTIVE" ? "HEALTHY" : t.status, t.status)}</td><td class="mono">${t.future_events}</td><td class="muted small">${esc(t.declared_status || "")}</td></tr>`).join("")}</tbody></table>` : `<div class="muted">none configured</div>`;
  const h = c.events.horizons;
  view.innerHTML = `<h1>📡 Coverage</h1><p class="sub">${esc(c.disclaimer)}</p>
    <div class="kpis">${kpi("Configured Coverage Index", c.configured_coverage_index + " / 100", "new")}${kpi("Targets active", st.ACTIVE || 0)}${kpi("Empty", st.EMPTY || 0, "h")}${kpi("Blocked", st.BLOCKED || 0, "h")}${kpi("Unverified", st.UNVERIFIED || 0)}${kpi("Disabled", st.DISABLED || 0)}
      ${kpi("Events today", h.today)}${kpi("Next 7 days", h["7d"])}${kpi("Next 30 days", h["30d"])}${kpi("Next 90 days", h["90d"])}${kpi("Cities with events", `${c.geography.cities_with_events} / ${c.geography.cities_configured}`)}${kpi("Venues with events", `${c.geography.venues_with_events} / ${c.geography.venues_registered}`)}</div>
    <div class="grid3">
      <div class="panel"><h3>By source (future events)</h3>${Object.entries(c.events.by_source).map(([k, v]) => `<div class="bar"><span class="mono">${esc(k)}</span><span class="mono">${v}</span></div>`).join("")}</div>
      <div class="panel"><h3>By source confidence</h3>${Object.entries(c.events.by_source_confidence).map(([k, v]) => `<div class="bar">${badge(k || "UNVERIFIED")}<span class="mono">${v}</span></div>`).join("")}<h3 style="margin-top:10px">By quality</h3>${Object.entries(c.events.by_quality).map(([k, v]) => `<div class="bar">${badge(k || "LOW")}<span class="mono">${v}</span></div>`).join("")}</div>
      <div class="panel"><h3>Gaps — configured cities without future events</h3><div class="small">${c.geography.cities_without_events.map(esc).join(", ") || "none"}</div><h3 style="margin-top:10px">By region</h3>${Object.entries(c.geography.by_region).map(([k, v]) => `<div class="bar"><span>${esc(k)}</span><span class="mono">${v}</span></div>`).join("")}</div>
    </div>
    <div class="panel" style="margin-top:16px"><h3>By category</h3><table><tbody>${c.events.by_category.map((r) => `<tr><td>${esc(r.category)}</td><td class="muted">${esc(r.subcategory || "")}</td><td class="mono">${r.count}</td></tr>`).join("")}</tbody></table></div>
    <div class="panel" style="margin-top:16px"><h3>Source health</h3><table><thead><tr><th>Source</th><th>Status</th><th>Auth</th><th>Future events</th><th>Failure rate</th><th>Last success</th><th>Avg ms</th></tr></thead><tbody>${c.sources.map((s) => `<tr class="clickable" data-href="#/sources/${s.id}"><td class="mono">${esc(s.key)}</td><td>${badge(s.status === "SOURCE SILENT" ? "FAILED" : s.status, s.status)}</td><td>${esc(s.auth)}</td><td class="mono">${s.future_events}</td><td class="mono">${s.failure_rate ?? "—"}</td><td class="small">${fmtDT(s.last_success_at)}</td><td class="mono">${s.avg_response_ms ?? "—"}</td></tr>`).join("")}</tbody></table></div>
    <div class="grid2" style="margin-top:16px">
      <div class="panel"><h3>Venue registry targets (${kindRows("venue").length})</h3>${tbl(kindRows("venue"))}</div>
      <div class="panel"><h3>Councils & tourism boards</h3>${tbl([...kindRows("council"), ...kindRows("tourism")])}<h3 style="margin-top:12px">Institutions</h3>${tbl([...kindRows("university"), ...kindRows("college"), ...kindRows("school")])}</div>
    </div>
    <div class="muted small" style="margin-top:10px">Index basis: weighted active ${c.index_basis.weighted_active} / weighted key-less configured ${c.index_basis.weighted_configured_keyless}. Weights: ${esc(JSON.stringify(c.index_basis.weights))}.</div>`;
}

export async function DataQuality(view) {
  const { data: q } = await api.dataQuality();
  const m = q.missing;
  view.innerHTML = `<h1>✅ Data Quality</h1><p class="sub">Computed over ${q.future_events} future events as of ${esc(q.as_of)}. LOW-quality events never receive automatic marketing recommendations.</p>
    <div class="kpis">${kpi("Avg quality score", q.avg_quality_score ?? "—", "new")}<a href="#/events?quality=HIGH">${kpi("HIGH", q.quality_levels.HIGH || 0, "new")}</a><a href="#/events?quality=MEDIUM">${kpi("MEDIUM", q.quality_levels.MEDIUM || 0)}</a><a href="#/events?quality=LOW">${kpi("LOW", q.quality_levels.LOW || 0, "h")}</a><a href="#/events?confidence=UNVERIFIED">${kpi("Unverified", q.source_confidence.UNVERIFIED || 0)}</a>${kpi("Multi-source", `${q.multi_source_events} (${q.multi_source_pct}%)`)}${kpi("Avg freshness", q.freshness.avg ?? "—")}${kpi("SOURCE SILENT", q.source_silent, q.source_silent ? "h" : "")}${kpi("Possible duplicates", q.possible_duplicates_total, q.possible_duplicates_total ? "h" : "")}</div>
    <div class="grid2">
      <div class="panel"><h3>Missing fields <span class="muted small">(click to filter the feed)</span></h3><table><tbody>${Object.entries(m).map(([k, v]) => `<tr class="clickable" data-href="#/events?missing=${esc({ time_start: "time", venue_id: "venue", city_id: "location", official_url: "official_url", coordinates: "coordinates", venue_capacity: "capacity", category_other: "" }[k] || "")}${k === "category_other" ? "&category=other" : ""}"><td>${esc(k)}</td><td class="mono">${v.count}</td><td class="mono muted">${v.pct}%</td><td style="width:40%"><div class="track"><div class="fill" style="width:${v.pct}%"></div></div></td></tr>`).join("")}</tbody></table><div class="muted small">official_url is absent for fixture-feed events by design (feeds publish no per-match URL); venue_capacity is null where no source-backed figure exists.</div></div>
      <div class="panel"><h3>Source confidence</h3>${Object.entries(q.source_confidence).map(([k, v]) => `<div class="bar">${badge(k || "UNVERIFIED")}<span class="mono">${v}</span></div>`).join("")}
        <h3 style="margin-top:12px">Possible duplicates (same normalised title + date)</h3>${q.possible_duplicates.length ? `<table><tbody>${q.possible_duplicates.map((d) => `<tr><td>${esc(d.title)}</td><td class="small">${esc(d.date)}</td><td class="mono">${d.count}</td></tr>`).join("")}</tbody></table>` : `<div class="muted">none</div>`}</div>
    </div>`;
}

export async function SourceDetail(view, id) {
  const { data: d, meta } = await api.sourceEvents(id, { page_size: 100 });
  view.innerHTML = `<a class="back" href="#/sources">← Sources</a><h1>🔌 ${esc(d.source.key)} ${badge(d.source.status)}</h1><p class="sub">${meta.total} linked events (all horizons) · last ${d.runs.length} runs</p>
    <div class="grid2"><div class="panel"><h3>Recent runs</h3><table><thead><tr><th>Run</th><th>Started</th><th>Status</th><th>Events</th><th>ms</th><th>Error</th></tr></thead><tbody>${d.runs.map((r) => `<tr><td>#${r.id}</td><td class="small">${fmtDT(r.started_at)}</td><td>${badge(r.status)}</td><td class="mono">${r.events}</td><td class="mono">${r.response_ms ?? "—"}</td><td class="small muted">${esc((r.error || "").slice(0, 140))}</td></tr>`).join("")}</tbody></table></div>
    <div class="panel"><h3>Events from this source</h3><table><thead><tr><th>Event</th><th>City</th><th>Date</th><th>Cat</th><th>Status</th><th>Score</th></tr></thead><tbody>${d.events.map(eventRow).join("")}</tbody></table></div></div>`;
}

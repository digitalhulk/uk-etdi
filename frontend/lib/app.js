// Hash-based router + global handlers. Zero-build vanilla ES modules so it can be hosted on any free static host.
import { api } from "./api.js";
import { toast } from "../components/ui.js";
import * as P from "../app/pages.js";

const routes = [
  [/^\/$/, P.Home], [/^\/map$/, P.MapPage], [/^\/events$/, P.Events], [/^\/events\/(\d+)$/, P.EventDetail],
  [/^\/opportunities$/, P.Opportunities], [/^\/actions$/, P.Actions], [/^\/calendar$/, P.Calendar], [/^\/analytics$/, P.Analytics],
  [/^\/changes$/, P.Changes], [/^\/sources$/, P.Sources], [/^\/sources\/(\d+)$/, P.SourceDetail],
  [/^\/coverage$/, P.Coverage], [/^\/quality$/, P.DataQuality], [/^\/system$/, P.System], [/^\/settings$/, P.Settings],
];

async function render() {
  const path = (location.hash.replace(/^#/, "") || "/").split("?")[0];
  const view = document.getElementById("view");
  document.querySelectorAll("#nav a").forEach((a) => a.classList.toggle("active", a.dataset.route === (path.startsWith("/events/") ? "/events" : path.startsWith("/sources/") ? "/sources" : path)));
  for (const [re, fn] of routes) {
    const m = path.match(re);
    if (m) {
      view.innerHTML = `<div class="loading">Loading…</div>`;
      try { await fn(view, ...m.slice(1)); } catch (e) { view.innerHTML = `<div class="error"><b>Failed to load:</b> ${e.message}<br><span class="muted small">Is the backend running? API base: ${window.UK_ETDI_API_BASE || location.origin}/api</span></div>`; }
      return;
    }
  }
  view.innerHTML = `<div class="error">Not found</div>`;
}

document.addEventListener("click", (ev) => {
  const row = ev.target.closest("tr[data-href]");
  if (row && !ev.target.closest("button,a")) location.hash = row.dataset.href;
});

document.getElementById("run-pipeline").onclick = async () => {
  const st = document.getElementById("pipeline-status");
  try {
    const { data } = await api.runPipeline();
    toast(data.message); st.textContent = "Pipeline running…";
    const poll = setInterval(async () => {
      const { data: runs } = await api.runs();
      if (runs[0] && runs[0].status !== "RUNNING") { clearInterval(poll); st.textContent = `Run #${runs[0].id}: ${runs[0].status} (${runs[0].duration_seconds}s)`; toast("Pipeline finished"); render(); }
    }, 3000);
  } catch (e) { toast("Error: " + e.message); }
};

window.addEventListener("hashchange", render);
render();

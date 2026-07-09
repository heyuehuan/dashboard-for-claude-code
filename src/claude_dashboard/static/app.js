/* Claude Usage Dashboard — frontend */

// ── Theme ──────────────────────────────────────────────────────────────────
const SUN_SVG = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/></svg>`;
const MOON_SVG = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>`;

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  const light = theme === "light";
  Chart.defaults.color = light ? "#6d6b67" : "#898781";
  Chart.defaults.borderColor = light ? "#e1e0d9" : "#383835";
  const btn = document.getElementById("themeBtn");
  if (btn) btn.innerHTML = light ? MOON_SVG : SUN_SVG;
}

function toggleTheme() {
  const next =
    document.documentElement.dataset.theme === "light" ? "dark" : "light";
  localStorage.setItem("theme", next);
  applyTheme(next);
  if (_summaryData) {
    destroyCharts();
    renderDailyCost(_summaryData.daily || []);
    renderModelDonut(_summaryData.tokens_by_model || {});
    renderToolsBar(_summaryData.tools || {});
    renderProjectsBar(_summaryData.top_projects || []);
    renderActivityHeatmap(_summaryData.activity || []);
    renderAutonomyDonut(_summaryData.permission_modes || {});
    renderSkillsBar(_summaryData.skills || {});
  }
}

Chart.defaults.font.family = "Inter, ui-sans-serif, system-ui, sans-serif";
Chart.defaults.font.size = 12;

// ── Remote mode ───────────────────────────────────────────────────────────
// Only the static export sets window.DASHBOARD_REMOTE (injected by export.py),
// so it's the single source of truth. Do NOT infer remote mode from hostname:
// the local server is reached over LAN/Tailscale via non-localhost hostnames,
// and those must still hit /api/* — not the static /data/*.json export paths.
const IS_REMOTE = !!window.DASHBOARD_REMOTE;

function _remoteDataUrl(path) {
  return "/data/" + path + ".json";
}
function _localApiUrl(path) {
  return "/api/" + path;
}
function dataUrl(path) {
  return IS_REMOTE ? _remoteDataUrl(path) : _localApiUrl(path);
}

applyTheme(localStorage.getItem("theme") || "light");

// Claude Code bills 1h cache writes at the 5m rate (1.25x input), not the API-published
// 2x rate, so cache_write_1h == cache_write_5m here. Keep in sync with pricing.py.
const MODEL_RATES = [
  [
    "fable-5",
    {
      input: 10.0,
      output: 50.0,
      cache_read: 1.0,
      cache_write_5m: 12.5,
      cache_write_1h: 12.5,
    },
  ],
  [
    "opus-4-8",
    {
      input: 5.0,
      output: 25.0,
      cache_read: 0.5,
      cache_write_5m: 6.25,
      cache_write_1h: 6.25,
    },
  ],
  [
    "opus-4-7",
    {
      input: 5.0,
      output: 25.0,
      cache_read: 0.5,
      cache_write_5m: 6.25,
      cache_write_1h: 6.25,
    },
  ],
  [
    "opus-4-6",
    {
      input: 5.0,
      output: 25.0,
      cache_read: 0.5,
      cache_write_5m: 6.25,
      cache_write_1h: 6.25,
    },
  ],
  [
    "opus-4-5",
    {
      input: 5.0,
      output: 25.0,
      cache_read: 0.5,
      cache_write_5m: 6.25,
      cache_write_1h: 6.25,
    },
  ],
  [
    "opus-4-1",
    {
      input: 15.0,
      output: 75.0,
      cache_read: 1.5,
      cache_write_5m: 18.75,
      cache_write_1h: 18.75,
    },
  ],
  [
    "opus-4",
    {
      input: 15.0,
      output: 75.0,
      cache_read: 1.5,
      cache_write_5m: 18.75,
      cache_write_1h: 18.75,
    },
  ],
  [
    "sonnet-4-6",
    {
      input: 3.0,
      output: 15.0,
      cache_read: 0.3,
      cache_write_5m: 3.75,
      cache_write_1h: 3.75,
    },
  ],
  [
    "sonnet-4-5",
    {
      input: 3.0,
      output: 15.0,
      cache_read: 0.3,
      cache_write_5m: 3.75,
      cache_write_1h: 3.75,
    },
  ],
  [
    "sonnet-4",
    {
      input: 3.0,
      output: 15.0,
      cache_read: 0.3,
      cache_write_5m: 3.75,
      cache_write_1h: 3.75,
    },
  ],
  [
    "haiku-4-5",
    {
      input: 1.0,
      output: 5.0,
      cache_read: 0.1,
      cache_write_5m: 1.25,
      cache_write_1h: 1.25,
    },
  ],
  [
    "haiku-3-5",
    {
      input: 0.8,
      output: 4.0,
      cache_read: 0.08,
      cache_write_5m: 1.0,
      cache_write_1h: 1.0,
    },
  ],
];

function modelCost(model, tok) {
  const m = model.toLowerCase();
  const entry = MODEL_RATES.find(([k]) => m.includes(k));
  if (!entry) return 0;
  const r = entry[1];
  return (
    ((tok.input || 0) * r.input) / 1e6 +
    ((tok.output || 0) * r.output) / 1e6 +
    ((tok.cache_read || 0) * r.cache_read) / 1e6 +
    ((tok.cache_write_5m || 0) * r.cache_write_5m) / 1e6 +
    ((tok.cache_write_1h || 0) * r.cache_write_1h) / 1e6
  );
}

let _donutMode = "tokens";

function setDonutMode(mode) {
  _donutMode = mode;
  document.querySelectorAll("#donutToggle .seg-opt").forEach((el) => {
    el.classList.toggle(
      "active",
      el.textContent
        .trim()
        .toLowerCase()
        .startsWith(mode === "tokens" ? "tok" : "est"),
    );
  });
  document.getElementById("donutTitle").textContent =
    mode === "tokens" ? "Token Share by Model" : "Est. API Cost by Model";
  if (_summaryData) renderModelDonut(_summaryData.tokens_by_model || {});
}

let _heatMode = "all"; // all | turns | prompts

function setHeatMode(mode) {
  _heatMode = mode;
  document.querySelectorAll("#heatToggle .seg-opt").forEach((el) => {
    el.classList.toggle(
      "active",
      el.textContent.trim().toLowerCase().startsWith(mode.slice(0, 4)),
    );
  });
  if (_summaryData) renderActivityHeatmap(_summaryData.activity);
}

const PALETTE = [
  "#5a67f2",
  "#8173e3",
  "#0ca30c",
  "#3987e5",
  "#d55181",
  "#ec835a",
  "#199e70",
  "#b77700",
  "#e34948",
  "#6d6b67",
];

let _charts = {};
let _summaryData = null;
let _projectsData = null;
let _sessionsData = null;
let _settingsData = null;
let _sortState = {};

// ── Tab routing ────────────────────────────────────────────────────────────

function showTab(name, _pushUrl = true) {
  document.querySelectorAll(".tab").forEach((t, i) => {
    const names = ["overview", "projects", "sessions", "settings"];
    t.classList.toggle("active", names[i] === name);
  });
  document
    .querySelectorAll(".page")
    .forEach((p) => p.classList.remove("active"));
  document.getElementById("page-" + name).classList.add("active");

  if (_pushUrl) {
    const url = name === "overview" ? "/" : "/" + name;
    history.pushState({ tab: name }, "", url);
  }

  if (name === "overview" && !_summaryData) loadOverview();
  if (name === "projects" && !_projectsData) loadProjects();
  if (name === "sessions" && !_sessionsData) loadSessions();
  if (name === "settings") loadSettings();
}

function goAllSessions() {
  history.pushState({ tab: "sessions" }, "", "/sessions");
  _sessionsData = null;
  showTab("sessions", false);
}

function navigateFromUrl(replaceState = true) {
  const path = window.location.pathname.replace(/^\/+/, "") || "overview";
  const params = new URLSearchParams(window.location.search);
  const validTabs = ["overview", "projects", "sessions", "settings"];
  const tab = validTabs.includes(path) ? path : "overview";

  if (replaceState) {
    const state =
      tab === "sessions" && params.has("project")
        ? { tab: "sessions", project: params.get("project") }
        : { tab };
    history.replaceState(state, "", window.location.href);
  }

  if (tab === "sessions" && params.has("project")) {
    showTab("sessions", false);
    openProject(params.get("project"), false);
  } else {
    showTab(tab, false);
  }
}

window.addEventListener("popstate", (e) => {
  const s = e.state;
  if (s?.project) {
    openProject(s.project, false);
  } else if (s?.tab === "sessions") {
    _sessionsData = null;
    showTab("sessions", false);
  } else if (s?.tab) {
    showTab(s.tab, false);
  } else {
    navigateFromUrl(false);
  }
});

// ── Load functions ─────────────────────────────────────────────────────────

async function loadOverview() {
  try {
    _summaryData = await fetchJSON(dataUrl("summary"));
  } catch (e) {
    document.getElementById("kpiGrid").innerHTML =
      `<p class="muted">Error: ${e.message}</p>`;
    return;
  }
  try {
    renderKPIs(_summaryData);
  } catch (_) {}
  try {
    _syncRangeInputs();
  } catch (_) {}
  try {
    renderDailyCost(_summaryData.daily || []);
  } catch (_) {}
  try {
    renderModelDonut(_summaryData.tokens_by_model || {});
  } catch (_) {}
  try {
    renderToolsBar(_summaryData.tools || {});
  } catch (_) {}
  try {
    renderProjectsBar(_summaryData.top_projects || []);
  } catch (_) {}
  try {
    renderActivityHeatmap(_summaryData.activity || []);
  } catch (_) {}
  try {
    renderAutonomyDonut(_summaryData.permission_modes || {});
  } catch (_) {}
  try {
    renderSkillsBar(_summaryData.skills || {});
  } catch (_) {}
}

async function loadProjects() {
  try {
    _projectsData = await fetchJSON(dataUrl("projects"));
    renderProjectsTable(groupProjectsByName(_projectsData));
  } catch (e) {
    document.getElementById("projectsContent").innerHTML =
      `<p class="muted">Error: ${e.message}</p>`;
  }
}

/**
 * Group per-path projects by their display name (project_name).
 * Projects sharing the same name are merged — stats are summed,
 * project_paths collects all paths. Pure frontend operation so renaming
 * back auto-splits without any backend migration.
 */
function groupProjectsByName(projects) {
  const map = new Map();
  const order = [];
  for (const p of projects) {
    const key = p.project_name || p.project_path;
    if (!map.has(key)) {
      map.set(key, { ...p, project_paths: [p.project_path] });
      order.push(key);
    } else {
      const m = map.get(key);
      m.project_paths.push(p.project_path);
      for (const f of [
        "session_count",
        "user_rounds",
        "assistant_messages",
        "api_duration_ms",
        "wall_duration_ms",
        "code_lines_added",
        "code_lines_removed",
        "cost_usd",
      ]) {
        m[f] = (m[f] || 0) + (p[f] || 0);
      }
      if (p.last_active)
        m.last_active =
          !m.last_active || p.last_active > m.last_active
            ? p.last_active
            : m.last_active;
      if (p.first_active)
        m.first_active =
          !m.first_active || p.first_active < m.first_active
            ? p.first_active
            : m.first_active;
      for (const [model, counts] of Object.entries(p.tokens_by_model || {})) {
        if (!m.tokens_by_model) m.tokens_by_model = {};
        if (!m.tokens_by_model[model]) m.tokens_by_model[model] = {};
        for (const [k, v] of Object.entries(counts))
          m.tokens_by_model[model][k] =
            (m.tokens_by_model[model][k] || 0) + (v || 0);
      }
      m.tools = m.tools || {};
      for (const [tool, cnt] of Object.entries(p.tools || {}))
        m.tools[tool] = (m.tools[tool] || 0) + cnt;
    }
  }
  return order.map((k) => map.get(k));
}

async function loadSessions() {
  try {
    _sessionsData = await fetchJSON(dataUrl("sessions"));
    renderSessionsTable(_sessionsData);
  } catch (e) {
    document.getElementById("sessionsContent").innerHTML =
      `<p class="muted">Error: ${e.message}</p>`;
  }
}

// ── Refresh ────────────────────────────────────────────────────────────────

async function doRefresh() {
  if (IS_REMOTE) return;
  const btn = document.getElementById("refreshBtn");
  const icon = document.getElementById("refreshIcon");
  btn.disabled = true;
  icon.style.animation = "spin .8s linear infinite";
  try {
    const r = await fetchJSON("/api/refresh", { method: "POST" });
    showToast(
      `✓ +${r.added} added, ${r.updated} updated, ${r.skipped} skipped`,
    );
    _summaryData = null;
    _projectsData = null;
    _sessionsData = null;
    destroyCharts();
    loadOverview();
    if (document.getElementById("page-projects").classList.contains("active"))
      loadProjects();
    if (document.getElementById("page-sessions").classList.contains("active"))
      loadSessions();
  } catch (e) {
    showToast("Refresh failed: " + e.message);
  } finally {
    btn.disabled = false;
    icon.style.animation = "";
  }
}

// ── Settings ───────────────────────────────────────────────────────────────

async function loadSettings() {
  document.getElementById("settingsContent").innerHTML =
    '<div class="loading"><div class="spinner"></div> Loading…</div>';
  try {
    const [projects, settings] = await Promise.all([
      fetchJSON(
        IS_REMOTE
          ? "/data/projects-all.json"
          : "/api/projects?include_hidden=true",
      ),
      fetchJSON(dataUrl("settings")),
    ]);
    _settingsData = { projects, settings };
    renderSettings(projects, settings, IS_REMOTE);
  } catch (e) {
    document.getElementById("settingsContent").innerHTML =
      `<p class="muted">Error: ${e.message}</p>`;
  }
}

function renderSettings(projects, settings, readOnly = false) {
  const hiddenCount = projects.filter((p) => {
    const s = settings[p.project_path];
    return s && s.hidden;
  }).length;

  const rows = projects
    .map((p) => {
      const s = settings[p.project_path] || {};
      const displayName = s.display_name || "";
      const hidden = s.hidden || false;
      const origName = esc(p.original_name || p.project_name || p.project_path);
      if (readOnly) {
        return `<tr class="${hidden ? "settings-row-hidden" : ""}">
        <td>
          <div class="settings-orig-name">${origName}</div>
          ${displayName ? `<div class="muted" style="font-size:.8rem">${esc(displayName)}</div>` : ""}
        </td>
        <td class="mono settings-path-cell">${esc(p.project_path)}</td>
        <td class="right">${hidden ? '<span class="badge">Hidden</span>' : '<span class="muted">—</span>'}</td>
      </tr>`;
      }
      return `<tr class="${hidden ? "settings-row-hidden" : ""}">
      <td>
        <div class="settings-orig-name">${origName}</div>
        <input class="settings-name-input" type="text"
          placeholder="${origName}"
          value="${esc(displayName)}"
          data-path="${esc(p.project_path)}"
          data-orig="${esc(p.project_name || p.project_path)}">
      </td>
      <td class="mono settings-path-cell">${esc(p.project_path)}</td>
      <td class="right">
        <label class="toggle-label">
          <input type="checkbox" class="settings-hidden-chk"
            data-path="${esc(p.project_path)}"
            ${hidden ? "checked" : ""}>
          <span class="toggle-track"><span class="toggle-thumb"></span></span>
        </label>
      </td>
      <td class="right">
        <button class="save-btn" onclick="saveProjectSetting(this, '${esc(p.project_path)}')">Save</button>
      </td>
    </tr>`;
    })
    .join("");

  const cols = readOnly
    ? `<th>Project</th><th>Path</th><th class="right">Hidden</th>`
    : `<th>Display Name</th><th>Path</th><th class="right">Hidden</th><th class="right">Action</th>`;
  const empty = readOnly
    ? `<tr><td colspan="3" class="muted" style="padding:20px">No projects</td></tr>`
    : `<tr><td colspan="4" class="muted" style="padding:20px">No projects</td></tr>`;

  document.getElementById("settingsContent").innerHTML = `
    <div class="settings-header">
      <div>
        <h2 class="settings-title">Project Settings${readOnly ? ' <span class="muted" style="font-size:.72rem;font-weight:400;margin-left:6px">read-only</span>' : ""}</h2>
        <p class="muted" style="font-size:.85rem;margin-top:4px">
          ${projects.length} projects &middot; ${hiddenCount} hidden
        </p>
      </div>
    </div>
    <div class="table-wrap">
      <table id="tbl-settings">
        <thead><tr>${cols}</tr></thead>
        <tbody>${rows || empty}</tbody>
      </table>
    </div>`;
}

async function saveProjectSetting(btn, projectPath) {
  const row = btn.closest("tr");
  const nameInput = row.querySelector(".settings-name-input");
  const hiddenChk = row.querySelector(".settings-hidden-chk");

  btn.disabled = true;
  btn.textContent = "…";
  try {
    await fetchJSON("/api/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        project_path: projectPath,
        display_name: nameInput.value.trim() || null,
        hidden: hiddenChk.checked,
      }),
    });
    row.classList.toggle("settings-row-hidden", hiddenChk.checked);
    btn.textContent = "Saved";
    btn.classList.add("save-btn-ok");
    setTimeout(() => {
      btn.textContent = "Save";
      btn.classList.remove("save-btn-ok");
    }, 1500);
    // invalidate caches so tabs reload with new settings
    _summaryData = null;
    _projectsData = null;
    destroyCharts();
  } catch (e) {
    showToast("Save failed: " + e.message);
    btn.textContent = "Save";
  } finally {
    btn.disabled = false;
  }
}

// ── KPI rendering ──────────────────────────────────────────────────────────

function renderKPIs(d) {
  const totalTok = sumTokens(d.tokens_by_model || {});
  const kpis = [
    {
      label: "Sessions",
      value: fmt(d.total_sessions),
      sub: `${fmt(d.total_subagents || 0)} subagents`,
    },
    {
      label: "Est. API Cost",
      value: `<span class="cost">$${fmtCost(d.total_cost)}</span>`,
      sub: "equivalent, Claude API",
    },
    {
      label: "Total Tokens",
      value: `<span class="tokens">${fmtBig(totalTok.total)}</span>`,
      sub: `${fmtBig(totalTok.output)} output, ${fmtBig(totalTok.input)} input`,
    },
    {
      label: "User Rounds",
      value: fmt(d.total_rounds),
      sub: `${fmt(d.total_assistant_messages)} responses`,
    },
    {
      label: "API Time",
      value: fmtDur(d.total_api_ms),
      sub: "processing time",
    },
    {
      label: "Lines Added",
      value: fmt(d.total_lines_added),
      sub: `${fmt(d.total_lines_removed)} removed`,
    },
  ];
  document.getElementById("kpiGrid").innerHTML = kpis
    .map(
      (k) => `
    <div class="kpi">
      <div class="label">${k.label}</div>
      <div class="value">${k.value}</div>
      ${k.sub ? `<div class="sub">${k.sub}</div>` : ""}
    </div>`,
    )
    .join("");
}

// ── Charts ─────────────────────────────────────────────────────────────────

// ── Daily cost range selection ───────────────────────────────────────────────
let _dailyRange = "14"; // '7' | '14' | 'all' | 'custom'
let _customFrom = null; // 'YYYY-MM-DD'
let _customTo = null; // 'YYYY-MM-DD'

function _ymd(d) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

// Resolve the [start, end] (inclusive, 'YYYY-MM-DD') for the active range.
function _resolveRange(daily) {
  const firstDate = daily.length ? daily[0].date : _ymd(new Date());
  const lastDate = daily.length
    ? daily[daily.length - 1].date
    : _ymd(new Date());
  let start, end;
  if (_dailyRange === "all") {
    start = firstDate;
    end = lastDate;
  } else if (_dailyRange === "custom") {
    start = _customFrom || firstDate;
    end = _customTo || lastDate;
    if (start > end) {
      const t = start;
      start = end;
      end = t;
    }
  } else {
    const n = parseInt(_dailyRange, 10);
    const today = new Date();
    const startD = new Date(today);
    startD.setDate(startD.getDate() - (n - 1));
    start = _ymd(startD);
    end = _ymd(today);
  }
  return { start, end };
}

// Take the sparse daily rows (only days with activity) and produce a continuous,
// gap-filled series for the currently selected range.
function buildDailySeries(daily) {
  if (!daily.length) return [];
  const byDate = {};
  for (const d of daily) byDate[d.date] = d;
  const { start, end } = _resolveRange(daily);

  const out = [];
  const cur = new Date(start + "T00:00:00");
  const endDate = new Date(end + "T00:00:00");
  let guard = 0;
  while (cur <= endDate && guard < 3660) {
    // cap ~10 years
    const key = _ymd(cur);
    const rec = byDate[key];
    out.push({
      date: key,
      cost: rec ? rec.cost : 0,
      sessions: rec ? rec.sessions : 0,
    });
    cur.setDate(cur.getDate() + 1);
    guard++;
  }
  return out;
}

function setDailyRange(range) {
  _dailyRange = range;
  document
    .querySelectorAll("#rangeToggle .seg-opt")
    .forEach((b) => b.classList.toggle("active", b.dataset.range === range));
  // Reflect the resolved window in the date inputs; CSS decides visibility
  // (always shown on desktop, only in custom mode on mobile).
  const custom = document.getElementById("rangeCustom");
  if (custom) custom.classList.toggle("is-custom", range === "custom");
  _syncRangeInputs();
  if (_summaryData) renderDailyCost(_summaryData.daily || []);
}

// Keep the date inputs' bounds + values in sync with the active range.
function _syncRangeInputs() {
  const from = document.getElementById("rangeFrom");
  const to = document.getElementById("rangeTo");
  if (!from || !to) return;
  const daily = (_summaryData && _summaryData.daily) || [];
  const minDate = daily.length ? daily[0].date : null;
  const maxDate = _ymd(new Date());
  if (minDate) {
    from.min = minDate;
    to.min = minDate;
  }
  from.max = maxDate;
  to.max = maxDate;
  // For preset ranges, mirror the computed window so desktop users see it.
  if (_dailyRange !== "custom") {
    const { start, end } = _resolveRange(daily);
    from.value = start;
    to.value = end;
  } else {
    if (!from.value) from.value = _customFrom || _resolveRange(daily).start;
    if (!to.value) to.value = _customTo || maxDate;
    _customFrom = from.value || null;
    _customTo = to.value || null;
  }
}

function applyCustomRange() {
  _customFrom = document.getElementById("rangeFrom").value || null;
  _customTo = document.getElementById("rangeTo").value || null;
  _dailyRange = "custom";
  document
    .querySelectorAll("#rangeToggle .seg-opt")
    .forEach((b) => b.classList.toggle("active", b.dataset.range === "custom"));
  const custom = document.getElementById("rangeCustom");
  if (custom) custom.classList.add("is-custom");
  if (_summaryData) renderDailyCost(_summaryData.daily || []);
}

function renderDailyCost(daily) {
  destroyChart("dailyCostChart");
  const series = buildDailySeries(daily);
  if (!series.length) return;
  const light = document.documentElement.dataset.theme === "light";
  const gridColor = light ? "#e1e0d9" : "#383835";
  const sessionsColor = light ? "rgba(217,119,87,.18)" : "rgba(217,119,87,.25)";
  const isMobile = window.matchMedia("(max-width: 560px)").matches;
  _charts["dailyCostChart"] = new Chart(
    document.getElementById("dailyCostChart"),
    {
      type: "bar",
      data: {
        labels: series.map((d) => d.date),
        datasets: [
          {
            type: "line",
            label: "Cost (USD)",
            data: series.map((d) => d.cost || 0),
            borderColor: "#5a67f2",
            backgroundColor: "rgba(217,119,87,.15)",
            fill: true,
            tension: 0.35,
            pointRadius: series.length > 31 ? 0 : 3,
            pointHoverRadius: 5,
            yAxisID: "y",
            order: 1,
          },
          {
            type: "bar",
            label: "Sessions",
            data: series.map((d) => d.sessions || 0),
            backgroundColor: sessionsColor,
            borderColor: "rgba(217,119,87,.45)",
            borderWidth: 1,
            borderRadius: 3,
            yAxisID: "y2",
            order: 2,
          },
        ],
      },
      options: {
        responsive: true,
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: { title: (items) => items[0].label } },
        },
        scales: {
          y: {
            ticks: { callback: (v) => "$" + v.toFixed(2) },
            grid: { color: gridColor },
          },
          y2: {
            position: "right",
            ticks: { callback: (v) => Math.round(v) },
            grid: { display: false },
            title: {
              display: !isMobile,
              text: "DAILY SESSIONS",
              font: {
                size: 10,
                weight: "600",
                family: "Inter, ui-sans-serif, system-ui, sans-serif",
              },
              color: Chart.defaults.color,
              letterSpacing: "0.08em",
            },
          },
          x: {
            grid: { display: false },
            ticks: {
              autoSkip: true,
              maxRotation: isMobile ? 90 : 0,
              maxTicksLimit: isMobile ? 7 : 16,
              // show MM-DD to keep labels compact
              callback(value) {
                const lbl = this.getLabelForValue(value);
                return typeof lbl === "string" ? lbl.slice(5) : lbl;
              },
            },
          },
        },
      },
    },
  );
}

// Each model is its own donut slice, colored by family to match the model
// badges in the Sessions "Models" column (see .badge.* in styles.css). Models
// of the same family (e.g. Opus 4.7 and Opus 4.8) share the family color.
const MODEL_FAMILY_COLOR = {
  fable: "#f5c842",
  opus: "#b0a7f2",
  sonnet: "#ec835a",
  haiku: "#55bf50",
  other: "#9b9893",
};

function renderModelDonut(tokByModel) {
  destroyChart("modelDonut");
  const isCost = _donutMode === "cost";
  const entries = Object.entries(tokByModel)
    .filter(([m]) => m !== "<synthetic>")
    .map(([m, t]) => ({
      label: shortModel(m),
      color:
        MODEL_FAMILY_COLOR[modelClass(m) || "other"] ||
        MODEL_FAMILY_COLOR.other,
      tokens: (t.input || 0) + (t.output || 0) + (t.cache_read || 0),
      cost: modelCost(m, t),
    }))
    .sort((a, b) => (isCost ? b.cost - a.cost : b.tokens - a.tokens));
  if (!entries.length) return;
  _charts["modelDonut"] = new Chart(document.getElementById("modelDonut"), {
    type: "doughnut",
    data: {
      labels: entries.map((e) => e.label),
      datasets: [
        {
          data: entries.map((e) => (isCost ? e.cost : e.tokens)),
          backgroundColor: entries.map((e) => e.color),
          borderWidth: 0,
        },
      ],
    },
    options: {
      responsive: true,
      plugins: {
        legend: {
          position: "right",
          labels: {
            color: Chart.defaults.color,
            generateLabels(chart) {
              const ds = chart.data.datasets[0];
              return chart.data.labels.map((label, i) => ({
                text: isCost
                  ? `${label}  $${fmtCost(entries[i].cost)}`
                  : `${label}  ${fmtBig(entries[i].tokens)}`,
                fillStyle: ds.backgroundColor[i],
                strokeStyle: ds.backgroundColor[i],
                fontColor: Chart.defaults.color,
                lineWidth: 0,
                index: i,
              }));
            },
            font: { size: 11 },
            boxWidth: 10,
            padding: 10,
          },
        },
        tooltip: {
          callbacks: {
            label: (ctx) =>
              isCost
                ? ` $${fmtCost(entries[ctx.dataIndex].cost)}`
                : ` ${fmtBig(ctx.raw)} tokens`,
          },
        },
      },
    },
  });
}

function barPctPlugin(total, horizontal, extraLabels) {
  return {
    id: "barPct",
    afterDatasetDraw(chart) {
      const { ctx } = chart;
      const meta = chart.getDatasetMeta(0);
      ctx.save();
      ctx.fillStyle = Chart.defaults.color;
      meta.data.forEach((bar, i) => {
        const val = chart.data.datasets[0].data[i];
        if (!val || !total) return;
        const pct = ((val / total) * 100).toFixed(1) + "%";
        if (horizontal) {
          ctx.font = `600 10.5px Inter, ui-sans-serif, system-ui, sans-serif`;
          ctx.textAlign = "left";
          ctx.textBaseline = "middle";
          ctx.fillText(pct, bar.x + 5, bar.y);
        } else {
          const extra = extraLabels ? extraLabels[i] : null;
          if (extra) {
            ctx.font = `600 10.5px Inter, ui-sans-serif, system-ui, sans-serif`;
            ctx.textAlign = "center";
            ctx.textBaseline = "bottom";
            ctx.fillText(extra, bar.x, bar.y - 16);
            ctx.font = `500 10px Inter, ui-sans-serif, system-ui, sans-serif`;
            ctx.fillText(pct, bar.x, bar.y - 4);
          } else {
            ctx.font = `600 10.5px Inter, ui-sans-serif, system-ui, sans-serif`;
            ctx.textAlign = "center";
            ctx.textBaseline = "bottom";
            ctx.fillText(pct, bar.x, bar.y - 4);
          }
        }
      });
      ctx.restore();
    },
  };
}

function renderToolsBar(tools) {
  destroyChart("toolsBar");
  const top = Object.entries(tools)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 10);
  if (!top.length) return;
  const total = top.reduce((s, t) => s + t[1], 0);
  const gridColor =
    document.documentElement.dataset.theme === "light" ? "#e1e0d9" : "#383835";
  _charts["toolsBar"] = new Chart(document.getElementById("toolsBar"), {
    type: "bar",
    data: {
      labels: top.map((t) => t[0]),
      datasets: [
        {
          data: top.map((t) => t[1]),
          backgroundColor: PALETTE,
          borderRadius: 4,
        },
      ],
    },
    options: {
      indexAxis: "y",
      responsive: true,
      layout: { padding: { right: 48 } },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (ctx) =>
              ` ${fmt(ctx.raw)}  (${((ctx.raw / total) * 100).toFixed(1)}%)`,
          },
        },
      },
      scales: {
        x: { grid: { color: gridColor } },
        y: { grid: { display: false } },
      },
    },
    plugins: [barPctPlugin(total, true)],
  });
}

function renderProjectsBar(projects) {
  destroyChart("projectsBar");
  let el = document.getElementById("projectsBar");
  if (!el) return;
  if (el.tagName === "CANVAS") {
    const div = document.createElement("div");
    div.id = "projectsBar";
    el.parentNode.replaceChild(div, el);
    el = div;
  }
  if (!projects.length) {
    el.innerHTML = "";
    return;
  }
  const total = projects.reduce((s, p) => s + (p.cost || 0), 0);
  const max = Math.max(...projects.map((p) => p.cost || 0));
  el.innerHTML = projects
    .map((p, i) => {
      const cost = p.cost || 0;
      const pct = total > 0 ? ((cost / total) * 100).toFixed(1) : "0.0";
      const barW = max > 0 ? ((cost / max) * 100).toFixed(1) : "0";
      const color = PALETTE[i % PALETTE.length];
      const name = p.project_name || p.project_path || "—";
      return `<div class="proj-cost-row">
      <div class="proj-cost-label">${projTagHtml(name)}</div>
      <div class="proj-cost-bar-wrap"><div class="proj-cost-bar" style="width:${barW}%;background:${color}"></div></div>
      <div class="proj-cost-val">$${fmtCost(cost)}<span class="muted"> ${pct}%</span></div>
    </div>`;
    })
    .join("");
}

// ── Activity heatmap (weekday × hour) ────────────────────────────────────────

const HEAT_DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const HEAT_UNIT = { all: "Messages", turns: "Turns", prompts: "Prompts" };
let _heatPinned = false;

// Position + fill the floating tooltip for a given cell.
function _heatShowTip(cell) {
  const el = document.getElementById("activityHeatmap");
  const tip = el && el.querySelector(".heatmap-tip");
  if (!tip) return;
  const d = +cell.dataset.d,
    h = +cell.dataset.h,
    v = +cell.dataset.v;
  tip.querySelector(".heatmap-tip-head").textContent =
    `${HEAT_DAYS[d]} ${String(h).padStart(2, "0")}:00`;
  tip.querySelector(".heatmap-tip-label").textContent =
    HEAT_UNIT[_heatMode] || "Messages";
  tip.querySelector(".heatmap-tip-val").textContent = v;
  const below = cell.offsetTop < 56; // flip under the cell near the top edge
  tip.classList.toggle("below", below);
  tip.style.left = cell.offsetLeft + cell.offsetWidth / 2 + "px";
  tip.style.top =
    (below ? cell.offsetTop + cell.offsetHeight : cell.offsetTop) + "px";
  tip.classList.add("show");
}

// Bind hover/click tooltip behavior once; #activityHeatmap persists across
// re-renders (only its innerHTML changes), so the guard prevents duplicates.
function _wireHeatmap() {
  const el = document.getElementById("activityHeatmap");
  if (!el || el.dataset.wired) return;
  el.dataset.wired = "1";
  const hide = () => {
    const tip = el.querySelector(".heatmap-tip");
    if (tip) tip.classList.remove("show");
  };
  el.addEventListener("mouseover", (e) => {
    const cell = e.target.closest(".heatmap-cell");
    if (cell && !_heatPinned) _heatShowTip(cell);
  });
  el.addEventListener("mouseleave", () => {
    if (!_heatPinned) hide();
  });
  el.addEventListener("click", (e) => {
    const cell = e.target.closest(".heatmap-cell");
    if (!cell) return;
    _heatPinned = true;
    _heatShowTip(cell);
  });
  // Click anywhere outside a cell dismisses a pinned tooltip.
  document.addEventListener("click", (e) => {
    if (_heatPinned && !e.target.closest("#activityHeatmap .heatmap-cell")) {
      hide();
      _heatPinned = false;
    }
  });
}

function renderActivityHeatmap(activity) {
  const el = document.getElementById("activityHeatmap");
  if (!el) return;
  _heatPinned = false;
  // `activity` is {all, turns, prompts} each a [{dow,hour,count}] list.
  // Tolerate a bare array (legacy) by treating it as the "all" series.
  const series = Array.isArray(activity)
    ? activity
    : (activity && activity[_heatMode]) || [];
  const grid = Array.from({ length: 7 }, () => new Array(24).fill(0));
  let max = 0;
  for (const a of series) {
    const d = a.dow,
      h = a.hour;
    if (d >= 0 && d < 7 && h >= 0 && h < 24) {
      grid[d][h] += a.count || 0;
      if (grid[d][h] > max) max = grid[d][h];
    }
  }
  if (!max) {
    el.innerHTML =
      '<p class="muted" style="padding:16px 4px">No activity yet.</p>';
    return;
  }
  const days = HEAT_DAYS;
  const order = [1, 2, 3, 4, 5, 6, 0]; // Mon..Sun
  const accent = "#5a67f2";
  let html = '<div class="heatmap">';
  html += '<div class="heatmap-row"><div class="heatmap-daylabel"></div>';
  for (let h = 0; h < 24; h++)
    html += `<div class="heatmap-hourlabel">${h % 6 === 0 ? h : ""}</div>`;
  html += "</div>";
  for (const d of order) {
    html += `<div class="heatmap-row"><div class="heatmap-daylabel">${days[d]}</div>`;
    for (let h = 0; h < 24; h++) {
      const v = grid[d][h];
      const op = v ? (0.18 + (0.82 * v) / max).toFixed(3) : 0;
      const style = v ? `background:${accent};opacity:${op}` : "";
      html += `<div class="heatmap-cell" data-d="${d}" data-h="${h}" data-v="${v}" style="${style}"></div>`;
    }
    html += "</div>";
  }
  html += "</div>";
  html +=
    '<div class="heatmap-tip">' +
    '<div class="heatmap-tip-head"></div>' +
    '<div class="heatmap-tip-row">' +
    '<span class="heatmap-tip-dot"></span>' +
    '<span class="heatmap-tip-label"></span>' +
    '<span class="heatmap-tip-val"></span>' +
    "</div></div>";
  el.innerHTML = html;
  _wireHeatmap();
}

// ── Autonomy profile (permission modes) ──────────────────────────────────────

function renderAutonomyDonut(modes) {
  destroyChart("autonomyDonut");
  const el = document.getElementById("autonomyDonut");
  if (!el) return;
  const entries = Object.entries(modes)
    .filter((e) => e[1] > 0)
    .sort((a, b) => b[1] - a[1]);
  if (!entries.length) return;
  const total = entries.reduce((s, e) => s + e[1], 0);
  _charts["autonomyDonut"] = new Chart(el, {
    type: "doughnut",
    data: {
      labels: entries.map((e) => e[0]),
      datasets: [
        {
          data: entries.map((e) => e[1]),
          backgroundColor: PALETTE,
          borderWidth: 0,
        },
      ],
    },
    options: {
      responsive: true,
      cutout: "60%",
      plugins: {
        legend: { position: "bottom", labels: { boxWidth: 12, padding: 12 } },
        tooltip: {
          callbacks: {
            label: (ctx) =>
              ` ${ctx.label}: ${fmt(ctx.raw)} (${((ctx.raw / total) * 100).toFixed(1)}%)`,
          },
        },
      },
    },
  });
}

// ── Skills invoked ───────────────────────────────────────────────────────────

function renderSkillsBar(skills) {
  destroyChart("skillsBar");
  const canvas = document.getElementById("skillsBar");
  const empty = document.getElementById("skillsEmpty");
  const top = Object.entries(skills)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 10);
  if (!top.length) {
    if (canvas) canvas.style.display = "none";
    if (empty) empty.style.display = "block";
    return;
  }
  if (canvas) canvas.style.display = "";
  if (empty) empty.style.display = "none";
  const total = top.reduce((s, t) => s + t[1], 0);
  const gridColor =
    document.documentElement.dataset.theme === "light" ? "#e1e0d9" : "#383835";
  const shortSkill = (n) => {
    const p = n.split(":");
    return p[p.length - 1];
  };
  _charts["skillsBar"] = new Chart(canvas, {
    type: "bar",
    data: {
      labels: top.map((t) => shortSkill(t[0])),
      datasets: [
        {
          data: top.map((t) => t[1]),
          backgroundColor: PALETTE,
          borderRadius: 4,
        },
      ],
    },
    options: {
      indexAxis: "y",
      responsive: true,
      layout: { padding: { right: 48 } },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (ctx) =>
              ` ${fmt(ctx.raw)}  (${((ctx.raw / total) * 100).toFixed(1)}%)`,
          },
        },
      },
      scales: {
        x: { grid: { color: gridColor } },
        y: { grid: { display: false } },
      },
    },
    plugins: [barPctPlugin(total, true)],
  });
}

// ── Projects table ─────────────────────────────────────────────────────────

function renderProjectsTable(projects) {
  const cols = [
    { key: "project_name", label: "Project" },
    { key: "session_count", label: "Sessions", right: true },
    { key: "cost_usd", label: "Est. Cost", right: true },
    { key: "tokens_total", label: "Tokens", right: true },
    { key: "user_rounds", label: "Rounds", right: true },
    { key: "code_lines_added", label: "Lines +", right: true },
    { key: "last_active", label: "Last Active" },
  ];
  const data = projects.map((p) => ({
    ...p,
    tokens_total: sumTokens(p.tokens_by_model || {}).total,
  }));
  document.getElementById("projectsContent").innerHTML = makeTable(
    "projects",
    cols,
    data,
    renderProjectRow,
    onProjectClick,
  );
  initSort(
    "projects",
    cols,
    data,
    renderProjectRow,
    "projectsContent",
    onProjectClick,
  );
}

function renderProjectRow(p) {
  const key = p.project_name || p.project_path;
  const paths = p.project_paths || [p.project_path];
  const pathsHtml = paths
    .map(
      (path) =>
        `<span class="muted mono" style="font-size:.75rem">${esc(path || "")}</span>`,
    )
    .join("<br>");
  return `<tr onclick="openProject(${esc(JSON.stringify(key))})">
    <td><strong>${projTagHtml(p.project_name || p.project_path)}</strong><br>${pathsHtml}</td>
    <td class="right">${fmt(p.session_count)}</td>
    <td class="right cost">$${fmtCost(p.cost_usd)}</td>
    <td class="right tokens">${fmtBig(p.tokens_total)}</td>
    <td class="right">${fmt(p.user_rounds)}</td>
    <td class="right">${fmt(p.code_lines_added)}</td>
    <td>${fmtDate(p.last_active)}</td>
  </tr>`;
}

function onProjectClick(row) {
  openProject(row.project_name || row.project_path.split("/").pop());
}

async function openProject(projectName, _pushUrl = true) {
  if (_pushUrl) {
    history.pushState(
      { tab: "sessions", project: projectName },
      "",
      "/sessions?project=" + encodeURIComponent(projectName),
    );
  }
  showTab("sessions", false);
  document.getElementById("sessionsContent").innerHTML =
    `<div class="loading"><div class="spinner"></div> Loading…</div>`;
  try {
    let proj;
    if (IS_REMOTE) {
      if (!_projectsData)
        _projectsData = await fetchJSON("/data/projects.json");
      if (!_sessionsData)
        _sessionsData = await fetchJSON("/data/sessions.json");
      const grouped = groupProjectsByName(_projectsData);
      const found = grouped.find(
        (p) => (p.project_name || p.project_path) === projectName,
      );
      if (!found) throw new Error("Project not found: " + projectName);
      const paths = found.project_paths || [found.project_path];
      proj = {
        ...found,
        sessions: _sessionsData.filter((s) => paths.includes(s.project_path)),
      };
    } else {
      proj = await fetchJSON(
        "/api/project?name=" + encodeURIComponent(projectName),
      );
    }
    const sessions = proj.sessions || [];
    const displayName = proj.project_name || proj.project_path;
    const paths = proj.project_paths || [proj.project_path];
    const pathsHtml = paths
      .map(
        (path) =>
          `<span class="muted" style="font-size:.85rem">${esc(path || "")}</span>`,
      )
      .join("<br>");
    const backBtn = `<button class="back-btn" onclick="goAllSessions()">← All Sessions</button>`;
    const heading = `<div style="margin-bottom:16px"><h2 style="font-size:1.1rem">${projTagHtml(displayName)}</h2>
      ${pathsHtml}</div>`;
    const summary = buildProjectSummary(proj);
    const cols = sessionCols();
    const sortedSessions = [...sessions].sort((a, b) =>
      String(b.ended_at || "").localeCompare(String(a.ended_at || "")),
    );
    const html =
      backBtn +
      heading +
      summary +
      makeTable("proj-sessions", cols, sortedSessions, renderSessionRow, (s) =>
        openSessionModal(s.session_id),
      );
    document.getElementById("sessionsContent").innerHTML = html;
    initSort(
      "proj-sessions",
      cols,
      sortedSessions,
      renderSessionRow,
      "sessionsContent",
      (s) => openSessionModal(s.session_id),
      0,
      -1,
    );
  } catch (e) {
    document.getElementById("sessionsContent").innerHTML =
      `<p class="muted">Error: ${e.message}</p>`;
  }
}

function buildProjectSummary(proj) {
  const tok = sumTokens(proj.tokens_by_model || {});
  const tools = proj.tools || {};
  const topTools = Object.entries(tools)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 8);

  const kpis = [
    { label: "Sessions", value: fmt(proj.session_count) },
    {
      label: "Est. API Cost",
      value: `<span class="cost">$${fmtCost(proj.cost_usd)}</span>`,
    },
    {
      label: "Total Tokens",
      value: `<span class="tokens">${fmtBig(tok.total)}</span>`,
      sub: `${fmtBig(tok.output)} output, ${fmtBig(tok.input)} input`,
    },
    { label: "User Rounds", value: fmt(proj.user_rounds) },
    { label: "API Time", value: fmtDur(proj.api_duration_ms) },
    {
      label: "Lines Added",
      value: fmt(proj.code_lines_added),
      sub: `${fmt(proj.code_lines_removed)} removed`,
    },
    { label: "First Session", value: fmtDate(proj.first_active) },
    { label: "Last Session", value: fmtDate(proj.last_active) },
  ];

  const projModelEntries = Object.entries(proj.tokens_by_model || {})
    .filter(([m]) => m !== "<synthetic>")
    .sort((a, b) => sumObj(b[1]) - sumObj(a[1]));
  const modelRows =
    projModelEntries
      .map(([m, t]) => {
        const cost = modelCost(m, t);
        return `<div class="model-row model-row-2">
      <div class="model-row-top">
        <span class="badge ${modelClass(m)}">${shortModel(m)}</span>
        <span class="muted" style="font-size:.8rem">${fmtBig(t.input || 0)} in / ${fmtBig(t.output || 0)} out / ${fmtBig(t.cache_read || 0)} cache_read / ${fmtBig((t.cache_write_5m || 0) + (t.cache_write_1h || 0))} cache_write</span>
        <span class="tokens" style="margin-left:auto">${fmtBig(sumObj(t))} total</span>
      </div>
      <div class="model-row-cost">
        <span class="muted" style="font-size:.72rem">Est. API Cost</span>
        <span class="cost" style="font-size:.85rem">$${fmtCost(cost)}</span>
      </div>
    </div>`;
      })
      .join("") || '<span class="muted">No token data</span>';
  const projTotalCost = projModelEntries.reduce(
    (s, [m, t]) => s + modelCost(m, t),
    0,
  );
  const projCostSummary =
    projModelEntries.length > 1
      ? `<div class="model-row" style="border-top:1px solid var(--border);margin-top:4px;padding-top:8px">
        <span class="muted" style="font-size:.78rem">Total Est. Cost</span>
        <span class="cost" style="margin-left:auto">$${fmtCost(projTotalCost)}</span>
       </div>`
      : "";

  const toolPills = topTools
    .map(
      ([n, c]) =>
        `<span class="tool-pill">${esc(n)} <strong>×${c}</strong></span>`,
    )
    .join("");

  return `
    <div class="chart-card" style="margin-bottom:20px">
      <div class="kpi-grid" style="margin-bottom:16px">${kpis
        .map(
          (k) => `<div class="kpi">
          <div class="label">${k.label}</div>
          <div class="value" style="font-size:1.4rem">${k.value}</div>
          ${k.sub ? `<div class="sub">${k.sub}</div>` : ""}
        </div>`,
        )
        .join("")}</div>
      <div class="proj-summary-grid">
        <div>
          <div class="section-title" style="margin-top:0;padding-top:0;border-top:none">Tokens &amp; Est. Cost by Model</div>
          ${modelRows}${projCostSummary}
        </div>
        <div>
          <div class="section-title" style="margin-top:0;padding-top:0;border-top:none">Tool Usage</div>
          <div class="tool-pills">${toolPills || '<span class="muted">None</span>'}</div>
        </div>
      </div>
    </div>`;
}

function sumObj(o) {
  return Object.values(o || {}).reduce((a, v) => a + (v || 0), 0);
}

// ── Sessions table ─────────────────────────────────────────────────────────

function renderSessionsTable(sessions) {
  const cols = sessionCols();
  const sorted = [...sessions].sort((a, b) =>
    String(b.ended_at || "").localeCompare(String(a.ended_at || "")),
  );
  document.getElementById("sessionsContent").innerHTML = makeTable(
    "sessions",
    cols,
    sorted,
    renderSessionRow,
    (s) => openSessionModal(s.session_id),
  );
  initSort(
    "sessions",
    cols,
    sorted,
    renderSessionRow,
    "sessionsContent",
    (s) => openSessionModal(s.session_id),
    0,
    -1,
  );
}

function sessionCols() {
  return [
    { key: "ended_at", label: "Last Updated" },
    { key: "started_at", label: "Started" },
    { key: "project_name", label: "Project" },
    { key: "wall_duration_ms", label: "Duration", right: true },
    { key: "user_rounds", label: "Rounds", right: true },
    { key: "assistant_messages", label: "Responses", right: true },
    { key: "cost_usd", label: "Est. Cost", right: true },
    { key: "code_lines_added", label: "Lines +", right: true },
    { key: "models", label: "Model(s)" },
  ];
}

function renderSessionRow(s) {
  const models = Object.keys(s.tokens_by_model || {}).filter(
    (m) => m !== "<synthetic>",
  );
  const modelBadges = models
    .map((m) => `<span class="badge ${modelClass(m)}">${shortModel(m)}</span>`)
    .join(" ");
  const isRecent =
    s.ended_at &&
    Date.now() - new Date(s.ended_at).getTime() < 2 * 60 * 60 * 1000;
  return `<tr class="${isRecent ? "row-active" : ""}" onclick="openSessionModal('${esc(s.session_id)}')">
    <td class="mono">${fmtDate(s.ended_at)}</td>
    <td class="mono">${fmtDate(s.started_at)}</td>
    <td>${s.project_name ? projTagHtml(s.project_name) : "—"}</td>
    <td class="right">${fmtDur(s.wall_duration_ms)}</td>
    <td class="right">${fmt(s.user_rounds)}</td>
    <td class="right">${fmt(s.assistant_messages)}</td>
    <td class="right cost">$${fmtCost(s.cost_usd)}</td>
    <td class="right">${fmt(s.code_lines_added)}</td>
    <td>${modelBadges || '<span class="muted">—</span>'}</td>
  </tr>`;
}

// ── Session modal ──────────────────────────────────────────────────────────

async function openSessionModal(sessionId) {
  document.getElementById("modalOverlay").classList.add("open");
  document.getElementById("modalContent").innerHTML =
    `<div class="loading"><div class="spinner"></div> Loading…</div>`;
  try {
    const s = await fetchJSON(
      IS_REMOTE
        ? "/data/sessions/" + sessionId + ".json"
        : "/api/sessions/" + sessionId,
    );
    document.getElementById("modalContent").innerHTML = buildSessionModal(s);
  } catch (e) {
    document.getElementById("modalContent").innerHTML =
      `<p class="muted">Error: ${e.message}</p>`;
  }
}

// Branch cell: primary (most-active) branch, plus "+N" and the full list of
// other branches the session touched, ordered by activity.
function branchValueHtml(s) {
  const primary = `<span class="mono">${esc(s.git_branch)}</span>`;
  const branches = s.branches || {};
  const others = Object.entries(branches)
    .sort((a, b) => b[1] - a[1])
    .map((e) => e[0])
    .filter((n) => n !== s.git_branch);
  if (!others.length) return primary;
  return `${primary} <span class="muted">+${others.length}</span>
    <div class="muted mono" style="font-size:.72rem;margin-top:3px;line-height:1.5">${others.map(esc).join(", ")}</div>`;
}

function buildSessionModal(s) {
  const tok = s.tokens_by_model || {};
  const models = Object.keys(tok).filter((m) => m !== "<synthetic>");
  const tools = s.tools || {};

  const details = [
    {
      label: "Session ID",
      value: `<span class="mono" style="font-size:.78rem">${esc(s.session_id)}</span>`,
    },
    {
      label: "Project",
      value: s.project_name ? projTagHtml(s.project_name) : "—",
    },
    ...(s.git_branch
      ? [{ label: "Git Branch", value: branchValueHtml(s) }]
      : []),
    { label: "Started", value: fmtDateFull(s.started_at) },
    { label: "Ended", value: fmtDateFull(s.ended_at) },
    { label: "Wall Duration", value: fmtDur(s.wall_duration_ms) },
    { label: "API Processing", value: fmtDur(s.api_duration_ms) },
    { label: "User Rounds", value: fmt(s.user_rounds) },
    { label: "Assistant Responses", value: fmt(s.assistant_messages) },
    { label: "Code Lines Added", value: fmt(s.code_lines_added) },
    { label: "Code Lines Removed", value: fmt(s.code_lines_removed) },
    { label: "Subagents", value: fmt(s.subagent_count) },
    {
      label: "Est. API Cost",
      value: `<span class="cost">$${fmtCost(s.cost_usd)}</span>`,
    },
  ];

  let modelRows =
    models
      .map((m) => {
        const t = tok[m];
        const total =
          (t.input || 0) +
          (t.output || 0) +
          (t.cache_read || 0) +
          (t.cache_write_5m || 0) +
          (t.cache_write_1h || 0);
        const cost = modelCost(m, t);
        return `<div class="model-row model-row-2">
      <div class="model-row-top">
        <span class="badge ${modelClass(m)}">${shortModel(m)}</span>
        <span class="muted">${fmtBig(t.input || 0)} in / ${fmtBig(t.output || 0)} out / ${fmtBig(t.cache_read || 0)} cache_read / ${fmtBig((t.cache_write_5m || 0) + (t.cache_write_1h || 0))} cache_write</span>
        <span class="tokens" style="margin-left:auto">${fmtBig(total)} total</span>
      </div>
      <div class="model-row-cost">
        <span class="muted" style="font-size:.72rem">Est. API Cost</span>
        <span class="cost" style="font-size:.85rem">$${fmtCost(cost)}</span>
      </div>
    </div>`;
      })
      .join("") || '<span class="muted">No token data</span>';
  const totalCost = models.reduce((s, m) => s + modelCost(m, tok[m] || {}), 0);
  const costSummary =
    models.length > 1
      ? `<div class="model-row" style="border-top:1px solid var(--border);margin-top:4px;padding-top:8px">
        <span class="muted" style="font-size:.78rem">Total Est. Cost</span>
        <span class="cost" style="margin-left:auto">$${fmtCost(totalCost)}</span>
       </div>`
      : "";

  const topTools = Object.entries(tools).sort((a, b) => b[1] - a[1]);
  const toolPills = topTools
    .map(([n, c]) => `<span class="tool-pill">${esc(n)} ×${c}</span>`)
    .join("");

  // Header: prefer the session's custom title. Subtitle is the AI summary when
  // available; sessions without one in session_summary.json show no subtitle.
  const heading = s.custom_title ? esc(s.custom_title) : "Session Detail";
  const subtitle = s.summary
    ? `<p class="modal-subtitle session-summary">${esc(s.summary)}</p>`
    : "";

  // Activity & reliability mini-stats
  const bashSub = s.bash_interrupted
    ? ` <span class="muted">(${fmt(s.bash_interrupted)} interrupted)</span>`
    : "";
  const statCards = [
    { label: "Bash Commands", value: fmt(s.bash_count || 0) + bashSub },
    { label: "Tool Errors", value: fmt(s.tool_errors || 0) },
    { label: "Rejections", value: fmt(s.user_rejections || 0) },
    { label: "Git Operations", value: fmt(s.git_operations || 0) },
    { label: "Tasks Completed", value: fmt(s.tasks_completed || 0) },
  ];
  const statGrid = `<div class="detail-grid">${statCards
    .map(
      (c) => `
      <div class="detail-item">
        <div class="label">${c.label}</div>
        <div class="value">${c.value}</div>
      </div>`,
    )
    .join("")}</div>`;

  // Autonomy (permission modes) and skills
  const pmPills = Object.entries(s.permission_modes || {})
    .sort((a, b) => b[1] - a[1])
    .map(([m, c]) => `<span class="tool-pill">${esc(m)} ×${c}</span>`)
    .join("");
  const skillPills = Object.entries(s.skills_used || {})
    .sort((a, b) => b[1] - a[1])
    .map(([n, c]) => `<span class="tool-pill">${esc(n)} ×${c}</span>`)
    .join("");
  const autonomySection = pmPills
    ? `<div class="section-title">Autonomy (Permission Modes)</div>
       <div class="tool-pills">${pmPills}</div>`
    : "";
  const skillsSection = skillPills
    ? `<div class="section-title">Skills Invoked</div>
       <div class="tool-pills">${skillPills}</div>`
    : "";

  return `
    <h2>${heading}</h2>${subtitle}
    <div class="detail-grid">${details
      .map(
        (d) => `
      <div class="detail-item">
        <div class="label">${d.label}</div>
        <div class="value">${d.value}</div>
      </div>`,
      )
      .join("")}
    </div>
    <div class="section-title">Activity &amp; Reliability</div>
    ${statGrid}
    <div class="section-title">Tokens &amp; Est. API Cost by Model</div>
    ${modelRows}${costSummary}
    <div class="section-title">Tool Usage</div>
    <div class="tool-pills">${toolPills || '<span class="muted">None</span>'}</div>
    ${autonomySection}
    ${skillsSection}
  `;
}

function closeModal(e) {
  if (!e || e.target === document.getElementById("modalOverlay")) {
    document.getElementById("modalOverlay").classList.remove("open");
  }
}

// ── Table helpers ──────────────────────────────────────────────────────────

function makeTable(id, cols, data, rowFn, clickFn) {
  const headers = cols
    .map(
      (c, i) =>
        `<th onclick="sortTable('${id}',${i})" class="${c.right ? "right" : ""}">
      ${c.label} <span class="sort-arrow">↕</span>
    </th>`,
    )
    .join("");
  const rows = data.map(rowFn).join("");
  return `<div class="table-wrap"><table id="tbl-${id}">
    <thead><tr>${headers}</tr></thead>
    <tbody>${rows || '<tr><td colspan="${cols.length}" class="muted" style="padding:20px">No data</td></tr>'}</tbody>
  </table></div>`;
}

function initSort(
  id,
  cols,
  initialData,
  rowFn,
  containerId,
  clickFn,
  defaultCol = null,
  defaultDir = -1,
) {
  _sortState[id] = {
    col: defaultCol,
    dir: defaultDir,
    data: initialData,
    cols,
    rowFn,
    containerId,
    clickFn,
  };
  if (defaultCol !== null) {
    const tbl = document.getElementById("tbl-" + id);
    if (tbl) {
      const th = tbl.querySelectorAll("thead th")[defaultCol];
      if (th) {
        th.classList.add("sorted");
        th.querySelector(".sort-arrow").textContent =
          defaultDir > 0 ? "↑" : "↓";
      }
    }
  }
}

function sortTable(id, colIdx) {
  const st = _sortState[id];
  if (!st) return;
  const col = st.cols[colIdx];
  if (st.col === colIdx) st.dir *= -1;
  else {
    st.col = colIdx;
    st.dir = 1;
  }

  const key = col.key;
  st.data = [...st.data].sort((a, b) => {
    const av = a[key] ?? "";
    const bv = b[key] ?? "";
    if (typeof av === "number" || typeof bv === "number")
      return ((Number(av) || 0) - (Number(bv) || 0)) * st.dir;
    return String(av).localeCompare(String(bv)) * st.dir;
  });

  // Re-render table body
  const tbl = document.getElementById("tbl-" + id);
  if (!tbl) return;
  tbl.querySelector("tbody").innerHTML = st.data.map(st.rowFn).join("");
  // Mark sorted header
  tbl.querySelectorAll("thead th").forEach((th, i) => {
    th.classList.toggle("sorted", i === colIdx);
    const arrow = th.querySelector(".sort-arrow");
    if (i === colIdx) arrow.textContent = st.dir > 0 ? "↑" : "↓";
    else arrow.textContent = "↕";
  });
}

// ── Utilities ──────────────────────────────────────────────────────────────

async function fetchJSON(url, opts = {}) {
  // In remote mode all fetches are static JSON files — bypass the browser cache so
  // a fresh deploy is always visible immediately.
  if (IS_REMOTE && !opts.method) opts = { ...opts, cache: "no-store" };
  const r = await fetch(url, opts);
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}

function sumTokens(tokByModel) {
  let input = 0,
    output = 0,
    cacheRead = 0,
    cacheWrite = 0,
    total = 0;
  for (const [m, t] of Object.entries(tokByModel)) {
    if (m === "<synthetic>") continue;
    input += t.input || 0;
    output += t.output || 0;
    cacheRead += t.cache_read || 0;
    cacheWrite += (t.cache_write_5m || 0) + (t.cache_write_1h || 0);
  }
  total = input + output + cacheRead + cacheWrite;
  return { input, output, cacheRead, cacheWrite, total };
}

function fmt(n) {
  return n == null ? "—" : Number(n).toLocaleString();
}
function fmtBig(n) {
  if (n == null) return "—";
  if (n >= 1e9) return (n / 1e9).toFixed(4) + "B";
  if (n >= 1e6) return (n / 1e6).toFixed(1) + "M";
  if (n >= 1e3) return (n / 1e3).toFixed(1) + "K";
  return String(n);
}
function fmtCost(n) {
  if (n == null || n === 0) return "0.00";
  return Number(n).toFixed(n < 0.01 ? 4 : 2);
}
function fmtDur(ms) {
  if (!ms) return "—";
  const s = Math.round(ms / 1000);
  if (s < 60) return s + "s";
  const m = Math.floor(s / 60),
    rem = s % 60;
  if (m < 60) return m + "m " + rem + "s";
  return Math.floor(m / 60) + "h " + (m % 60) + "m";
}
function fmtDate(ts) {
  if (!ts) return "—";
  try {
    const d = new Date(ts);
    const mm = String(d.getMonth() + 1).padStart(2, "0");
    const dd = String(d.getDate()).padStart(2, "0");
    const hh = String(d.getHours()).padStart(2, "0");
    const min = String(d.getMinutes()).padStart(2, "0");
    return `${d.getFullYear()}-${mm}-${dd} ${hh}:${min}`;
  } catch {
    return ts;
  }
}
function fmtDateFull(ts) {
  if (!ts) return "—";
  try {
    const d = new Date(ts);
    const mm = String(d.getMonth() + 1).padStart(2, "0");
    const dd = String(d.getDate()).padStart(2, "0");
    const hh = String(d.getHours()).padStart(2, "0");
    const min = String(d.getMinutes()).padStart(2, "0");
    const ss = String(d.getSeconds()).padStart(2, "0");
    return `${d.getFullYear()}-${mm}-${dd} ${hh}:${min}:${ss}`;
  } catch {
    return ts;
  }
}
function esc(s) {
  // Escapes single quotes too: several call sites interpolate esc() output into
  // single-quoted inline handlers, e.g. onclick="openSessionModal('${esc(id)}')",
  // where an unescaped ' would break out of the JS string literal.
  return String(s || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function shortModel(m) {
  if (!m) return "?";
  m = m.toLowerCase();
  if (m.includes("fable-5")) return "Fable 5";
  if (m.includes("opus-4-8")) return "Opus 4.8";
  if (m.includes("opus-4-7")) return "Opus 4.7";
  if (m.includes("opus-4-6")) return "Opus 4.6";
  if (m.includes("opus-4-5")) return "Opus 4.5";
  if (m.includes("opus-4-1")) return "Opus 4.1";
  if (m.includes("opus-4")) return "Opus 4";
  if (m.includes("sonnet-4-6")) return "Sonnet 4.6";
  if (m.includes("sonnet-4-5")) return "Sonnet 4.5";
  if (m.includes("sonnet-4")) return "Sonnet 4";
  if (m.includes("haiku-4-5")) return "Haiku 4.5";
  if (m.includes("haiku-3-5")) return "Haiku 3.5";
  return m.slice(0, 12);
}
function modelClass(m) {
  m = (m || "").toLowerCase();
  if (m.includes("fable")) return "fable";
  if (m.includes("opus")) return "opus";
  if (m.includes("sonnet")) return "sonnet";
  if (m.includes("haiku")) return "haiku";
  return "";
}

// ── Project tag helpers ────────────────────────────────────────────────────
const _TAG_PALETTE = [
  "#6366f1",
  "#f59e0b",
  "#10b981",
  "#ef4444",
  "#8b5cf6",
  "#06b6d4",
  "#f97316",
  "#ec4899",
  "#84cc16",
  "#14b8a6",
  "#a855f7",
  "#0ea5e9",
];
function parseTag(name) {
  if (!name) return { tag: null, title: name || "" };
  const i = name.indexOf("/");
  return i > 0
    ? { tag: name.slice(0, i), title: name.slice(i + 1) }
    : { tag: null, title: name };
}
function tagColor(tag) {
  let h = 0;
  for (let i = 0; i < tag.length; i++)
    h = (Math.imul(31, h) + tag.charCodeAt(i)) | 0;
  return _TAG_PALETTE[Math.abs(h) % _TAG_PALETTE.length];
}
function projTagHtml(name) {
  const { tag, title } = parseTag(name);
  if (!tag) return esc(name);
  const c = tagColor(tag);
  return `<span class="proj-tag" style="background:${c}26;color:${c};border-color:${c}55">${esc(tag)}</span>${esc(title)}`;
}
function projTagLabel(name) {
  const { tag, title } = parseTag(name);
  return tag ? `[${tag}] ${title}` : name || "";
}

function destroyChart(id) {
  if (_charts[id]) {
    _charts[id].destroy();
    delete _charts[id];
  }
}
function destroyCharts() {
  Object.keys(_charts).forEach(destroyChart);
}

function showToast(msg) {
  const el = document.getElementById("toast");
  el.textContent = msg;
  el.classList.add("show");
  setTimeout(() => el.classList.remove("show"), 3000);
}

// ── Boot ────────────────────────────────────────────────────────────────────
if (IS_REMOTE) _initRemoteHeader();
navigateFromUrl();

function _initRemoteHeader() {
  const btn = document.getElementById("refreshBtn");
  if (!btn) return;
  const label = document.createElement("span");
  label.id = "lastUpdatedLabel";
  label.className = "last-updated-label";
  label.textContent = "…";
  btn.replaceWith(label);
  fetchJSON("/data/meta.json")
    .then((m) => {
      if (m?.updated_at) {
        _showLastUpdated(m.updated_at);
        setInterval(() => _showLastUpdated(m.updated_at), 60000);
      }
    })
    .catch(() => {});
}

function _showLastUpdated(isoStr) {
  const el = document.getElementById("lastUpdatedLabel");
  if (!el) return;
  const mins = Math.floor((Date.now() - new Date(isoStr).getTime()) / 60000);
  el.textContent =
    mins < 1
      ? "Just updated"
      : mins < 60
        ? `Updated ${mins}m ago`
        : `Updated ${Math.floor(mins / 60)}h ${mins % 60}m ago`;
}

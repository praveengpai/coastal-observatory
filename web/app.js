/* Kochi Coastal One Health Observatory: dashboard client. No external libraries. */
(function () {
  "use strict";

  const S = {
    token: null, user: null, tab: null, layer: "combined", site: null, includeTest: false,
    scen: { rain_mm: 80, tide_m: 1.1, temp_c: 32, rh: 78 }, dataset: "samples", siteType: "",
    query: null, done: {}, cache: {}, rid: 0, rform: "", rdays: 90, wyear: "",
  };
  const TABS = { master: "Master dashboard", asha: "ASHA / field", ward: "Ward member",
    science: "Scientist", reports: "Household reports", advisories: "Advisories", admin: "Admin" };
  const ROLE_TABS = {
    admin: ["master", "asha", "ward", "science", "reports", "advisories", "admin"],
    coordinator: ["master", "asha", "ward", "science", "reports", "advisories", "admin"],
    scientist: ["master", "science", "reports"], doctor: ["master", "reports", "advisories", "asha"],
    asha: ["asha", "reports", "advisories"], ward: ["ward", "reports"],
  };
  const ROLE_NAMES = { admin: "Admin", coordinator: "Coordinator", scientist: "Scientist", doctor: "Doctor",
    asha: "ASHA", ward: "Ward member" };
  const ANALYSTS = ["admin", "coordinator", "scientist", "doctor"];
  const LAYERS = [["combined", "Combined"], ["water", "Water"], ["illness", "Illness"], ["salinity", "Salinity"],
    ["heat", "Heat"], ["vulnerability", "Elder vulnerability"]];
  const LAYER_NOTE = { combined: "Highest of all layers", water: "Positive samples, 8 weeks (NIO lab, else Aquadip©)",
    illness: "Diarrhoea reports per 100 households visited, 4 weeks", salinity: "Median water TDS",
    heat: "Highest heat index, next 3 days", vulnerability: "Share of screened 60+ living alone, needing evacuation help or frail" };

  const $ = (sel) => document.querySelector(sel);
  const view = () => $("#view");

  // ---------------------------------------------------------------- helpers
  function esc(v) {
    return String(v == null ? "" : v).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }
  const pct = (x) => (x == null ? "–" : Math.round(x * 100) + "%");
  const num = (x, d = 0) => (x == null ? "–" : Number(x).toFixed(d));
  const lvClass = (l) => "lv-" + (l || "none");
  const lvLabel = (l) => (l ? l[0].toUpperCase() + l.slice(1) : "No data");
  const qs = () => (S.includeTest ? "?include_test=1" : "");
  const withQs = (path) => path + (path.includes("?") ? (S.includeTest ? "&include_test=1" : "") : qs());

  async function api(path, opts = {}) {
    const headers = Object.assign({ Authorization: "Bearer " + S.token }, opts.headers || {});
    if (opts.json !== undefined) { headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(opts.json); }
    const r = await fetch(path, Object.assign({}, opts, { headers }));
    if (r.status === 401) { logout(); throw new Error("Signed out"); }
    const ct = r.headers.get("content-type") || "";
    const body = ct.includes("json") ? await r.json() : await r.text();
    if (!r.ok) throw new Error((body && body.detail) || "Request failed");
    return body;
  }
  const get = (path) => api(withQs(path));
  const can = (...roles) => roles.includes(S.user.role);

  async function download(path, filename) {
    const r = await fetch(withQs(path), { headers: { Authorization: "Bearer " + S.token } });
    if (!r.ok) { alertMsg("Download failed."); return; }
    const url = URL.createObjectURL(await r.blob());
    const a = document.createElement("a");
    a.href = url; a.download = filename; document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
  }
  function alertMsg(text) {
    const el = $("#flash");
    if (el) { el.textContent = text; }
  }
  const bar = (frac) => `<div class="bar"><i style="width:${Math.max(2, Math.min(100, Math.round((frac || 0) * 100)))}%"></i></div>`;
  const metric = (label, value, frac) => `<div class="metric"><div class="top-line"><span>${esc(label)}</span><b>${esc(value)}</b></div>${bar(frac)}</div>`;

  // ---------------------------------------------------------------- auth
  function showLogin() { $("#login").hidden = false; $("#shell").hidden = true; $("#u").focus(); }
  function logout() {
    S.token = null; S.user = null;
    try { sessionStorage.removeItem("obs_token"); } catch (e) { /* storage blocked */ }
    showLogin();
  }
  $("#login-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    $("#login-error").textContent = "";
    try {
      const r = await fetch("/api/auth/login", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: $("#u").value, password: $("#p").value }) });
      const body = await r.json();
      if (!r.ok) throw new Error(body.detail || "Sign-in failed");
      S.token = body.token;
      try { sessionStorage.setItem("obs_token", body.token); } catch (err) { /* storage blocked */ }
      $("#p").value = "";
      await start();
    } catch (err) { $("#login-error").textContent = err.message; }
  });
  $("#logout").addEventListener("click", logout);
  $("#refresh").addEventListener("click", () => render());
  $("#include-test").addEventListener("change", (e) => { S.includeTest = e.target.checked; render(); });

  async function start() {
    S.user = await api("/api/me");
    $("#login").hidden = true; $("#shell").hidden = false;
    $("#who").textContent = `${S.user.name} · ${S.user.role}` + (S.user.sites !== "*" ? ` · sites ${S.user.sites}` : "");
    $("#test-toggle").hidden = !can("admin", "coordinator");
    const tabs = ROLE_TABS[S.user.role] || [];
    S.tab = tabs.includes(S.tab) ? S.tab : tabs[0];
    $("#tabs").innerHTML = tabs.map((t) => `<button type="button" class="btn" data-tab="${t}" aria-pressed="${t === S.tab}">${TABS[t]}</button>`).join("");
    render();
  }
  $("#tabs").addEventListener("click", (e) => {
    const b = e.target.closest("[data-tab]");
    if (!b) return;
    S.tab = b.dataset.tab;
    document.querySelectorAll("#tabs .btn").forEach((x) => x.setAttribute("aria-pressed", String(x.dataset.tab === S.tab)));
    render();
  });

  async function render() {
    const rid = ++S.rid;
    view().innerHTML = `<p class="mut">Loading…</p>`;
    try {
      await ({ master: renderMaster, asha: renderAsha, ward: renderWard, science: renderScience,
        reports: renderReports, advisories: renderAdvisories, admin: renderAdmin })[S.tab](rid);
    } catch (err) {
      if (err.message !== "Signed out") view().innerHTML = `<p class="error">${esc(err.message)}</p>`;
    }
  }

  // ---------------------------------------------------------------- charts (inline SVG)
  function siteMap(sites) {
    const pts = sites.filter((s) => s.lat != null && s.lon != null);
    if (!pts.length) return `<p class="empty">Add latitude and longitude to sites to see them on the map.</p>`;
    const lats = pts.map((s) => s.lat), lons = pts.map((s) => s.lon);
    const pad = 0.004, minLat = Math.min(...lats) - pad, maxLat = Math.max(...lats) + pad;
    const minLon = Math.min(...lons) - pad, maxLon = Math.max(...lons) + pad;
    const W = 560, H = 300;
    const X = (lon) => 30 + ((lon - minLon) / (maxLon - minLon || 1)) * (W - 60);
    const Y = (lat) => H - 30 - ((lat - minLat) / (maxLat - minLat || 1)) * (H - 60);
    const fill = { low: "#7CC7C4", watch: "#E8B45A", high: "#D9642F" };
    const dots = pts.map((s) => {
      const l = s.layers[S.layer];
      const sel = S.site === s.code;
      return `<g><circle cx="${X(s.lon).toFixed(1)}" cy="${Y(s.lat).toFixed(1)}" r="${sel ? 14 : 11}" fill="${fill[l] || "#C5D0D2"}" stroke="${sel ? "#12262E" : "#fff"}" stroke-width="${sel ? 3 : 2}"></circle>
      <text x="${(X(s.lon) + 16).toFixed(1)}" y="${(Y(s.lat) + 4).toFixed(1)}" font-size="12" fill="#12262E">${esc(s.code)}</text></g>`;
    }).join("");
    return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Sites placed by their coordinates, coloured by the selected layer" style="width:100%;height:auto;background:#EEF4F4;border-radius:8px">
      <text x="${W - 12}" y="20" font-size="11" text-anchor="end" fill="#4A5D63">N ↑ · positions to scale, no base map</text>${dots}</svg>`;
  }

  function trendChart(weeks) {
    const W = 560, H = 190, L = 34, R = 34, T = 14, B = 30;
    const n = weeks.length;
    const x = (i) => L + (i * (W - L - R)) / Math.max(1, n - 1);
    const maxD = Math.max(1, ...weeks.map((w) => w.diarrhoea));
    const yP = (v) => T + (1 - v) * (H - T - B);
    const yD = (v) => T + (1 - v / maxD) * (H - T - B);
    const line = (vals, y) => {
      let d = "", pen = false;
      vals.forEach((v, i) => { if (v == null) { pen = false; return; } d += (pen ? "L" : "M") + x(i).toFixed(1) + " " + y(v).toFixed(1) + " "; pen = true; });
      return d;
    };
    const labels = weeks.map((w, i) => (i % 2 === 0 ? `<text x="${x(i).toFixed(1)}" y="${H - 8}" font-size="11" text-anchor="middle" fill="#4A5D63">${esc(w.week.slice(5))}</text>` : "")).join("");
    return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Weekly share of positive water samples and diarrhoea reports" style="width:100%;height:auto">
      <g stroke="#E3EAEB">${[0, 0.5, 1].map((v) => `<line x1="${L}" x2="${W - R}" y1="${yP(v)}" y2="${yP(v)}"></line>`).join("")}</g>
      <text x="4" y="${yP(1) + 4}" font-size="11" fill="#0B6770">100%</text><text x="4" y="${yP(0) + 4}" font-size="11" fill="#0B6770">0%</text>
      <text x="${W - 4}" y="${yD(maxD) + 4}" font-size="11" text-anchor="end" fill="#A33E17">${maxD}</text>
      <path d="${line(weeks.map((w) => w.positivity), yP)}" fill="none" stroke="#0E7C86" stroke-width="2.5"></path>
      <path d="${line(weeks.map((w) => w.diarrhoea), yD)}" fill="none" stroke="#B8461A" stroke-width="2.5" stroke-dasharray="6 4"></path>
      ${weeks.map((w, i) => (w.positivity == null ? "" : `<circle cx="${x(i)}" cy="${yP(w.positivity)}" r="3.5" fill="#0E7C86"></circle>`)).join("")}
      ${labels}</svg>
      <div class="legend"><span><i class="sw" style="background:#0E7C86;height:3px"></i>Positive samples (%)</span><span><i class="sw" style="border-top:3px dashed #B8461A;background:none;height:0"></i>Diarrhoea reports (right scale)</span></div>`;
  }

  function scatter(points, fit) {
    if (points.length < 3) return `<p class="empty">Not enough linked readings yet (needs TDS and BP for the same household).</p>`;
    const W = 560, H = 210, L = 44, R = 14, T = 12, B = 34;
    const xs = points.map((p) => p.tds), ys = points.map((p) => p.sbp);
    const x0 = 0, x1 = Math.max(...xs) * 1.05, y0 = Math.min(90, ...ys) - 5, y1 = Math.max(...ys) + 5;
    const X = (v) => L + ((v - x0) / (x1 - x0)) * (W - L - R);
    const Y = (v) => T + (1 - (v - y0) / (y1 - y0)) * (H - T - B);
    const dots = points.map((p) => `<circle cx="${X(p.tds).toFixed(1)}" cy="${Y(p.sbp).toFixed(1)}" r="4" fill="#0E7C86" fill-opacity="0.6"></circle>`).join("");
    const fl = fit ? `<line x1="${X(x0)}" y1="${Y(fit.intercept + fit.slope * x0)}" x2="${X(x1)}" y2="${Y(fit.intercept + fit.slope * x1)}" stroke="#B8461A" stroke-width="2.5"></line>` : "";
    return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Household water TDS against systolic blood pressure in residents 60 and over" style="width:100%;height:auto">
      <line x1="${L}" x2="${W - R}" y1="${H - B}" y2="${H - B}" stroke="#9FB3B7"></line><line x1="${L}" x2="${L}" y1="${T}" y2="${H - B}" stroke="#9FB3B7"></line>
      ${[1000].map((v) => `<line x1="${X(v)}" x2="${X(v)}" y1="${T}" y2="${H - B}" stroke="#E8B45A" stroke-dasharray="4 4"></line><text x="${X(v) + 4}" y="${T + 10}" font-size="11" fill="#A33E17">1,000 mg/L</text>`).join("")}
      ${dots}${fl}
      <text x="${(L + W - R) / 2}" y="${H - 6}" font-size="11" text-anchor="middle" fill="#4A5D63">Household water TDS (mg/L)</text>
      <text x="6" y="${T + 8}" font-size="11" fill="#4A5D63">${Math.round(y1)}</text><text x="6" y="${H - B}" font-size="11" fill="#4A5D63">${Math.round(y0)}</text>
      </svg>`;
  }

  // ---------------------------------------------------------------- master view
  async function renderMaster(rid) {
    const analyst = can(...ANALYSTS);
    const [summary, sites, fc, ageing, quality, loop, queries, trend, sal, assoc, model, decisions] = await Promise.all([
      get("/api/summary?days=30"), get("/api/sites"), get("/api/forecast"), get("/api/ageing"), get("/api/quality"),
      get("/api/loop"), get("/api/queries"),
      analyst ? get("/api/stats/trend") : null, analyst ? get("/api/stats/salinity-bp") : null,
      analyst ? get("/api/stats/associations") : null, analyst ? get("/api/stats/model") : null,
      can("admin", "coordinator") ? get("/api/decisions") : [],
    ]);
    S.cache.sites = sites;
    if (rid !== S.rid) return;
    if (!S.site && sites.length) S.site = sites[0].code;
    const sel = sites.find((s) => s.code === S.site) || sites[0];

    if (rid !== S.rid) return;
    view().innerHTML = `
    <div id="flash" class="mut" role="status"></div>
    <section class="streams" aria-label="Data in the past ${summary.days} days">
      ${summary.streams.map((s) => `<div class="card"><p class="mut small">${esc(s.source)}</p><p class="num">${esc(s.value)}</p><p class="small" style="margin:0">${esc(s.what)}, ${summary.days} days</p></div>`).join("")}
    </section>

    <div class="row">
      <section class="card grow" aria-label="Site risk map">
        <div class="form-row" style="justify-content:space-between"><h2>Site risk map</h2>
          <div class="chips" role="group" aria-label="Map layer">${LAYERS.map(([id, label]) => `<button type="button" class="btn small" data-act="layer" data-id="${id}" aria-pressed="${id === S.layer}">${label}</button>`).join("")}</div></div>
        ${siteMap(sites)}
        <div class="tiles">${sites.map((s) => `<button type="button" class="tile ${lvClass(s.layers[S.layer])}" data-act="site" data-id="${esc(s.code)}" aria-pressed="${s.code === S.site}">
          <span><b>${esc(s.label)}</b><br><small>${esc(s.code)} · ${esc(s.site_type)}</small></span><span class="lv">${lvLabel(s.layers[S.layer])}</span></button>`).join("") || `<p class="empty">No sites yet. An administrator adds them on the Admin tab.</p>`}</div>
        <div class="legend"><span><i class="sw lv-low"></i>Low</span><span><i class="sw lv-watch"></i>Watch</span><span><i class="sw lv-high"></i>High</span><span><i class="sw lv-none"></i>No data</span><span style="margin-left:auto">${esc(LAYER_NOTE[S.layer])}</span></div>
      </section>
      <section class="card dark side" aria-label="Site detail">
        <p class="lbl">Site detail</p>
        ${sel ? `<h2 style="font-size:22px">${esc(sel.label)}</h2>
        <p class="mut">${esc(sel.code)} · ${esc(sel.site_type)}</p>
        <div class="kv">
          <div><span>Samples, 8 weeks</span><strong>${esc(sel.metrics.samples_8wk)}</strong></div>
          <div><span>Positive</span><strong>${pct(sel.metrics.positivity)}</strong></div>
          <div><span>Diarrhoea / 100 households</span><strong>${num(sel.metrics.diarrhoea_per_100hh_4wk, 1)}</strong></div>
          <div><span>Median TDS (mg/L)</span><strong>${num(sel.metrics.tds_median)}</strong></div>
          <div><span>Residents 60+</span><strong>${esc(sel.metrics.elders_registered)}</strong></div>
          <div><span>Vulnerable 60+</span><strong>${pct(sel.metrics.vulnerable_share)}</strong></div>
        </div>
        <div class="chips">${LAYERS.slice(1).map(([id, label]) => `<span class="status ${lvClass(sel.layers[id])}" style="color:#12262E;padding:4px 8px;border-radius:6px">${label}: ${lvLabel(sel.layers[id])}</span>`).join("")}</div>` : `<p class="mut">No site selected.</p>`}
      </section>
    </div>

    <section class="card" aria-label="Seven-day forecast">
      <div class="form-row" style="justify-content:space-between"><h2>Next 7 days: forecast risk</h2><p class="mut">Weather forecast and tide table × contamination model × heat index</p></div>
      ${fc.length ? `<div class="days">${fc.map((d) => `<div class="day ${lvClass(d.level)}"><b>${esc(new Date(d.day + "T00:00").toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short" }))}</b>
        <span>Rain ${num(d.rain_mm)} mm</span><span>High tide ${d.tide_m == null ? "–" : num(d.tide_m, 1) + " m"}</span><span>Heat index ${num(d.heat_index_c)} °C</span>
        <span class="status">${lvLabel(d.level)}</span><span>${d.actions.map(esc).join("; ")}</span></div>`).join("")}</div>`
        : `<p class="empty">No forecast loaded. A coordinator can fetch the weather and upload the tide table on the Admin tab.</p>`}
    </section>

    <div class="row">
      <section class="card grow" aria-label="Scenario model">
        <p class="lbl">Modelling</p><h2>What-if scenario</h2>
        <p class="mut">Move the levers to see the model’s estimate for the sites you can see.</p>
        <div class="sliders">
          <label><span>Rainfall in 48 h: <span id="v-rain">${S.scen.rain_mm}</span> mm</span><input type="range" data-scen="rain_mm" min="0" max="200" step="5" value="${S.scen.rain_mm}"></label>
          <label><span>High tide: <span id="v-tide">${S.scen.tide_m.toFixed(1)}</span> m</span><input type="range" data-scen="tide_m" min="0.4" max="1.8" step="0.1" value="${S.scen.tide_m}"></label>
          <label><span>Air temperature: <span id="v-temp">${S.scen.temp_c}</span> °C</span><input type="range" data-scen="temp_c" min="24" max="42" step="1" value="${S.scen.temp_c}"></label>
          <label><span>Relative humidity: <span id="v-rh">${S.scen.rh}</span> %</span><input type="range" data-scen="rh" min="40" max="98" step="1" value="${S.scen.rh}"></label>
        </div>
        <div class="outs" id="scen-out"></div>
        <p class="mut small" id="scen-note"></p>
      </section>
      <section class="card warm side" aria-label="Climate and ageing">
        <p class="lbl">Climate change and ageing</p><h2>Heat and flood exposure of residents 60+</h2>
        <div class="form-row"><span class="num" style="font-size:32px">${num(ageing.heat_index_next3d)} °C</span><b style="color:#A33E17">Heat index, next 3 days · ${esc(ageing.heat_band || "no forecast")}</b></div>
        ${metric("Residents 60+ registered", ageing.elders_registered, 1)}
        ${metric("Living alone", ageing.living_alone, ageing.living_alone / Math.max(1, ageing.elders_screened))}
        ${metric("Need help to evacuate", ageing.need_evacuation_help, ageing.need_evacuation_help / Math.max(1, ageing.elders_screened))}
        ${metric("Frail (CFS 5+)", ageing.frail_cfs5plus, ageing.frail_cfs5plus / Math.max(1, ageing.elders_screened))}
        ${metric("Heat symptoms this year", ageing.heat_symptoms, ageing.heat_symptoms / Math.max(1, ageing.elders_screened))}
        ${metric("Two or more falls", ageing.falls_2plus, ageing.falls_2plus / Math.max(1, ageing.elders_screened))}
        ${metric("Mini-Cog positive", ageing.minicog_positive, ageing.minicog_positive / Math.max(1, ageing.elders_screened))}
        ${metric("PHQ-2 positive", ageing.phq2_positive, ageing.phq2_positive / Math.max(1, ageing.elders_screened))}
        <p class="mut">${ageing.tide_alert ? `<b>High tide alert:</b> ${num(ageing.tide_next3d_m, 1)} m forecast. ` : ""}Feeds the elders’ heat–health plan and ward evacuation lists.</p>
      </section>
    </div>

    ${analyst ? `<div class="row">
      <section class="card third" aria-label="Trend"><p class="lbl">Statistics</p><h2>Water positivity and diarrhoea reports</h2>${trendChart(trend.weeks)}
        <p class="mut">${trend.lag1_correlation ? `Positivity this week vs diarrhoea next week: r = ${trend.lag1_correlation.r} (95% CI ${trend.lag1_correlation.ci.join(" to ")}, ${trend.lag1_correlation.n} weeks).` : "Lagged correlation appears after 4 weeks with both measures."}</p></section>
      <section class="card third" aria-label="Salinity and blood pressure"><p class="lbl">Statistics</p><h2>Water salinity and systolic BP, 60+</h2>${scatter(sal.points, sal.fit)}
        <p class="mut">${sal.correlation ? `r = ${sal.correlation.r} (95% CI ${sal.correlation.ci.join(" to ")}, n = ${sal.correlation.n})${sal.fit ? `; +${(sal.fit.slope * 500).toFixed(1)} mmHg per 500 mg/L` : ""}. Unadjusted.` : ""}</p></section>
    </div>
    <div class="row">
      <section class="card grow" aria-label="Associations"><p class="lbl">Statistics</p><h2>Key associations (odds ratios)</h2>
        <div class="scroll"><table><tr><th>Association</th><th>OR</th><th>95% CI</th><th>n</th></tr>
        ${assoc.map((a) => `<tr><td>${esc(a.name)}</td><td class="n">${a.or == null ? "–" : esc(a.or)}</td><td class="n">${a.ci ? esc(a.ci.join("–")) : "–"}</td><td class="n">${a.n == null ? "–" : esc(a.n)}</td></tr>`).join("")}</table></div>
        <p class="mut">2×2 tables with Woolf intervals; crude, not adjusted for confounders.</p></section>
      <section class="card side" aria-label="Contamination model"><p class="lbl">Model</p><h2>What predicts a positive sample?</h2>
        ${model.fitted ? `<div class="scroll"><table><tr><th>Term</th><th>OR</th><th>95% CI</th></tr>${model.terms.slice(1).map((t) => `<tr><td>${esc(t.term)}</td><td class="n">${esc(t.or)}</td><td class="n">${esc(t.ci.join("–"))}</td></tr>`).join("")}</table></div>
        <p class="mut">Logistic regression, n = ${model.n}, ${model.events} positive, AUC ${model.auc}.</p>` : `<p class="empty">${esc(model.reason)} (n = ${model.n}, ${model.events} positive)</p>`}</section>
    </div>` : ""}

    <div class="row">
      <section class="card third" aria-label="Loop closed"><p class="lbl">Loop closed</p><h2>Do results reach people?</h2>
        ${metric("Positive households given advice", `${loop.advised} of ${loop.positive_households}`, loop.advised_share)}
        ${metric("Referrals completed", `${loop.referrals_completed} of ${loop.referrals}`, loop.referral_share)}
        ${metric("Advisories reviewed by a doctor", pct(loop.advisories_reviewed_share), loop.advisories_reviewed_share)}
        <p class="mut">Median days from sample to advice: ${num(loop.median_days_to_advice)}</p></section>
      <section class="card third" aria-label="Data quality"><p class="lbl">Data quality</p><h2>Is the data publishable?</h2>
        ${metric("Registration completeness", pct(quality.registration_completeness), quality.registration_completeness)}
        ${metric("Measurement completeness", pct(quality.measurement_completeness), quality.measurement_completeness)}
        ${metric("Samples with GPS", pct(quality.samples_with_gps), quality.samples_with_gps)}
        ${metric("Samples confirmed by NIO lab", pct(quality.samples_lab_confirmed), quality.samples_lab_confirmed)}
        ${metric("Aquadip© agrees with NIO lab", pct(quality.aquadip_vs_lab.agreement), quality.aquadip_vs_lab.agreement)}
        <p class="mut">Aquadip© vs lab: ${quality.aquadip_vs_lab.pairs} pairs, kappa ${num(quality.aquadip_vs_lab.kappa, 2)}, sensitivity ${pct(quality.aquadip_vs_lab.sensitivity)}, specificity ${pct(quality.aquadip_vs_lab.specificity)}.</p></section>
      <section class="card third" aria-label="National systems"><p class="lbl">Feeds national systems</p><h2>Complements, never duplicates</h2>
        <table>${[["IHIP / IDSP", "Syndromic case counts"], ["JJM WQMIS", "Drinking-water results"], ["Kerala One Health", "Volunteer event reports"], ["K-CDC", "Monsoon surveillance grid"], ["NPCCHH", "Heat-related illness"]].map(([a, b]) => `<tr><td><b>${a}</b></td><td>${b}</td></tr>`).join("")}</table>
        <p class="mut">Data-sharing formats to be agreed with each system owner.</p></section>
    </div>

    <div class="row">
      ${can(...ANALYSTS, "asha") ? `<section class="card grow" aria-label="Ask the Observatory"><p class="lbl">Ask the Observatory</p><h2>Questions answered from the linked data</h2>
        <div class="chips">${queries.map((q) => `<button type="button" class="btn small" data-act="query" data-id="${esc(q.name)}" aria-pressed="${S.query === q.name}">${esc(q.question)}</button>`).join("")}</div>
        <div id="query-out"><p class="empty">Choose a question.</p></div></section>` : ""}
      <section class="card dark side" aria-label="Signals"><h2>This week’s signals</h2>
        ${fc.slice(0, 3).flatMap((d) => d.actions.filter((a) => !a.startsWith("Routine")).map((a) => [d, a])).slice(0, 3).map(([d, a]) => `<div class="signal"><p class="tag">Forecast · ${esc(d.day)}</p><p>${esc(a)}</p></div>`).join("")}
        ${decisions.filter((d) => d.status === "open").slice(0, 3).map((d) => `<div class="signal"><p class="tag">Decision · ${esc(d.site)}</p><p>${esc(d.title)}</p><p class="mut">${esc(d.reason)}</p></div>`).join("")}
        ${sites.filter((s) => s.layers.water === "high").slice(0, 3).map((s) => `<div class="signal"><p class="tag">Water · ${esc(s.code)}</p><p>${pct(s.metrics.positivity)} of samples positive in 8 weeks</p></div>`).join("")}
      </section>
    </div>`;
    updateScenario();
    if (S.query) runQuery(S.query);
  }

  let scenTimer = null;
  async function updateScenario() {
    const out = $("#scen-out");
    if (!out) return;
    const r = await api(withQs("/api/model/scenario"), { method: "POST", json: S.scen });
    const lvl = (x) => (x >= 0.5 ? "High" : x >= 0.2 ? "Watch" : "Low");
    out.innerHTML = [
      ["Chance of contamination spike", pct(r.contamination_probability), r.contamination_probability, lvl(r.contamination_probability)],
      ["Households needing advisory", `${r.households_needing_advisory} of ${r.households_surveyed}`, r.households_needing_advisory / Math.max(1, r.households_surveyed), ""],
      ["Heat index", `${r.heat_index_c} °C`, Math.min(1, r.heat_index_c / 55), r.heat_band],
      ["Residents 60+ at heat risk", `${r.elders_at_heat_risk} of ${r.elders_registered}`, r.elders_at_heat_risk / Math.max(1, r.elders_registered), ""],
    ].map(([l, v, f, b]) => `<div class="out"><span class="mut small">${esc(l)}</span><span class="num">${esc(v)}</span>${bar(f)}<span class="status">${esc(b)}</span></div>`).join("");
    $("#scen-note").textContent = r.note;
  }

  async function runQuery(name) {
    const box = $("#query-out");
    if (!box) return;
    box.innerHTML = `<p class="mut">Looking…</p>`;
    const r = await get("/api/queries/" + encodeURIComponent(name));
    if (!r.rows.length) { box.innerHTML = `<p class="empty">None found.</p>`; return; }
    const cols = Object.keys(r.rows[0]);
    box.innerHTML = `<p><b>${r.count}</b> found.</p><div class="scroll"><table><tr>${cols.map((c) => `<th>${esc(c.replace(/_/g, " "))}</th>`).join("")}</tr>
      ${r.rows.slice(0, 50).map((row) => `<tr>${cols.map((c) => `<td>${esc(row[c] === true ? "yes" : row[c] === false ? "no" : row[c])}</td>`).join("")}</tr>`).join("")}</table></div>
      ${r.count > 50 ? `<p class="mut">Showing the first 50.</p>` : ""}`;
  }

  // ---------------------------------------------------------------- ASHA view
  async function renderAsha(rid) {
    const tasks = await get("/api/tasks");
    const groups = { report: "Illness reported this week", referral: "Referral follow-ups", advice: "Give water results and advice",
      resample: "Repeat water samples", elder: "Elder checks before tide or heat" };
    const done = tasks.filter((t, i) => S.done[taskKey(t, i)]).length;
    if (rid !== S.rid) return;
    view().innerHTML = `
    <div class="row">
      <section class="card grow" aria-label="Today's tasks"><p class="lbl">Field view</p><h2 style="font-size:22px">Tasks for your sites</h2>
        <p class="mut">${done} of ${tasks.length} ticked on this device. Record each visit in the ODK household-visit form; the task closes automatically after the next sync.</p>
        ${Object.entries(groups).map(([k, label]) => {
          const list = tasks.map((t, i) => [t, i]).filter(([t]) => t.kind === k);
          if (!list.length) return "";
          return `<h2 style="font-size:16px;margin-top:8px">${label} (${list.length})</h2>` + list.map(([t, i]) => {
            const key = taskKey(t, i);
            return `<div class="task"><input type="checkbox" id="t${i}" data-act="task" data-id="${esc(key)}" ${S.done[key] ? "checked" : ""}>
              <label for="t${i}"><b>${esc(t.title)}</b><span class="mut">${esc(t.detail)}${t.hh_id ? " · " + esc(t.hh_id) : ""} · ${esc(t.site)}${t.since ? " · since " + esc(t.since) : ""}</span></label></div>`;
          }).join("");
        }).join("") || `<p class="empty">Nothing pending. Well done.</p>`}
      </section>
      <section class="card side" aria-label="Send advisories"><h2>Approved messages to send</h2>
        <p class="mut">Download the list of doctor-approved messages with phone numbers, send them by WhatsApp, then mark them sent on the Advisories tab.</p>
        ${can("admin", "coordinator", "asha") ? `<button type="button" class="btn primary" data-act="sendlist">Download send list (CSV)</button>` : ""}
        <div id="flash" class="mut" role="status"></div>
      </section>
    </div>`;
  }
  const taskKey = (t) => [t.kind, t.person_id || "", t.hh_id || "", t.title].join("|");

  // ---------------------------------------------------------------- ward view
  async function renderWard(rid) {
    const [decisions, sites, ageing] = await Promise.all([get("/api/decisions"), get("/api/sites"), get("/api/ageing")]);
    if (rid !== S.rid) return;
    view().innerHTML = `
    <div class="row">
      <section class="card grow" aria-label="Decisions needed"><p class="lbl">Ward member view</p><h2 style="font-size:22px">Decisions needed</h2>
        ${decisions.map((d) => `<div class="task" style="justify-content:space-between;flex-wrap:wrap">
          <div style="flex:1 1 320px;min-width:0"><b>${esc(d.title)}</b><p class="mut">${esc(d.reason)} · ${esc(d.site)}</p>
          <p class="status" style="margin:4px 0 0">${esc(d.status)}${d.decided_by ? " by " + esc(d.decided_by) : ""}</p></div>
          <div class="chips"><button type="button" class="btn small ${d.status === "approved" ? "ok" : ""}" data-act="decide" data-id="${d.id}" data-status="approved">Approve</button>
          <button type="button" class="btn small" data-act="decide" data-id="${d.id}" data-status="declined">Decline</button></div></div>`).join("") || `<p class="empty">No decisions waiting.</p>`}
      </section>
      <section class="card side" aria-label="Your sites"><h2>Your sites</h2>
        <table><tr><th>Site</th><th>Water</th><th>Illness</th><th>Heat</th></tr>${sites.map((s) => `<tr><td>${esc(s.label)}</td>${["water", "illness", "heat"].map((l) => `<td><span class="status ${lvClass(s.layers[l])}" style="padding:2px 6px;border-radius:4px">${lvLabel(s.layers[l])}</span></td>`).join("")}</tr>`).join("")}</table>
        <h2 style="margin-top:8px">Elders in your wards</h2>
        <p>${esc(ageing.need_evacuation_help)} need help to evacuate · ${esc(ageing.living_alone)} live alone · ${esc(ageing.frail_cfs5plus)} frail</p>
        <p class="mut">Names are held by the ASHA team; ask the coordinator for the evacuation list when a warning is issued.</p>
      </section>
    </div>`;
  }

  // ---------------------------------------------------------------- scientist view
  async function renderScience(rid) {
    const [rec, model, quality] = await Promise.all([
      get(`/api/records/${S.dataset}?limit=200${S.siteType ? "&site_type=" + encodeURIComponent(S.siteType) : ""}`),
      get("/api/stats/model"), get("/api/quality")]);
    const cols = rec.rows.length ? Object.keys(rec.rows[0]) : [];
    if (rid !== S.rid) return;
    view().innerHTML = `
    <div id="flash" class="mut" role="status"></div>
    <section class="card" aria-label="Linked records"><p class="lbl">Scientist view</p>
      <div class="form-row" style="justify-content:space-between"><h2 style="font-size:22px">Linked records (de-identified)</h2>
        <div class="form-row">
          <label>Dataset<select data-act="dataset">${["samples", "persons", "households", "screening", "visits"].map((d) => `<option value="${d}" ${d === S.dataset ? "selected" : ""}>${d}</option>`).join("")}</select></label>
          <label>Site type<select data-act="sitetype">${[["", "All"], ["village", "Villages"], ["colony", "Canal colonies"], ["flats", "Flats"], ["ward", "Wards"]].map(([v, l]) => `<option value="${v}" ${v === S.siteType ? "selected" : ""}>${l}</option>`).join("")}</select></label>
          ${can("admin", "coordinator", "scientist") ? `<button type="button" class="btn primary" data-act="export">Export CSV</button>` : ""}
        </div></div>
      <p class="mut">${rec.total} records${rec.total > rec.rows.length ? `, first ${rec.rows.length} shown` : ""}. No names or phone numbers; GPS rounded to about 100 m; persons without research consent excluded.</p>
      <div class="scroll" style="max-height:480px;overflow:auto"><table><tr>${cols.map((c) => `<th>${esc(c)}</th>`).join("")}</tr>
      ${rec.rows.map((r) => `<tr>${cols.map((c) => `<td>${esc(r[c] === true ? "yes" : r[c] === false ? "no" : r[c])}</td>`).join("")}</tr>`).join("")}</table></div>
    </section>
    <div class="row">
      <section class="card third"><p class="lbl">Model diagnostics</p><h2>Contamination model</h2>
        ${model.fitted ? `<table><tr><th>Term</th><th>Coef</th><th>SE</th><th>OR (95% CI)</th></tr>${model.terms.map((t) => `<tr><td>${esc(t.term)}</td><td class="n">${t.coef}</td><td class="n">${t.se}</td><td class="n">${t.or} (${t.ci.join("–")})</td></tr>`).join("")}</table>
        <p class="mut">n = ${model.n}, events ${model.events}, AUC ${model.auc}, converged: ${model.converged ? "yes" : "no"}.</p>` : `<p class="empty">${esc(model.reason)}</p>`}</section>
      <section class="card third"><p class="lbl">Method agreement</p><h2>Aquadip© vs NIO lab</h2>
        <table><tr><td>Paired samples</td><td class="n">${quality.aquadip_vs_lab.pairs}</td></tr><tr><td>Agreement</td><td class="n">${pct(quality.aquadip_vs_lab.agreement)}</td></tr>
        <tr><td>Cohen’s kappa</td><td class="n">${num(quality.aquadip_vs_lab.kappa, 2)}</td></tr><tr><td>Sensitivity</td><td class="n">${pct(quality.aquadip_vs_lab.sensitivity)}</td></tr><tr><td>Specificity</td><td class="n">${pct(quality.aquadip_vs_lab.specificity)}</td></tr></table>
        <p class="mut">This is the validation evidence for the CSR deliverable.</p></section>
      <section class="card third"><p class="lbl">Upload</p><h2>Lab results and tide table</h2>
        <label class="mut">NIO lab results CSV: sample_id, method, result, ecoli_cfu, coliform_cfu, vibrio, amr_note, tested_on
          <input type="file" accept=".csv" data-act="upload" data-path="/api/import/lab"></label>
        ${can("admin", "coordinator", "scientist") ? `<label class="mut">Tide table CSV: date, high_tide_m<input type="file" accept=".csv" data-act="upload" data-path="/api/import/tides"></label>` : ""}
      </section>
    </div>`;
  }

  // ---------------------------------------------------------------- advisories
  async function renderAdvisories(rid) {
    const [list, siteList, tr] = await Promise.all([get("/api/advisories"), get("/api/sites"), get("/api/translate/status")]);
    S.cache.siteList = siteList; S.cache.tr = tr;
    const doctor = can("doctor", "admin");
    if (rid !== S.rid) return;
    view().innerHTML = `
    <div id="flash" class="mut" role="status"></div>
    <section class="card"><p class="lbl">Advisories</p><h2 style="font-size:22px">Household and community messages</h2>
      <p class="mut">Every message starts as a draft. A doctor approves it before anyone sends it.</p>
      <p class="mut small">Malayalam text is a machine-assisted translation for accessibility. English is the reference.</p>
      ${can("admin", "coordinator", "doctor") ? `<form id="custom-adv" class="card" style="background:#F4F7F7">
        <h2>Write a new message</h2>
        <div class="form-row"><label>Site<select name="site">${(S.cache.siteList || []).map((s) => `<option value="${esc(s.code)}">${esc(s.label)}</option>`).join("")}</select></label>
        <label>Household (optional)<input name="hh_id" placeholder="CVB-014"></label></div>
        <label class="mut" style="display:flex;flex-direction:column;gap:4px">Message in English<textarea name="text_en" rows="3" required minlength="5" maxlength="1500" style="font:inherit;padding:10px;border:1.5px solid #9FB3B7;border-radius:8px"></textarea></label>
        <label class="mut" style="display:flex;flex-direction:column;gap:4px">Malayalam (leave empty to translate automatically${S.cache.tr && S.cache.tr.enabled ? " with Sarvam AI" : "; translation service not configured"})<textarea name="text_ml" rows="3" lang="ml" maxlength="3000" style="font:inherit;padding:10px;border:1.5px solid #9FB3B7;border-radius:8px"></textarea></label>
        <button class="btn primary" type="submit">Save as draft</button></form>` : ""}
      ${list.map((a) => `<div class="task" style="flex-wrap:wrap;justify-content:space-between">
        <div style="flex:1 1 420px;min-width:0"><p class="status" style="margin:0">${esc(a.status)} · ${esc(a.kind)} · ${esc(a.site)}${a.hh_id ? " · " + esc(a.hh_id) : ""}${a.reviewed_by ? " · reviewed by " + esc(a.reviewed_by) : ""}</p>
          <p class="ml" lang="ml" style="margin:4px 0">${esc(a.text_ml)}</p><p class="mut">${esc(a.text_en)}</p></div>
        <div class="chips">
          ${doctor && a.status === "draft" ? `<button type="button" class="btn small ok" data-act="adv" data-id="${a.id}" data-status="approved">Approve</button><button type="button" class="btn small" data-act="adv" data-id="${a.id}" data-status="rejected">Reject</button>` : ""}
          ${a.status === "approved" && can("admin", "coordinator", "asha") ? `<button type="button" class="btn small" data-act="adv" data-id="${a.id}" data-status="sent">Mark sent</button>` : ""}
        </div></div>`).join("") || `<p class="empty">No advisories yet.</p>`}
    </section>`;
    const f = $("#custom-adv");
    if (f) f.addEventListener("submit", async (e) => {
      e.preventDefault();
      const data = Object.fromEntries(new FormData(f).entries());
      if (!data.hh_id) delete data.hh_id;
      if (!data.text_ml) delete data.text_ml;
      try { await api("/api/advisories/custom", { method: "POST", json: data }); render(); }
      catch (err) { alertMsg(err.message); }
    });
  }

  // ---------------------------------------------------------------- household reports
  const fmtDT = (v) => (v ? new Date(v + (v.endsWith("Z") || v.includes("+") ? "" : "Z")).toLocaleString("en-IN",
    { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "never");

  function workdaysCard(wd) {
    const years = [new Date().getFullYear(), new Date().getFullYear() - 1];
    const big = (label, v) => `<div class="out"><span class="mut small">${esc(label)}</span><span class="num">${esc(v)}</span></div>`;
    return `<section class="card warm" aria-label="Workdays lost">
      <div class="form-row" style="justify-content:space-between"><div><p class="lbl">Productivity loss</p>
        <h2 style="font-size:22px">Days lost to water-related illness</h2></div>
        <label>Period<select data-act="wyear"><option value="">Past 12 months</option>${years.map((y) => `<option value="${y}" ${String(y) === String(S.wyear) ? "selected" : ""}>${y}</option>`).join("")}</select></label></div>
      <div class="outs">${big("Productive days lost", wd.productive_days)}${big("Workdays (the ill person)", wd.work_days)}
        ${big("Days family stayed home to care", wd.carer_days)}${big("School days missed", wd.school_days)}
        ${big("Episodes reported", wd.episodes)}${wd.value_rs != null ? big(`Value at ₹${wd.daily_wage_rs} a day`, "₹" + Number(wd.value_rs).toLocaleString("en-IN"))
          : `<div class="out"><span class="mut small">Value in rupees</span><span class="small">Shown once an admin sets a daily wage on the Admin tab.</span></div>`}</div>
      <div class="row">
        <div class="grow"><table><tr><th>Type of illness</th><th>Episodes</th><th>Workdays</th><th>Carer days</th><th>School days</th><th>Admitted</th></tr>
          ${wd.by_class.map((c) => `<tr><td>${esc(c.label)}</td><td class="n">${c.episodes}</td><td class="n">${c.work_days}</td><td class="n">${c.carer_days}</td><td class="n">${c.school_days}</td><td class="n">${c.admitted}</td></tr>`).join("") || `<tr><td colspan="6">No water-related illness reported in this period.</td></tr>`}</table></div>
        <div class="side"><table><tr><th>Site</th><th>Episodes</th><th>Productive days</th></tr>
          ${wd.by_site.map((x) => `<tr><td>${esc(x.site)}</td><td class="n">${x.episodes}</td><td class="n">${x.work_days + x.carer_days}</td></tr>`).join("") || `<tr><td colspan="3">None yet.</td></tr>`}</table></div>
      </div>
      <p class="mut">${wd.per_1000_people != null ? `${wd.per_1000_people} productive days lost per 1,000 registered people. ` : ""}${esc(wd.note)}</p>
    </section>`;
  }

  async function renderReports(rid) {
    const q = `/api/reports?days=${S.rdays}` + (S.rform ? `&form_id=${encodeURIComponent(S.rform)}` : "");
    const showWd = can(...ANALYSTS, "ward");
    const [rep, wd] = await Promise.all([get(q), showWd ? get("/api/stats/workdays" + (S.wyear ? `?year=${S.wyear}` : "")) : null]);
    if (rid !== S.rid) return;
    const rows = rep.rows;
    const who = (r) => r.name ? esc(r.name) : r.person_id ? esc(r.person_id) : `<span class="mut">${r.hh_id === null ? "–" : "Name not shared"}</span>`;
    view().innerHTML = `
    ${wd ? workdaysCard(wd) : ""}
    <section class="card" aria-label="Reports"><p class="lbl">Household reports</p>
      <div class="form-row" style="justify-content:space-between"><h2 style="font-size:22px">Reported from households</h2>
        <div class="form-row">
          <label>Form<select data-act="rform"><option value="">All forms you can see</option>${rep.forms.map((f) => `<option value="${esc(f.form_id)}" ${f.form_id === S.rform ? "selected" : ""}>${esc(f.title)}</option>`).join("")}</select></label>
          <label>Period<select data-act="rdays">${[[7, "Past week"], [30, "Past month"], [90, "Past 3 months"], [365, "Past year"]].map(([v, l]) => `<option value="${v}" ${v === S.rdays ? "selected" : ""}>${l}</option>`).join("")}</select></label>
        </div></div>
      <p class="mut">Reported by ASHAs, volunteers and ward members after scanning the house sticker. ${S.user.role === "ward" ? "Names and household numbers are held by the health team." : can("scientist") ? "No names are shown in this view." : "Names appear only where the family agreed."}</p>
      ${rows.length ? `<div class="scroll" style="max-height:560px;overflow:auto"><table><tr><th>Date</th><th>Form</th><th>Site</th>${S.user.role === "ward" ? "" : "<th>Household</th><th>Person</th>"}<th>Age, sex</th><th>What</th><th>Water-related</th><th>Days ill</th><th>Workdays</th><th>Carer days</th><th>School days</th><th>Treatment</th><th>Reported by</th></tr>
        ${rows.map((r) => `<tr><td style="white-space:nowrap">${esc(r.date)}</td><td>${esc(r.form.replace("Report: ", ""))}</td><td>${esc(r.site)}</td>
          ${S.user.role === "ward" ? "" : `<td>${esc(r.hh_id || "–")}</td><td>${who(r)}</td>`}
          <td>${r.age == null ? "–" : esc(r.age)}${r.sex ? ", " + esc(r.sex) : ""}</td>
          <td>${r.danger ? '<b class="error">Danger signs</b> ' : ""}${esc(r.condition || (r.events || "").replace(/_/g, " ") || "–")}</td>
          <td>${esc(r.water_related || "–")}</td><td class="n">${r.days_ill == null ? "–" : r.days_ill}</td><td class="n">${r.work_days}</td>
          <td class="n">${r.carer_days}</td><td class="n">${r.school_days}</td><td>${esc(r.care || "–")}</td><td>${esc(r.reported_by || "–")}</td></tr>`).join("")}</table></div>`
        : `<p class="empty">No reports in this period.</p>`}
    </section>`;
  }

  // ---------------------------------------------------------------- admin
  async function renderAdmin(rid) {
    const admin = can("admin");
    const [audit, summary, srcs, rforms, wd] = await Promise.all([
      admin ? get("/api/admin/audit?limit=50") : [], get("/api/summary"), get("/api/admin/sources"),
      admin ? get("/api/admin/report-forms") : [], admin ? get("/api/stats/workdays") : null]);
    if (rid !== S.rid) return;
    const roleBoxes = (name, chosen) => Object.entries(ROLE_NAMES).map(([r, l]) => `<label class="check"><input type="checkbox" name="${name}" value="${r}" ${chosen.includes(r) ? "checked" : ""} ${r === "admin" ? "checked disabled" : ""}> ${l}</label>`).join("");
    view().innerHTML = `
    <div id="flash" class="mut" role="status" style="font-weight:600"></div>
    <section class="card" aria-label="Data sources"><p class="lbl">Data sources</p><h2>Where the data comes from</h2>
      <div class="scroll"><table><tr><th>Source</th><th>Brings in</th><th>Key</th><th>Last updated</th><th>Status</th><th></th></tr>
      ${srcs.map((x) => {
        const failing = x.last_error && (!x.last_ok || x.last_attempt > x.last_ok);
        const key = x.needs_key ? (x.key_present ? "Present" : "Missing") : "Not needed";
        return `<tr><td><b>${esc(x.name)}</b><br><span class="mut small">${esc(x.schedule)}</span></td><td>${esc(x.what)}</td>
          <td><span class="status ${x.needs_key ? (x.key_present ? "lv-low" : "lv-watch") : ""}" style="padding:2px 6px;border-radius:4px">${key}</span></td>
          <td>${x.last_ok ? esc(fmtDT(x.last_ok)) : "never"}<br><span class="mut small">${esc(x.coverage || "")}</span></td>
          <td>${failing ? `<span class="error">${esc(x.last_error)}</span>` : x.last_ok ? esc(x.detail || "OK") : `<span class="mut">${x.needs_key && !x.key_present ? "Waiting for a key" : "Not run yet"}</span>`}</td>
          <td>${x.fetch ? `<button type="button" class="btn small" data-act="src-fetch" data-id="${esc(x.key)}">Fetch now</button>` : ""}</td></tr>`;
      }).join("")}</table></div>
      <p class="mut">Keys are kept in the server's settings file, never on this page. This page shows only whether each key is there.</p></section>
    <div class="row">
      <section class="card third"><p class="lbl">Data</p><h2>Run jobs</h2>
        <div class="chips"><button type="button" class="btn" data-act="job" data-path="/api/rules/run">Generate advisories and decisions</button></div>
        <table><tr><th>Form</th><th>Last sync</th><th>Total</th></tr>${summary.sync.map((s) => `<tr><td>${esc(s.form)}</td><td>${esc(s.last_run ? fmtDT(s.last_run) : "never")}</td><td class="n">${esc(s.total)}</td></tr>`).join("") || `<tr><td colspan="3">Not synced yet.</td></tr>`}</table>
        <p class="mut">Sync and weather also run on their own schedule.</p></section>
      ${admin ? `<section class="card third"><p class="lbl">Sites</p><h2>Upload sites.csv</h2>
        <p class="mut">The same file attached to the ODK forms: name, label, site_type, lat, lon. Run tools/publish_sites.py to update the forms on ODK Central.</p>
        <input type="file" accept=".csv" data-act="upload" data-path="/api/import/sites"></section>
      <section class="card third"><p class="lbl">Users</p><h2>Add or update a user</h2>
        <form id="user-form" class="form-row" style="flex-direction:column;align-items:stretch">
          <label>Username<input name="username" required pattern="[a-z0-9._-]{3,60}"></label>
          <label>Full name<input name="full_name" required></label>
          <label>Role<select name="role">${Object.keys(ROLE_NAMES).map((r) => `<option>${r}</option>`).join("")}</select></label>
          <label>Sites (codes separated by spaces, or *)<input name="sites" value="*"></label>
          <label>Temporary password (10+ characters)<input name="password" type="password" minlength="10" required autocomplete="new-password"></label>
          <button class="btn primary" type="submit">Save user</button></form></section>` : ""}
    </div>
    ${admin ? `<section class="card" aria-label="Report forms"><p class="lbl">Household report forms</p><h2>Who sees each report form</h2>
      <p class="mut">Ticked roles see that form's reports on the Household reports tab. Names still appear only for roles that care for people (ASHA, doctor, coordinator, admin); ward members never see names.</p>
      <div class="scroll"><table><tr><th>Form</th><th>Who can see the reports</th><th>Phones that can fill it</th><th>Reports</th><th>On</th><th></th></tr>
      ${rforms.map((f) => `<tr data-rf="${esc(f.form_id)}"><td><input name="title" value="${esc(f.title)}" style="min-width:220px"><br><span class="mut small">${esc(f.form_id)}</span></td>
        <td><div class="chips">${roleBoxes("roles", f.visible_roles)}</div></td><td class="small">${esc(f.phone_groups || "–")}</td>
        <td class="n">${f.reports}</td><td><input type="checkbox" name="active" ${f.active ? "checked" : ""} aria-label="Form in use"></td>
        <td><button type="button" class="btn small" data-act="rf-save" data-id="${esc(f.form_id)}">Save</button></td></tr>`).join("")}</table></div>
      <form id="rf-upload" class="card" style="background:#F4F7F7">
        <h2>Add a new report form, or update one</h2>
        <p class="mut">1. <button type="button" class="btn small" data-act="rf-template">Download the template</button> and edit it in Excel: change the title, the form_id (must start with obs_report_) and the questions in the middle. Keep the household, person and "effect on daily life" questions so workdays lost keep adding up.<br>
          2. Choose who sees its reports and which phones can fill it, then publish. The phones get it the next time they refresh their forms.</p>
        <label>Form file (.xlsx)<input type="file" name="file" accept=".xlsx" required></label>
        <p class="mut small" style="margin-top:6px">Who sees the reports</p><div class="chips">${roleBoxes("roles", ["coordinator", "doctor", "asha"])}</div>
        <p class="mut small" style="margin-top:6px">Phones that can fill it</p><div id="pg-box" class="chips"><button type="button" class="btn small" data-act="pg-load">Show phone accounts</button></div>
        <button class="btn primary" type="submit">Publish to the phones</button></form>
      <form id="wage-form" class="form-row"><label>Daily wage used to value lost workdays (₹)<input name="wage" type="number" min="0" step="1" value="${wd && wd.daily_wage_rs != null ? esc(wd.daily_wage_rs) : ""}" placeholder="e.g. a local daily wage"></label>
        <button class="btn" type="submit">Save</button><span class="mut small">Leave empty to show days only.</span></form>
    </section>` : ""}
    ${admin ? `<section class="card"><p class="lbl">Audit log</p><h2>Last 50 requests</h2><div class="scroll"><table><tr><th>Time (UTC)</th><th>User</th><th>Request</th><th>Status</th><th>IP</th></tr>
      ${audit.map((a) => `<tr><td>${esc(a.at)}</td><td>${esc(a.user || "–")}</td><td>${esc(a.method + " " + a.path)}</td><td class="n">${esc(a.status)}</td><td>${esc(a.ip)}</td></tr>`).join("")}</table></div></section>` : ""}`;
    const f = $("#user-form");
    if (f) f.addEventListener("submit", async (e) => {
      e.preventDefault();
      const data = Object.fromEntries(new FormData(f).entries());
      try { await api("/api/admin/users", { method: "POST", json: data }); alertMsg(`Saved user ${data.username}.`); f.reset(); }
      catch (err) { alertMsg(err.message); }
    });
    const up = $("#rf-upload");
    if (up) up.addEventListener("submit", async (e) => {
      e.preventDefault();
      const fd = new FormData();
      fd.append("file", up.querySelector('input[name="file"]').files[0]);
      const roles = [...up.querySelectorAll('input[name="roles"]:checked')].map((x) => x.value).join(" ");
      const users = [...up.querySelectorAll('input[name="pg"]:checked')].map((x) => x.value).join(" ");
      alertMsg("Publishing…");
      try {
        const r = await api(`/api/admin/report-forms?visible_roles=${encodeURIComponent(roles)}&app_users=${encodeURIComponent(users)}`, { method: "POST", body: fd });
        alertMsg(`Published ${r.title}.`); render();
      } catch (err) { alertMsg(err.message); }
    });
    const wf = $("#wage-form");
    if (wf) wf.addEventListener("submit", async (e) => {
      e.preventDefault();
      const v = wf.querySelector('input[name="wage"]').value;
      try { await api("/api/admin/settings/wage", { method: "POST", json: { daily_wage_rs: v === "" ? null : Number(v) } }); alertMsg("Daily wage saved."); }
      catch (err) { alertMsg(err.message); }
    });
  }

  // ---------------------------------------------------------------- events
  view().addEventListener("click", async (e) => {
    const b = e.target.closest("[data-act]");
    if (!b) return;
    const act = b.dataset.act, id = b.dataset.id;
    try {
      if (act === "layer") { S.layer = id; render(); }
      else if (act === "site") { S.site = id; render(); }
      else if (act === "query") {
        S.query = id;
        document.querySelectorAll('[data-act="query"]').forEach((x) => x.setAttribute("aria-pressed", String(x.dataset.id === id)));
        runQuery(id);
      }
      else if (act === "decide") { await api(`/api/decisions/${id}`, { method: "POST", json: { status: b.dataset.status } }); render(); }
      else if (act === "adv") { await api(`/api/advisories/${id}`, { method: "POST", json: { status: b.dataset.status } }); render(); }
      else if (act === "sendlist") { await download("/api/advisories/send-list.csv", "send-list.csv"); }
      else if (act === "rf-template") { await download("/api/admin/report-form-template", "report_form_template.xlsx"); }
      else if (act === "src-fetch") {
        b.disabled = true; alertMsg("Fetching…");
        const r = await api(`/api/admin/sources/${encodeURIComponent(id)}/fetch`, { method: "POST" });
        await render(); alertMsg((r.ok ? "Done: " : "Not fetched: ") + r.result);
      }
      else if (act === "rf-save") {
        const row = document.querySelector(`tr[data-rf="${CSS.escape(id)}"]`);
        const body = { title: row.querySelector('input[name="title"]').value,
          visible_roles: [...row.querySelectorAll('input[name="roles"]:checked')].map((x) => x.value),
          active: row.querySelector('input[name="active"]').checked };
        await api(`/api/admin/report-forms/${encodeURIComponent(id)}`, { method: "POST", json: body });
        alertMsg("Saved.");
      }
      else if (act === "pg-load") {
        const users = await api("/api/admin/phone-groups");
        $("#pg-box").innerHTML = users.map((u) => `<label class="check"><input type="checkbox" name="pg" value="${u.id}"> ${esc(u.name)}</label>`).join("") || "No phone accounts found.";
      }
      else if (act === "export") { await download(`/api/export/${S.dataset}.csv`, `observatory-${S.dataset}.csv`); }
      else if (act === "job") {
        b.disabled = true; alertMsg("Working…");
        const r = await api(withQs(b.dataset.path), { method: "POST" });
        alertMsg("Done: " + JSON.stringify(r)); b.disabled = false;
      }
    } catch (err) { b.disabled = false; alertMsg(err.message); }
  });
  view().addEventListener("change", async (e) => {
    const t = e.target;
    if (t.dataset.act === "task") { S.done[t.dataset.id] = t.checked; }
    else if (t.dataset.act === "dataset") { S.dataset = t.value; render(); }
    else if (t.dataset.act === "sitetype") { S.siteType = t.value; render(); }
    else if (t.dataset.act === "rform") { S.rform = t.value; render(); }
    else if (t.dataset.act === "rdays") { S.rdays = Number(t.value); render(); }
    else if (t.dataset.act === "wyear") { S.wyear = t.value; render(); }
    else if (t.dataset.act === "upload" && t.files.length) {
      const fd = new FormData();
      fd.append("file", t.files[0]);
      try { const r = await api(t.dataset.path, { method: "POST", body: fd }); alertMsg("Uploaded: " + JSON.stringify(r)); }
      catch (err) { alertMsg(err.message); }
      t.value = "";
    }
  });
  view().addEventListener("input", (e) => {
    const k = e.target.dataset.scen;
    if (!k) return;
    S.scen[k] = Number(e.target.value);
    const lab = { rain_mm: "#v-rain", tide_m: "#v-tide", temp_c: "#v-temp", rh: "#v-rh" }[k];
    $(lab).textContent = k === "tide_m" ? S.scen[k].toFixed(1) : S.scen[k];
    clearTimeout(scenTimer);
    scenTimer = setTimeout(updateScenario, 200);
  });

  // ---------------------------------------------------------------- boot
  (async function boot() {
    try { S.token = sessionStorage.getItem("obs_token"); } catch (e) { S.token = null; }
    if (!S.token) return showLogin();
    try { await start(); } catch (e) { showLogin(); }
  })();
})();

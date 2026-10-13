/* Contractor estimator + schedule: single-page frontend (no build step). */
(() => {
  "use strict";

  // ------------------------------------------------------------ state
  const S = {
    user: null,
    pricing: null,          // {region, book, calculators, statuses, event_types}
    jobs: [],
    route: location.hash.slice(1) || "dashboard",
    calMonth: startOfMonth(new Date()),
  };
  const root = document.getElementById("root");

  // ------------------------------------------------------------ helpers
  const $ = (sel, el = document) => el.querySelector(sel);
  const $$ = (sel, el = document) => [...el.querySelectorAll(sel)];
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const money = (n) => (Number(n) || 0).toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
  const money2 = (n) => (Number(n) || 0).toLocaleString("en-US", { style: "currency", currency: "USD" });
  const num = (n) => (Number(n) || 0).toLocaleString("en-US", { maximumFractionDigits: 2 });
  const titleCase = (s) => String(s || "").replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  const STATUS_LABEL = { lead: "Lead", estimating: "Estimating", quoted: "Quoted", approved: "Approved", in_progress: "In progress", complete: "Complete", lost: "Lost" };
  const TYPE_LABEL = { site_visit: "Site visit", work: "Work day", inspection: "Inspection", delivery: "Delivery", meeting: "Meeting", other: "Other" };

  function startOfMonth(d) { return new Date(d.getFullYear(), d.getMonth(), 1); }
  function ymd(d) { return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; }
  function fmtDate(iso, opts = { month: "short", day: "numeric" }) { return iso ? new Date(iso).toLocaleDateString("en-US", opts) : ""; }
  function fmtTime(iso) { return iso ? new Date(iso).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" }) : ""; }
  function fmtDT(iso) { return iso ? `${fmtDate(iso, { weekday: "short", month: "short", day: "numeric" })} · ${fmtTime(iso)}` : ""; }
  function relDate(iso) {
    if (!iso) return "";
    const diff = (new Date(iso) - new Date()) / 864e5;
    if (Math.abs(diff) < 1) return "today";
    return diff < 0 ? `${Math.round(-diff)}d ago` : `in ${Math.round(diff)}d`;
  }

  async function api(path, opts = {}) {
    const r = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts, body: opts.body ? JSON.stringify(opts.body) : undefined });
    let data = {};
    try { data = await r.json(); } catch (_) { /* no body */ }
    if (r.status === 401 && S.user) { S.user = null; render(); }
    if (!r.ok) throw new Error(data.error || `Request failed (${r.status})`);
    return data;
  }

  function toast(msg, kind = "") {
    const t = document.createElement("div");
    t.className = `toast ${kind}`;
    t.textContent = msg;
    $("#toasts").appendChild(t);
    setTimeout(() => t.remove(), 3200);
  }

  function modal(html, { wide = false } = {}) {
    const bg = document.createElement("div");
    bg.className = "modal-bg";
    bg.innerHTML = `<div class="modal ${wide ? "wide" : ""}">${html}</div>`;
    bg.addEventListener("click", (e) => { if (e.target === bg) close(); });
    const onKey = (e) => { if (e.key === "Escape") close(); };
    document.addEventListener("keydown", onKey);
    document.body.appendChild(bg);
    function close() { bg.remove(); document.removeEventListener("keydown", onKey); }
    $$("[data-close]", bg).forEach((b) => b.addEventListener("click", close));
    return { el: bg, close };
  }

  function askNumber(title, text, initial) {
    return new Promise((res) => {
      const m = modal(`<h2>${esc(title)}</h2><p class="muted">${esc(text)}</p><input type="number" step="any" id="askn" value="${esc(initial)}" style="max-width:160px">
        <div class="actions"><button class="btn" data-close>Cancel</button><button class="btn primary" id="ok">OK</button></div>`);
      const inp = $("#askn", m.el);
      setTimeout(() => { inp.focus(); inp.select(); }, 30);
      const ok = () => { const v = parseFloat(inp.value); m.close(); res(v > 0 ? v : null); };
      $("#ok", m.el).onclick = ok;
      inp.onkeydown = (e) => { if (e.key === "Enter") ok(); };
      m.el.addEventListener("click", (e) => { if (e.target === m.el) res(null); });
      $("[data-close]", m.el).addEventListener("click", () => res(null));
    });
  }

  function confirmDlg(text) {
    return new Promise((res) => {
      const m = modal(`<h2>Are you sure?</h2><p class="muted">${esc(text)}</p>
        <div class="actions"><button class="btn" data-close>Cancel</button><button class="btn danger" id="ok">Delete</button></div>`);
      $("#ok", m.el).onclick = () => { m.close(); res(true); };
      m.el.addEventListener("click", (e) => { if (e.target === m.el) res(false); });
    });
  }

  const formData = (form) => {
    const o = {};
    new FormData(form).forEach((v, k) => (o[k] = v));
    $$("input[type=checkbox]", form).forEach((c) => (o[c.name] = c.checked));
    return o;
  };

  const ICON = {
    dash: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/></svg>',
    jobs: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 7h18v13H3z"/><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>',
    calc: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="4" y="2" width="16" height="20" rx="2"/><path d="M8 6h8M8 11h2M12 11h2M16 11h0M8 15h2M12 15h2M16 15v3"/></svg>',
    cal: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="17" rx="2"/><path d="M3 9h18M8 2v4M16 2v4"/></svg>',
    book: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 4h12a3 3 0 0 1 3 3v13H7a3 3 0 0 0-3 3z"/><path d="M4 4v16"/><path d="M8 9h7M8 13h5"/></svg>',
    gear: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/></svg>',
    plus: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M12 5v14M5 12h14"/></svg>',
    trash: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/></svg>',
    ruler: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="8" width="20" height="8" rx="1.5"/><path d="M6 8v3M10 8v4M14 8v3M18 8v4"/></svg>',
    move: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 12h16M14 6l6 6-6 6"/></svg>',
    refresh: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a9 9 0 1 1-2.6-6.4"/><path d="M21 3v6h-6"/></svg>',
    lock: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/></svg>',
    ext: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 4h6v6M20 4l-9 9M19 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h5"/></svg>',
  };

  // ------------------------------------------------------------ boot
  async function boot() {
    const { user } = await api("/api/auth/me");
    S.user = user;
    if (user) await loadPricing();
    render();
  }
  async function loadPricing() { S.pricing = await api("/api/pricing"); }
  async function loadJobs() { S.jobs = (await api("/api/jobs")).jobs; return S.jobs; }

  window.addEventListener("hashchange", () => { S.route = location.hash.slice(1) || "dashboard"; render(); });
  const go = (r) => { location.hash = r; };

  // ------------------------------------------------------------ render shell
  function render() {
    if (!S.user) return renderAuth();
    const [page, arg] = S.route.split("/");
    const nav = [["dashboard", "Dashboard", ICON.dash], ["jobs", "Jobs", ICON.jobs], ["calculators", "Calculators", ICON.calc], ["schedule", "Schedule", ICON.cal], ["pricebook", "Price book", ICON.book], ["settings", "Settings", ICON.gear]];
    root.innerHTML = `
      <div id="app">
        <aside class="sidebar">
          <div class="brand"><div class="logo">${esc((S.user.business_name || "C")[0].toUpperCase())}</div>
            <div><div class="name">${esc(S.user.business_name || "Job Estimator")}</div></div></div>
          <nav class="nav">${nav.map(([r, l, i]) => `<a href="#${r}" class="${page === r ? "active" : ""}">${i}<span>${l}</span></a>`).join("")}</nav>
          <div class="spacer"></div>
          <div class="userbox"><div class="biz">${esc(S.user.name || S.user.email)}</div><div class="dim">${esc(S.user.email)}</div>
            <button class="btn ghost sm mt" id="logout">Sign out</button></div>
        </aside>
        <main class="main" id="main"></main>
      </div>`;
    $("#logout").onclick = async () => { await api("/api/auth/logout", { method: "POST" }); S.user = null; render(); };
    const pages = { dashboard: pageDashboard, jobs: arg ? () => pageJob(+arg) : pageJobs, calculators: () => pageCalculators(arg), schedule: pageSchedule, pricebook: pagePriceBook, settings: pageSettings };
    (pages[page] || pageDashboard)();
  }

  const main = () => $("#main");
  const head = (title, sub = "", actions = "") => `<div class="page-head"><div><h1>${title}</h1>${sub ? `<div class="sub">${sub}</div>` : ""}</div><div class="row">${actions}</div></div>`;

  // ------------------------------------------------------------ auth
  function renderAuth(mode = "login") {
    root.innerHTML = `
      <div class="auth-wrap"><div class="auth"><div class="card">
        <div class="tabs"><button class="${mode === "login" ? "active" : ""}" data-m="login">Sign in</button><button class="${mode === "register" ? "active" : ""}" data-m="register">Create account</button></div>
        <form id="authf" class="stack">
          ${mode === "register" ? `<label class="field"><span>Your name</span><input name="name" type="text" autocomplete="name"></label>
          <label class="field"><span>Business name</span><input name="business_name" type="text" placeholder="e.g. Cape Fear Carpentry LLC"></label>` : ""}
          <label class="field"><span>Email</span><input name="email" type="email" required autocomplete="username"></label>
          <label class="field"><span>Password</span><input name="password" type="password" required minlength="8" autocomplete="${mode === "login" ? "current-password" : "new-password"}"></label>
          <div class="error" id="autherr"></div>
          <button class="btn primary" style="justify-content:center">${mode === "login" ? "Sign in" : "Create account"}</button>
        </form>
        ${mode === "login" ? `<div class="right" style="margin-top:12px"><a href="#" id="demo" class="dim" style="font-size:12px">Use demo account</a></div>` : ""}
      </div></div></div>`;
    $$(".tabs button").forEach((b) => (b.onclick = () => renderAuth(b.dataset.m)));
    const demo = $("#demo");
    if (demo) demo.onclick = (e) => { e.preventDefault(); $("[name=email]").value = "demo@example.com"; $("[name=password]").value = "demo1234"; $("#authf").requestSubmit(); };
    $("#authf").onsubmit = async (e) => {
      e.preventDefault();
      try {
        const { user } = await api(`/api/auth/${mode}`, { method: "POST", body: formData(e.target) });
        S.user = user; await loadPricing(); render();
      } catch (err) { $("#autherr").textContent = err.message; }
    };
  }

  // ------------------------------------------------------------ dashboard
  async function pageDashboard() {
    const hr = new Date().getHours(), first = (S.user.name || "").split(" ")[0];
    const hello = `${hr < 12 ? "Morning" : hr < 17 ? "Afternoon" : "Evening"}${first ? `, ${esc(first)}` : ""}.`;
    main().innerHTML = head(`<span class="greeting">${hello}</span>`, new Date().toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" }),
      `<button class="btn" id="newev">${ICON.plus} Schedule</button><button class="btn primary" id="newjob">${ICON.plus} New job</button>`) + `<div id="dash" class="empty">Loading…</div>`;
    $("#newjob").onclick = () => jobModal();
    $("#newev").onclick = () => eventModal();
    const d = await api("/api/dashboard");
    const active = Object.entries(d.by_status).filter(([s]) => !["complete", "lost"].includes(s)).reduce((a, [, v]) => a + v.count, 0);
    const totalCount = Object.values(d.by_status).reduce((a, v) => a + v.count, 0) || 1;
    $("#dash").className = "";
    $("#dash").innerHTML = `
      <div class="grid c4">
        <div class="card stat"><div class="label">Pipeline (estimating + quoted)</div><div class="value accent">${money(d.pipeline_value)}</div><div class="foot">${d.by_status.estimating.count + d.by_status.quoted.count} jobs waiting on a yes</div></div>
        <div class="card stat"><div class="label">Booked work</div><div class="value">${money(d.booked_value)}</div><div class="foot">${d.by_status.approved.count + d.by_status.in_progress.count} approved or in progress</div></div>
        <div class="card stat"><div class="label">Active jobs</div><div class="value">${active}</div><div class="foot">${d.by_status.lead.count} new leads</div></div>
        <div class="card stat"><div class="label">Next 7 days</div><div class="value">${d.upcoming.filter((e) => (new Date(e.start) - Date.now()) < 7 * 864e5).length}</div><div class="foot">scheduled events</div></div>
      </div>
      <div class="grid side mt">
        <div>
          <div class="card">
            <div class="card-head"><h3>Job pipeline</h3><a href="#jobs">All jobs</a></div>
            <div class="pipe">${Object.entries(d.by_status).map(([s, v]) => `<span class="c-${s}" style="width:${(v.count / totalCount) * 100}%" title="${STATUS_LABEL[s]}: ${v.count}"></span>`).join("")}</div>
            <div class="legend">${Object.entries(d.by_status).map(([s, v]) => `<span><i class="c-${s}"></i>${STATUS_LABEL[s]} <b>${v.count}</b> <span class="dim">${money(v.value)}</span></span>`).join("")}</div>
          </div>
          <div class="card pad-0">
            <div class="card-head" style="padding:14px 18px 0"><h3>Recent jobs</h3></div>
            ${jobsTable(d.recent_jobs)}
          </div>
        </div>
        <div class="card">
          <div class="card-head"><h3>Coming up</h3><a href="#schedule">Calendar</a></div>
          ${agenda(d.upcoming)}
        </div>
      </div>`;
    wireJobRows();
    wireAgenda();
  }

  function agenda(events) {
    if (!events.length) return `<div class="empty">Nothing scheduled.</div>`;
    return `<div class="agenda">${events.map((e) => `
      <div class="item" data-ev='${esc(JSON.stringify(e))}'>
        <div class="when"><div class="d">${new Date(e.start).getDate()}</div><div class="m">${fmtDate(e.start, { month: "short" })}</div><div class="t">${e.all_day ? "all day" : fmtTime(e.start)}</div></div>
        <div class="what"><div class="title"><span class="dot ${e.type}"></span>${esc(e.title)}</div>
          <div class="sub">${e.job_no ? `<a href="#jobs/${e.job_id}">${esc(e.job_no)}</a> · ${esc(e.job_title)}` : TYPE_LABEL[e.type] || ""}${e.location ? ` · ${esc(e.location)}` : ""}</div></div>
      </div>`).join("")}</div>`;
  }
  function wireAgenda() { $$(".agenda .item").forEach((el) => (el.onclick = (e) => { if (e.target.tagName === "A") return; eventModal(JSON.parse(el.dataset.ev)); })); }

  // ------------------------------------------------------------ jobs list
  function jobsTable(jobs, { withStatus = false } = {}) {
    if (!jobs.length) return `<div class="empty">No jobs yet. Create one to start estimating.</div>`;
    return `<div class="table-wrap"><table>
      <thead><tr><th>Job</th><th>Client</th><th>Type</th><th>Status</th><th class="num">Estimate</th><th>Updated</th></tr></thead>
      <tbody>${jobs.map((j) => `<tr class="clickable" data-id="${j.id}">
        <td><div style="font-weight:600">${esc(j.title)}</div><div class="dim mono" style="font-size:11.5px">${esc(j.job_no)}</div></td>
        <td>${esc(j.client_name || "—")}<div class="dim" style="font-size:12px">${esc(j.address || "")}</div></td>
        <td class="muted">${esc(j.job_type || "—")}</td>
        <td>${withStatus ? statusSelect(j) : `<span class="badge ${j.status}">${STATUS_LABEL[j.status]}</span>`}</td>
        <td class="num">${money(j.summary.total)}</td>
        <td class="dim">${relDate(j.updated_at)}</td></tr>`).join("")}</tbody></table></div>`;
  }
  function statusSelect(j) {
    return `<select class="status-select badge ${j.status}" data-status="${j.id}">${S.pricing.statuses.map((s) => `<option value="${s}" ${s === j.status ? "selected" : ""}>${STATUS_LABEL[s]}</option>`).join("")}</select>`;
  }
  function wireJobRows() {
    $$("tr[data-id]").forEach((tr) => (tr.onclick = (e) => { if (e.target.tagName === "SELECT") return; go(`jobs/${tr.dataset.id}`); }));
    $$("select[data-status]").forEach((sel) => (sel.onchange = async () => {
      await api(`/api/jobs/${sel.dataset.status}`, { method: "PUT", body: { status: sel.value } });
      sel.className = `status-select badge ${sel.value}`;
      toast("Status updated", "ok");
    }));
  }

  async function pageJobs() {
    let filter = "all", q = "", hideDone = true;
    try { hideDone = localStorage.getItem("hideDone") !== "0"; } catch (_) { /* ignore */ }
    main().innerHTML = head("Jobs", "", `<button class="btn primary" id="newjob">${ICON.plus} New job</button>`) + `
      <div class="row between wrap mb"><div class="chips" id="chips"></div><div class="row"><label class="check" style="padding:0;white-space:nowrap"><input type="checkbox" id="hidedone"> Hide completed</label><input type="text" id="q" placeholder="Search client, address, job…" style="max-width:280px"></div></div>
      <div class="card pad-0" id="list"><div class="empty">Loading…</div></div>`;
    $("#newjob").onclick = () => jobModal();
    await loadJobs();
    const draw = () => {
      const counts = { all: S.jobs.length };
      S.jobs.forEach((j) => (counts[j.status] = (counts[j.status] || 0) + 1));
      $("#chips").innerHTML = ["all", ...S.pricing.statuses].filter((s) => s === "all" || counts[s]).map((s) =>
        `<button class="chip ${filter === s ? "active" : ""}" data-f="${s}">${s === "all" ? "All" : STATUS_LABEL[s]} <span class="dim">${counts[s] || 0}</span></button>`).join("");
      $$("#chips .chip").forEach((c) => (c.onclick = () => { filter = c.dataset.f; draw(); }));
      const rows = S.jobs.filter((j) => (filter === "all" ? !(hideDone && ["complete", "lost"].includes(j.status)) : j.status === filter) && (!q || `${j.title} ${j.client_name} ${j.address} ${j.job_no} ${j.job_type}`.toLowerCase().includes(q)));
      $("#list").innerHTML = jobsTable(rows, { withStatus: true });
      wireJobRows();
    };
    $("#q").oninput = (e) => { q = e.target.value.toLowerCase(); draw(); };
    $("#hidedone").checked = hideDone;
    $("#hidedone").onchange = (e) => { hideDone = e.target.checked; try { localStorage.setItem("hideDone", hideDone ? "1" : "0"); } catch (_) { /* ignore */ } draw(); };
    draw();
  }

  function jobModal(job = null, onSaved) {
    const j = job || {};
    const isEdit = !!(job && job.id);
    const m = modal(`<h2>${isEdit ? "Edit job" : "New job"}</h2>
      <form id="jf" class="form-grid">
        <label class="field full"><span>Job title *</span><input name="title" type="text" required value="${esc(j.title || "")}" placeholder="e.g. Backyard composite deck"></label>
        <label class="field"><span>Client name</span><input name="client_name" type="text" value="${esc(j.client_name || "")}"></label>
        <label class="field"><span>Phone</span><input name="client_phone" type="text" value="${esc(j.client_phone || "")}"></label>
        <label class="field"><span>Email</span><input name="client_email" type="email" value="${esc(j.client_email || "")}"></label>
        <label class="field"><span>Job type</span><input name="job_type" type="text" list="jtypes" value="${esc(j.job_type || "")}" placeholder="Deck, Roofing, Addition…">
          <datalist id="jtypes">${["Deck", "Interior", "Framing", "Drywall", "Trim", "Paint", "Remodel", "Repair", "Other"].map((t) => `<option value="${t}">`).join("")}</datalist></label>
        <label class="field full"><span>Job address</span><input name="address" type="text" value="${esc(j.address || "")}" placeholder="Street, Wilmington, NC"></label>
        <label class="field"><span>Status</span><select name="status">${S.pricing.statuses.map((s) => `<option value="${s}" ${(j.status || "lead") === s ? "selected" : ""}>${STATUS_LABEL[s]}</option>`).join("")}</select></label>
        <label class="field full"><span>Notes</span><textarea name="notes" placeholder="Access, HOA, client preferences, scope notes…">${esc(j.notes || "")}</textarea></label>
      </form>
      <div class="actions"><button class="btn" data-close>Cancel</button><button class="btn primary" id="save">${isEdit ? "Save" : "Create job"}</button></div>`);
    $("#save", m.el).onclick = async () => {
      const f = $("#jf", m.el);
      if (!f.reportValidity()) return;
      try {
        const res = isEdit ? await api(`/api/jobs/${job.id}`, { method: "PUT", body: formData(f) }) : await api("/api/jobs", { method: "POST", body: formData(f) });
        m.close(); toast(isEdit ? "Job saved" : "Job created", "ok");
        if (onSaved) onSaved(res.job); else go(`jobs/${res.job.id}`);
      } catch (err) { toast(err.message, "err"); }
    };
    setTimeout(() => $("[name=title]", m.el).focus(), 30);
  }

  // ------------------------------------------------------------ favorites
  const isFav = (id) => (S.user.favorites || []).includes(id);
  const starHtml = (id) => `<button class="star ${isFav(id) ? "on" : ""}" data-fav="${esc(id)}" title="${isFav(id) ? "Remove from favorites" : "Add to favorites"}">${isFav(id) ? "★" : "☆"}</button>`;
  async function toggleFav(id) {
    const cur = S.user.favorites || [];
    const next = cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id];
    const { user } = await api("/api/settings", { method: "PUT", body: { favorites: next } });
    S.user = user;
  }
  function wireStars(root_, after) {
    $$("[data-fav]", root_).forEach((b) => (b.onclick = async (e) => { e.stopPropagation(); await toggleFav(b.dataset.fav); if (after) after(); }));
  }
  const sectionOptions = (val) => Object.entries(S.pricing.sections).map(([k, l]) => `<option value="${k}" ${val === k ? "selected" : ""}>${esc(l)}</option>`).join("") + `<option value="Misc" ${!(val in S.pricing.sections) ? "selected" : ""}>Misc / other</option>`;

  // ------------------------------------------------------------ market prices
  async function refreshMarketPrices(btn, after) {
    if (btn) { btn.disabled = true; btn.textContent = "Checking…"; }
    try {
      const r = await api("/api/prices/refresh", { method: "POST" });
      await loadPricing();
      const moved = r.sections.filter((x) => Math.abs(x.since_last_pct) >= 0.05);
      if (!moved.length && r.repriced_items === 0) toast(`Already current with the ${r.latest_month} index data. New data posts around the middle of each month.`, "ok");
      else {
        const moves = r.sections.map((x) => `${x.label.replace("PPI ", "")} ${x.change_pct >= 0 ? "+" : ""}${x.change_pct}%`).join(", ");
        toast(`Prices updated (${r.latest_month}): ${moves}. ${r.repriced_items} line${r.repriced_items === 1 ? "" : "s"} on ${r.repriced_jobs} open estimate${r.repriced_jobs === 1 ? "" : "s"} repriced.`, "ok");
      }
      if (after) after();
    } catch (err) { toast(err.message, "err"); }
    finally { if (btn) { btn.disabled = false; btn.innerHTML = `${ICON.refresh} Update market prices`; } }
  }
  function marketMetaLine() {
    const m = S.pricing.price_meta;
    if (!m || !m.updated) return `<span class="dim">Prices not yet updated from the market index.</span>`;
    return `<span class="dim">Market prices as of ${esc(m.latest_month)} · updated ${fmtDate(m.updated, { month: "short", day: "numeric", year: "numeric" })}</span>`;
  }

  // ------------------------------------------------------------ totals + competitors
  function totalsHtml(sm) {
    const hrs = sm.labor_hours_adj || sm.labor_hours || 0;
    return `<h3 class="mb">Totals</h3><div class="totals">
      ${Object.entries(sm.by_category).map(([c, v]) => `<div class="line"><span><span class="cat ${c}">${c}</span>${c === "labor" ? ` <span class="dim">${num(sm.labor_hours)} hr</span>` : ""}</span><b>${money2(v)}</b></div>`).join("")}
      <div class="line" style="border-top:1px solid var(--border);padding-top:7px"><span>Direct cost</span><b>${money2(sm.direct_cost)}</b></div>
      ${sm.conditions_adj ? `<div class="line"><span>Site conditions (+${sm.conditions_pct}% labor)</span><b>${money2(sm.conditions_adj)}</b></div>` : ""}
      ${sm.trips_cost ? `<div class="line"><span>${sm.trips} trips × ${money2(sm.trip_charge)}</span><b>${money2(sm.trips_cost)}</b></div>` : ""}
      <div class="line"><span>Sales tax on materials (${sm.tax_pct}%)</span><b>${money2(sm.sales_tax)}</b></div>
      <div class="line"><span>Contingency (${sm.contingency_pct}%)</span><b>${money2(sm.contingency)}</b></div>
      <div class="line"><span>Markup on materials + pass-throughs (${sm.markup_pct}%)</span><b>${money2(sm.markup)}</b></div>
      ${sm.minimum_adj ? `<div class="line"><span>Minimum job charge (${money(sm.minimum_job)})</span><b>${money2(sm.minimum_adj)}</b></div>` : ""}
      <div class="line grand"><span>Client price</span><b>${money2(sm.total)}</b></div>
      ${hrs ? `<div class="dim" style="font-size:12px;text-align:right">≈ ${num(hrs)} man-hours · ${num(sm.crew_days)} days with a ${sm.crew_size}-person crew</div>` : ""}
    </div>`;
  }

  function competitorsHtml(bands, ours) {
    if (!bands || !bands.length || !ours) return `<h3 class="mb">What others would likely quote</h3><div class="dim">Add line items first.</div>`;
    const lo = Math.min(...bands.map((b) => b.low), ours), hi = Math.max(...bands.map((b) => b.high), ours);
    const pct = (v) => ((v - lo) / (hi - lo || 1)) * 100;
    const mine = bands.find((b) => ours >= b.low && ours <= b.high);
    const verdict = mine ? `sits in the <b>${esc(mine.name.toLowerCase())}</b> range.` : ours < bands[0].low ? "is <b>below handyman rates</b>. Check the hours." : ours > bands[bands.length - 1].high ? "is <b>above established-remodeler rates</b>." : "is between bands.";
    return `<h3 class="mb">What others would likely quote</h3><div class="cmp">${bands.map((b) => `
      <div class="band ${b.key}" title="${esc(b.blurb)}"><div class="name">${esc(b.name)}<small>$${b.rate}/hr · ${b.markup}% on materials</small></div>
        <div class="track"><span style="left:${pct(b.low).toFixed(1)}%;width:${(pct(b.high) - pct(b.low)).toFixed(1)}%"></span><i class="you" style="left:${pct(ours).toFixed(1)}%"></i></div>
        <div class="range">${money(b.low)} – ${money(b.high)}</div></div>`).join("")}</div>
      <div class="dim mt" style="font-size:12px">Your price <b style="color:var(--accent)">${money(ours)}</b> ${verdict}</div>`;
  }

  // ------------------------------------------------------------ job detail
  async function pageJob(id) {
    let job;
    try { job = (await api(`/api/jobs/${id}`)).job; } catch (_) { main().innerHTML = head("Job not found") + `<a href="#jobs">Back to jobs</a>`; return; }
    // groups start collapsed; the ones he opens are remembered per job
    const openKey = `open-${id}`;
    let opened = new Set();
    try { opened = new Set(JSON.parse(localStorage.getItem(openKey) || "[]")); } catch (_) { /* ignore */ }
    const saveOpened = () => { try { localStorage.setItem(openKey, JSON.stringify([...opened])); } catch (_) { /* ignore */ } };
    const draw = () => {
      const u = S.user, sm = job.summary;
      const groups = {};
      job.items.forEach((it) => { (groups[it.group_label || "Other items"] ||= []).push(it); });
      main().innerHTML = head(`<span class="dim mono" style="font-size:14px;font-weight:500">${esc(job.job_no)}</span> ${esc(job.title)}`,
        `${esc(job.client_name || "No client")}${job.job_type ? ` · ${esc(job.job_type)}` : ""}`,
        `${job.locked ? `<span class="badge quoted" title="Unit prices are frozen once a job is quoted">${ICON.lock} Prices locked</span>` : !job.price_sync ? `<span class="badge estimating" title="This job keeps its prices until you update them">${ICON.lock} Prices held${job.stale_count ? ` · ${job.stale_count} differ from price book` : ""}</span> <button class="btn sm" id="reprice">${ICON.refresh} Update to price book</button>` : `<button class="btn ghost sm" id="hold" title="Stop this job following price book changes">Hold prices</button>`} ${statusSelect(job)} <button class="btn" id="edit">Edit</button><button class="btn" id="proposal">Proposal preview</button><button class="btn ghost danger" id="del">${ICON.trash}</button>`) + `
        <div class="grid side">
          <div>
            <div class="card pad-0">
              <div class="card-head" style="padding:14px 18px 0"><h3>Estimate</h3>
                <div class="row">${Object.keys(groups).length > 1 ? `<button class="btn ghost sm" id="togall">${Object.keys(groups).every((g) => opened.has(g)) ? "Collapse all" : "Expand all"}</button>` : ""}<button class="btn sm" id="addcustom">${ICON.plus} Custom line</button><button class="btn sm" id="addmat">${ICON.plus} From price book</button><button class="btn sm primary" id="addcalc">${ICON.plus} From calculator</button></div></div>
              ${job.items.length ? `<div class="table-wrap"><table>
                <thead><tr><th style="width:44%">Item</th><th>Type</th><th class="num">Qty</th><th>Unit</th><th class="num">Unit cost</th><th class="num">Total</th><th></th></tr></thead>
                <tbody>${Object.entries(groups).map(([g, items], gi) => { const open = opened.has(g); return `
                  <tr class="group-head clickable" data-toggle="${esc(g)}"><td colspan="5"><span class="chev ${open ? "open" : ""}">▸</span> ${esc(g)} <span class="dim" style="font-weight:400;font-size:12px">· ${items[0].source === "custom" ? "custom" : titleCase(items[0].source)} · ${items.length} line${items.length === 1 ? "" : "s"}</span></td>
                    <td class="num">${money2(items.reduce((a, i) => a + i.total, 0))}</td>
                    <td class="right"><button class="btn ghost xs danger" data-delgroup="${esc(g)}" title="Remove group">${ICON.trash}</button></td></tr>
                  ${items.map((it) => `<tr class="${open ? "" : "hidden"}" data-group="${esc(g)}">
                    <td>${esc(it.description)}</td><td><span class="cat ${it.category}">${it.category}</span></td>
                    <td class="num"><input class="inline-num" data-qty="${it.id}" value="${it.qty}"></td><td class="dim">${esc(it.unit)}</td>
                    <td class="num"><input class="inline-num" data-uc="${it.id}" value="${it.unit_cost}" ${job.locked ? "disabled" : ""}></td>
                    <td class="num">${money2(it.total)}</td>
                    <td class="right"><button class="btn ghost xs" data-delitem="${it.id}" title="Remove">✕</button></td></tr>`).join("")}`; }).join("")}
                </tbody></table></div>` : `<div class="empty">No line items yet. Add from a calculator or type a custom line.</div>`}
            </div>
            <div class="card">
              <div class="card-head"><h3>Schedule for this job</h3><button class="btn sm" id="addev">${ICON.plus} Add to schedule</button></div>
              ${job.events.length ? agenda(job.events) : `<div class="dim">Nothing scheduled yet.</div>`}
            </div>
          </div>
          <div>
            <div class="card">
              ${totalsHtml(sm)}
              <div class="pct-row mt">
                <label class="field"><span>Markup %</span><input type="number" step="0.5" data-pct="markup_pct" value="${job.markup_pct ?? ""}" placeholder="${u.markup_pct}"></label>
                <label class="field"><span>Contingency %</span><input type="number" step="0.5" data-pct="contingency_pct" value="${job.contingency_pct ?? ""}" placeholder="${u.contingency_pct}"></label>
                <label class="field"><span>Tax %</span><input type="number" step="0.25" data-pct="tax_pct" value="${job.tax_pct ?? ""}" placeholder="${u.tax_pct}"></label>
              </div>
            </div>
            <div class="card">
              <h3 class="mb">Job factors</h3>
              <div class="stack" style="gap:2px">${S.pricing.conditions.map((c) => `<label class="check"><input type="checkbox" data-cond="${c.key}" ${(job.conditions || []).includes(c.key) ? "checked" : ""}> ${esc(c.label)} <span class="dim">+${c.pct}%</span></label>`).join("")}</div>
              <label class="field mt"><span>Trips to the site</span><input type="number" min="0" step="1" id="trips" value="${job.trips || 0}" style="max-width:120px"></label>
            </div>
            <div class="card">${competitorsHtml(job.competitors, sm.total)}</div>
            <div class="card">
              <h3 class="mb">Client</h3>
              <dl class="kv">
                <dt>Name</dt><dd>${esc(job.client_name || "—")}</dd>
                <dt>Phone</dt><dd>${job.client_phone ? `<a href="tel:${esc(job.client_phone)}">${esc(job.client_phone)}</a>` : "—"}</dd>
                <dt>Email</dt><dd>${job.client_email ? `<a href="mailto:${esc(job.client_email)}">${esc(job.client_email)}</a>` : "—"}</dd>
                <dt>Address</dt><dd>${job.address ? `<a target="_blank" rel="noopener" href="https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(job.address)}">${esc(job.address)} ${ICON.ext}</a>` : "—"}</dd>
                <dt>Created</dt><dd>${fmtDate(job.created_at, { month: "short", day: "numeric", year: "numeric" })}</dd>
              </dl>
            </div>
            ${job.notes ? `<div class="card"><h3 class="mb">Notes</h3><div class="notes-box">${esc(job.notes)}</div></div>` : ""}
          </div>
        </div>`;

      wireAgenda();
      $$("tr[data-toggle]").forEach((tr) => (tr.onclick = (e) => {
        if (e.target.closest("button")) return;
        const g = tr.dataset.toggle;
        if (opened.has(g)) opened.delete(g); else opened.add(g);
        saveOpened(); draw();
      }));
      const ta = $("#togall");
      if (ta) ta.onclick = () => { if (Object.keys(groups).every((g) => opened.has(g))) opened.clear(); else Object.keys(groups).forEach((g) => opened.add(g)); saveOpened(); draw(); };
      $("select[data-status]").onchange = async (e) => { job = (await api(`/api/jobs/${job.id}`, { method: "PUT", body: { status: e.target.value } })).job; draw(); toast("Status updated", "ok"); };
      $("#edit").onclick = () => jobModal(job, (j) => { job = j; draw(); });
      const rp = $("#reprice");
      if (rp) rp.onclick = async () => { const r = await api(`/api/jobs/${job.id}/reprice`, { method: "POST", body: { follow: true } }); job = r.job; draw(); toast(`${r.repriced} line${r.repriced === 1 ? "" : "s"} updated. This job now follows the price book.`, "ok"); };
      const hd = $("#hold");
      if (hd) hd.onclick = async () => { job = (await api(`/api/jobs/${job.id}`, { method: "PUT", body: { price_sync: false } })).job; draw(); toast("Prices held"); };
      $("#del").onclick = async () => { if (await confirmDlg(`Delete "${job.title}" and its estimate? Scheduled events are kept but unlinked.`)) { await api(`/api/jobs/${job.id}`, { method: "DELETE" }); toast("Job deleted"); go("jobs"); } };
      $("#addcalc").onclick = () => go(`calculators/${job.id}`);
      $("#addev").onclick = () => eventModal({ job_id: job.id, location: job.address }, () => reload());
      $("#proposal").onclick = () => proposalModal(job);
      $("#addcustom").onclick = () => customLineModal(job, (j) => { job = j; draw(); });
      $("#addmat").onclick = () => materialPickerModal(job, (j) => { job = j; draw(); });
      $$("[data-delitem]").forEach((b) => (b.onclick = async () => { job = (await api(`/api/jobs/${job.id}/items/${b.dataset.delitem}`, { method: "DELETE" })).job; draw(); }));
      $$("[data-delgroup]").forEach((b) => (b.onclick = async () => { if (await confirmDlg(`Remove all lines in "${b.dataset.delgroup}"?`)) { job = (await api(`/api/jobs/${job.id}/groups?label=${encodeURIComponent(b.dataset.delgroup)}`, { method: "DELETE" })).job; draw(); } }));
      const saveItem = async (id, body) => { job = (await api(`/api/jobs/${job.id}/items/${id}`, { method: "PUT", body })).job; draw(); };
      $$("[data-qty]").forEach((i) => (i.onchange = () => saveItem(i.dataset.qty, { qty: i.value })));
      $$("[data-uc]").forEach((i) => (i.onchange = () => saveItem(i.dataset.uc, { unit_cost: i.value })));
      $$("[data-pct]").forEach((i) => (i.onchange = async () => { job = (await api(`/api/jobs/${job.id}`, { method: "PUT", body: { [i.dataset.pct]: i.value } })).job; draw(); }));
      $$("[data-cond]").forEach((i) => (i.onchange = async () => { const conds = $$("[data-cond]").filter((c) => c.checked).map((c) => c.dataset.cond); job = (await api(`/api/jobs/${job.id}`, { method: "PUT", body: { conditions: conds } })).job; draw(); }));
      $("#trips").onchange = async (e) => { job = (await api(`/api/jobs/${job.id}`, { method: "PUT", body: { trips: e.target.value } })).job; draw(); };
    };
    const reload = async () => { job = (await api(`/api/jobs/${id}`)).job; draw(); };
    draw();
  }

  function customLineModal(job, onSaved) {
    const m = modal(`<h2>Add custom line</h2>
      <form id="cf" class="form-grid">
        <label class="field full"><span>Description *</span><input name="description" type="text" required placeholder="e.g. Dumpster rental, Tile allowance, Design fee"></label>
        <label class="field"><span>Group</span><input name="group_label" type="text" value="Custom items" list="groups"><datalist id="groups">${[...new Set(job.items.map((i) => i.group_label))].map((g) => `<option value="${esc(g)}">`).join("")}</datalist></label>
        <label class="field"><span>Category</span><select name="category">${["material", "labor", "permit", "equipment", "disposal", "other"].map((c) => `<option>${c}</option>`).join("")}</select></label>
        <label class="field"><span>Qty</span><input name="qty" type="number" step="0.01" value="1"></label>
        <label class="field"><span>Unit</span><input name="unit" type="text" value="ea"></label>
        <label class="field"><span>Unit cost ($)</span><input name="unit_cost" type="number" step="0.01" required></label>
      </form>
      <div class="actions"><button class="btn" data-close>Cancel</button><button class="btn primary" id="save">Add line</button></div>`);
    $("#save", m.el).onclick = async () => {
      const f = $("#cf", m.el);
      if (!f.reportValidity()) return;
      const d = formData(f);
      const res = await api(`/api/jobs/${job.id}/items`, { method: "POST", body: { items: [{ ...d, source: "custom" }], group_label: d.group_label, status_bump: true } });
      m.close(); onSaved(res.job); toast("Line added", "ok");
    };
    setTimeout(() => $("[name=description]", m.el).focus(), 30);
  }

  function materialPickerModal(job, onSaved) {
    const mats = S.pricing.materials;
    const picked = {}; // id -> qty
    const groups = [...new Set(job.items.map((i) => i.group_label))];
    const m = modal(`<h2>Add from price book</h2>
      <div class="row mb"><button class="chip" id="mfav">★ Favorites</button><input type="text" id="mq" placeholder="Search lumber, hardware, drywall, trim, paint…" class="grow"><input type="text" id="mg" list="mgroups" value="Materials" style="max-width:200px" title="Group name on the estimate"><datalist id="mgroups">${groups.map((g) => `<option value="${esc(g)}">`).join("")}</datalist></div>
      <div class="table-wrap" style="max-height:52vh;overflow:auto"><table><thead><tr><th></th><th>Item</th><th>Section</th><th class="num">Cost</th><th class="num">Qty</th></tr></thead><tbody id="mrows"></tbody></table></div>
      <div class="row between mt"><span class="dim" id="msum">Nothing picked yet</span><div class="row"><button class="btn" data-close>Cancel</button><button class="btn primary" id="save">Add to estimate</button></div></div>`, { wide: true });
    let favOnly = false;
    const draw = () => {
      const q = $("#mq", m.el).value.toLowerCase();
      const rows = mats.filter((x) => (!favOnly || isFav(x.id)) && (!q || `${x.label} ${x.section}`.toLowerCase().includes(q)))
        .sort((a, b) => (isFav(b.id) - isFav(a.id)));
      $("#mrows", m.el).innerHTML = rows.map((x) => `<tr><td>${starHtml(x.id)}</td><td>${esc(x.label)}${x.builtin ? "" : ''}</td><td class="dim">${esc(x.section)}</td><td class="num">${money2(x.cost)} <span class="dim">/ ${esc(x.unit)}</span></td>
        <td class="num"><input class="inline-num" type="number" step="any" min="0" data-id="${esc(x.id)}" value="${picked[x.id] ?? ""}" placeholder="0"></td></tr>`).join("") || `<tr><td colspan="5" class="empty">${favOnly ? "No favorites yet. Star items to pin them here." : "No matches. Add it under Price book."}</td></tr>`;
      $$("input[data-id]", m.el).forEach((i) => (i.oninput = () => { const v = parseFloat(i.value); if (v > 0) picked[i.dataset.id] = v; else delete picked[i.dataset.id]; sum(); }));
      wireStars(m.el, draw);
    };
    $("#mfav", m.el).onclick = () => { favOnly = !favOnly; $("#mfav", m.el).classList.toggle("active", favOnly); draw(); };
    const sum = () => {
      const n = Object.keys(picked).length, t = Object.entries(picked).reduce((a, [id, q]) => a + q * (mats.find((x) => x.id === id)?.cost || 0), 0);
      $("#msum", m.el).textContent = n ? `${n} item${n > 1 ? "s" : ""} · ${money2(t)} before tax/markup` : "Nothing picked yet";
    };
    $("#mq", m.el).oninput = draw;
    $("#save", m.el).onclick = async () => {
      const items = Object.entries(picked).map(([id, qty]) => { const x = mats.find((y) => y.id === id); return { description: x.label, category: x.category, qty, unit: x.unit, unit_cost: x.cost, source: "pricebook", price_key: x.id }; });
      if (!items.length) return toast("Enter a quantity on at least one item", "err");
      const res = await api(`/api/jobs/${job.id}/items`, { method: "POST", body: { items, group_label: $("#mg", m.el).value || "Materials", status_bump: true } });
      m.close(); onSaved(res.job); toast(`${items.length} line${items.length > 1 ? "s" : ""} added`, "ok");
    };
    draw();
    setTimeout(() => $("#mq", m.el).focus(), 30);
  }

  function proposalModal(job) {
    const u = S.user, sm = job.summary;
    const groups = {};
    job.items.forEach((it) => { (groups[it.group_label || "Other items"] ||= []).push(it); });
    const today = new Date().toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" });
    modal(`<div class="row between no-print mb"><h2 style="margin:0">Proposal preview</h2><div class="row"><button class="btn" onclick="window.print()">Print / Save PDF</button><button class="btn" data-close>Close</button></div></div>
      <div class="print-area"><div class="proposal">
        <div class="row between" style="align-items:flex-start"><div><h1>${esc(u.business_name || "Proposal")}</h1><div class="small">${esc(u.address || "")}<br>${esc(u.phone || "")}${u.license_no ? `<br>${esc(u.license_no)}` : ""}</div></div>
          <div class="right"><div style="font-size:18px;font-weight:700">PROPOSAL</div><div class="small">${esc(job.job_no)}<br>${today}</div></div></div>
        <hr style="border:none;border-top:1px solid #ddd;margin:18px 0">
        <div class="grid c2"><div><div class="small">PREPARED FOR</div><b>${esc(job.client_name || "")}</b><br>${esc(job.address || "")}<br>${esc(job.client_phone || "")}</div>
          <div><div class="small">PROJECT</div><b>${esc(job.title)}</b><br>${esc(job.job_type || "")}</div></div>
        <table class="mt"><thead><tr><th>Scope</th><th class="num">Amount</th></tr></thead><tbody>
          ${Object.entries(groups).map(([g, items]) => { const sub = items.reduce((a, i) => a + i.total, 0); const share = sm.direct_cost ? sub / sm.direct_cost : 0;
            const client = sub + (sm.total - sm.direct_cost) * share;
            return `<tr><td><b>${esc(g)}</b><div class="small">${items.map((i) => esc(i.description)).join(", ")}</div></td><td class="num">${money2(client)}</td></tr>`; }).join("")}
        </tbody></table>
        <div class="totals mt" style="max-width:320px;margin-left:auto"><div class="line grand"><span>Total</span><b>${money2(sm.total)}</b></div></div>
        <p class="small mt">Valid for 30 days. 30% deposit to schedule, balance on completion.</p>
        <div class="grid c2 mt" style="margin-top:36px"><div>Accepted by: _______________________<div class="small">Client signature / date</div></div><div>${esc(u.name || "")}<div class="small">${esc(u.business_name || "")}</div></div></div>
      </div></div>`, { wide: true });
  }

  // ------------------------------------------------------------ calculators
  async function pageCalculators(jobIdArg) {
    const cats = S.pricing.calculators;
    let active = Object.keys(cats)[0], result = null, timer;
    if (!S.jobs.length) await loadJobs();
    const openJobs = S.jobs.filter((j) => !["complete", "lost"].includes(j.status));
    main().innerHTML = head("Calculators", marketMetaLine(), `<button class="btn" id="market">${ICON.refresh} Update market prices</button>`) + `
      <div class="grid side-l">
        <div class="card pad-0" style="padding:8px"><div class="calc-list" id="clist"></div></div>
        <div>
          <div class="card"><div class="card-head"><h2 id="ctitle"></h2></div><form id="cform" class="form-grid"></form></div>
          <div class="card" id="cres"></div>
        </div>
      </div>`;
    const list = $("#clist");
    $("#market").onclick = (e) => refreshMarketPrices(e.currentTarget, () => { $("#main .page-head .sub").innerHTML = marketMetaLine(); run(); });
    const descs = { deck: "Full lumber + hardware takeoff", framing: "Studs, plates, headers, nails", drywall: "Board, mud, screws, finish", paint: "Walls, ceilings, trim, doors", trim: "Base, casing, crown, doors", hourly: "Any trade by the hour" };
    const drawList = () => {
      list.innerHTML = Object.entries(cats).map(([k, c]) => `<button class="${k === active ? "active" : ""}" data-k="${k}">${esc(c.label)}<small>${descs[k] || ""}</small></button>`).join("");
      $$("button", list).forEach((b) => (b.onclick = () => { active = b.dataset.k; drawList(); drawForm(); }));
    };
    const drawForm = () => {
      const c = cats[active];
      $("#ctitle").textContent = c.label;
      $("#cform").innerHTML = c.fields.map((f) => {
        if (f.type === "checkbox") return `<label class="check"><input type="checkbox" name="${f.name}" ${f.default ? "checked" : ""}> ${esc(f.label)}</label>`;
        if (f.type === "select") return `<label class="field"><span>${esc(f.label)}</span><select name="${f.name}">${f.options.map((o) => { const [v, l] = Array.isArray(o) ? o : [o, o]; return `<option value="${esc(v)}" ${String(v) === String(f.default) ? "selected" : ""}>${esc(l)}</option>`; }).join("")}</select></label>`;
        return `<label class="field"><span>${esc(f.label)}</span><input type="${f.type}" name="${f.name}" value="${esc(f.default)}" ${f.type === "number" ? 'step="any"' : ""}></label>`;
      }).join("");
      $("#cform").oninput = () => { clearTimeout(timer); timer = setTimeout(run, 180); };
      run();
    };
    const groupLabel = () => {
      const d = formData($("#cform")), c = cats[active];
      const dims = ["length_ft", "width_ft"].filter((k) => d[k]).map((k) => d[k]).join("x");
      const main_ = d.wall_sqft ? `${d.wall_sqft} sqft` : d.wall_lf ? `${d.wall_lf} lf` : d.baseboard_lf !== undefined ? `${d.baseboard_lf || 0} lf base, ${d.doors || 0} doors` : d.hours ? `${d.hours} hr ${titleCase(d.trade)}` : "";
      return `${c.label}${dims ? ` ${dims}` : main_ ? ` ${main_}` : ""}`;
    };
    let sumTimer;
    const drawTotals = () => { $("#ctot").innerHTML = totalsHtml(result.summary); $("#ccmp").innerHTML = competitorsHtml(result.competitors, result.summary.total); };
    const resummarize = () => {
      clearTimeout(sumTimer);
      sumTimer = setTimeout(async () => {
        try { const r = await api("/api/summarize", { method: "POST", body: { items: result.items } }); result.summary = r.summary; result.competitors = r.competitors; drawTotals(); } catch (_) { /* keep last */ }
      }, 250);
    };
    const run = async () => {
      try { result = await api(`/api/calc/${active}`, { method: "POST", body: formData($("#cform")) }); } catch (err) { $("#cres").innerHTML = `<div class="error">${esc(err.message)}</div>`; return; }
      $("#cres").innerHTML = `
        <div class="row between wrap mb"><div class="row wrap">${Object.entries(result.meta).map(([k, v]) => `<span class="meta-chip">${titleCase(k)} <b>${num(v)}</b></span>`).join("")}</div>
          <div class="row"><select id="jobsel" style="width:240px"><option value="">Add to job…</option><option value="__new">+ New job from this</option>${openJobs.map((j) => `<option value="${j.id}" ${String(j.id) === String(jobIdArg) ? "selected" : ""}>${esc(j.job_no)} · ${esc(j.title)}</option>`).join("")}</select>
            <button class="btn primary" id="addtojob">${ICON.plus} Add</button></div></div>
        <div class="table-wrap"><table><thead><tr><th>Item</th><th>Type</th><th class="num">Qty</th><th>Unit</th><th class="num">Unit cost</th><th class="num">Total</th><th></th></tr></thead>
          <tbody>${result.items.map((i, idx) => `<tr>
            <td><input type="text" class="inline-text" data-desc="${idx}" value="${esc(i.description)}"></td><td><span class="cat ${i.category}">${i.category}</span></td>
            <td class="num"><input class="inline-num" data-qty="${idx}" value="${i.qty}"></td><td class="dim">${esc(i.unit)}</td>
            <td class="num"><input class="inline-num" data-uc="${idx}" value="${i.unit_cost}"></td><td class="num" data-tot="${idx}">${money2(i.total)}</td>
            <td class="right">${i.price_key ? `<button class="btn ghost xs hidden" data-savepk="${idx}" title="Save this price to the price book">save price</button>` : ""}</td></tr>`).join("")}</tbody></table></div>
        <div class="grid c2 mt"><div id="ctot">${totalsHtml(result.summary)}</div>
          <div id="ccmp">${competitorsHtml(result.competitors, result.summary.total)}</div></div>`;
      const edit = (idx, field, raw) => {
        const it = result.items[idx];
        if (field === "description") { it.description = raw; return; }
        const v = parseFloat(raw); if (isNaN(v)) return;
        it[field] = v; it.total = Math.round(it.qty * it.unit_cost * 100) / 100;
        $(`[data-tot="${idx}"]`).textContent = money2(it.total);
        if (field === "unit_cost") { const b = $(`[data-savepk="${idx}"]`); if (b) b.classList.toggle("hidden", v === it.book_cost); }
        resummarize();
      };
      $$("[data-desc]").forEach((i) => (i.onchange = () => edit(+i.dataset.desc, "description", i.value)));
      $$("[data-qty]").forEach((i) => (i.oninput = () => edit(+i.dataset.qty, "qty", i.value)));
      $$("[data-uc]").forEach((i) => (i.oninput = () => edit(+i.dataset.uc, "unit_cost", i.value)));
      $$("[data-savepk]").forEach((b) => (b.onclick = async () => {
        const it = result.items[+b.dataset.savepk];
        const field = it.price_key.startsWith("labor.") ? "rate" : "cost";
        const merged = { ...(S.user.price_overrides || {}), [it.price_key]: { ...((S.user.price_overrides || {})[it.price_key] || {}), [field]: it.unit_cost } };
        const { user } = await api("/api/settings", { method: "PUT", body: { price_overrides: merged } });
        S.user = user; await loadPricing(); it.book_cost = it.unit_cost; b.classList.add("hidden"); toast("Saved to price book", "ok");
      }));
      $("#addtojob").onclick = async () => {
        const v = $("#jobsel").value;
        if (!v) return toast("Pick a job first", "err");
        const push = async (jobId) => { await api(`/api/jobs/${jobId}/items`, { method: "POST", body: { items: result.items, group_label: groupLabel(), status_bump: true } }); toast("Added to job", "ok"); go(`jobs/${jobId}`); };
        if (v === "__new") jobModal({ title: groupLabel(), job_type: cats[active].label }, (j) => push(j.id));
        else push(v);
      };
    };
    drawList(); drawForm();
  }

  // ------------------------------------------------------------ schedule
  async function pageSchedule() {
    if (!S.jobs.length) await loadJobs();
    main().innerHTML = head("Schedule", "",
      `<button class="btn primary" id="newev">${ICON.plus} New event</button>`) + `
      <div class="grid side"><div><div class="card" id="calcard"></div></div>
        <div><div class="card"><div class="card-head"><h3>Next up</h3></div><div id="upcoming"></div></div>
        <div class="card" id="sync"></div></div></div>`;
    $("#newev").onclick = () => eventModal({}, drawAll);
    const drawCal = async () => {
      const m = S.calMonth, first = new Date(m), last = new Date(m.getFullYear(), m.getMonth() + 1, 0);
      const gridStart = new Date(first); gridStart.setDate(first.getDate() - first.getDay());
      const gridEnd = new Date(last); gridEnd.setDate(last.getDate() + (6 - last.getDay()) + 1);
      const { events } = await api(`/api/events?start=${ymd(gridStart)}&end=${ymd(gridEnd)}`);
      const byDay = {};
      events.forEach((e) => { (byDay[e.start.slice(0, 10)] ||= []).push(e); });
      const today = ymd(new Date());
      let cells = "";
      for (let d = new Date(gridStart); d < gridEnd; d.setDate(d.getDate() + 1)) {
        const k = ymd(d), evs = byDay[k] || [], other = d.getMonth() !== m.getMonth();
        cells += `<div class="day ${other ? "other" : ""} ${k === today ? "today" : ""}" data-day="${k}"><span class="n">${d.getDate()}</span>
          ${evs.slice(0, 3).map((e) => `<div class="ev ${e.type}" data-ev='${esc(JSON.stringify(e))}' title="${esc(e.title)}">${e.all_day ? "" : `<span class="dim">${fmtTime(e.start).replace(":00", "")}</span> `}${esc(e.title)}</div>`).join("")}
          ${evs.length > 3 ? `<div class="ev-more">+${evs.length - 3} more</div>` : ""}${evs.length ? `<span class="count">${evs.length} event${evs.length > 1 ? "s" : ""}</span>` : ""}</div>`;
      }
      $("#calcard").innerHTML = `<div class="cal-head"><button class="btn sm" id="prev">‹ Prev</button><h2>${m.toLocaleDateString("en-US", { month: "long", year: "numeric" })}</h2><div class="row"><button class="btn sm" id="today">Today</button><button class="btn sm" id="next">Next ›</button></div></div>
        <div class="cal">${["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map((d) => `<div class="dow">${d}</div>`).join("")}${cells}</div>
        <div class="legend mt">${Object.entries(TYPE_LABEL).map(([k, v]) => `<span><span class="dot ${k}"></span>${v}</span>`).join("")}</div>`;
      $("#prev").onclick = () => { S.calMonth = new Date(m.getFullYear(), m.getMonth() - 1, 1); drawCal(); };
      $("#next").onclick = () => { S.calMonth = new Date(m.getFullYear(), m.getMonth() + 1, 1); drawCal(); };
      $("#today").onclick = () => { S.calMonth = startOfMonth(new Date()); drawCal(); };
      $$(".day").forEach((el) => (el.onclick = (e) => { if (e.target.closest(".ev")) return; eventModal({ start: `${el.dataset.day}T08:00` }, drawAll); }));
      $$(".ev[data-ev]").forEach((el) => (el.onclick = () => eventModal(JSON.parse(el.dataset.ev), drawAll)));
    };
    const drawUpcoming = async () => {
      const { events } = await api(`/api/events?start=${ymd(new Date())}`);
      $("#upcoming").innerHTML = agenda(events.slice(0, 8));
      $$("#upcoming .agenda .item").forEach((el) => (el.onclick = (e) => { if (e.target.tagName === "A") return; eventModal(JSON.parse(el.dataset.ev), drawAll); }));
    };
    const drawSync = () => {
      const url = `${location.origin}/calendar/${S.user.ics_token}.ics`;
      $("#sync").innerHTML = `<h3 class="mb">Link to your calendar</h3>
        <div class="row"><div class="code grow" id="icsurl">${esc(url)}</div><button class="btn sm" id="copy">Copy</button></div>
        <ol class="steps mt">
          <li><b>Google Calendar:</b> Other calendars → <b>+</b> → <i>From URL</i> → paste.</li>
          <li><b>iPhone:</b> Settings → Calendar → Accounts → Add Subscribed Calendar → paste.</li>
          <li><b>Outlook:</b> Add calendar → Subscribe from web → paste.</li>
        </ol>`;
      $("#copy").onclick = async () => { try { await navigator.clipboard.writeText(url); toast("Link copied", "ok"); } catch (_) { toast("Select and copy the link manually"); } };
    };
    const drawAll = () => { drawCal(); drawUpcoming(); };
    drawAll(); drawSync();
  }

  function googleCalUrl(e) {
    const fmt = (iso, allDay) => { const d = new Date(iso); return allDay ? ymd(d).replace(/-/g, "") : `${ymd(d).replace(/-/g, "")}T${String(d.getHours()).padStart(2, "0")}${String(d.getMinutes()).padStart(2, "0")}00`; };
    const end = e.end || new Date(new Date(e.start).getTime() + (e.all_day ? 864e5 : 72e5)).toISOString();
    const p = new URLSearchParams({ action: "TEMPLATE", text: (e.job_no ? `[${e.job_no}] ` : "") + e.title, dates: `${fmt(e.start, e.all_day)}/${fmt(end, e.all_day)}`, details: `${e.job_title ? `Job: ${e.job_title}\n` : ""}${e.notes || ""}`, location: e.location || "" });
    return `https://calendar.google.com/calendar/render?${p}`;
  }

  function eventModal(ev = {}, onSaved) {
    const isEdit = !!ev.id;
    const start = ev.start ? ev.start.slice(0, 16) : `${ymd(new Date())}T08:00`;
    const end = ev.end ? ev.end.slice(0, 16) : "";
    const m = modal(`<h2>${isEdit ? "Edit event" : "Schedule something"}</h2>
      <form id="ef" class="form-grid">
        <label class="field full"><span>Title *</span><input name="title" type="text" required value="${esc(ev.title || "")}" placeholder="e.g. Site visit + measure"></label>
        <label class="field"><span>Type</span><select name="type">${S.pricing.event_types.map((t) => `<option value="${t}" ${(ev.type || "work") === t ? "selected" : ""}>${TYPE_LABEL[t]}</option>`).join("")}</select></label>
        <label class="field"><span>Job</span><select name="job_id"><option value="">— none —</option>${S.jobs.map((j) => `<option value="${j.id}" ${String(ev.job_id) === String(j.id) ? "selected" : ""}>${esc(j.job_no)} · ${esc(j.title)}</option>`).join("")}</select></label>
        <label class="field"><span>Start</span><input name="start" type="datetime-local" required value="${start}"></label>
        <label class="field"><span>End</span><input name="end" type="datetime-local" value="${end}"></label>
        <label class="check full"><input type="checkbox" name="all_day" ${ev.all_day ? "checked" : ""}> All day</label>
        <label class="field full"><span>Location</span><input name="location" type="text" value="${esc(ev.location || "")}" placeholder="Defaults to the job address in the calendar feed"></label>
        <label class="field full"><span>Notes</span><textarea name="notes">${esc(ev.notes || "")}</textarea></label>
      </form>
      <div class="actions" style="justify-content:space-between">
        <div class="row">${isEdit ? `<button class="btn ghost danger" id="del">${ICON.trash} Delete</button><a class="btn ghost" target="_blank" rel="noopener" href="${googleCalUrl(ev)}">${ICON.ext} Add to Google Calendar</a>` : ""}</div>
        <div class="row"><button class="btn" data-close>Cancel</button><button class="btn primary" id="save">${isEdit ? "Save" : "Add"}</button></div></div>`);
    $("#save", m.el).onclick = async () => {
      const f = $("#ef", m.el);
      if (!f.reportValidity()) return;
      const d = formData(f);
      d.job_id = d.job_id ? +d.job_id : null;
      if (!d.end) delete d.end;
      try {
        await (isEdit ? api(`/api/events/${ev.id}`, { method: "PUT", body: d }) : api("/api/events", { method: "POST", body: d }));
        m.close(); toast(isEdit ? "Event saved" : "Added to schedule", "ok");
        if (onSaved) onSaved(); else render();
      } catch (err) { toast(err.message, "err"); }
    };
    const del = $("#del", m.el);
    if (del) del.onclick = async () => { await api(`/api/events/${ev.id}`, { method: "DELETE" }); m.close(); toast("Event deleted"); if (onSaved) onSaved(); else render(); };
    setTimeout(() => $("[name=title]", m.el).focus(), 30);
  }

  // ------------------------------------------------------------ price book
  function pagePriceBook() {
    const { region, book } = S.pricing;
    const overrides = { ...(S.user.price_overrides || {}) };
    const sections = { labor: "Labor rates ($ per hour, what the client is charged)", production: "Production rates (man-hours per unit of work)", job: "Job factors", conditions: "Site conditions (% added to labor)", competitors: "Competitor benchmarks (for the comparison card)", lumber: "Lumber", hardware: "Hardware & fasteners", drywall: "Drywall", trim: "Trim & doors", paint: "Paint", equipment: "Equipment & site protection", permits: "Permits (New Hanover County)", disposal: "Disposal", defaults: "Estimate defaults" };
    const mine = S.pricing.materials.filter((x) => !x.builtin);
    const loose = mine.filter((x) => !x.section_key);
    const favs = S.pricing.materials.filter((x) => isFav(x.id) && !(overrides[x.id] && overrides[x.id].hidden));
    const customRow = (x) => `<tr>
          <td class="star-cell">${starHtml(x.id)}</td>
          <td><span class="editable" data-clabel="${x.db_id}" title="Double-click to rename">${esc(x.label)}</span> <span class="mover" data-move="${x.db_id}"><button class="btn ghost xs" title="Move to another section">${ICON.move}</button></span></td>
          <td class="right"><input class="price-input" type="number" step="any" data-mid="${x.db_id}" data-f="cost" value="${x.cost}"> <span class="dim editable" style="font-size:11px" data-cunit="${x.db_id}" title="Double-click to change the unit">/ ${esc(x.unit)}</span>
            <button class="btn ghost xs danger hidden" data-delmat="${x.db_id}" title="Delete">${ICON.trash}</button></td></tr>`;
    const builtinRow = (x) => { const [sec, key] = x.id.split("."); const o = handEdited(x.id, "cost") ? 1 : undefined;
      return `<tr><td class="star-cell">${starHtml(x.id)}</td><td><span class="editable" data-label="${x.id}" title="Double-click to rename">${esc(x.label)}</span>${lengthsLine(x.id)}</td><td class="right">${lengthsBtn(x.id)}<input class="price-input ${o !== undefined ? "changed" : ""}" type="number" step="any" data-path="${x.id}" data-f="cost" value="${x.cost}"> <span class="dim editable" style="font-size:11px" data-unit="${x.id}" title="Double-click to change the unit">/ ${esc(x.unit)}${x.base_unit === "lf" && x.unit !== "lf" ? ` (${S.pricing.book[x.id.split(".")[0]][x.id.split(".")[1]].piece_ft || 8} ft)` : ""}</span> <button class="btn ghost xs danger hidden" data-hide="${x.id}" title="Remove from price book">${ICON.trash}</button></td></tr>`; };
    const hiddenIds = Object.entries(overrides).filter(([, v]) => v && v.hidden).map(([k]) => k);
    const applied = S.pricing.price_meta?.applied || {};
    const handEdited = (id, f) => { const o = overrides[id]?.[f]; return o !== undefined && !(f === "cost" && applied[id] !== undefined && Math.abs(o - applied[id]) < 0.005); };
    const entryOf = (id) => { const [sec, key] = id.split("."); return book[sec]?.[key]; };
    const lengthsLine = (id) => { const v = entryOf(id); const L = v?.lengths ? Object.entries(v.lengths).sort((a, b) => a[0] - b[0]) : []; return L.length ? `<div class="dim" style="font-size:11px">${L.map(([ft, c]) => `${(+ft).toString()}' ${money2(c)}`).join(" · ")}</div>` : ""; };
    const lengthsBtn = (id) => { const v = entryOf(id); return v?.base_unit === "lf" ? `<button class="btn ghost xs" data-lengths="${id}" title="Stock lengths and per-piece prices">${ICON.ruler}</button> ` : ""; };
    main().innerHTML = head("Price book", marketMetaLine(),
      `${hiddenIds.length ? `<button class="btn ghost" id="showhidden">Hidden (${hiddenIds.length})</button>` : ""}<button class="btn" id="market">${ICON.refresh} Update market prices</button><button class="btn" id="addmat">${ICON.plus} Add material</button><button class="btn" id="reset">Reset built-ins</button><button class="btn primary" id="save">Save changes</button>`) + `
      <div class="card pad-0 mb"><div class="card-head" style="padding:14px 18px 0"><h3>★ Favorites</h3></div>
        ${favs.length ? `<table><tbody>${favs.map((x) => x.builtin ? builtinRow(x) : customRow(x)).join("")}</tbody></table>` : `<div class="empty">Star any material below to pin it here and to the top of the job picker.</div>`}</div>
      ${loose.length ? `<div class="card pad-0 mb"><div class="card-head" style="padding:14px 18px 0"><h3>My materials (misc)</h3></div>
        <table><tbody>${loose.map(customRow).join("")}</tbody></table></div>` : ""}
      <div class="grid c2">${Object.entries(sections).map(([sec, label]) => `
        <div class="card pad-0"><div class="card-head" style="padding:14px 18px 0"><h3>${label}</h3>${S.pricing.price_meta?.series?.[sec] ? `<span class="dim" style="font-size:11px">market ${S.pricing.price_meta.series[sec].change_pct >= 0 ? "up" : "down"} ${Math.abs(S.pricing.price_meta.series[sec].change_pct)}% since June</span>` : ""}</div>
          <table><tbody>${Object.entries(book[sec]).filter(([, v]) => !v.hidden).map(([key, v]) => {
            const fields = Object.keys(v).filter((k) => ["cost", "rate", "hours", "pct"].includes(k));
            const id = `${sec}.${key}`;
            const starCell = Object.values(book[sec]).some((b) => "unit" in b) ? `<td class="star-cell">${"unit" in v ? starHtml(id) : ""}</td>` : "";
            return `<tr>${starCell}<td><span class="editable" data-label="${id}" title="Double-click to rename">${esc(v.label)}</span>${lengthsLine(id)}</td>
              <td class="right">${lengthsBtn(id)}${fields.map((f) => `<span class="dim" style="font-size:11px;margin-left:8px">${fields.length > 1 ? f : ""}</span> <input class="price-input ${handEdited(id, f) ? "changed" : ""}" type="number" step="any" data-path="${id}" data-f="${f}" value="${v[f]}">`).join("")}${"unit" in v ? ` <span class="dim editable" style="font-size:11px" data-unit="${id}" title="Double-click to change the unit">/ ${esc(v.unit)}${v.base_unit === "lf" && v.unit !== "lf" ? ` (${v.piece_ft || 8} ft)` : ""}</span>` : ""} <button class="btn ghost xs danger hidden" data-hide="${id}" title="Remove from price book">${ICON.trash}</button></td></tr>`; }).join("")}
          ${mine.filter((x) => x.section_key === sec).map(customRow).join("")}
          </tbody></table></div>`).join("")}</div>`;
    wireStars(document, () => render());
    const inlineEdit = (el, id, field, orig, display, saver, onDone) => {
      if (el.querySelector("input")) return;
      el.innerHTML = `<input type="text" value="${esc(orig)}" style="padding:4px 8px;${field === "unit" ? "width:70px" : ""}">`;
      const inp = el.querySelector("input");
      inp.focus(); inp.select();
      let done = false;
      const finish = async (save) => {
        if (done) return; done = true;
        const val = inp.value.trim();
        if (!save || !val || val === orig) { el.textContent = display(orig); if (onDone) onDone(); return; }
        let suffix = "";
        if (saver) await saver(val);
        else {
          const extra = {};
          const [sec, key] = id.split(".");
          const baseUnit = S.pricing.book[sec]?.[key]?.base_unit;
          if (field === "unit" && baseUnit === "lf" && val !== "lf") {
            const ft = await askNumber("Feet per piece", "The price will be converted to per piece, and the calculators will count pieces.", S.pricing.book[sec][key].piece_ft || 8);
            if (ft) { extra.piece_ft = ft; suffix = ` (${ft} ft)`; if (S.pricing.book[sec][key].unit === "lf") extra.cost = Math.round(S.pricing.book[sec][key].cost * ft * 100) / 100; }
          } else if (field === "unit" && baseUnit === "lf" && val === "lf" && S.pricing.book[sec][key].unit !== "lf") {
            extra.cost = Math.round(S.pricing.book[sec][key].cost / (S.pricing.book[sec][key].piece_ft || 8) * 100) / 100;
          }
          const merged = { ...(S.user.price_overrides || {}), [id]: { ...((S.user.price_overrides || {})[id] || {}), [field]: val, ...extra } };
          const { user } = await api("/api/settings", { method: "PUT", body: { price_overrides: merged } });
          S.user = user;
        }
        await loadPricing();
        el.textContent = display(val) + suffix;
        if (onDone) onDone();
        toast(field === "unit" ? "Unit changed" : "Renamed", "ok");
        if (field === "unit") render();
      };
      inp.onkeydown = (e) => { if (e.key === "Enter") finish(true); if (e.key === "Escape") finish(false); };
      inp.onblur = () => finish(true);
    };
    const showHide = (el, on) => { const b = el.closest("tr").querySelector("[data-hide]"); if (b) b.classList.toggle("hidden", !on); };
    $$("td[data-label]").forEach((td) => (td.ondblclick = () => { showHide(td, true); inlineEdit(td, td.dataset.label, "label", td.textContent, (v) => v, null, () => setTimeout(() => showHide(td, false), 250)); }));
    $$("[data-unit]").forEach((sp) => (sp.ondblclick = () => { showHide(sp, true); inlineEdit(sp, sp.dataset.unit, "unit", sp.textContent.replace(/^\/\s*/, "").replace(/\s*\(.*\)$/, ""), (v) => `/ ${v}`, null, () => setTimeout(() => showHide(sp, false), 250)); }));
    const setHidden = async (id, hidden) => {
      const cur = { ...(S.user.price_overrides || {}) };
      const entry = { ...(cur[id] || {}) };
      if (hidden) entry.hidden = true; else delete entry.hidden;
      if (Object.keys(entry).length) cur[id] = entry; else delete cur[id];
      const { user } = await api("/api/settings", { method: "PUT", body: { price_overrides: cur } });
      S.user = user; await loadPricing(); render();
    };
    $$("[data-hide]").forEach((b) => (b.onmousedown = (e) => e.preventDefault(), b.onclick = async () => { if (await confirmDlg("Remove this entry from your price book? You can bring it back from the Hidden button.")) setHidden(b.dataset.hide, true); }));
    $$("[data-lengths]").forEach((b) => (b.onclick = () => lengthsModal(b.dataset.lengths)));
    const sh = $("#showhidden");
    if (sh) sh.onclick = () => {
      const m = modal(`<h2>Hidden entries</h2><table><tbody>${hiddenIds.map((id) => { const [sec, key] = id.split("."); const v = book[sec]?.[key]; return v ? `<tr><td>${esc(v.label)}<div class="dim" style="font-size:11px">${esc(sections[sec] || sec)}</div></td><td class="right"><button class="btn sm" data-restore="${id}">Restore</button></td></tr>` : ""; }).join("")}</tbody></table>
        <div class="actions"><button class="btn" data-close>Close</button></div>`);
      $$("[data-restore]", m.el).forEach((b) => (b.onclick = async () => { m.close(); await setHidden(b.dataset.restore, false); }));
    };
    const customSave = (id, field) => async (val) => { const row = mine.find((x) => x.db_id === +id); await api(`/api/materials/${id}`, { method: "PUT", body: { ...row, section: row.section_key || row.section, [field]: val } }); };
    const showDel = (el, on) => { const b = el.closest("tr").querySelector("[data-delmat]"); if (b) b.classList.toggle("hidden", !on); };
    $$("[data-clabel]").forEach((sp) => (sp.ondblclick = () => { showDel(sp, true); inlineEdit(sp, sp.dataset.clabel, "label", sp.textContent, (v) => v, customSave(sp.dataset.clabel, "label"), () => setTimeout(() => showDel(sp, false), 250)); }));
    $$("[data-cunit]").forEach((sp) => (sp.ondblclick = () => { showDel(sp, true); inlineEdit(sp, sp.dataset.cunit, "unit", sp.textContent.replace(/^\/\s*/, ""), (v) => `/ ${v}`, customSave(sp.dataset.cunit, "unit"), () => setTimeout(() => showDel(sp, false), 250)); }));
    const armMover = (wrap) => {
      wrap.querySelector("button").onclick = () => {
        const row = mine.find((x) => x.db_id === +wrap.dataset.move);
        wrap.innerHTML = `<select style="width:auto;padding:4px 26px 4px 8px;font-size:12px">${sectionOptions(row.section_key || row.section)}</select>`;
        const sel = wrap.querySelector("select");
        sel.focus();
        sel.onchange = () => saveMat(wrap.dataset.move, { section: sel.value });
        sel.onblur = () => { wrap.innerHTML = `<button class="btn ghost xs" title="Move to another section">${ICON.move}</button>`; armMover(wrap); };
      };
    };
    $$("[data-move]").forEach(armMover);
    const dirty = {};
    $$(".price-input[data-path]").forEach((i) => (i.oninput = () => { (dirty[i.dataset.path] ||= {})[i.dataset.f] = i.value; $$(`.price-input[data-path="${i.dataset.path}"]`).forEach((o) => { o.value = i.value; o.classList.add("changed"); }); }));
    $("#save").onclick = async () => {
      const merged = { ...overrides };
      Object.entries(dirty).forEach(([p, vals]) => (merged[p] = { ...(merged[p] || {}), ...vals }));
      const { user } = await api("/api/settings", { method: "PUT", body: { price_overrides: merged } });
      S.user = user; await loadPricing(); toast("Price book saved", "ok"); render();
    };
    $("#addmat").onclick = () => materialModal();
    $("#market").onclick = (e) => refreshMarketPrices(e.currentTarget, () => render());
    const saveMat = async (id, body) => { const row = mine.find((x) => x.db_id === +id); await api(`/api/materials/${id}`, { method: "PUT", body: { ...row, section: row.section_key || row.section, ...body } }); toast("Material saved", "ok"); if ("section" in body) { await loadPricing(); render(); } else Object.assign(row, body); };
    $$("[data-mid]").forEach((i) => (i.onchange = () => saveMat(i.dataset.mid, { [i.dataset.f]: i.value })));
    $$("[data-delmat]").forEach((b) => (b.onclick = async () => { if (!(await confirmDlg("Delete this material from your price book?"))) return; await api(`/api/materials/${b.dataset.delmat}`, { method: "DELETE" }); await loadPricing(); render(); }));
    $("#reset").onclick = async () => {
      if (!(await confirmDlg("Reset every built-in price back to the Wilmington defaults? Your own materials are kept."))) return;
      const { user } = await api("/api/settings", { method: "PUT", body: { price_overrides: {} } });
      S.user = user; await loadPricing(); toast("Defaults restored"); render();
    };
  }

  function lengthsModal(id) {
    const [sec, key] = id.split(".");
    const v = S.pricing.book[sec][key];
    let rows = Object.entries(v.lengths || {}).map(([ft, c]) => ({ ft: +ft, cost: c })).sort((a, b) => a.ft - b.ft);
    const m = modal(`<h2>${esc(v.label)}: stock lengths</h2>
      <p class="muted">Price per piece for each length you buy. The calculators pick the length that fits the job (9 ft studs for a 9 ft wall, plates out of 16 footers). Leave it empty to price by the foot only.</p>
      <table><thead><tr><th>Length (ft)</th><th class="num">Price per piece</th><th></th></tr></thead><tbody id="lrows"></tbody></table>
      <div class="row mt"><button class="btn sm" id="addlen">${ICON.plus} Add length</button><span class="grow"></span><span class="dim" style="font-size:12px">Per-foot fallback: ${money2(v.cost)} / lf</span></div>
      <div class="actions"><button class="btn" data-close>Cancel</button><button class="btn primary" id="save">Save</button></div>`);
    const draw = () => {
      $("#lrows", m.el).innerHTML = rows.map((r, i) => `<tr><td><input type="number" step="any" min="0" data-lft="${i}" value="${r.ft}" style="width:90px"></td><td class="num"><input class="price-input" type="number" step="any" min="0" data-lcost="${i}" value="${r.cost}"></td><td class="right"><button class="btn ghost xs danger" data-ldel="${i}">✕</button></td></tr>`).join("") || `<tr><td colspan="3" class="empty">No stock lengths. Priced per foot.</td></tr>`;
      $$("[data-lft]", m.el).forEach((i) => (i.oninput = () => (rows[+i.dataset.lft].ft = parseFloat(i.value))));
      $$("[data-lcost]", m.el).forEach((i) => (i.oninput = () => (rows[+i.dataset.lcost].cost = parseFloat(i.value))));
      $$("[data-ldel]", m.el).forEach((b) => (b.onclick = () => { rows.splice(+b.dataset.ldel, 1); draw(); }));
    };
    $("#addlen", m.el).onclick = () => { const last = rows[rows.length - 1]; rows.push({ ft: last ? last.ft + 2 : 8, cost: last ? Math.round((last.cost / last.ft) * (last.ft + 2) * 100) / 100 : Math.round(v.cost * 8 * 100) / 100 }); draw(); };
    $("#save", m.el).onclick = async () => {
      const lengths = {};
      rows.filter((r) => r.ft > 0 && r.cost >= 0).forEach((r) => (lengths[r.ft] = r.cost));
      const merged = { ...(S.user.price_overrides || {}), [id]: { ...((S.user.price_overrides || {})[id] || {}), lengths } };
      const { user } = await api("/api/settings", { method: "PUT", body: { price_overrides: merged } });
      S.user = user; await loadPricing(); m.close(); toast("Lengths saved", "ok"); render();
    };
    draw();
  }

  function materialModal() {
    const secs = [...new Set(S.pricing.materials.filter((x) => !x.builtin).map((x) => x.section))];
    const m = modal(`<h2>Add material</h2>
      <form id="mf" class="form-grid">
        <label class="field full"><span>Name *</span><input name="label" type="text" required placeholder="e.g. Cedar 1x6 T&G, per lf"></label>
        <label class="field"><span>Section</span><select name="section">${sectionOptions("lumber")}</select></label>
        <label class="field"><span>Category</span><select name="category">${["material", "labor", "equipment", "disposal", "other"].map((c) => `<option>${c}</option>`).join("")}</select></label>
        <label class="field"><span>Unit</span><input name="unit" type="text" value="ea" list="units"><datalist id="units">${["ea", "lf", "sqft", "sheet", "box", "lb", "gal", "bag", "hr", "load"].map((x) => `<option value="${x}">`).join("")}</datalist></label>
        <label class="field"><span>Cost per unit ($) *</span><input name="cost" type="number" step="0.01" required></label>
      </form>
      <div class="actions"><button class="btn" data-close>Cancel</button><button class="btn primary" id="save">Add to price book</button></div>`);
    $("#save", m.el).onclick = async () => {
      const f = $("#mf", m.el);
      if (!f.reportValidity()) return;
      try { await api("/api/materials", { method: "POST", body: formData(f) }); m.close(); await loadPricing(); toast("Material added", "ok"); render(); }
      catch (err) { toast(err.message, "err"); }
    };
    setTimeout(() => $("[name=label]", m.el).focus(), 30);
  }

  // ------------------------------------------------------------ settings
  function pageSettings() {
    const u = S.user;
    main().innerHTML = head("Settings") + `
      <div class="grid c2">
        <div class="card"><h3 class="mb">Business</h3>
          <form id="bf" class="stack">
            <label class="field"><span>Business name</span><input name="business_name" type="text" value="${esc(u.business_name || "")}"></label>
            <label class="field"><span>Your name</span><input name="name" type="text" value="${esc(u.name || "")}"></label>
            <label class="field"><span>Phone</span><input name="phone" type="text" value="${esc(u.phone || "")}"></label>
            <label class="field"><span>NC license #</span><input name="license_no" type="text" value="${esc(u.license_no || "")}" placeholder="NC GC license (required over $40,000)"></label>
            <label class="field"><span>Business address</span><input name="address" type="text" value="${esc(u.address || "")}"></label>
            <button class="btn primary" style="align-self:flex-start">Save business</button>
          </form></div>
        <div>
          <div class="card"><h3 class="mb">Estimate defaults</h3>
            <form id="df" class="stack">
              <div class="pct-row">
                <label class="field"><span>Markup % (materials + pass-throughs)</span><input name="markup_pct" type="number" step="0.5" value="${u.markup_pct}"></label>
                <label class="field"><span>Contingency %</span><input name="contingency_pct" type="number" step="0.5" value="${u.contingency_pct}"></label>
                <label class="field"><span>Sales tax % (materials)</span><input name="tax_pct" type="number" step="0.25" value="${u.tax_pct}"></label>
              </div>
              <button class="btn primary" style="align-self:flex-start">Save defaults</button>
            </form></div>
          <div class="card"><h3 class="mb">Account</h3>
            <form id="pf" class="stack">
              <label class="field"><span>Email</span><input type="email" value="${esc(u.email)}" disabled></label>
              <label class="field"><span>New password</span><input name="new_password" type="password" minlength="8" autocomplete="new-password" placeholder="8+ characters"></label>
              <div class="row"><button class="btn">Change password</button><button class="btn ghost" type="button" id="rotate">Reset calendar link</button></div>
            </form>
          </div>
          <div class="card"><h3 class="mb">Look</h3>
            <div class="chips">${[["default", "Original"], ["jobsite", "Jobsite"], ["ledger", "Ledger"]].map(([k, l]) => `<button class="chip ${(document.documentElement.dataset.theme || "default") === k ? "active" : ""}" data-theme-pick="${k}">${l}</button>`).join("")}</div>
          </div>
          <div class="card"><h3 class="mb">Backups</h3>
            <div id="bkinfo" class="muted" style="font-size:13px">Checking…</div>
            <div class="row mt"><a class="btn" href="/api/backup/download">${ICON.ext} Download a copy</a><button class="btn ghost" id="bknow">Back up now</button></div>
          </div>
        </div></div>`;
    const save = (form, msg) => async (e) => { e.preventDefault(); const { user } = await api("/api/settings", { method: "PUT", body: formData(form) }); S.user = user; toast(msg, "ok"); render(); };
    $("#bf").onsubmit = save($("#bf"), "Business saved");
    $("#df").onsubmit = save($("#df"), "Defaults saved");
    $("#pf").onsubmit = async (e) => { e.preventDefault(); const pw = $("[name=new_password]").value; if (pw.length < 8) return toast("Password must be 8+ characters", "err"); await api("/api/settings", { method: "PUT", body: { new_password: pw } }); toast("Password changed", "ok"); $("[name=new_password]").value = ""; };
    $$("[data-theme-pick]").forEach((b) => (b.onclick = () => { const k = b.dataset.themePick; try { localStorage.setItem("theme", k); } catch (_) { /* ignore */ } if (k === "default") delete document.documentElement.dataset.theme; else document.documentElement.dataset.theme = k; render(); }));
    const bk = async () => { try { const b = await api("/api/backup/status"); $("#bkinfo").innerHTML = `Nightly at ${esc(b.hour)}:00 server time · ${b.count} kept on disk · last: ${b.last ? fmtDT(b.last) : "none yet"}${b.offsite ? " · also copied off-site" : ""}`; } catch (_) { $("#bkinfo").textContent = "Status unavailable"; } };
    bk();
    $("#bknow").onclick = async () => { try { await api("/api/backup/now", { method: "POST" }); toast("Backup written", "ok"); bk(); } catch (err) { toast(err.message, "err"); } };
    $("#rotate").onclick = async () => { const { user } = await api("/api/settings", { method: "PUT", body: { rotate_ics_token: true } }); S.user = user; toast("Calendar link reset"); };
  }

  boot().catch((e) => { root.innerHTML = `<div class="auth-wrap"><div class="card error">Could not reach the server: ${esc(e.message)}</div></div>`; });
})();

/* ClipDistrict Studio — front end (no build step). */
"use strict";

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const S = 360 / 1080; // preview scale

const state = {
  status: null, themes: [], layouts: {}, positions: {},
  jobs: [], project: null, momentId: null, words: [],
  style: null, drafts: {}, clipSig: "", lastJobStates: {},
};

/* ---------------------------------------------------------------- helpers */
async function api(path, opts = {}) {
  const init = { ...opts };
  if (init.json !== undefined) {
    init.method = init.method || "POST";
    init.headers = { "Content-Type": "application/json" };
    init.body = JSON.stringify(init.json);
    delete init.json;
  }
  const res = await fetch(path, init);
  let data = {};
  try { data = await res.json(); } catch { /* empty */ }
  if (res.status === 401) { location.href = "/login"; throw new Error("Please sign in"); }
  if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
  return data;
}

let toastTimer;
function toast(msg, bad = false) {
  const el = $("#toast");
  el.textContent = msg;
  el.className = "toast show" + (bad ? " bad" : "");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (el.className = "toast"), 3800);
}

function fmt(t) {
  t = Math.max(0, Number(t) || 0);
  const h = Math.floor(t / 3600), m = Math.floor((t % 3600) / 60), s = t % 60;
  const ss = s.toFixed(1).padStart(4, "0");
  return h ? `${h}:${String(m).padStart(2, "0")}:${ss}` : `${m}:${ss}`;
}
function parseT(v) {
  if (v === "" || v == null) return null;
  const parts = String(v).trim().split(":").map(Number);
  if (parts.some((x) => Number.isNaN(x))) return null;
  return parts.reduce((a, b) => a * 60 + b, 0);
}
function theme(id) { return state.themes.find((t) => t.id === id) || state.themes[0]; }

/* ---------------------------------------------------------------- boot */
async function boot() {
  const [status, th] = await Promise.all([api("/api/status"), api("/api/themes")]);
  state.status = status;
  state.themes = th.themes; state.layouts = th.layouts; state.positions = th.positions;
  renderChannel();
  initSettings();
  window.addEventListener("hashchange", route);
  route();
  pollJobs();
  setInterval(pollJobs, 1500);
}

function renderChannel() {
  const st = state.status, pill = $("#channelPill");
  pill.classList.toggle("ok", !!st.channel);
  const n = (st.channels || []).length;
  $("#channelText").textContent = n ? (n > 1 ? `${n} channels connected` : st.channel.title) : "Connect YouTube";
  $("#autoDot").classList.toggle("on", !!(st.settings.watch_enabled || st.settings.autopilot));
  pill.onclick = () => $("#settingsDialog").showModal();
}

function route() {
  const hash = location.hash || "#/";
  $$(".topnav a").forEach((a) => a.classList.toggle("active",
    (hash === "#/" && a.dataset.nav === "home") || (hash.startsWith("#/library") && a.dataset.nav === "library")
    || (hash.startsWith("#/auto") && a.dataset.nav === "auto")));
  stopPreview();
  if (hash.startsWith("#/p/")) return viewProject(hash.slice(4));
  if (hash.startsWith("#/auto")) return viewAuto();
  if (hash.startsWith("#/library")) return viewLibrary();
  return viewHome();
}

/* ---------------------------------------------------------------- home */
const QUICK = ["GTA 6", "GTA 6 live", "IShowSpeed GTA 6", "Kai Cenat GTA 6", "GTA 6 reaction", "Vice City GTA 6"];

function viewHome() {
  $("#view").innerHTML = `
  <section class="hero">
    <h1>CLIP <span class="grad">GTA 6</span> MOMENTS<br>INTO VIRAL SHORTS</h1>
    <p>Paste a stream link → we find the best moments → styled captions → upload to your channel.</p>
  </section>

  <section class="card import-card">
    <div class="link-row">
      <input id="link" type="url" placeholder="Paste a YouTube, Twitch or Kick video link…" autocomplete="off">
      <button class="btn primary" id="importBtn">Find clips</button>
    </div>
    <div class="preview-strip" id="linkPreview"></div>
    <div class="import-options">
      <label>Only from <input id="from" type="text" placeholder="0:00 (optional)"></label>
      <label>To <input id="to" type="text" placeholder="end (optional)"></label>
      <label>Creator name (for credit) <input id="creator" type="text" placeholder="@IShowSpeed"></label>
    </div>
    <div class="import-foot">
      <label class="check"><input type="checkbox" id="perm">
        <span>This creator allows clipping (public clip policy or clipping program). I keep proof.</span></label>
      <label class="check"><input type="checkbox" id="autoImport" ${state.status.settings.autopilot ? "checked" : ""}>
        <span><b>Autopilot</b> · make the best Shorts${state.status.settings.auto_upload !== "off" ? " and upload them" : ""} automatically</span></label>
    </div>
    <div class="inbox" id="inbox"></div>
    <div class="drop" id="drop">
      <b>Or drop a video file here</b> · MP4, MOV, MKV, WEBM · add an .srt too if you have one
      <input type="file" id="fileIn" accept="video/*,.mkv,.srt" multiple hidden>
    </div>
  </section>

  <section class="discover">
    <div class="discover-head">
      <h2 class="section-title">FIND <span>GTA 6</span> STREAMS</h2>
      <div class="row" style="flex:1;max-width:460px">
        <input id="q" type="text" placeholder="Search YouTube…" value="GTA 6">
        <button class="btn" id="searchBtn">Search</button>
      </div>
    </div>
    <div class="chips">${QUICK.map((q) => `<button class="chip" data-q="${esc(q)}">${esc(q)}</button>`).join("")}</div>
    <div class="results" id="results">
      <div class="empty" style="grid-column:1/-1">${state.status.api_key
        ? "Pick a search above to see the latest GTA 6 videos and live streams."
        : "Add a YouTube API key in Settings to search streams here. Pasting links works without it."}</div>
    </div>
  </section>`;

  let infoTimer;
  $("#link").addEventListener("input", () => {
    clearTimeout(infoTimer);
    infoTimer = setTimeout(checkLink, 600);
  });
  $("#importBtn").onclick = importLink;
  $("#link").addEventListener("keydown", (e) => e.key === "Enter" && importLink());
  const drop = $("#drop"), fileIn = $("#fileIn");
  drop.onclick = () => fileIn.click();
  fileIn.onchange = () => importFiles([...fileIn.files]);
  drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
  drop.addEventListener("dragleave", () => drop.classList.remove("over"));
  drop.addEventListener("drop", (e) => { e.preventDefault(); drop.classList.remove("over"); importFiles([...e.dataTransfer.files]); });
  loadInbox();
  $("#searchBtn").onclick = () => doSearch($("#q").value);
  $("#q").addEventListener("keydown", (e) => e.key === "Enter" && doSearch($("#q").value));
  $$(".chip").forEach((c) => (c.onclick = () => {
    $$(".chip").forEach((x) => x.classList.remove("on")); c.classList.add("on");
    $("#q").value = c.dataset.q.replace(" live", "");
    doSearch(c.dataset.q.replace(" live", ""), c.dataset.q.endsWith(" live"));
  }));
}

async function loadInbox() {
  const box = $("#inbox");
  if (!box) return;
  let data;
  try { data = await api("/api/inbox"); } catch { return; }
  const where = data.folder.includes("/drive/MyDrive/")
    ? "Google Drive › My Drive › " + data.folder.split("/drive/MyDrive/")[1].replace(/\//g, " › ")
    : data.folder;
  box.innerHTML = `<div class="inbox-head"><b>📥 Your inbox</b>
      <span class="muted">Put videos in <code>${esc(where)}</code></span>
      <button class="btn small ghost" id="inboxRefresh">↻ Refresh</button></div>
    ${data.files.length ? data.files.map((f, i) => `<div class="hit">
        <span style="flex:1">🎞️ ${esc(f.name)} <span class="muted">· ${gb(f.size)}</span></span>
        <button class="btn small primary" data-inbox="${i}">Import</button></div>`).join("")
      : `<p class="hint">Empty. Add a video to that folder (from your phone, PC, or "Add to Drive" on a shared link), then click Refresh.</p>`}`;
  $("#inboxRefresh").onclick = loadInbox;
  $$("[data-inbox]", box).forEach((b) => (b.onclick = async () => {
    if (!$("#perm").checked) return toast("Tick the box to confirm the creator allows clipping", true);
    const f = data.files[Number(b.dataset.inbox)];
    try {
      const p = await api("/api/inbox/import", { json: {
        name: f.name, start: $("#from").value, end: $("#to").value, creator: $("#creator").value,
        autopilot: $("#autoImport").checked, permission: true,
      } });
      toast("Importing from your inbox…"); location.hash = "#/p/" + p.id;
    } catch (e) { toast(e.message, true); }
  }));
}

async function checkLink() {
  const url = $("#link")?.value.trim(), box = $("#linkPreview");
  if (!box) return;
  if (!/^https?:\/\//.test(url || "")) { box.classList.remove("show"); return; }
  box.classList.add("show");
  box.innerHTML = `<span class="muted">Reading link…</span>`;
  try {
    const info = await api("/api/info", { json: { url } });
    box.innerHTML = `${info.thumbnail ? `<img src="${esc(info.thumbnail)}" alt="">` : ""}
      <div><b>${esc(info.title)}</b><span class="muted">${esc(info.creator)} · ${info.duration ? fmt(info.duration) : "?"}</span>
      ${info.is_live ? ' <span class="badge live">Live now</span>' : ""}</div>`;
    if (!$("#creator").value && info.creator) $("#creator").value = info.creator;
    box.dataset.title = info.title;
  } catch (e) {
    box.innerHTML = `<span class="hint bad">${esc(e.message)}</span>`;
  }
}

async function importLink() {
  const url = $("#link").value.trim();
  if (!url) return toast("Paste a video link first", true);
  if (!$("#perm").checked) return toast("Tick the box to confirm the creator allows clipping", true);
  try {
    const p = await api("/api/projects", { json: {
      url, start: $("#from").value, end: $("#to").value, creator: $("#creator").value,
      title: $("#linkPreview").dataset.title || "", permission: true, autopilot: $("#autoImport").checked,
    } });
    toast("Importing… you can follow progress at the bottom right");
    location.hash = "#/p/" + p.id;
  } catch (e) { toast(e.message, true); }
}

async function importFiles(files) {
  const video = files.find((f) => !f.name.toLowerCase().endsWith(".srt"));
  const srt = files.find((f) => f.name.toLowerCase().endsWith(".srt"));
  if (!video) return toast("Choose a video file", true);
  if (!$("#perm").checked) return toast("Tick the box to confirm the creator allows clipping", true);
  const form = new FormData();
  form.append("file", video);
  if (srt) form.append("srt", srt);
  form.append("creator", $("#creator").value);
  form.append("autopilot", $("#autoImport").checked ? "1" : "0");
  toast("Uploading file to the app…");
  try {
    const p = await api("/api/projects/upload", { method: "POST", body: form });
    location.hash = "#/p/" + p.id;
  } catch (e) { toast(e.message, true); }
}

async function doSearch(q, live = false) {
  const box = $("#results");
  box.innerHTML = `<div class="empty" style="grid-column:1/-1">Searching…</div>`;
  try {
    const { results } = await api(`/api/search?q=${encodeURIComponent(q)}&live=${live ? 1 : 0}`);
    if (!results.length) { box.innerHTML = `<div class="empty" style="grid-column:1/-1">Nothing found.</div>`; return; }
    box.innerHTML = results.map((r) => `
      <article class="card result">
        <img src="${esc(r.thumbnail)}" alt="" loading="lazy">
        <div class="body">
          <span class="title">${esc(decodeHTML(r.title))}</span>
          <span class="meta">${esc(r.creator)} · ${new Date(r.published_at).toLocaleDateString()} ${live ? '<span class="badge live">Live</span>' : ""}</span>
        </div>
        <button class="btn small" data-url="${esc(r.url)}" data-creator="${esc(r.creator)}">Clip this</button>
      </article>`).join("");
    $$(".result .btn", box).forEach((b) => (b.onclick = () => {
      $("#link").value = b.dataset.url; $("#creator").value = b.dataset.creator;
      window.scrollTo({ top: 0, behavior: "smooth" }); checkLink();
    }));
  } catch (e) {
    box.innerHTML = `<div class="empty" style="grid-column:1/-1">${esc(e.message)}</div>`;
  }
}
function decodeHTML(s) { const t = document.createElement("textarea"); t.innerHTML = s; return t.value; }

/* ---------------------------------------------------------------- library */
async function viewLibrary() {
  $("#view").innerHTML = `<h2 class="section-title">YOUR <span>PROJECTS</span></h2><div class="lib-grid" id="lib"></div>`;
  const { projects } = await api("/api/projects");
  const box = $("#lib");
  if (!projects.length) { box.innerHTML = `<div class="empty card" style="grid-column:1/-1">No projects yet. <a href="#/">Import your first stream →</a></div>`; return; }
  box.innerHTML = projects.map((p) => `
    <a class="card lib-item" href="#/p/${p.id}">
      <div class="lib-thumb" style="background-image:url('/api/projects/${p.id}/poster.jpg')">${statusBadge(p.status)}</div>
      <div class="lib-body"><b>${esc(p.title)}</b>
        <span class="muted">${esc(p.creator || "")} · ${p.moments.length} moments · ${p.clips.length} shorts</span></div>
    </a>`).join("");
}

function statusBadge(s) {
  const map = { ready: ["ready", "Ready"], error: ["bad", "Error"], downloading: ["work", "Downloading"],
    transcribing: ["work", "Subtitles"], analyzing: ["work", "Analyzing"], importing: ["work", "Importing"] };
  const [cls, label] = map[s] || ["", s];
  return `<span class="badge ${cls}">${esc(label)}</span>`;
}

/* ---------------------------------------------------------------- project */
async function viewProject(id) {
  state.momentId = null; state.clipSig = "";
  let p;
  try { p = await api("/api/projects/" + id); } catch { $("#view").innerHTML = `<div class="empty">Project not found.</div>`; return; }
  state.project = p;
  $("#view").innerHTML = `
    <div class="project-head">
      <div>
        <h2 id="pTitle">${esc(p.title)}</h2>
        <div class="row" style="margin-top:8px">
          <span id="pBadge">${statusBadge(p.status)}</span>
          <span class="muted">${esc(p.creator || "Unknown creator")} · ${fmt(p.duration)}</span>
          ${p.source_url ? `<a class="muted" href="${esc(p.source_url)}" target="_blank" rel="noopener">Source ↗</a>` : ""}
        </div>
      </div>
      <div class="row">
        <button class="btn" id="autoBtn" title="Render the best moments with your Autopilot settings">⚡ Autopilot</button>
        <button class="btn" id="reBtn">Find moments again</button>
        <button class="btn ghost" id="freeBtn" title="Delete the big source video, keep your Shorts">🧹 Free space</button>
        <button class="btn ghost danger" id="delBtn">Delete</button>
      </div>
    </div>
    <div id="pError"></div>
    <div id="pBody"></div>
    <section class="clips"><h2 class="section-title">YOUR <span>SHORTS</span></h2><div class="clip-grid" id="clipGrid"></div></section>`;
  $("#delBtn").onclick = async () => {
    if (!confirm("Delete this project and all its Shorts?")) return;
    await api("/api/projects/" + id, { method: "DELETE" });
    location.hash = "#/library";
  };
  $("#autoBtn").onclick = async () => {
    try { const r = await api(`/api/projects/${id}/autopilot`, { method: "POST" }); toast(r.queued ? `Autopilot: rendering ${r.queued} Shorts` : "No moment scored high enough for Autopilot", !r.queued); }
    catch (e) { toast(e.message, true); }
  };
  $("#freeBtn").onclick = async () => {
    if (!confirm("Delete the downloaded source video? Your finished Shorts stay. You won't be able to make new Shorts from this stream.")) return;
    const r = await api(`/api/projects/${id}/free`, { method: "POST" });
    toast(`Freed ${(r.freed / 1e9).toFixed(2)} GB`); state.project.source_removed = true; stopPreview(); renderProjectBody();
  };
  $("#reBtn").onclick = async () => {
    const len = prompt("Clip length in seconds (10–90)?", state.status.settings.clip_length);
    if (len === null) return;
    const count = prompt("How many clips?", state.status.settings.clips_per_video);
    if (count === null) return;
    await api(`/api/projects/${id}/reanalyze`, { json: { clip_length: Number(len), clips_per_video: Number(count) } });
    state.status.settings.clip_length = Number(len); state.status.settings.clips_per_video = Number(count);
    toast("Finding moments again…");
  };
  renderProjectBody();
  renderClips(true);
}

function renderProjectBody() {
  const p = state.project, body = $("#pBody");
  $("#pBadge").innerHTML = statusBadge(p.status);
  $("#pError").innerHTML = p.error ? `<div class="card" style="padding:12px 16px;margin-bottom:16px;border-color:${p.status === "error" ? "var(--red)" : "var(--orange)"}">${esc(p.error)}</div>` : "";
  if (p.status !== "ready") {
    body.innerHTML = `<div class="card empty" id="progressCard"><h3 style="margin:0 0 6px">Working on it…</h3>
      <p id="progressMsg">${p.status === "error" ? "Import failed." : "Download → subtitles → best moments. You can leave this page."}</p>
      <div class="bar indet" style="max-width:420px;margin:14px auto 0"><i id="progressBar"></i></div></div>`;
    return;
  }
  if (p.source_removed) {
    body.innerHTML = `<div class="card empty">🧹 The source video was cleaned up to save space. Your Shorts are below.
      ${p.source_url ? `<br><br><button class="btn" id="reimport">Import this stream again</button>` : ""}</div>`;
    const btn = $("#reimport");
    if (btn) btn.onclick = () => { location.hash = "#/"; setTimeout(() => { $("#link").value = p.source_url; $("#creator").value = p.creator || ""; }, 50); };
    return;
  }
  body.innerHTML = `
    <div class="project-grid">
      <div class="card player-card">
        <video id="srcVideo" src="/api/projects/${p.id}/source" controls preload="metadata" poster="/api/projects/${p.id}/poster.jpg"></video>
        <div class="timeline" id="timeline"></div>
        <div class="add-range">
          <span class="muted">Add your own moment:</span>
          <input id="mFrom" placeholder="from 1:20"> <input id="mTo" placeholder="to 1:55">
          <button class="btn small" id="useHead">From playhead</button>
          <button class="btn small primary" id="addMoment">Add</button>
        </div>
        <div class="stream-search">
          <div class="row"><input id="sq" type="text" placeholder="🔎 Search what he says… e.g. police chase, lucia, no way">
            <button class="btn small" id="sqBtn">Search</button></div>
          <div id="sqHits" class="hits"></div>
        </div>
      </div>
      <div class="moments" id="moments"></div>
    </div>
    <div id="editorWrap"></div>`;
  const v = $("#srcVideo");
  v.addEventListener("timeupdate", drawTimeline);
  $("#timeline").onclick = (e) => {
    const r = e.currentTarget.getBoundingClientRect();
    v.currentTime = ((e.clientX - r.left) / r.width) * p.duration;
  };
  $("#useHead").onclick = () => { $("#mFrom").value = fmt(v.currentTime); $("#mTo").value = fmt(Math.min(p.duration, v.currentTime + 30)); };
  $("#addMoment").onclick = async () => {
    try {
      const m = await api(`/api/projects/${p.id}/moments`, { json: { start: $("#mFrom").value, end: $("#mTo").value } });
      p.moments.push(m); p.moments.sort((a, b) => a.start - b.start);
      renderMoments(); selectMoment(m.id);
    } catch (e) { toast(e.message, true); }
  };
  const runSearch = async () => {
    const q = $("#sq").value.trim(), box = $("#sqHits");
    if (!q) { box.innerHTML = ""; return; }
    const { hits } = await api(`/api/projects/${p.id}/search?q=${encodeURIComponent(q)}`);
    box.innerHTML = hits.length ? hits.map((h, i) => `<div class="hit">
        <button class="btn small ghost" data-seek="${h.at}">▶ ${fmt(h.at)}</button>
        <span class="ctx">“…${esc(h.context)}…”</span>
        <button class="btn small" data-mk="${i}">+ Make clip</button></div>`).join("")
      : `<p class="hint">Not said in this stream${p.error ? " (no subtitles)" : ""}.</p>`;
    $$("[data-seek]", box).forEach((b) => (b.onclick = () => { v.currentTime = Number(b.dataset.seek) - 2; v.play(); }));
    $$("[data-mk]", box).forEach((b) => (b.onclick = async () => {
      const h = hits[Number(b.dataset.mk)];
      try {
        const m = await api(`/api/projects/${p.id}/moments`, { json: { start: h.start, end: h.end } });
        m.reasons = [`you searched "${h.term}"`];
        p.moments.push(m); p.moments.sort((a, b2) => a.start - b2.start);
        renderMoments(); drawTimeline(); selectMoment(m.id);
      } catch (e) { toast(e.message, true); }
    }));
  };
  $("#sqBtn").onclick = runSearch;
  $("#sq").addEventListener("keydown", (e) => e.key === "Enter" && runSearch());
  renderMoments();
  drawTimeline();
  if (p.moments.length) selectMoment(p.moments[0].id, false);
}

function drawTimeline() {
  const p = state.project, tl = $("#timeline"), v = $("#srcVideo");
  if (!tl || !p.duration) return;
  tl.innerHTML = p.moments.map((m) => `<div class="mark ${m.id === state.momentId ? "sel" : ""}"
    style="left:${(m.start / p.duration) * 100}%;width:${Math.max(0.6, ((m.end - m.start) / p.duration) * 100)}%"></div>`).join("")
    + `<div class="head" style="left:${((v?.currentTime || 0) / p.duration) * 100}%"></div>`;
}

function renderMoments() {
  const p = state.project, box = $("#moments");
  if (!box) return;
  if (!p.moments.length) { box.innerHTML = `<div class="card empty">No moments found. Add one yourself on the left.</div>`; return; }
  box.innerHTML = p.moments.map((m) => {
    const cls = m.score >= 75 ? "hot" : m.score >= 45 ? "warm" : "cool";
    return `<article class="card moment ${m.id === state.momentId ? "sel" : ""}" data-id="${m.id}">
      <div class="moment-top">
        <span class="score ${cls}">${m.manual ? "★" : m.score}</span>
        <div style="flex:1"><span class="moment-time">${fmt(m.start)} → ${fmt(m.end)}</span>
          <span class="muted"> · ${Math.round(m.end - m.start)}s</span></div>
        <button class="btn small ghost" data-play="${m.id}" title="Play in source">▶</button>
        <button class="btn small ghost danger" data-del="${m.id}" title="Remove">✕</button>
      </div>
      ${m.hook ? `<div class="moment-hook">${esc(m.hook)}</div>` : ""}
      <div class="reasons">${m.reasons.map((r) => `<span>${esc(r)}</span>`).join("")}</div>
      ${m.transcript ? `<div class="snippet">“${esc(m.transcript)}”</div>` : ""}
    </article>`;
  }).join("");
  $$(".moment", box).forEach((el) => (el.onclick = (e) => {
    if (e.target.closest("[data-play],[data-del]")) return;
    selectMoment(el.dataset.id);
  }));
  $$("[data-play]", box).forEach((b) => (b.onclick = () => {
    const m = p.moments.find((x) => x.id === b.dataset.play), v = $("#srcVideo");
    v.currentTime = m.start; v.play();
  }));
  $$("[data-del]", box).forEach((b) => (b.onclick = async () => {
    await api(`/api/projects/${p.id}/moments/${b.dataset.del}`, { method: "DELETE" });
    p.moments = p.moments.filter((x) => x.id !== b.dataset.del);
    if (state.momentId === b.dataset.del) { state.momentId = null; $("#editorWrap").innerHTML = ""; stopPreview(); }
    renderMoments(); drawTimeline();
  }));
}

/* ---------------------------------------------------------------- editor */
function defaultStyle() {
  const s = state.status.settings, p = state.project;
  return {
    theme: s.default_theme || "vice-city", layout: s.default_layout || "blur",
    caption_position: "middle", caption_scale: 1, words_per_line: 0, uppercase: null,
    captions: true, show_hook: true, hook_seconds: 3.5, show_progress: true, normalize_audio: true,
    focus_x: 0.5, zoom: 1.0, cam_corner: "top-right", cam_size: 0.3,
    watermark: s.channel_tag || "", credit: p.creator ? `Clip: ${p.creator.startsWith("@") ? p.creator : p.creator}` : "",
  };
}

async function selectMoment(id, scroll = true) {
  const p = state.project, m = p.moments.find((x) => x.id === id);
  if (!m) return;
  state.momentId = id;
  state.style = { ...(state.style || defaultStyle()), hook: m.hook || "" };
  state.trim = { start: m.start, end: m.end };
  $$(".moment").forEach((el) => el.classList.toggle("sel", el.dataset.id === id));
  drawTimeline();
  const { words } = await api(`/api/projects/${p.id}/words?start=${Math.max(0, m.start - 30)}&end=${m.end + 60}`);
  state.words = words;
  renderEditor();
  if (scroll) $("#editorWrap").scrollIntoView({ behavior: "smooth", block: "start" });
}

function seg(name, options, value) {
  return `<div class="seg" data-seg="${name}">${options.map(([v, label]) =>
    `<button type="button" data-v="${esc(v)}" class="${String(v) === String(value) ? "on" : ""}">${esc(label)}</button>`).join("")}</div>`;
}

function renderEditor() {
  const st = state.style, m = state.project.moments.find((x) => x.id === state.momentId);
  $("#editorWrap").innerHTML = `
  <section class="card editor">
    <div>
      <div class="phone" id="phone"></div>
      <div class="phone-controls">
        <button class="btn small" id="pvPlay">▶ Play</button>
        <button class="btn small" id="pvRestart">⟲ Restart</button>
        <button class="btn small" id="pvMute">🔊</button>
      </div>
      <div class="phone-time" id="pvTime"></div>
    </div>
    <div class="controls">
      <div class="ctrl">
        <h4>Trim</h4>
        <div class="trim">
          <div class="trim-box"><button class="btn small" data-nudge="start:-0.5">−</button>
            <input id="tStart" value="${fmt(state.trim.start)}"><button class="btn small" data-nudge="start:0.5">+</button></div>
          <div class="trim-box"><button class="btn small" data-nudge="end:-0.5">−</button>
            <input id="tEnd" value="${fmt(state.trim.end)}"><button class="btn small" data-nudge="end:0.5">+</button></div>
        </div>
        <p class="hint" id="tLen"></p>
      </div>

      <div class="ctrl"><h4>Caption style</h4>
        <div class="themes">${state.themes.map((t) => `
          <button type="button" class="theme ${t.id === st.theme ? "on" : ""}" data-theme="${t.id}">
            <div class="sample" style="font-family:'${t.font}';color:${t.text};-webkit-text-stroke:2px ${t.outline};paint-order:stroke fill;text-shadow:${t.blur ? `0 0 6px ${t.outline},0 0 12px ${t.outline}` : `2px 2px 0 ${t.shadow}`}">
              ${t.upper ? "GTA" : "Gta"} <span style="${activeCss(t, 0.33)}">${t.upper ? "SIX" : "six"}</span></div>
            <small>${esc(t.label)}</small></button>`).join("")}</div>
      </div>

      <div class="ctrl"><h4>Layout</h4>
        ${seg("layout", Object.entries(state.layouts), st.layout)}
      </div>

      <div class="sliders" id="layoutOpts"></div>

      <div class="ctrl"><h4>Captions</h4>
        <div class="row">
          ${seg("caption_position", [["upper", "Top"], ["middle", "Middle"], ["lower", "Bottom"]], st.caption_position)}
          ${seg("words_per_line", [[0, "Auto"], [1, "1 word"], [2, "2"], [3, "3"], [4, "4"]], st.words_per_line)}
        </div>
        <div class="sliders" style="margin-top:12px">
          <label>Size <input type="range" min="0.7" max="1.4" step="0.05" data-k="caption_scale" value="${st.caption_scale}"></label>
          <label class="check" style="align-self:end"><input type="checkbox" data-k="uppercase" ${st.uppercase ?? theme(st.theme).upper ? "checked" : ""}> ALL CAPS</label>
        </div>
      </div>

      <div class="ctrl"><h4>Hook title (top of video)</h4>
        <div class="row"><input type="text" data-k="hook" value="${esc(st.hook)}" style="flex:1" maxlength="60">
          ${seg("hook_seconds", [[3.5, "3s"], [6, "6s"], [0, "Whole clip"]], st.hook_seconds)}</div>
      </div>

      <div class="grid2">
        <label>Channel tag <input type="text" data-k="watermark" value="${esc(st.watermark)}"></label>
        <label>Credit line <input type="text" data-k="credit" value="${esc(st.credit)}"></label>
      </div>

      <div class="toggles">
        <label class="check"><input type="checkbox" data-k="captions" ${st.captions ? "checked" : ""}> Captions</label>
        <label class="check"><input type="checkbox" data-k="show_hook" ${st.show_hook ? "checked" : ""}> Hook title</label>
        <label class="check"><input type="checkbox" data-k="show_progress" ${st.show_progress ? "checked" : ""}> Progress bar</label>
        <label class="check"><input type="checkbox" data-k="normalize_audio" ${st.normalize_audio ? "checked" : ""}> Loudness boost</label>
      </div>

      <div class="render-bar">
        <span class="muted">${state.words.length ? "Preview = final look" : "No subtitles for this video → captions off"}</span>
        <div class="row">
          <button class="btn" id="renderAll">Render all (${state.project.moments.length})</button>
          <button class="btn primary" id="renderOne">Render this Short</button>
        </div>
      </div>
    </div>
  </section>`;
  bindEditor(m);
  renderLayoutOpts();
  buildPreview();
}

function renderLayoutOpts() {
  const st = state.style, box = $("#layoutOpts");
  let html = `<label>Horizontal focus <input type="range" min="0" max="1" step="0.01" data-k="focus_x" value="${st.focus_x}"></label>`;
  if (st.layout === "blur") html += `<label>Zoom <input type="range" min="1" max="2" step="0.05" data-k="zoom" value="${st.zoom}"></label>`;
  if (st.layout === "split") html += `<label>Facecam size <input type="range" min="0.15" max="0.6" step="0.01" data-k="cam_size" value="${st.cam_size}"></label>
    <div class="ctrl" style="grid-column:1/-1"><h4>Facecam corner in the stream</h4>${seg("cam_corner",
      [["top-left", "↖ Top left"], ["top-right", "↗ Top right"], ["bottom-left", "↙ Bottom left"], ["bottom-right", "↘ Bottom right"]], st.cam_corner)}</div>`;
  box.innerHTML = html;
  bindInputs(box);
  bindSegs(box);
}

function bindInputs(root) {
  $$("[data-k]", root).forEach((el) => {
    const k = el.dataset.k;
    const handler = () => {
      state.style[k] = el.type === "checkbox" ? el.checked : el.type === "range" ? Number(el.value) : el.value;
      if (["focus_x", "zoom", "cam_size"].includes(k)) layoutPreview();
      drawPreview(true);
    };
    el.addEventListener("input", handler);
  });
}
function bindSegs(root) {
  $$("[data-seg]", root).forEach((segEl) => $$("button", segEl).forEach((b) => (b.onclick = () => {
    const k = segEl.dataset.seg, raw = b.dataset.v;
    state.style[k] = ["words_per_line", "hook_seconds"].includes(k) ? Number(raw) : raw;
    $$("button", segEl).forEach((x) => x.classList.toggle("on", x === b));
    if (k === "layout") { renderLayoutOpts(); buildPreview(); }
    else if (k === "cam_corner") layoutPreview();
    drawPreview(true);
  })));
}

function bindEditor(m) {
  const root = $("#editorWrap");
  bindInputs($(".controls", root));
  bindSegs($(".controls", root));
  $$("[data-theme]", root).forEach((b) => (b.onclick = () => {
    state.style.theme = b.dataset.theme; state.style.uppercase = null;
    $$("[data-theme]", root).forEach((x) => x.classList.toggle("on", x === b));
    const up = $('[data-k="uppercase"]', root); if (up) up.checked = theme(b.dataset.theme).upper;
    drawPreview(true);
  }));
  const syncTrim = () => {
    const a = parseT($("#tStart").value), b = parseT($("#tEnd").value);
    if (a != null && b != null && b > a) { state.trim = { start: a, end: b }; }
    $("#tLen").textContent = `Length: ${(state.trim.end - state.trim.start).toFixed(1)}s ${state.trim.end - state.trim.start > 60 ? "· over 60s won't count as a Short on some accounts" : ""}`;
  };
  $("#tStart").onchange = () => { syncTrim(); restartPreview(); };
  $("#tEnd").onchange = syncTrim;
  $$("[data-nudge]", root).forEach((b) => (b.onclick = () => {
    const [k, d] = b.dataset.nudge.split(":");
    state.trim[k] = Math.max(0, Math.min(state.project.duration, state.trim[k] + Number(d)));
    $("#tStart").value = fmt(state.trim.start); $("#tEnd").value = fmt(state.trim.end);
    syncTrim(); if (k === "start") restartPreview();
  }));
  syncTrim();
  $("#pvPlay").onclick = togglePreview;
  $("#pvRestart").onclick = restartPreview;
  $("#pvMute").onclick = () => { const v = pv.master; if (!v) return; v.muted = !v.muted; $("#pvMute").textContent = v.muted ? "🔇" : "🔊"; };
  $("#renderOne").onclick = () => renderShort(m, state.trim.start, state.trim.end);
  $("#renderAll").onclick = async () => {
    if (!confirm(`Render all ${state.project.moments.length} moments with this style?`)) return;
    for (const mm of state.project.moments) {
      await renderShort(mm, mm.start, mm.end, mm.hook, true);
    }
    toast("All Shorts are in the render queue");
  };
}

async function renderShort(m, start, end, hook, quiet = false) {
  const style = { ...state.style };
  if (hook !== undefined) style.hook = hook;
  if (style.uppercase === null) delete style.uppercase;
  if (!style.words_per_line) delete style.words_per_line;
  try {
    const clip = await api(`/api/projects/${state.project.id}/render`, { json: {
      moment_id: m.id, start, end, style, titles: m.titles || [], title: (m.titles || [])[0] || "",
    } });
    state.project.clips.push(clip);
    renderClips(true);
    if (!quiet) { toast("Rendering… it will appear under Your Shorts"); $(".clips").scrollIntoView({ behavior: "smooth" }); }
  } catch (e) { toast(e.message, true); }
}

/* ------------------------------------------------------- live 9:16 preview */
const pv = { videos: [], master: null, raf: 0 };

function stopPreview() {
  cancelAnimationFrame(pv.raf);
  pv.videos.forEach((v) => { v.pause(); v.removeAttribute("src"); v.load(); });
  pv.videos = []; pv.master = null;
}

function makeVideo(cls = "") {
  const v = document.createElement("video");
  v.src = `/api/projects/${state.project.id}/source`;
  v.muted = true; v.playsInline = true; v.preload = "auto";
  if (cls) v.className = cls;
  return v;
}

function buildPreview() {
  stopPreview();
  const phone = $("#phone"), st = state.style;
  phone.innerHTML = "";
  if (st.layout === "blur") {
    const bg = makeVideo("bg"); phone.append(bg);
    const layer = document.createElement("div"); layer.className = "layer"; layer.id = "lyMain";
    const fg = makeVideo(); layer.append(fg); phone.append(layer);
    pv.videos = [fg, bg];
  } else if (st.layout === "crop") {
    const layer = document.createElement("div"); layer.className = "layer"; layer.id = "lyMain";
    const v = makeVideo(); layer.append(v); phone.append(layer);
    pv.videos = [v];
  } else {
    const cam = document.createElement("div"); cam.className = "layer"; cam.id = "lyCam";
    const game = document.createElement("div"); game.className = "layer"; game.id = "lyMain";
    const v1 = makeVideo(), v2 = makeVideo();
    cam.append(v1); game.append(v2); phone.append(cam, game);
    const line = document.createElement("div"); line.className = "layer";
    Object.assign(line.style, { left: 0, right: 0, top: "239px", height: "2px", background: "#000" });
    phone.append(line);
    pv.videos = [v2, v1];
  }
  phone.insertAdjacentHTML("beforeend", `<div class="credit" id="pvCredit"></div><div class="hook" id="pvHook"></div>
    <div class="cap" id="pvCap"></div><div class="tag" id="pvTag"></div><div class="pbar" id="pvBar"></div>`);
  pv.master = pv.videos[0];
  pv.master.muted = false;
  pv.master.addEventListener("loadedmetadata", () => { pv.master.currentTime = state.trim.start; layoutPreview(); });
  pv.videos.slice(1).forEach((v) => v.addEventListener("loadedmetadata", () => (v.currentTime = state.trim.start)));
  layoutPreview();
  loop();
}

function layoutPreview() {
  const st = state.style, p = state.project;
  const sw = p.width || 1920, sh = p.height || 1080, ar = sw / sh;
  const place = (v, w, h, left, top) => Object.assign(v.style, { width: w + "px", height: h + "px", left: left + "px", top: top + "px" });
  const main = $("#lyMain");
  if (!main) return;
  const vid = $("video", main);
  if (st.layout === "blur") {
    const fw = 360 * st.zoom, fh = fw / ar, lw = Math.min(fw, 360);
    Object.assign(main.style, { width: lw + "px", height: fh + "px", left: (360 - lw) / 2 + "px", top: (640 - fh) / 2 - 20 + "px" });
    place(vid, fw, fh, -(fw - lw) * st.focus_x, 0);
  } else if (st.layout === "crop") {
    Object.assign(main.style, { inset: 0 });
    const h = 640, w = h * ar;
    place(vid, w, h, -(w - 360) * st.focus_x, 0);
  } else {
    const camL = $("#lyCam"), topH = 240, botH = 400;
    Object.assign(camL.style, { left: 0, top: 0, width: "360px", height: topH + "px" });
    Object.assign(main.style, { left: 0, top: topH + "px", width: "360px", height: botH + "px" });
    const w = botH * ar; place(vid, w, botH, -(w - 360) * st.focus_x, 0);
    const regionW = sw * st.cam_size, regionH = regionW * (720 / 1080), k = 360 / regionW;
    const camX = st.cam_corner.includes("left") ? 0 : sw - regionW;
    const camY = st.cam_corner.includes("top") ? 0 : sh - regionH;
    place($("video", camL), sw * k, sh * k, -camX * k, -camY * k);
  }
}

function chunksFor(words, start, end) {
  const st = state.style, t = theme(st.theme);
  const upper = st.uppercase ?? t.upper, per = st.words_per_line || t.words;
  const local = words.filter((w) => w.end > start && w.start < end)
    .map((w) => ({ start: Math.max(0, w.start - start), end: Math.min(end - start, w.end - start), word: upper ? w.word.toUpperCase() : w.word }));
  const chunks = [];
  for (const w of local) {
    const last = chunks[chunks.length - 1];
    const gap = last && w.start - last[last.length - 1].end > 0.6;
    const sentence = last && /[.!?]$/.test(last[last.length - 1].word);
    if (!last || last.length >= per || gap || sentence) chunks.push([]);
    chunks[chunks.length - 1].push(w);
  }
  return chunks;
}

function activeCss(t, scale) {
  let css = `color:${t.active};transform:scale(${t.pop / 100})${t.tilt ? ` rotate(${-t.tilt}deg)` : ""};`;
  if (t.mode === "box") css = `color:${t.box_text};-webkit-text-stroke:${Math.max(10, t.outline_w * 2) * scale * 2}px ${t.active};transform:scale(${t.pop / 100});`;
  return css;
}

let lastCapKey = "";
function drawPreview(force = false) {
  const v = pv.master; if (!v) return;
  const st = state.style, t = theme(st.theme), len = state.trim.end - state.trim.start;
  const local = v.currentTime - state.trim.start;
  const upper = st.uppercase ?? t.upper;

  // captions
  const cap = $("#pvCap");
  let html = "", key = "";
  if (st.captions && state.words.length) {
    const chunks = chunksFor(state.words, state.trim.start, state.trim.end);
    for (let ci = 0; ci < chunks.length; ci++) {
      const ch = chunks[ci];
      let chEnd = ch[ch.length - 1].end + 0.25;
      if (ci + 1 < chunks.length) chEnd = Math.min(chEnd, chunks[ci + 1][0].start);
      if (local >= ch[0].start && local < chEnd) {
        let active = 0;
        ch.forEach((w, i) => { if (local >= w.start) active = i; });
        key = ci + ":" + active;
        html = ch.map((w, i) => {
          let css = "";
          if (i === active) css = activeCss(t, S);
          else if (i > active && t.mode === "reveal") css = "visibility:hidden";
          else if (i < active && t.mode === "karaoke") css = `color:${t.active}`;
          return `<span class="w" style="${css}">${esc(w.word)}</span>`;
        }).join(" ");
        break;
      }
    }
  }
  if (force || key !== lastCapKey) {
    lastCapKey = key;
    const size = t.size * S * st.caption_scale;
    Object.assign(cap.style, {
      top: state.positions[st.caption_position] * S + "px", fontFamily: `'${t.font}'`, fontSize: size + "px",
      color: t.text, WebkitTextStroke: `${t.outline_w * S * 2}px ${t.outline}`, paintOrder: "stroke fill",
      textShadow: t.blur ? `0 0 ${t.blur * 1.2}px ${t.outline}, 0 0 ${t.blur * 2.5}px ${t.outline}` : `${t.shadow_d * S}px ${t.shadow_d * S}px 0 ${t.shadow}`,
    });
    cap.innerHTML = html;
  }

  // hook
  const hook = $("#pvHook"), showHook = st.show_hook && st.hook && (st.hook_seconds <= 0 || local < st.hook_seconds);
  hook.innerHTML = showHook ? `<span style="background:${t.accent};color:${t.accent_text};font-family:'${t.font}';font-size:${t.size * 0.72 * S * st.caption_scale}px">${esc(upper ? st.hook.toUpperCase() : st.hook)}</span>` : "";
  $("#pvTag").textContent = st.watermark || "";
  $("#pvCredit").textContent = st.credit || "";
  const bar = $("#pvBar");
  bar.style.display = st.show_progress ? "block" : "none";
  bar.style.background = t.accent;
  bar.style.width = Math.max(0, Math.min(100, (local / len) * 100)) + "%";
  $("#pvTime").textContent = `${fmt(Math.max(0, local))} / ${fmt(len)}`;
}

function loop() {
  const v = pv.master;
  if (v) {
    if (v.currentTime >= state.trim.end || v.currentTime < state.trim.start - 1) {
      v.currentTime = state.trim.start;
    }
    pv.videos.slice(1).forEach((o) => {
      if (Math.abs(o.currentTime - v.currentTime) > 0.2) o.currentTime = v.currentTime;
      if (v.paused !== o.paused) v.paused ? o.pause() : o.play().catch(() => {});
    });
    drawPreview();
  }
  pv.raf = requestAnimationFrame(loop);
}

function togglePreview() {
  const v = pv.master; if (!v) return;
  if (v.paused) { v.play().catch(() => {}); $("#pvPlay").textContent = "⏸ Pause"; }
  else { v.pause(); $("#pvPlay").textContent = "▶ Play"; }
}
function restartPreview() { pv.videos.forEach((v) => (v.currentTime = state.trim.start)); }

/* ---------------------------------------------------------------- clips */
function clipDescription(c) {
  const p = state.project, s = state.status.settings;
  const credit = p.creator ? `🎥 Credit: ${p.creator}${p.source_url ? ` — ${p.source_url}` : ""}\n` : (p.source_url ? `Source: ${p.source_url}\n` : "");
  return `${c.title || ""}\n\n${credit}Clipped with permission.\n\n${s.default_hashtags || "#GTA6 #Shorts"}`;
}

function renderClips(force = false) {
  const p = state.project, grid = $("#clipGrid");
  if (!grid || !p) return;
  const sig = JSON.stringify(p.clips.map((c) => [c.id, c.status, c.upload?.state]));
  if (!force && sig === state.clipSig) return updateClipProgress();
  state.clipSig = sig;
  if (!p.clips.length) { grid.innerHTML = `<div class="empty card" style="grid-column:1/-1">Pick a moment above and hit <b>Render this Short</b>.</div>`; return; }
  grid.innerHTML = [...p.clips].reverse().map((c) => {
    const d = state.drafts[c.id] || (state.drafts[c.id] = {
      title: c.title || "", description: "", tags: "GTA6, GTAVI, ViceCity, Shorts, gaming", privacy: "private", rights: false,
    });
    if (!d.description) d.description = clipDescription({ ...c, title: d.title });
    let media;
    if (c.status === "uploaded-removed") media = `<div class="render-wait"><div>🧹 File removed after upload</div></div>`;
    else if (c.status === "ready") media = `<video src="/api/projects/${p.id}/clips/${c.id}.mp4#t=0.5" controls preload="metadata"></video>`;
    else if (c.status === "error") media = `<div class="render-wait"><div><b class="hint bad">Render failed</b><p class="muted">${esc(c.error)}</p></div></div>`;
    else media = `<div class="render-wait"><div><b>Rendering…</b><div class="bar" style="width:180px;margin:12px auto"><i data-clipbar="${c.id}" style="width:0"></i></div><span class="muted" data-clipmsg="${c.id}">Waiting in queue</span></div></div>`;
    const up = c.upload;
    const uploadBox = up?.state === "done"
      ? `<div class="uploaded">✅ Uploaded to <b>${esc(up.channel || "YouTube")}</b> as <b>${esc(up.privacy)}</b> · <a href="${esc(up.url)}" target="_blank" rel="noopener">View Short</a> · <a href="${esc(up.studio_url)}" target="_blank" rel="noopener">Open in Studio</a></div>`
      : up?.state === "uploading" ? `<div class="bar"><i data-upbar="${c.id}" style="width:0"></i></div><span class="muted" data-upmsg="${c.id}">Uploading…</span>`
      : `${up?.state === "error" ? `<p class="hint bad">${esc(up.error)}</p>` : ""}
        <label>Title <input type="text" data-f="title" maxlength="100" value="${esc(d.title)}"></label>
        ${(c.titles || []).length ? `<div class="title-ideas">${c.titles.map((t) => `<button type="button" data-idea="${esc(t)}">${esc(t)}</button>`).join("")}</div>` : ""}
        <label>Description <textarea data-f="description">${esc(d.description)}</textarea></label>
        <label>Tags <input type="text" data-f="tags" value="${esc(d.tags)}"></label>
        ${(state.status.channels || []).length > 1 ? `<label>Channel <select data-f="channel_id">${state.status.channels.map((ch) =>
          `<option value="${esc(ch.id)}" ${d.channel_id === ch.id ? "selected" : ""}>${esc(ch.title)}</option>`).join("")}</select></label>` : ""}
        <div class="row">
          <select data-f="privacy" style="width:auto">
            ${["private", "unlisted", "public"].map((x) => `<option ${d.privacy === x ? "selected" : ""}>${x}</option>`).join("")}
          </select>
          <label class="check" style="flex:1"><input type="checkbox" data-f="rights" ${d.rights ? "checked" : ""}> I have permission to post this</label>
        </div>
        <button class="btn primary" data-upload="${c.id}" ${c.status !== "ready" ? "disabled" : ""}>Upload to YouTube</button>`;
    return `<article class="card clip" data-clip="${c.id}">
      ${media}
      <div class="row" style="justify-content:space-between">
        <span class="muted">${fmt(c.start)} → ${fmt(c.end)} · ${esc(theme(c.style?.theme)?.label || "")}</span>
        <div class="row">
          ${c.status === "ready" ? `<a class="btn small" href="/api/projects/${p.id}/clips/${c.id}.mp4?download=1">Download</a>` : ""}
          <button class="btn small ghost danger" data-delclip="${c.id}">Delete</button>
        </div>
      </div>
      ${uploadBox}
    </article>`;
  }).join("");

  $$(".clip", grid).forEach((card) => {
    const id = card.dataset.clip, d = state.drafts[id];
    $$("[data-f]", card).forEach((el) => el.addEventListener("input", () => {
      d[el.dataset.f] = el.type === "checkbox" ? el.checked : el.value;
    }));
    $$("[data-idea]", card).forEach((b) => (b.onclick = () => {
      const old = d.title; d.title = b.dataset.idea;
      $('[data-f="title"]', card).value = d.title;
      const desc = $('[data-f="description"]', card);
      if (desc.value.startsWith(old)) { desc.value = d.title + desc.value.slice(old.length); d.description = desc.value; }
    }));
  });
  $$("[data-delclip]", grid).forEach((b) => (b.onclick = async () => {
    if (!confirm("Delete this Short?")) return;
    await api(`/api/projects/${p.id}/clips/${b.dataset.delclip}`, { method: "DELETE" });
    p.clips = p.clips.filter((c) => c.id !== b.dataset.delclip);
    renderClips(true);
  }));
  $$("[data-upload]", grid).forEach((b) => (b.onclick = async () => {
    const id = b.dataset.upload, d = state.drafts[id];
    if (!state.status.channel) { toast("Connect your YouTube channel in Settings first", true); $("#settingsDialog").showModal(); return; }
    if (!d.title.trim()) return toast("Add a title", true);
    if (!d.rights) return toast("Confirm you have permission to post this clip", true);
    if (d.privacy === "public" && !confirm("Publish this Short publicly right now?")) return;
    try {
      await api(`/api/projects/${p.id}/clips/${id}/upload`, { json: {
        title: d.title, description: d.description, tags: d.tags, privacy: d.privacy, rights_confirmed: true,
        channel_id: d.channel_id || "",
      } });
      const c = p.clips.find((x) => x.id === id); c.upload = { state: "uploading" };
      renderClips(true); toast("Uploading to YouTube…");
    } catch (e) { toast(e.message, true); }
  }));
  updateClipProgress();
}

function updateClipProgress() {
  for (const j of state.jobs) {
    if (j.state !== "running" && j.state !== "queued") continue;
    const bar = $(`[data-clipbar="${j.clip_id}"]`) || $(`[data-upbar="${j.clip_id}"]`);
    const msg = $(`[data-clipmsg="${j.clip_id}"]`) || $(`[data-upmsg="${j.clip_id}"]`);
    if (bar && j.progress != null) bar.style.width = j.progress * 100 + "%";
    if (msg) msg.textContent = j.message;
  }
}

/* ---------------------------------------------------------------- jobs */
async function pollJobs() {
  let jobs;
  try { ({ jobs } = await api("/api/jobs")); } catch { return; }
  state.jobs = jobs;
  const dock = $("#jobsDock");
  const visible = jobs.filter((j) => j.state === "running" || j.state === "queued" || (j.state === "error" && Date.now() / 1000 - j.updated < 30));
  // jobs of a deleted project disappear right away
  dock.innerHTML = visible.slice(0, 4).map((j) => `
    <div class="job ${j.state}"><b>${esc(j.label)}</b>
      <div class="msg">${esc(j.state === "error" ? j.error : j.message)}</div>
      ${j.state !== "error" ? `<div class="bar ${j.progress == null ? "indet" : ""}"><i style="width:${(j.progress || 0) * 100}%"></i></div>` : ""}
    </div>`).join("");

  const p = state.project;
  if (!p || !location.hash.startsWith("#/p/" + p.id)) return;
  let changed = false;
  for (const j of jobs) {
    if (j.project_id !== p.id) continue;
    if (state.lastJobStates[j.id] !== j.state && (j.state === "done" || j.state === "error")) changed = true;
    state.lastJobStates[j.id] = j.state;
  }
  const running = jobs.find((j) => j.project_id === p.id && j.kind !== "render" && j.kind !== "upload" && j.state === "running");
  if (running && $("#progressMsg")) {
    $("#progressMsg").textContent = running.message;
    const bar = $("#progressBar");
    if (running.progress != null) { bar.parentElement.classList.remove("indet"); bar.style.width = running.progress * 100 + "%"; }
    else bar.parentElement.classList.add("indet");
  }
  updateClipProgress();
  if (changed || (p.status !== "ready" && p.status !== "error")) {
    const fresh = await api("/api/projects/" + p.id);
    const wasReady = p.status === "ready";
    const momentsChanged = JSON.stringify(fresh.moments.map((m) => m.id)) !== JSON.stringify(p.moments.map((m) => m.id));
    state.project = fresh;
    $("#pBadge").innerHTML = statusBadge(fresh.status);
    if (!wasReady && fresh.status === "ready") renderProjectBody();
    else if (fresh.status !== "ready") renderProjectBody();
    else if (momentsChanged) { renderMoments(); drawTimeline(); }
    renderClips();
  }
}

/* ---------------------------------------------------------------- settings */
function initSettings() {
  const dlg = $("#settingsDialog");
  $("#settingsBtn").onclick = () => { fillSettings(); dlg.showModal(); };
  $("#channelPill").addEventListener("click", fillSettings);
  $("#saveKey").onclick = async () => {
    await api("/api/settings", { json: { youtube_api_key: $("#apiKey").value } });
    $("#apiKey").value = ""; await refreshStatus(); toast("API key saved");
  };
  $("#oauthFile").onchange = async (e) => {
    const form = new FormData(); form.append("file", e.target.files[0]);
    try { await api("/api/settings/oauth-client", { method: "POST", body: form }); await refreshStatus(); toast("Client file saved — now sign in"); }
    catch (err) { toast(err.message, true); }
  };
  $("#signInBtn").onclick = async () => {
    if (state.status.hosted) { window.top.location.href = state.status.public_url + "/oauth/start"; return; }
    $("#oauthState").textContent = "A Google sign-in tab is opening… finish it there.";
    try { const r = await api("/api/youtube/signin", { method: "POST" }); await refreshStatus(); toast(`Connected ${r.channel.title}`); }
    catch (err) { $("#oauthState").textContent = err.message; $("#oauthState").className = "hint bad"; }
  };

  $("#saveSettings").onclick = async () => {
    const data = {
      whisper_model: $("#setWhisper").value, language: $("#setLang").value,
      clip_length: Number($("#setLength").value), clips_per_video: Number($("#setCount").value),
      channel_tag: $("#setTag").value, default_hashtags: $("#setTags").value, keywords: $("#setKeywords").value,
    };
    state.status.settings = await api("/api/settings", { json: data });
    toast("Defaults saved");
  };
}

async function refreshStatus() {
  state.status = await api("/api/status");
  renderChannel(); fillSettings();
}

function fillSettings() {
  const st = state.status, s = st.settings;
  $("#apiKeyState").textContent = st.api_key ? "✓ API key saved" : "No key yet";
  $("#apiKeyState").className = "hint " + (st.api_key ? "ok" : "");
  $("#oauthState").className = "hint " + (st.channel ? "ok" : "");
  $("#oauthState").textContent = st.channel ? "" : st.oauth_client ? "Client file saved. Click “Add a channel”." : "No client file yet";
  $("#chanList").innerHTML = (st.channels || []).map((c) => `<div class="chan">
      ${c.thumb ? `<img src="${esc(c.thumb)}" alt="">` : `<span class="brand-mark" style="width:28px;height:28px;font-size:13px">YT</span>`}
      <b>${esc(c.title)}</b><span class="badge ready">connected</span>
      <button type="button" class="btn small ghost danger" data-rmch="${esc(c.id)}">Remove</button></div>`).join("");
  $$("[data-rmch]").forEach((b) => (b.onclick = async () => {
    await api("/api/youtube/remove", { json: { id: b.dataset.rmch } }); await refreshStatus();
  }));
  $("#setKeywords").value = s.keywords || "";
  $("#setWhisper").value = s.whisper_model; $("#setLang").value = s.language;
  $("#setLength").value = s.clip_length; $("#setCount").value = s.clips_per_video;
  $("#setTag").value = s.channel_tag; $("#setTags").value = s.default_hashtags;
  $("#oauthHosted").innerHTML = st.hosted ? `Online mode: create the OAuth client as <b>Web application</b> and add this
    redirect URI in Google Cloud: <code>${esc(st.redirect_uri)}</code>. Paste the client JSON in the Space secret
    <b>GOOGLE_OAUTH_CLIENT_JSON</b>.` : "";
  $("#logoutLink").style.display = st.login ? "" : "none";
  $("#sysState").innerHTML = `FFmpeg + captions: ${st.ffmpeg ? "✓" : "✗ missing — run start.bat again"} · Auto-subtitles: ${st.whisper ? "✓" : "✗ missing"} · v${esc(st.version)}`;
}


/* ---------------------------------------------------------------- autopilot page */
async function viewAuto() {
  $("#view").innerHTML = `<div class="empty">Loading…</div>`;
  await refreshStatus();
  const st = state.status, s = st.settings;
  const chOpts = (st.channels || []).map((c) => `<option value="${esc(c.id)}" ${s.auto_channel === c.id ? "selected" : ""}>${esc(c.title)}</option>`).join("");
  $("#view").innerHTML = `
  <h2 class="section-title">AUTO<span>PILOT</span></h2>
  <p class="muted" style="margin-top:-6px">Let the app find, cut and post Shorts on its own. Keep the app open (and the PC awake) for it to work.</p>

  <div class="auto-flow card">
    <div class="flow-step"><b>1 · Watch</b><span>Checks your creators' channels for new GTA 6 videos</span></div><i>→</i>
    <div class="flow-step"><b>2 · Import</b><span>Downloads + writes subtitles</span></div><i>→</i>
    <div class="flow-step"><b>3 · Pick</b><span>Scores moments with your keywords + hype</span></div><i>→</i>
    <div class="flow-step"><b>4 · Render</b><span>Your theme, captions, hook, credit</span></div><i>→</i>
    <div class="flow-step"><b>5 · Post</b><span>Uploads to your channel</span></div><i>→</i>
    <div class="flow-step"><b>6 · Clean</b><span>Deletes the big source file</span></div>
  </div>

  <div class="auto-grid">
    <section class="card auto-card">
      <div class="auto-head"><h3>⚡ Autopilot rules</h3>
        <label class="switch"><input type="checkbox" id="aOn" ${s.autopilot ? "checked" : ""}><span></span> On for every import</label></div>
      <div class="grid2">
        <label>Shorts per video <input type="number" id="aClips" min="1" max="10" value="${s.auto_clips}"></label>
        <label>Minimum score (0–100) <input type="number" id="aMin" min="0" max="100" value="${s.auto_min_score}"></label>
        <label>Max length (sec) <input type="number" id="aMax" min="10" max="180" value="${s.auto_max_seconds}"></label>
        <label>Layout <select id="aLayout">${Object.entries(state.layouts).map(([k, v]) => `<option value="${k}" ${s.auto_layout === k ? "selected" : ""}>${esc(v)}</option>`).join("")}</select></label>
        <label>Caption theme <select id="aTheme">${state.themes.map((t) => `<option value="${t.id}" ${s.auto_theme === t.id ? "selected" : ""}>${esc(t.label)}</option>`).join("")}</select></label>
        <label>After rendering <select id="aUpload">
          ${[["off", "Don't upload (I'll check first)"], ["private", "Upload as Private"], ["unlisted", "Upload as Unlisted"], ["public", "Upload as Public"]]
            .map(([k, v]) => `<option value="${k}" ${s.auto_upload === k ? "selected" : ""}>${v}</option>`).join("")}</select></label>
        <label>Post to channel <select id="aChannel">${chOpts || `<option value="">No channel connected</option>`}</select></label>
      </div>
      <p class="hint warn">⚠️ Google keeps uploads from a new, unverified API project <b>private</b> until you pass the free YouTube API audit
        (<a href="https://support.google.com/youtube/contact/yt_api_form" target="_blank" rel="noopener">form</a>). Until then, use “Don't upload”
        and post the finished Shorts from YouTube Studio or the app.</p>
      <div class="row end"><button class="btn primary" id="aSave">Save rules</button></div>
    </section>

    <section class="card auto-card">
      <div class="auto-head"><h3>👀 Watchlist</h3>
        <label class="switch"><input type="checkbox" id="wOn" ${s.watch_enabled ? "checked" : ""}><span></span> Watching</label></div>
      <div class="row"><input type="text" id="wAdd" placeholder="@IShowSpeed or channel link" style="flex:1">
        <button class="btn" id="wAddBtn">Add creator</button></div>
      <div class="chan-list" id="wList">${s.watch_channels.map((c) => `<div class="chan">
          ${c.thumb ? `<img src="${esc(c.thumb)}" alt="">` : ""}<b>${esc(c.title)}</b>
          <button class="btn small ghost danger" data-wrm="${esc(c.id)}">Remove</button></div>`).join("") || `<p class="hint">No creators yet. Only add creators who allow clipping.</p>`}</div>
      <div class="grid2" style="margin-top:14px">
        <label>Only videos whose title has <input type="text" id="wKeys" value="${esc(s.watch_keywords)}"></label>
        <label>Check every (minutes) <input type="number" id="wEvery" min="10" max="1440" value="${s.watch_interval}"></label>
        <label>Long streams: use only the first (minutes) <input type="number" id="wMax" min="10" max="720" value="${s.watch_max_minutes}"></label>
      </div>
      <p class="hint">Uses your YouTube API key (cheap: about 2 quota points per creator per check). Only videos posted after you turned it on are imported.</p>
      <div class="row end">
        <button class="btn ghost" id="wNow">Check now</button>
        <button class="btn primary" id="wSave">Save watchlist</button>
      </div>
    </section>

    <section class="card auto-card">
      <div class="auto-head"><h3>🧹 Cleanup</h3><span class="muted" id="store"></span></div>
      <div class="toggles" style="flex-direction:column;gap:10px">
        <label class="check"><input type="checkbox" id="cSrc" ${s.delete_source_after_auto ? "checked" : ""}> Delete the source video when Autopilot is done</label>
        <label class="check"><input type="checkbox" id="cClip" ${s.delete_clip_after_upload ? "checked" : ""}> Delete the Short file after it's uploaded</label>
      </div>
      <div class="grid2" style="margin-top:12px">
        <label>Auto-delete source videos older than (days, 0 = never) <input type="number" id="cDays" min="0" max="365" value="${s.keep_days}"></label>
      </div>
      <div class="row end">
        <button class="btn ghost danger" id="cAll">Delete all source videos now</button>
        <button class="btn primary" id="cSave">Save cleanup</button>
      </div>
    </section>

    <section class="card auto-card">
      <div class="auto-head"><h3>📜 Activity</h3><span class="muted" id="lastCheck"></span></div>
      <div class="activity" id="activity"></div>
    </section>
  </div>`;

  const save = async (data, msg) => { state.status.settings = await api("/api/settings", { json: data }); renderChannel(); toast(msg); };
  $("#aSave").onclick = () => save({
    autopilot: $("#aOn").checked, auto_clips: Number($("#aClips").value), auto_min_score: Number($("#aMin").value),
    auto_max_seconds: Number($("#aMax").value), auto_layout: $("#aLayout").value, auto_theme: $("#aTheme").value,
    auto_upload: $("#aUpload").value, auto_channel: $("#aChannel").value,
  }, "Autopilot rules saved");
  $("#aOn").onchange = () => save({ autopilot: $("#aOn").checked }, $("#aOn").checked ? "Autopilot is on for new imports" : "Autopilot off");
  $("#aUpload").onchange = () => { if ($("#aUpload").value === "public" && !confirm("Shorts will be posted publicly without you checking them first. Continue?")) $("#aUpload").value = "off"; };
  $("#wOn").onchange = async () => {
    if ($("#wOn").checked) await api("/api/watch/reset", { method: "POST" });
    save({ watch_enabled: $("#wOn").checked }, $("#wOn").checked ? "Watching for new videos" : "Watchlist paused");
  };
  $("#wSave").onclick = () => save({ watch_keywords: $("#wKeys").value, watch_interval: Number($("#wEvery").value),
    watch_max_minutes: Number($("#wMax").value) }, "Watchlist saved");
  $("#wAddBtn").onclick = async () => {
    try { const c = await api("/api/watch/channels", { json: { channel: $("#wAdd").value } }); toast(`Watching ${c.title}`); viewAuto(); }
    catch (e) { toast(e.message, true); }
  };
  $$("[data-wrm]").forEach((b) => (b.onclick = async () => { await api(`/api/watch/channels/${b.dataset.wrm}`, { method: "DELETE" }); viewAuto(); }));
  $("#wNow").onclick = async () => {
    try { const r = await api("/api/watch/check", { method: "POST" }); toast(r.added ? `${r.added} new video(s) sent to Autopilot` : "No new GTA 6 videos yet"); loadActivity(); }
    catch (e) { toast(e.message, true); }
  };
  $("#cSave").onclick = () => save({ delete_source_after_auto: $("#cSrc").checked, delete_clip_after_upload: $("#cClip").checked,
    keep_days: Number($("#cDays").value) }, "Cleanup saved");
  $("#cAll").onclick = async () => {
    if (!confirm("Delete every downloaded source video? Your finished Shorts stay.")) return;
    const r = await api("/api/cleanup", { json: { all_sources: true } }); toast(`Freed ${(r.freed / 1e9).toFixed(2)} GB`); loadActivity();
  };
  loadActivity();
}

function gb(b) { return b >= 1e9 ? (b / 1e9).toFixed(1) + " GB" : (b / 1e6).toFixed(0) + " MB"; }

async function loadActivity() {
  const a = await api("/api/automation");
  const box = $("#activity"); if (!box) return;
  $("#store").textContent = `Using ${gb(a.storage.total)} · videos ${gb(a.storage.sources)} · Shorts ${gb(a.storage.clips)}`;
  $("#lastCheck").textContent = a.last_check ? `Last check ${new Date(a.last_check * 1000).toLocaleTimeString()}` : "";
  const icon = { ok: "✅", error: "❌", warn: "⚠️", info: "•" };
  box.innerHTML = a.activity.length ? a.activity.map((x) => `<div class="act ${x.level}">
      <span class="t">${new Date(x.t * 1000).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}</span>
      <span>${icon[x.level] || "•"} ${esc(x.msg)}${x.project_id ? ` <a href="#/p/${x.project_id}">open</a>` : ""}</span></div>`).join("")
    : `<p class="hint">Nothing yet.</p>`;
}

boot().catch((e) => { document.body.innerHTML = `<p style="padding:40px">App failed to start: ${esc(e.message)}</p>`; });

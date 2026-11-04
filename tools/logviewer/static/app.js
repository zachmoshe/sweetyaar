"use strict";

// SweetYaar log viewer. The server merges every fetched snapshot per device
// (tools/logviewer/history.py); this page draws the timeline, the charts and
// the log lines. Records are arrays:
// [realX, awakeX, boot, ms, name, area, level, text, badges], badges being
// [text, tone] pairs that translate codes and bit fields (decoders.py).
const R = { real: 0, awake: 1, boot: 2, ms: 3, name: 4, area: 5, level: 6, text: 7, badges: 8 };
const AREA_LABELS = { log: "Boot/log", main: "Main", ble: "BLE app", classic: "Classic BT",
                      power: "Power", playback: "Playback", ota: "Update" };
const STATE_LABELS = { playing_song: "Song", playing_animal: "Animal", bt_streaming: "BT audio",
                       killswitch: "Quiet time" };
const LEVEL_RANK = { info: 0, warn: 1, error: 2 };
const GUTTER = 156;
const ROW_HEIGHT = 18;

const $ = (id) => document.getElementById(id);
const state = {
  devices: [], data: null, mode: "real", view: null, cursor: null, hover: null,
  areas: new Set(Object.keys(AREA_LABELS)), level: "info", search: "", filtered: [],
  selectedRecord: null, tab: "stats", notes: [], source: recall("source") === "cloud" ? "cloud" : "folder",
  cores: new Map(),  // boot -> {text, bad, open, scroll}: decoded core dumps of the device shown
};

function css(name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }
function store(key, value) { try { localStorage.setItem("sylog." + key, value); } catch (e) { /* private mode */ } }
function recall(key) { try { return localStorage.getItem("sylog." + key); } catch (e) { return null; } }

// Every API call names the source: the log folder or the cloud uploads. A
// modal covers the page while any call is in flight.
let busyCalls = 0;
async function getJson(url, extra = "", busyText = "") {
  const separator = url.includes("?") ? "&" : "?";
  $("busy-text").textContent = busyText || `Reading ${state.source === "cloud" ? "the cloud uploads" : "the log folder"}…`;
  busyCalls += 1;
  $("busy").hidden = false;
  try {
    const response = await fetch(`${url}${separator}source=${state.source}${extra}`, { cache: "no-store" });
    const body = await response.json();
    if (!response.ok) throw new Error(body.error || response.statusText);
    return body;
  } finally {
    busyCalls -= 1;
    $("busy").hidden = busyCalls === 0;
  }
}

// --- Coordinates ------------------------------------------------------------

const recX = (record) => record[state.mode === "real" ? R.real : R.awake];
const bootX0 = (boot) => state.mode === "real" ? boot.realStart : boot.awakeStart;
const bootX1 = (boot) => bootX0(boot) + boot.duration;
const ivX0 = (iv) => state.mode === "real" ? iv.x0 : iv.xa0;
const ivX1 = (iv) => state.mode === "real" ? iv.x1 : iv.xa1;
const ptX = (point) => state.mode === "real" ? point.x : point.xa;

function fullRange() {
  const boots = state.data.boots;
  if (!boots.length) return [0, 60];
  const x0 = Math.min(...boots.map(bootX0));
  const x1 = Math.max(...boots.map(bootX1));
  const pad = Math.max(5, (x1 - x0) * 0.01);
  return [x0 - pad, x1 + pad];
}

// A device opens on its last 48 hours (of the current axis); Fit shows all.
const OPEN_SPAN_S = 48 * 3600;
function latestRange() {
  const [a, b] = fullRange();
  return [Math.max(a, b - OPEN_SPAN_S), b];
}

function plotWidth(canvas) { return Math.max(1, canvas.clientWidth - GUTTER - 12); }
function toPx(x) { const [a, b] = state.view; return GUTTER + (x - a) / (b - a) * plotWidth($("timeline")); }
function toX(px) { const [a, b] = state.view; return a + (px - GUTTER) / plotWidth($("timeline")) * (b - a); }

function bootOf(number) { return state.data.bootIndex.get(number); }
function wallKnown(boot) { return boot && boot.timeKnown && !state.data.relativeTime; }

function pad(n, width = 2) { return String(n).padStart(width, "0"); }
function wallText(x, withMs = true) {
  const d = new Date(x * 1000);  // local wall time stored as if UTC
  const text = `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())} ` +
               `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())}`;
  return withMs ? `${text}.${pad(d.getUTCMilliseconds(), 3)}` : text;
}
function uptimeText(ms) {
  const s = Math.floor(ms / 1000);
  return `+${Math.floor(s / 3600)}:${pad(Math.floor(s / 60) % 60)}:${pad(s % 60)}.${pad(ms % 1000, 3)}`;
}
function durationText(seconds) {
  if (seconds < 60) return `${seconds.toFixed(seconds < 10 ? 1 : 0)} s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min ${Math.round(seconds % 60)} s`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} h ${Math.round(seconds / 60 % 60)} min`;
  return `${(seconds / 86400).toFixed(1)} days`;
}
function recordTime(record) {
  const boot = bootOf(record[R.boot]);
  return wallKnown(boot) ? wallText(record[R.real]) : `B${record[R.boot]} ${uptimeText(record[R.ms])}`;
}

// --- Loading ----------------------------------------------------------------

// Devices are picked in the All devices table; the timeline shows the one
// picked last, if the source still has it.
async function loadDevices(reload = false) {
  const body = await getJson("/api/devices", reload ? "&reload=1" : "");
  state.devices = body.devices;
  $("source").textContent = `${body.directory}`;
  const current = state.data && state.devices.some((d) => d.device === state.data.device) ? state.data.device : null;
  if (!current) clearDevice();
  if (state.tab === "stats") return renderStats();
  if (current) return loadDevice(current);
  showNotice(noDeviceText());
}

function noDeviceText() {
  if (state.devices.length) return "Pick a device in the table.";
  return state.source === "cloud" ? "No toy has uploaded logs yet."
    : "No fetched logs in the log folder. Run make fetch-logs, then Reload.";
}

function clearDevice() {
  state.data = null;
  state.notes = [];
  $("note-editor").hidden = true;
  $("cards").innerHTML = "";
  $("snapshots").innerHTML = "";
  state.cores = new Map();
  $("device-label").textContent = "";
  state.filtered = logRows = [];
  for (const row of $("log").querySelectorAll(".row")) row.remove();
  $("log-spacer").style.height = "0px";
  $("count").textContent = "";
  history.replaceState(null, "", location.pathname);
  draw();
}

async function loadDevice(id) {
  const data = await getJson(`/api/device?id=${encodeURIComponent(id)}`);
  data.device = id;
  await loadNotes(id);
  const listed = state.devices.find((d) => d.device === id);
  $("device-label").textContent = listed ? `${listed.name || "(unnamed)"} · ${id}` : id;
  data.bootIndex = new Map(data.boots.map((boot) => [boot.boot, boot]));
  data.charts = buildCharts(data);
  state.data = data;
  state.selectedRecord = null;
  state.cursor = null;
  history.replaceState(null, "", `#device=${encodeURIComponent(id)}`);
  state.view = latestRange();
  renderCards();
  renderSnapshots();
  state.cores = new Map();
  showNotice(data.relativeTime
    ? "No boot in this history has a clock (the parent app never synced it), so real time is estimated: boots are placed one minute apart." : "");
  applyFilters();
  draw();
  state.logToEnd = true;
  scrollLogToEnd();
}

// The log of a newly opened device starts at its latest line, once visible.
function scrollLogToEnd() {
  if (!state.logToEnd || $("timeline-view").hidden) return;
  state.logToEnd = false;
  $("log").scrollTop = $("log").scrollHeight;
  paintLog();
}

function showNotice(text) { $("notice").hidden = !text; $("notice").textContent = text; }

// --- Summary ----------------------------------------------------------------

function card(label, value, sub = "", bad = false) {
  return `<div class="card"><div class="label">${label}</div><div class="value${bad ? " bad" : ""}">${value}</div>` +
         (sub ? `<div class="sub">${sub}</div>` : "") + "</div>";
}

function renderCards() {
  const s = state.data.summary;
  const drain = (d) => d.mvPerHour === null ? "—" : `${d.mvPerHour} mV/h`;
  const span = s.firstTime !== null ? `${wallText(s.firstTime, false).slice(0, 10)} → ${wallText(s.lastTime, false).slice(0, 10)}` : "";
  $("cards").innerHTML = [
    card("Boots", s.boots, `B${s.firstBoot}–B${s.lastBoot}, ${s.snapshots} fetch${s.snapshots === 1 ? "" : "es"}`),
    card("Abnormal resets", s.abnormalResets, `${s.crashes} with crash record`, s.abnormalResets > 0),
    card("Awake", `${s.awakeHours} h`, span),
    card("Local playback", `${s.localHours} h`, `${s.songsStarted} songs, ${s.animalsStarted} animals`),
    card("Bluetooth audio", `${s.btHours} h`),
    card("Drain playing", drain(s.drain.playing), `${s.drain.playing.hours} h measured`),
    card("Drain idle", drain(s.drain.idle), `${s.drain.idle.hours} h measured`),
    card("Warnings / errors", `${s.warnings} / ${s.errors}`, `${s.records} records`, s.errors > 0),
    card("Firmware history", s.firmware.join(" → ") || "—",
         s.installs ? `${s.installs} installation${s.installs === 1 ? "" : "s"}` : ""),
  ].join("");
}

// Core dumps the toy copied into its log after a crash. Their chunk records
// are left out of the log list; the "Core dump copied" line (or the start
// line, when the end was overwritten) carries Download and Decode, and the
// decoded report opens under it.
const CORE_TEXT_HEIGHT = 380;

function coreOf(record) {
  const name = record[R.name];
  if (name !== "COREDUMP_END" && name !== "COREDUMP_BEGIN") return null;
  const core = (state.data.coreDumps || []).find((item) => item.boot === record[R.boot]);
  if (!core) return null;
  const ended = state.data.records.some((other) => other[R.boot] === core.boot && other[R.name] === "COREDUMP_END");
  return (name === "COREDUMP_END") === ended ? core : null;
}

function coreActions(core) {
  const line = document.createElement("div");
  line.className = "core-actions";
  if (!core.complete) {
    line.innerHTML = `<span class="badge bad">incomplete: part of it was overwritten</span>`;
    return line;
  }
  const shown = state.cores.get(core.boot);
  const link = `/api/core?id=${encodeURIComponent(state.data.device)}&boot=${core.boot}&source=${state.source}`;
  line.innerHTML = `<button data-decode="${core.boot}">${shown && shown.open ? "Hide" : "Decode"}</button>` +
    `<a href="${link}" download>Download .bin</a>` +
    `<span class="muted">firmware ${escapeHtml(core.firmware || "unknown")} · ${(core.size / 1024).toFixed(1)} KB</span>`;
  return line;
}

async function decodeCore(boot) {
  const shown = state.cores.get(boot);
  if (shown) {
    shown.open = !shown.open;
  } else {
    try {
      const body = await getJson(`/api/core/decode?id=${encodeURIComponent(state.data.device)}&boot=${boot}`, "",
                                 "Decoding the core dump (the first time downloads its firmware's ELF)…");
      state.cores.set(boot, { text: body.text, bad: false, open: true, scroll: 0 });
    } catch (error) {
      state.cores.set(boot, { text: error.message, bad: true, open: true, scroll: 0 });
    }
  }
  const top = $("log").scrollTop;
  renderLog();
  $("log").scrollTop = top;
}

function renderSnapshots() {
  const rows = state.data.snapshots.map((snap) =>
    `<tr><td>${snap.file}</td><td>${snap.fetched.replace("T", " ")}</td><td>${snap.records} records</td>` +
    `<td>${snap.sectors} sectors${snap.sequence ? `, sequence ${snap.sequence[0]}–${snap.sequence[1]}` : ""}</td>` +
    `<td>${snap.problems.join("; ")}</td></tr>`).join("");
  $("snapshots").innerHTML = `<table><tr><th>File</th><th>Fetched</th><th></th><th></th><th>Problems</th></tr>${rows}</table>`;
}

// --- Charts data ------------------------------------------------------------

function buildCharts(data) {
  const battery = data.telemetry.filter((p) => p.battery);
  // The cell's whole range (3.0-4.2 V), widened only by readings outside it.
  const mv = battery.map((p) => p.battery);
  const bMin = Math.min(3000, ...mv), bMax = Math.max(4200, ...mv);
  // Up to 25 KB (free heap after boot), widened by larger readings.
  const heapMax = Math.max(25000, ...data.telemetry.map((p) => p.free));
  return {
    battery: { min: bMin, max: bMax, hasData: battery.length > 0 },
    heap: { min: 0, max: heapMax },
  };
}

// --- Timeline drawing -------------------------------------------------------

function lanes() {
  // Lanes of one section share a background; sections alternate and have a
  // separator line. Charts carry a legend in the left margin.
  const areaRows = Object.keys(AREA_LABELS).map((area) => ({ id: "area:" + area, label: AREA_LABELS[area], h: 13,
                                                              area, section: "events" }));
  return [
    { id: "notes", label: "Notes", h: 22, section: "axis" },
    { id: "axis", label: "", h: 26, section: "axis" },
    { id: "boots", label: "Boots", h: 28, section: "boots" },
    { id: "firmware", label: "Firmware", h: 18, section: "boots" },
    { id: "state", label: "Playing", h: 20, section: "activity" },
    { id: "ble", label: "App session", h: 16, section: "activity" },
    { id: "classic", label: "Phone (A2DP)", h: 16, section: "activity" },
    { id: "events", label: "Events by area", h: 18, heading: true, section: "events" },
    ...areaRows,
    { id: "events-end", label: "", h: 4, section: "events" },
    { id: "battery", label: "Battery", h: 124, chart: true, section: "battery",
      legend: [["--battery", "line", "voltage, mV"], ["--charging-key", "box", "charging"]] },
    { id: "volume", label: "Volume", h: 68, chart: true, section: "volume",
      legend: [["--volume", "line", "effective, %"]] },
    { id: "heap", label: "Heap", h: 116, chart: true, section: "heap",
      legend: [["--heap", "line", "free now"], ["--heap-largest", "line", "largest free block"],
               ["--heap-min", "dash", "lowest since boot"]] },
  ];
}

function layout() {
  let y = 0;
  return lanes().map((lane) => { const placed = { ...lane, y }; y += lane.h; return placed; });
}

function laneAt(py) { return layout().find((lane) => py >= lane.y && py < lane.y + lane.h); }

function draw() {
  const canvas = $("timeline");
  const ratio = window.devicePixelRatio || 1;
  const width = canvas.clientWidth;
  const placed = layout();
  const height = placed[placed.length - 1].y + placed[placed.length - 1].h + 4;
  canvas.style.height = height + "px";
  canvas.width = width * ratio;
  canvas.height = height * ratio;
  const ctx = canvas.getContext("2d");
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  ctx.clearRect(0, 0, width, height);
  if (!state.data) return;
  ctx.font = "11px -apple-system, BlinkMacSystemFont, sans-serif";
  ctx.textBaseline = "middle";

  const right = GUTTER + plotWidth(canvas);
  drawSections(ctx, placed, width);
  for (const lane of placed) {
    if (!lane.label) continue;
    const bold = lane.heading || lane.chart;
    ctx.fillStyle = css(bold ? "--text" : "--muted");
    ctx.font = `${bold ? "600 " : ""}11px -apple-system, BlinkMacSystemFont, sans-serif`;
    ctx.fillText(lane.label, lane.area ? 16 : 8, lane.chart ? lane.y + 11 : lane.y + lane.h / 2);
    ctx.font = "11px -apple-system, BlinkMacSystemFont, sans-serif";
    (lane.legend || []).forEach(([color, kind, text], index) => {
      const y = lane.y + 26 + index * 14;
      ctx.fillStyle = css(color);
      if (kind === "line") ctx.fillRect(8, y - 1, 14, 2.5);
      else if (kind === "dash") { ctx.fillRect(8, y - 1, 5, 2.5); ctx.fillRect(17, y - 1, 5, 2.5); }
      else ctx.fillRect(8, y - 5, 14, 10);
      ctx.fillStyle = css("--muted");
      ctx.fillText(text, 27, y);
    });
  }
  ctx.font = "11px -apple-system, BlinkMacSystemFont, sans-serif";
  const axis = placed.find((l) => l.id === "axis");
  drawUnknownTime(ctx, axis, right);
  drawAxis(ctx, axis, height, right);
  ctx.save();
  ctx.beginPath();
  ctx.rect(GUTTER, 0, right - GUTTER, height);
  ctx.clip();
  const lane = (id) => placed.find((l) => l.id === id);
  drawFirmware(ctx, lane("firmware"), height);
  drawBoots(ctx, lane("boots"));
  drawIntervals(ctx, lane("state"), "state");
  drawIntervals(ctx, lane("ble"), "ble");
  drawIntervals(ctx, lane("classic"), "classic");
  drawEvents(ctx, placed.filter((l) => l.area));
  drawBattery(ctx, lane("battery"));
  drawVolume(ctx, lane("volume"));
  drawHeap(ctx, lane("heap"));
  if (state.cursor !== null) {
    const px = toPx(state.cursor);
    ctx.strokeStyle = css("--cursor");
    ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(px + 0.5, 0); ctx.lineTo(px + 0.5, height); ctx.stroke();
  }
  if (drag && (drag.select || drag.note)) {
    ctx.fillStyle = css("--select");
    ctx.fillRect(Math.min(drag.startPx, drag.lastPx), 0, Math.abs(drag.lastPx - drag.startPx), height);
  }
  ctx.restore();
  drawScaleLabels(ctx);
  drawNotes(ctx, placed.find((l) => l.id === "notes"), axis, height, right);
  drawHover(ctx, axis, height, right);
}

// A faint line under the pointer, with its time in the axis lane.
function drawHover(ctx, axis, height, right) {
  if (state.hover === null || drag) return;
  const px = Math.round(toPx(state.hover)) + 0.5;
  if (px < GUTTER || px > right) return;
  ctx.save();
  ctx.strokeStyle = css("--muted");
  ctx.globalAlpha = 0.7;
  ctx.setLineDash([3, 3]);
  ctx.beginPath(); ctx.moveTo(px, 0); ctx.lineTo(px, height); ctx.stroke();
  ctx.restore();
  const text = hoverTime(state.hover);
  const width = ctx.measureText(text).width + 10;
  const left = px + 4 + width > right ? px - 4 - width : px + 4;
  ctx.fillStyle = css("--text");
  ctx.fillRect(left, axis.y + 4, width, axis.h - 8);
  ctx.fillStyle = css("--bg");
  ctx.fillText(text, left + 5, axis.y + axis.h / 2);
}

// --- Notes ------------------------------------------------------------------
// The developer's own comments on a moment or a range (tools/logviewer/notes.py).
// Their ends are {boot, ms}, so they follow the boot on either axis.

function noteX(end) {
  const boot = bootOf(end.boot);
  if (!boot) return null;
  const x = bootX0(boot) + (end.ms - boot.startMs) / 1000;
  return state.mode === "awake" ? Math.min(Math.max(x, bootX0(boot)), bootX1(boot)) : x;
}

// The boot running at |x| (the longest, if estimated starts make them
// overlap: a short boot can appear to start a moment inside the next one);
// between boots, the one that started nearest before |x| (the earliest one
// before them all). Boots are in number order, which estimated times need not
// follow.
function noteEnd(x) {
  const boots = state.data.boots;
  const running = boots.filter((b) => bootX0(b) <= x && x <= bootX1(b));
  let boot = running.length ? running.reduce((a, b) => b.duration > a.duration ? b : a) : null;
  if (!boot) {
    boot = boots.reduce((a, b) => bootX0(b) < bootX0(a) ? b : a);
    for (const candidate of boots) if (bootX0(candidate) <= x && bootX0(candidate) > bootX0(boot)) boot = candidate;
  }
  if (state.mode === "awake") x = Math.min(x, bootX1(boot));
  return { boot: boot.boot, ms: Math.round(boot.startMs + (x - bootX0(boot)) * 1000) };
}

function noteTime(end) {
  const boot = bootOf(end.boot);
  if (!boot) return `B${end.boot} ${uptimeText(end.ms)}`;
  return wallKnown(boot) ? wallText(boot.realStart + (end.ms - boot.startMs) / 1000, false)
                         : `B${end.boot} ${uptimeText(end.ms)}`;
}

function noteSpan(note) {
  return note.end ? `${noteTime(note.start)} → ${noteTime(note.end)}` : noteTime(note.start);
}

function fitText(ctx, text, width) {
  text = text.replace(/\s+/g, " ").trim();
  if (width < 12) return "";
  if (ctx.measureText(text).width <= width) return text;
  let lo = 0, hi = text.length;
  while (lo < hi) { const mid = (lo + hi + 1) >> 1; if (ctx.measureText(text.slice(0, mid) + "…").width <= width) lo = mid; else hi = mid - 1; }
  return lo ? text.slice(0, lo) + "…" : "";
}

// Where each note was drawn, for hovering and clicking.
let noteBoxes = [];
function drawNotes(ctx, lane, axis, height, right) {
  noteBoxes = [];
  const placed = state.notes.map((note) => ({ note, x0: noteX(note.start), x1: note.end ? noteX(note.end) : null }))
    .filter((p) => p.x0 !== null).sort((a, b) => a.x0 - b.x0);
  const accent = css("--note");
  ctx.save();
  ctx.beginPath();
  ctx.rect(GUTTER, 0, right - GUTTER, height);
  ctx.clip();
  placed.forEach((p, i) => {
    const px0 = toPx(p.x0), px1 = p.x1 === null ? px0 : Math.max(px0 + 2, toPx(p.x1));
    const next = placed[i + 1] ? toPx(placed[i + 1].x0) : right;
    if (px1 < GUTTER - 200 || px0 > right) return;
    const top = lane.y + 3, h = lane.h - 6;
    // A faint band or line through every lane below.
    ctx.globalAlpha = 0.08;
    ctx.fillStyle = accent;
    if (p.x1 !== null) ctx.fillRect(px0, axis.y, px1 - px0, height - axis.y);
    ctx.globalAlpha = 0.5;
    if (p.x1 === null) ctx.fillRect(Math.round(px0), axis.y, 1, height - axis.y);
    let textLeft;
    if (p.x1 !== null) {
      ctx.globalAlpha = 0.3;
      ctx.fillRect(px0, top, px1 - px0, h);
      ctx.globalAlpha = 1;
      ctx.fillRect(px0, top, 2, h);
      ctx.fillRect(px1 - 2, top, 2, h);
      textLeft = px0 + 5;
    } else {
      ctx.globalAlpha = 1;
      ctx.beginPath();  // a flag: pole and pennant
      ctx.fillRect(Math.round(px0), top, 1.5, h);
      ctx.moveTo(px0 + 1.5, top); ctx.lineTo(px0 + 8, top + 3.5); ctx.lineTo(px0 + 1.5, top + 7); ctx.fill();
      textLeft = px0 + 10;
    }
    const room = Math.max(px1 - 4, next - 6) - textLeft;
    const text = fitText(ctx, p.note.text, room);
    ctx.fillStyle = css("--text");
    ctx.fillText(text, textLeft, lane.y + lane.h / 2);
    noteBoxes.push({ note: p.note, px0: px0 - 3, px1: Math.max(px1, textLeft + ctx.measureText(text).width) + 3 });
  });
  ctx.restore();
}

async function loadNotes(device) {
  state.notes = await getJson(`/api/notes?device=${encodeURIComponent(device)}`);
}

async function saveNotes(notes) {
  const device = state.data.device;
  const response = await fetch(`/api/notes?device=${encodeURIComponent(device)}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(notes) });
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || response.statusText);
  if (state.data && state.data.device === device) { state.notes = body; draw(); }
}

// The editor opens at the pointer, for a new note ({start, end}) or an existing one.
function editNote(note, clientX, clientY) {
  const editor = $("note-editor");
  $("note-when").textContent = noteSpan(note);
  $("note-text").value = note.text || "";
  $("note-delete").hidden = !note.id;
  editor.hidden = false;
  editor.style.left = `${Math.max(8, Math.min(clientX, window.innerWidth - editor.offsetWidth - 8))}px`;
  editor.style.top = `${Math.max(8, Math.min(clientY + 12, window.innerHeight - editor.offsetHeight - 8))}px`;
  $("note-text").focus();
  const close = () => { editor.hidden = true; editor.onsubmit = null; $("note-delete").onclick = null; };
  const others = state.notes.filter((n) => n.id !== note.id);
  editor.onsubmit = (e) => {
    e.preventDefault();
    const text = $("note-text").value.trim();
    if (!text) return;
    const id = note.id || `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;
    close();
    saveNotes([...others, { ...note, id, text }]).catch(showError);
  };
  $("note-delete").onclick = () => { close(); saveNotes(others).catch(showError); };
  $("note-cancel").onclick = close;
}

function hoverTime(x) {
  if (state.mode === "awake") return `awake ${durationLabel(x, 1)}`;
  if (state.data.relativeTime) return `≈ ${durationLabel(x - (state.data.boots[0]?.realStart || 0), 1)}`;
  const text = wallText(x, false);
  // Inside a boot whose clock was never set, the time is a guess.
  return unknownTimeSpans().some(([x0, x1]) => x >= x0 && x <= x1) ? `≈ ${text}` : text;
}

function drawSections(ctx, placed, width) {
  let index = -1;
  placed.forEach((lane, position) => {
    const first = position === 0 || placed[position - 1].section !== lane.section;
    if (first) index += 1;
    if (index % 2 === 1) {
      ctx.fillStyle = css("--band");
      ctx.fillRect(0, lane.y, width, lane.h);
    }
    if (first && index > 0) {
      ctx.fillStyle = css("--line-strong");
      ctx.fillRect(0, lane.y, width, 1.5);
    }
  });
}

// Real time: stripe the time axis where its times are a guess (boots before
// the first clock sync, placed one after another), up to the next dated boot.
// Only the axis: the events and their order are still exact.
function unknownTimeSpans() {
  if (state.mode !== "real" || state.data.relativeTime) return [];
  const spans = [];
  let start = null;
  for (const boot of state.data.boots) {
    if (!wallKnown(boot)) { if (start === null) start = bootX0(boot); continue; }
    if (start !== null) { spans.push([start, bootX0(boot)]); start = null; }
  }
  const last = state.data.boots[state.data.boots.length - 1];
  if (start !== null) spans.push([start, bootX1(last)]);
  return spans;
}

let stripes = null;
function drawUnknownTime(ctx, lane, right) {
  const spans = unknownTimeSpans();
  if (!spans.length) return;
  if (!stripes || stripes.color !== css("--unknown")) {
    const tile = document.createElement("canvas");
    tile.width = tile.height = 10;
    const t = tile.getContext("2d");
    t.strokeStyle = css("--unknown");
    t.globalAlpha = 0.35;
    t.lineWidth = 2;
    t.beginPath();
    t.moveTo(-2, 12); t.lineTo(12, -2);   // one diagonal plus the corners, so tiles join
    t.moveTo(-2, 2); t.lineTo(2, -2);
    t.moveTo(8, 12); t.lineTo(12, 8);
    t.stroke();
    stripes = { color: css("--unknown"), pattern: ctx.createPattern(tile, "repeat") };
  }
  ctx.fillStyle = stripes.pattern;
  for (const [x0, x1] of spans) {
    const px0 = Math.max(GUTTER, toPx(x0)), px1 = Math.min(right, toPx(x1));
    if (px1 > px0) ctx.fillRect(px0, lane.y, px1 - px0, lane.h);
  }
}

function niceStep(span, target, units) {
  const raw = span / target;
  return units.find((u) => u >= raw) || units[units.length - 1];
}

function drawAxis(ctx, lane, height, right) {
  const [a, b] = state.view;
  const relative = state.mode === "awake" || state.data.relativeTime;
  const units = [1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600, 7200, 10800, 21600, 43200, 86400,
                 172800, 604800, 2592000];
  const step = niceStep(b - a, Math.max(2, plotWidth($("timeline")) / 110), units);
  const origin = relative ? (state.mode === "awake" ? 0 : state.data.boots[0]?.realStart || 0) : 0;
  ctx.fillStyle = css("--muted");
  ctx.strokeStyle = css("--grid");
  ctx.lineWidth = 1;
  for (let t = Math.ceil((a - origin) / step) * step + origin; t <= b; t += step) {
    const px = Math.round(toPx(t)) + 0.5;
    if (px < GUTTER || px > right) continue;
    ctx.beginPath(); ctx.moveTo(px, lane.y + lane.h); ctx.lineTo(px, height); ctx.stroke();
    let label;
    if (relative) {
      label = durationLabel(t - origin, step);
    } else {
      const full = wallText(t, false);
      label = step >= 86400 ? full.slice(5, 10) : step >= 3600 ? full.slice(5, 16) : full.slice(11, step < 60 ? 19 : 16);
    }
    ctx.fillText(label, px + 3, lane.y + lane.h / 2);
  }
  ctx.fillText(state.mode === "awake" ? "awake time" : relative ? "estimated" : "local time", 8, lane.y + lane.h / 2);
}

function durationLabel(seconds, step) {
  const h = Math.floor(seconds / 3600), m = Math.floor(seconds / 60) % 60, s = Math.round(seconds % 60);
  if (step >= 3600) return `${h} h`;
  if (step >= 60) return `${h}:${pad(m)}`;
  return `${h}:${pad(m)}:${pad(s)}`;
}

function bootColor(boot) {
  if (boot.abnormal) return css("--boot-bad");
  if (boot.reset === "deep-sleep") return css("--boot");
  return css("--boot-cold");
}

function drawBoots(ctx, lane) {
  const top = lane.y + 4, h = lane.h - 8;
  const boots = state.data.boots;
  // Sleep between a boot that entered deep sleep and its wake (real time only).
  if (state.mode === "real") {
    ctx.strokeStyle = css("--boot");
    ctx.setLineDash([2, 3]);
    for (let i = 0; i + 1 < boots.length; i++) {
      if (!boots[i].sleep || boots[i + 1].reset !== "deep-sleep") continue;
      const y = top + h / 2 + 0.5;
      ctx.beginPath(); ctx.moveTo(toPx(bootX1(boots[i])), y); ctx.lineTo(toPx(bootX0(boots[i + 1])), y); ctx.stroke();
    }
    ctx.setLineDash([]);
  }
  for (const boot of boots) {
    const x0 = toPx(bootX0(boot)), x1 = Math.max(x0 + 2, toPx(bootX1(boot)));
    if (x1 < GUTTER || x0 > GUTTER + plotWidth($("timeline"))) continue;
    ctx.fillStyle = bootColor(boot);
    ctx.globalAlpha = state.mode === "real" && !wallKnown(boot) && !state.data.relativeTime ? 0.45 : 1;
    ctx.fillRect(x0, top, x1 - x0, h);
    ctx.globalAlpha = 1;
    if (boot.startOverwritten) {
      ctx.fillStyle = css("--unknown");
      ctx.fillRect(x0, top, 3, h);
    }
    if (x1 - x0 > 30) {
      ctx.fillStyle = "#fff";
      ctx.fillText(`B${boot.boot}`, Math.max(x0, GUTTER) + 4, top + h / 2);
    }
    if (boot.crashedInto !== undefined) drawCross(ctx, x1, top + h / 2, css("--error"));
  }
}

// Runs of consecutive boots on the same installation: version and app slot
// (an update over BLE always switches slot, so a reinstall starts a new run).
// A boot whose BOOT record was overwritten joins the run around it.
function firmwareRuns() {
  const runs = [];
  for (const boot of state.data.boots) {
    const version = boot.firmware, slot = boot.slot;
    const last = runs[runs.length - 1];
    if (last && (version === null || (version === last.version && slot === last.slot))) { last.boots.push(boot); continue; }
    if (last && last.version === null) { Object.assign(last, { version, slot }); last.boots.push(boot); continue; }
    runs.push({ version, slot, boots: [boot] });
  }
  return runs;
}

function drawFirmware(ctx, lane, height) {
  const palette = [css("--fw0"), css("--fw1"), css("--fw2"), css("--fw3")];
  const versions = [];
  const runs = firmwareRuns();
  runs.forEach((run, index) => {
    if (!versions.includes(run.version)) versions.push(run.version);
    const x0 = toPx(bootX0(run.boots[0]));
    const next = runs[index + 1];
    const x1 = next ? toPx(bootX0(next.boots[0])) : Math.max(x0 + 2, toPx(bootX1(run.boots[run.boots.length - 1])));
    ctx.fillStyle = run.version === null ? css("--unknown") : palette[versions.indexOf(run.version) % palette.length];
    ctx.fillRect(x0, lane.y + 2, x1 - x0 - 1, lane.h - 4);
    if (x1 - x0 > 40) {
      ctx.fillStyle = "#fff";
      ctx.fillText(run.version ?? "?", Math.max(x0, GUTTER) + 4, lane.y + lane.h / 2);
    }
    if (index > 0) {
      // A version change: dashed line across every lane.
      ctx.strokeStyle = css("--accent");
      ctx.setLineDash([4, 4]);
      ctx.beginPath(); ctx.moveTo(Math.round(x0) + 0.5, 0); ctx.lineTo(Math.round(x0) + 0.5, height); ctx.stroke();
      ctx.setLineDash([]);
    }
  });
}

function drawCross(ctx, x, y, color) {
  ctx.strokeStyle = color;
  ctx.lineWidth = 2.5;
  ctx.beginPath();
  ctx.moveTo(x - 5, y - 5); ctx.lineTo(x + 5, y + 5);
  ctx.moveTo(x + 5, y - 5); ctx.lineTo(x - 5, y + 5);
  ctx.stroke();
  ctx.lineWidth = 1;
}

function intervalColor(iv) {
  if (iv.lane === "ble") return css("--ble");
  if (iv.lane === "classic") return css("--classic");
  return css({ playing_song: "--song", playing_animal: "--animal", bt_streaming: "--stream" }[iv.kind] || "--kill");
}

function drawIntervals(ctx, lane, kind) {
  for (const iv of state.data.intervals) {
    if (iv.lane !== kind) continue;
    const x0 = toPx(ivX0(iv)), x1 = Math.max(x0 + 2, toPx(ivX1(iv)));
    ctx.fillStyle = intervalColor(iv);
    ctx.fillRect(x0, lane.y + 3, x1 - x0, lane.h - 6);
  }
}

function drawEvents(ctx, rows) {
  // One mark per pixel column and area, colored by its most severe record.
  const width = Math.ceil(plotWidth($("timeline")));
  const byArea = new Map(rows.map((row) => [row.area, new Int8Array(width + 1).fill(-1)]));
  const [a, b] = state.view;
  for (const record of state.data.records) {
    const x = recX(record);
    if (x < a || x > b) continue;
    const column = Math.round((x - a) / (b - a) * width);
    const cells = byArea.get(record[R.area]);
    const rank = LEVEL_RANK[record[R.level]];
    if (cells && rank > cells[column]) cells[column] = rank;
  }
  const colors = [css("--info"), css("--warn"), css("--error")];
  for (const row of rows) {
    ctx.fillStyle = css("--grid");
    ctx.fillRect(GUTTER, row.y + row.h - 1, width, 1);
    const cells = byArea.get(row.area);
    for (let column = 0; column <= width; column++) {
      if (cells[column] < 0) continue;
      ctx.fillStyle = colors[cells[column]];
      const tall = cells[column] > 0 ? 0 : 2;
      ctx.fillRect(GUTTER + column - (cells[column] > 0 ? 1 : 0), row.y + 1 + tall, cells[column] > 0 ? 3 : 2, row.h - 3 - tall);
    }
  }
  // A repeating condition: a bar from its stored record to its last repeat.
  const rowOf = new Map(rows.map((row) => [row.area, row]));
  for (const span of state.data.repeats || []) {
    const row = rowOf.get(span.area);
    const x0 = state.mode === "real" ? span.x0 : span.xa0, x1 = state.mode === "real" ? span.x1 : span.xa1;
    if (!row || x1 < a || x0 > b) continue;
    ctx.fillStyle = colors[LEVEL_RANK[span.level]] || colors[1];
    ctx.globalAlpha = 0.6;
    ctx.fillRect(toPx(x0), row.y + row.h / 2 - 1.5, Math.max(2, toPx(x1) - toPx(x0)), 3);
    ctx.globalAlpha = 1;
  }
}

const CHART_INSET = 16;  // px between a chart's plot and its lane edges
function yScale(lane, min, max) { return (value) => lane.y + lane.h - CHART_INSET - (value - min) / (max - min) * (lane.h - 2 * CHART_INSET); }

function drawSeries(ctx, points, valueOf, y, color, dash = []) {
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.5;
  ctx.setLineDash(dash);
  ctx.beginPath();
  let previous = null;
  for (const point of points) {
    const value = valueOf(point);
    if (value === null || value === undefined) { previous = null; continue; }
    const px = toPx(ptX(point)), py = y(value);
    if (previous && previous.boot === point.boot) ctx.lineTo(px, py); else ctx.moveTo(px, py);
    previous = point;
  }
  ctx.stroke();
  ctx.setLineDash([]);
  ctx.lineWidth = 1;
  for (const point of points) {
    const value = valueOf(point);
    if (value === null || value === undefined) continue;
    ctx.fillStyle = color;
    ctx.fillRect(toPx(ptX(point)) - 1.5, y(value) - 1.5, 3, 3);
  }
}

// Scale labels sit in the left margin, right-aligned against the plot; the
// optional gridlines are faint so they never read as data.
// Grey dashed lines at `ticks`; only the values in `labels` get a scale label.
function drawGrid(ctx, lane, min, max, ticks, format, labels = ticks) {
  const y = yScale(lane, min, max);
  ctx.save();
  ctx.strokeStyle = css("--muted");
  ctx.globalAlpha = 0.5;
  ctx.setLineDash([3, 3]);
  ctx.lineWidth = 1;
  for (const tick of ticks) {
    const ty = Math.round(y(tick)) + 0.5;
    ctx.beginPath();
    ctx.moveTo(GUTTER, ty);
    ctx.lineTo(GUTTER + plotWidth($("timeline")), ty);
    ctx.stroke();
    if (labels.includes(tick)) scaleLabels.push([format(tick), y(tick)]);
  }
  ctx.restore();
}

// Collected while the plot is clipped, drawn in the margin afterwards.
let scaleLabels = [];
function drawScaleLabels(ctx) {
  ctx.fillStyle = css("--muted");
  ctx.textAlign = "right";
  for (const [text, y] of scaleLabels) ctx.fillText(text, GUTTER - 6, y);
  ctx.textAlign = "left";
  scaleLabels = [];
}

function drawBattery(ctx, lane) {
  const telemetry = state.data.telemetry;
  const { min, max, hasData } = state.data.charts.battery;
  const y = yScale(lane, min, max);
  ctx.fillStyle = css("--charging");
  for (let i = 0; i + 1 < telemetry.length; i++) {
    if (telemetry[i].charger === 4 && telemetry[i + 1].boot === telemetry[i].boot) {
      const x0 = toPx(ptX(telemetry[i])), x1 = toPx(ptX(telemetry[i + 1]));
      ctx.fillRect(x0, lane.y, x1 - x0, lane.h);
    }
  }
  drawGrid(ctx, lane, min, max, [3000, 3400, 3800, 4200], (v) => `${v}`);
  if (!hasData) {
    ctx.fillStyle = css("--muted");
    ctx.fillText("No valid battery readings (charger only or ADC invalid)", GUTTER + 60, lane.y + lane.h / 2);
    return;
  }
  drawSeries(ctx, telemetry, (p) => p.battery, y, css("--battery"));
}

function drawVolume(ctx, lane) {
  const y = yScale(lane, 0, 100);
  drawGrid(ctx, lane, 0, 100, [0, 50, 100], (v) => `${v}%`);
  drawSeries(ctx, state.data.telemetry, (p) => p.volume, y, css("--volume"));
}

function drawHeap(ctx, lane) {
  const { min, max } = state.data.charts.heap;
  const y = yScale(lane, min, max);
  drawGrid(ctx, lane, min, max, [0, 5000, 10000, 15000, 20000, 25000],
           (v) => `${v / 1000} KB`, [0, 10000, 20000]);
  drawSeries(ctx, state.data.telemetry, (p) => p.minFree, y, css("--heap-min"), [4, 3]);
  drawSeries(ctx, state.data.telemetry, (p) => p.largest, y, css("--heap-largest"));
  drawSeries(ctx, state.data.telemetry, (p) => p.free, y, css("--heap"));
}

function range(start, stop, step) { const out = []; for (let v = start; v <= stop; v += step) out.push(v); return out; }

// --- Hover and click --------------------------------------------------------

function hitTest(px, py) {
  const lane = laneAt(py);
  if (!lane || px < GUTTER || !state.data) return null;
  const x = toX(px);
  const slack = (toX(px + 6) - toX(px));
  const data = state.data;
  if (lane.id === "notes") {
    const box = noteBoxes.find((b) => px >= b.px0 && px <= b.px1);
    return box ? { kind: "note", note: box.note } : null;
  }
  if (lane.id === "axis") {
    const span = unknownTimeSpans().find(([x0, x1]) => x >= x0 && x <= x1);
    return span ? { kind: "unknownTime", span } : null;
  }
  if (lane.id === "boots") {
    const crashed = data.boots.find((b) => b.crashedInto !== undefined && Math.abs(bootX1(b) - x) <= slack);
    if (crashed) return { kind: "crash", boot: crashed };
    const boot = data.boots.find((b) => x >= bootX0(b) - slack && x <= bootX1(b) + slack);
    return boot ? { kind: "boot", boot } : null;
  }
  if (lane.id === "firmware") {
    const runs = firmwareRuns();
    const index = runs.findIndex((run, i) => x >= bootX0(run.boots[0]) - slack &&
      x <= (runs[i + 1] ? bootX0(runs[i + 1].boots[0]) : bootX1(run.boots[run.boots.length - 1])) + slack);
    return index >= 0 ? { kind: "firmware", run: runs[index], previous: runs[index - 1] } : null;
  }
  if (["state", "ble", "classic"].includes(lane.id)) {
    const iv = data.intervals.find((i) => i.lane === lane.id && x >= ivX0(i) - slack && x <= ivX1(i) + slack);
    return iv ? { kind: "interval", iv } : null;
  }
  if (lane.area) {
    let best = null, bestDistance = slack;
    for (const record of data.records) {
      if (record[R.area] !== lane.area) continue;
      const distance = Math.abs(recX(record) - x);
      if (distance <= bestDistance && (!best || distance < bestDistance || LEVEL_RANK[record[R.level]] > LEVEL_RANK[best[R.level]])) {
        best = record; bestDistance = distance;
      }
    }
    return best ? { kind: "record", record: best } : null;
  }
  if (["battery", "volume", "heap"].includes(lane.id)) {
    let best = null, bestDistance = slack * 2;
    for (const point of data.telemetry) {
      const distance = Math.abs(ptX(point) - x);
      if (distance < bestDistance) { best = point; bestDistance = distance; }
    }
    return best ? { kind: "telemetry", point: best } : null;
  }
  return null;
}

function describeHit(hit) {
  const data = state.data;
  if (hit.kind === "note") return `${noteSpan(hit.note)}\n${hit.note.text}\nclick to edit`;
  if (hit.kind === "unknownTime") {
    return "Time unknown: clock not set.\nBoots placed 60 s apart; axis times are a guess.";
  }
  if (hit.kind === "boot" || hit.kind === "crash") {
    const b = hit.boot;
    const lines = [`Boot ${b.boot}${b.startOverwritten ? " (start overwritten)" : ""}`,
      `reset: ${b.reset ?? "?"}  wake: ${b.wake ?? "?"}  fw: ${b.firmware ?? "?"} (${b.slot ?? "?"})`,
      `awake ${durationText(b.duration)}, ${b.records} records${b.stable ? "" : ", never reached 60 s"}`,
      wallKnown(b) ? `started ${wallText(b.realStart, false)}` : "wall time unknown"];
    if (b.sleep) lines.push("ended by entering deep sleep");
    if (b.crashedInto !== undefined) {
      const next = data.bootIndex.get(b.crashedInto);
      lines.push(`✖ ended abnormally: boot ${next.boot} reports ${next.reset}` +
                 (next.crash ? ` (task ${next.crash.task}, cause ${next.crash.cause})` : ""));
      if (hit.kind === "crash") lines.push("click: show the lines before it");
    }
    if (b.crash) lines.push(`crash record: task ${b.crash.task}, cause ${b.crash.cause}`);
    if ((data.coreDumps || []).some((core) => core.boot === b.boot)) lines.push("core dump stored: Decode it from its line in the log");
    return lines.join("\n");
  }
  if (hit.kind === "firmware") {
    const { run, previous } = hit;
    const first = run.boots[0], last = run.boots[run.boots.length - 1];
    const abnormal = run.boots.filter((b) => b.abnormal).length;
    const awake = run.boots.reduce((sum, b) => sum + b.duration, 0);
    const only = firmwareRuns().length === 1;
    return [`Firmware ${run.version ?? "unknown"}`,
      previous ? (previous.version === run.version ? `reinstalled at boot ${first.boot} (now in ${run.slot})`
                                                   : `updated from ${previous.version ?? "?"} at boot ${first.boot}`)
               : only ? "the only version in the log" : "oldest version in the log",
      `boots B${first.boot}–B${last.boot} (${run.boots.length}), awake ${durationText(awake)}`,
      `abnormal resets: ${abnormal}` + (abnormal && awake > 0 ? ` (${(abnormal / (awake / 3600)).toFixed(2)} per awake hour)` : ""),
      wallKnown(first) ? `from ${wallText(first.realStart, false)}` : ""].filter(Boolean).join("\n");
  }
  if (hit.kind === "interval") {
    const iv = hit.iv;
    const label = iv.lane === "state" ? STATE_LABELS[iv.kind] || iv.kind : iv.kind;
    return `${label}: ${durationText(ivX1(iv) - ivX0(iv))}\nfrom ${recordTime(data.records[iv.record])}`;
  }
  if (hit.kind === "record") {
    const badges = (hit.record[R.badges] || []).map(([text]) => `• ${text}`).join("\n");
    return `${recordTime(hit.record)}  ${hit.record[R.name]}\n${hit.record[R.text]}` + (badges ? `\n${badges}` : "");
  }
  if (hit.kind === "telemetry") {
    const p = hit.point;
    const charger = ["unknown", "no input", "disabled", "not charging", "charging", "finished"][p.charger] || p.charger;
    return `Telemetry, boot ${p.boot}\nbattery ${p.battery ?? "—"} mV  charger ${charger}  volume ${p.volume}%\n` +
           `heap free ${p.free}  largest ${p.largest}  lowest ${p.minFree}\nactivity 0x${p.activity.toString(16)}`;
  }
  return "";
}

function hitX(hit) {
  if (hit.kind === "boot") return bootX0(hit.boot);
  if (hit.kind === "note") return noteX(hit.note.start);
  if (hit.kind === "unknownTime") return hit.span[0];
  if (hit.kind === "firmware") return bootX0(hit.run.boots[0]);
  if (hit.kind === "crash") return bootX1(hit.boot);
  if (hit.kind === "interval") return ivX0(hit.iv);
  if (hit.kind === "record") return recX(hit.record);
  return ptX(hit.point);
}

function onClick(hit, px) {
  if (hit && hit.kind === "crash") {
    // The lines before the crash are the end of the boot that crashed.
    const b = hit.boot, next = state.data.bootIndex.get(b.crashedInto);
    const end = bootX1(b);
    state.view = [end - Math.min(180, b.duration), Math.max(end + 10, Math.min(bootX0(next) + 5, end + 600))];
  }
  state.cursor = hit ? hitX(hit) : toX(px);
  state.selectedRecord = hit && hit.kind === "record" ? hit.record : null;
}

// --- Log list ---------------------------------------------------------------

function applyFilters() {
  if (!state.data) return;
  const minimum = LEVEL_RANK[state.level];
  const needle = state.search.toLowerCase();
  state.filtered = state.data.records.filter((record) => record[R.name] !== "COREDUMP_CHUNK" &&
    state.areas.has(record[R.area]) && LEVEL_RANK[record[R.level]] >= minimum &&
    (!needle || record[R.text].toLowerCase().includes(needle) || record[R.name].toLowerCase().includes(needle) ||
     (record[R.badges] || []).some(([text]) => text.toLowerCase().includes(needle))));
  renderLog();
}

function visibleRecords() {
  const [a, b] = state.view;
  return state.filtered.filter((record) => { const x = recX(record); return x >= a && x <= b; });
}

// Rows with badges take a second line, so rows have two heights; logTops
// holds each row's offset for the virtual scrolling.
let logRows = [];
let logTops = new Float64Array(1);
function rowHeight(record) {
  let height = (record[R.badges] && record[R.badges].length ? 2 : 1) * ROW_HEIGHT;
  const core = coreOf(record);
  if (core) height += ROW_HEIGHT + 6 + (state.cores.get(core.boot)?.open ? CORE_TEXT_HEIGHT + 6 : 0);
  return height;
}

function renderLog() {
  logRows = visibleRecords();
  logTops = new Float64Array(logRows.length + 1);
  logRows.forEach((record, i) => { logTops[i + 1] = logTops[i] + rowHeight(record); });
  $("count").textContent = `${logRows.length.toLocaleString()} lines in view` +
    (logRows.length !== state.filtered.length ? ` (${state.filtered.length.toLocaleString()} match)` : "");
  $("log-spacer").style.height = `${logTops[logRows.length]}px`;
  paintLog();
}

function rowAt(offset) {
  let lo = 0, hi = logRows.length;
  while (lo < hi) { const mid = (lo + hi) >> 1; if (logTops[mid + 1] <= offset) lo = mid + 1; else hi = mid; }
  return lo;
}

function paintLog() {
  const log = $("log");
  const first = Math.max(0, rowAt(log.scrollTop) - 10);
  const last = Math.min(logRows.length, rowAt(log.scrollTop + log.clientHeight) + 10);
  for (const old of log.querySelectorAll(".row")) old.remove();
  const fragment = document.createDocumentFragment();
  for (let i = first; i < last; i++) {
    const record = logRows[i];
    const row = document.createElement("div");
    row.className = `row ${record[R.level]}` + (record === state.selectedRecord ? " hi" : "") +
                    (record[R.name] === "BOOT" ? " boot" : "");
    row.style.top = `${logTops[i]}px`;
    row.style.height = `${rowHeight(record)}px`;
    row.dataset.index = i;
    row.innerHTML = `<span class="t"></span><span class="a"></span><span class="x"></span>`;
    row.children[0].textContent = recordTime(record);
    row.children[1].textContent = AREA_LABELS[record[R.area]] || record[R.area];
    row.children[2].textContent = record[R.text];
    if (record[R.badges] && record[R.badges].length) {
      const line = document.createElement("div");
      line.className = "badges";
      for (const [text, tone] of record[R.badges]) {
        const badge = document.createElement("span");
        badge.className = `badge ${tone}`;
        badge.textContent = text;
        line.appendChild(badge);
      }
      row.appendChild(line);
    }
    const core = coreOf(record);
    if (core) {
      row.appendChild(coreActions(core));
      const shown = state.cores.get(core.boot);
      if (shown && shown.open) {
        const text = document.createElement("pre");
        text.className = "core-text" + (shown.bad ? " bad" : "");
        text.style.height = `${CORE_TEXT_HEIGHT}px`;
        text.textContent = shown.text;
        text.addEventListener("scroll", () => { shown.scroll = text.scrollTop; });
        row.appendChild(text);
        requestAnimationFrame(() => { text.scrollTop = shown.scroll; });
      }
    }
    row.title = record[R.name];
    fragment.appendChild(row);
  }
  log.appendChild(fragment);
}

function selectNearest(x, exact) {
  let index = exact ? logRows.indexOf(exact) : -1;
  if (index < 0) index = logRows.findIndex((record) => recX(record) >= x);
  if (index < 0) index = logRows.length - 1;
  if (index < 0) return;
  state.selectedRecord = logRows[index];
  const log = $("log");
  log.scrollTop = Math.max(0, logTops[index] - log.clientHeight / 2);
  paintLog();
}

// --- Stats ------------------------------------------------------------------

async function renderStats() {
  const stats = await getJson("/api/stats");
  const fleet = stats.fleet;
  const versions = [...new Set([...Object.keys(stats.firmware), ...fleet.adoption.versions,
                                ...fleet.crashRate.map((r) => r.version), ...fleet.memory.map((r) => r.version)])]
    .sort(compareVersions);
  const palette = ["--fw0", "--fw1", "--fw2", "--fw3", "--song", "--animal", "--stream", "--kill"].map(css);
  const colorOf = (version) => palette[versions.indexOf(version) % palette.length];
  const panel = (label, body, title = "") =>
    `<div class="card"${title ? ` title="${escapeHtml(title)}"` : ""}><div class="label">${label}</div>${body}</div>`;
  const w = fleet.uploads.windows;
  $("totals").innerHTML = [
    `<div class="card count"><div class="label">Devices</div><div class="value">${stats.devices.length}</div></div>`,
    panel(state.source === "cloud" ? "Devices uploading" : "Devices fetched",
          `<div class="windows"><b>${w["1"]}</b> today · <b>${w["7"]}</b> in 7 days · <b>${w["30"]}</b> in 30 days</div>` +
          uploadChart(fleet.uploads)),
    panel("Current firmware", firmwarePie(stats.firmware, colorOf)),
    panel("Firmware adoption", adoptionChart(fleet.adoption, colorOf),
          "Share of devices on each version, by day (a device counts from its first dated boot)"),
    panel("Abnormal resets per 100 awake hours", barRows(fleet.crashRate.map((r) => ({
      label: r.version, value: r.per100h ?? 0, text: r.per100h === null ? "—" : `${r.per100h}`, color: colorOf(r.version),
      title: `${r.version}: ${r.abnormal} abnormal reset${r.abnormal === 1 ? "" : "s"} in ${r.awakeHours} awake hours`,
    })))),
    panel("Lowest free heap, 5th percentile", barRows(fleet.memory.map((r) => ({
      label: r.version, value: r.p5, text: `${(r.p5 / 1000).toFixed(1)} KB`, color: colorOf(r.version),
      title: `${r.version}: 5 % of ${r.boots} boots dropped to ${r.p5} bytes free or less`,
    })), 25000)),
    panel("Battery drain, mV/h", drainChart(stats.devices),
          "Each dot is a device: voltage drop per hour while playing and while idle (not charging)"),
  ].join("");
  const recent = new Set(fleet.recentAbnormal);
  const drain = (d) => d.mvPerHour === null ? "—" : `${d.mvPerHour}`;
  const head = ["Name", "Device", "Fetches", "Last fetch", "Last sector", "Boots", "Abnormal", "Awake h", "Local h", "BT h", "Songs",
                "Drain playing mV/h", "Drain idle mV/h", "Errors", "Firmware history (old → new)"];
  const rows = stats.devices.map((d) => `<tr data-device="${d.device}"><td>` +
    (recent.has(d.device) ? `<span class="alert" title="Abnormal reset in the last 48 hours">⚠</span> ` : "") +
    `${escapeHtml(d.name || "—")}</td><td>${d.device}</td><td>${d.snapshots}</td>` +
    `<td>${d.lastFetched.replace("T", " ")}</td><td>${d.lastSector ?? "—"}</td><td>${d.boots}</td><td>${d.abnormalResets}</td><td>${d.awakeHours}</td>` +
    `<td>${d.localHours}</td><td>${d.btHours}</td><td>${d.songsStarted}</td><td>${drain(d.drain.playing)}</td>` +
    `<td>${drain(d.drain.idle)}</td><td>${d.errors}</td><td>${d.firmware.join(" → ")}</td></tr>`).join("");
  $("stats-table").innerHTML = `<thead><tr>${head.map((h) => `<th>${h}</th>`).join("")}</tr></thead><tbody>${rows}</tbody>`;
}

function compareVersions(a, b) { return a.localeCompare(b, undefined, { numeric: true }); }
function plural(n, word) { return `${n} ${word}${n === 1 ? "" : "s"}`; }

// Devices per firmware version, most common first; the three largest slices
// are labelled, and every count is in the hover text.
function firmwarePie(counts, colorOf) {
  const slices = Object.entries(counts).sort((a, b) => b[1] - a[1] || compareVersions(b[0], a[0]));
  const total = slices.reduce((sum, [, n]) => sum + n, 0);
  if (!total) return `<div class="value">—</div>`;
  const hover = (version, n) => `${escapeHtml(version)}: ${plural(n, "device")} (${Math.round(n / total * 100)} %)`;
  const point = (a, r) => [20 + r * Math.cos(a), 20 + r * Math.sin(a)];
  const xy = (a, r) => point(a, r).map((v) => v.toFixed(2)).join(" ");
  let angle = -Math.PI / 2;
  const paths = [], labels = [];
  slices.forEach(([version, n], i) => {
    const color = colorOf(version);
    const a0 = angle, a1 = angle + n / total * 2 * Math.PI;
    angle = a1;
    paths.push(n === total
      ? `<circle cx="20" cy="20" r="18" fill="${color}"><title>${hover(version, n)}</title></circle>`
      : `<path d="M20 20 L${xy(a0, 18)} A18 18 0 ${a1 - a0 > Math.PI ? 1 : 0} 1 ${xy(a1, 18)} Z" fill="${color}">` +
        `<title>${hover(version, n)}</title></path>`);
    if (i < 3) {
      const mid = n === total ? -Math.PI / 4 : (a0 + a1) / 2;
      const [x, y] = point(mid, 21);
      const anchor = Math.cos(mid) >= 0 ? "start" : "end";
      labels.push(`<text x="${x.toFixed(1)}" y="${(y + 2.5).toFixed(1)}" text-anchor="${anchor}" font-size="7" ` +
                  `fill="${css("--text")}">${escapeHtml(version)}</text>`);
    }
  });
  const legend = slices.map(([version, n]) =>
    `<li title="${hover(version, n)}"><i style="background:${colorOf(version)}"></i>${escapeHtml(version)}</li>`);
  return `<div class="pie"><svg viewBox="-22 -2 84 44" width="126" height="66">${paths.join("")}${labels.join("")}</svg>` +
         `<ul>${legend.join("")}</ul></div>`;
}

// Small charts share one frame: a plot with y labels on the left, faint
// dashed gridlines, and the first and last day below.
const CHART_W = 230, PLOT_L = 24, PLOT_T = 4, PLOT_H = 48;
const PLOT_W = CHART_W - PLOT_L - 4;
const fade = () => `stroke="${css("--muted")}" stroke-opacity="0.45" stroke-dasharray="2 2" stroke-width="0.6"`;
const small = (x, y, text, anchor = "end") =>
  `<text x="${x}" y="${y}" text-anchor="${anchor}" font-size="8" fill="${css("--muted")}">${text}</text>`;

// |gridOnTop| keeps the gridlines visible over filled columns.
function frame(ticks, days, body, gridOnTop = false) {
  const grid = ticks.map(([share, text]) => {
    const y = (PLOT_T + PLOT_H * (1 - share)).toFixed(1);
    return `<line x1="${PLOT_L}" x2="${PLOT_L + PLOT_W}" y1="${y}" y2="${y}" ${fade()}/>` + small(PLOT_L - 3, Number(y) + 3, text);
  });
  const bottom = PLOT_T + PLOT_H + 10;
  const layers = gridOnTop ? body + grid.join("") : grid.join("") + body;
  return `<svg class="mini" viewBox="0 0 ${CHART_W} ${bottom + 1}">${layers}` +
         small(PLOT_L, bottom, days[0].slice(5), "start") + small(PLOT_L + PLOT_W, bottom, "today") + `</svg>`;
}

// Whole-number ticks: 0, half and the top.
function countTicks(max) {
  const step = Math.max(1, Math.ceil(max / 2));
  return { top: step * 2, ticks: [[0, "0"], [0.5, `${step}`], [1, `${step * 2}`]] };
}

function uploadChart(uploads) {
  const { top, ticks } = countTicks(Math.max(...uploads.devices));
  const step = PLOT_W / uploads.days.length;
  const bars = uploads.devices.map((n, i) => {
    const x = PLOT_L + i * step;
    const h = n / top * PLOT_H;
    return (n ? `<rect x="${(x + 0.5).toFixed(1)}" y="${(PLOT_T + PLOT_H - h).toFixed(1)}" width="${(step - 1).toFixed(1)}" ` +
                `height="${h.toFixed(1)}" fill="${css("--accent")}"/>` : "") +
           `<rect x="${x.toFixed(1)}" y="${PLOT_T}" width="${step.toFixed(1)}" height="${PLOT_H}" fill="transparent">` +
           `<title>${uploads.days[i]}: ${plural(n, "device")}</title></rect>`;
  });
  return frame(ticks, uploads.days, bars.join(""));
}

// 100 % stacked columns: each day's devices split by the version they ran.
function adoptionChart(adoption, colorOf) {
  if (!adoption.versions.length) return `<div class="value">—</div>`;
  const step = PLOT_W / adoption.days.length;
  const columns = adoption.counts.map((counts, i) => {
    const total = counts.reduce((a, b) => a + b, 0);
    if (!total) return "";
    let y = PLOT_T + PLOT_H;
    const parts = counts.map((n, v) => {
      if (!n) return "";
      const h = n / total * PLOT_H;
      y -= h;
      return `<rect x="${(PLOT_L + i * step).toFixed(1)}" y="${y.toFixed(1)}" width="${(step + 0.3).toFixed(1)}" ` +
             `height="${h.toFixed(1)}" fill="${colorOf(adoption.versions[v])}"/>`;
    });
    const text = adoption.versions.map((version, v) => counts[v] ? `${version}: ${counts[v]}` : "").filter(Boolean).join(", ");
    return `<g><title>${adoption.days[i]}: ${escapeHtml(text)}</title>${parts.join("")}</g>`;
  });
  return frame([[0, "0"], [0.5, "50%"], [1, "100%"]], adoption.days, columns.join(""), true);
}

// One row per version: label, bar, value; |max| fixes the scale.
function barRows(rows, max = null) {
  if (!rows.length) return `<div class="value">—</div>`;
  const top = max ?? Math.max(...rows.map((r) => r.value), 1e-9);
  return `<div class="bars">${rows.map((r) =>
    `<div class="bar-row" title="${escapeHtml(r.title)}"><span>${escapeHtml(r.label)}</span>` +
    `<span class="track"><i style="width:${Math.min(100, r.value / top * 100).toFixed(1)}%;background:${r.color}"></i></span>` +
    `<span class="num">${r.text}</span></div>`).join("")}</div>`;
}

// Two rows of dots, one dot per device with its figure above it, on an axis
// with faint dashed gridlines.
function drainChart(devices) {
  const rows = [["playing", "Playing"], ["idle", "Idle"]];
  const values = devices.flatMap((d) => rows.map(([key]) => d.drain[key].mvPerHour)).filter((v) => v !== null);
  if (!values.length) return `<div class="value">—</div>`;
  const unit = [5, 10, 20, 25, 50, 100, 200, 500].find((u) => Math.max(...values) / u <= 4) || 1000;
  const max = Math.max(unit, Math.ceil(Math.max(...values) / unit) * unit);
  const left = 40, width = CHART_W - left - 10, bottom = 66;
  const x = (v) => (left + v / max * width).toFixed(1);
  const grid = [];
  for (let v = 0; v <= max; v += unit) {
    grid.push(`<line x1="${x(v)}" x2="${x(v)}" y1="4" y2="${bottom - 10}" ${fade()}/>` + small(x(v), bottom, v, "middle"));
  }
  const dots = rows.map(([key, label], row) => {
    const y = 22 + row * 24;
    const marks = devices.filter((d) => d.drain[key].mvPerHour !== null).map((d) => {
      const value = d.drain[key].mvPerHour;
      return `<circle cx="${x(value)}" cy="${y}" r="3.5" fill="${css(key === "playing" ? "--song" : "--accent")}" ` +
             `fill-opacity="0.75"><title>${escapeHtml(d.name || d.device)}: ${value} mV/h ${label.toLowerCase()} ` +
             `(${d.drain[key].hours} h measured)</title></circle>` + small(x(value), y - 6, Math.round(value), "middle");
    });
    return small(0, y + 3, label, "start") + marks.join("");
  });
  return `<svg class="mini" viewBox="0 0 ${CHART_W} ${bottom + 1}">${grid.join("")}${dots.join("")}</svg>`;
}

function escapeHtml(text) {
  return text.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

// |load| false only switches the view (the caller reads the data).
function showTab(tab, load = true) {
  state.tab = tab;
  $("timeline-view").hidden = tab !== "timeline";
  $("stats-view").hidden = tab !== "stats";
  document.querySelector(".timeline-only").hidden = tab !== "timeline";
  if (tab === "stats") return load ? renderStats().catch(showError) : Promise.resolve();
  if (!state.data) showNotice(noDeviceText());
  draw();
  scrollLogToEnd();
  return Promise.resolve();
}

function showError(error) {
  showNotice(`Error: ${error.message}`);
  if (state.tab === "stats") $("totals").innerHTML = `<p class="bad">Error: ${escapeHtml(error.message)}</p>`;
  console.error(error);
}

// --- Events -----------------------------------------------------------------

let drag = null;

function setup() {
  const canvas = $("timeline");
  const chips = $("areas");
  for (const [area, label] of Object.entries(AREA_LABELS)) {
    const chip = document.createElement("button");
    chip.className = "chip";
    chip.textContent = label;
    chip.setAttribute("aria-pressed", "true");
    chip.addEventListener("click", () => {
      state.areas.has(area) ? state.areas.delete(area) : state.areas.add(area);
      chip.setAttribute("aria-pressed", state.areas.has(area));
      applyFilters();
    });
    chips.appendChild(chip);
  }
  $("level").addEventListener("change", (e) => { state.level = e.target.value; applyFilters(); });
  let searchTimer = null;
  $("search").addEventListener("input", (e) => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => { state.search = e.target.value; applyFilters(); }, 150);
  });
  $("log").addEventListener("scroll", paintLog);
  $("log").addEventListener("click", (e) => {
    const decode = e.target.closest("[data-decode]");
    if (decode) { decodeCore(Number(decode.dataset.decode)); return; }
    if (e.target.closest(".core-text, .core-actions a")) return;
    const row = e.target.closest(".row");
    if (!row) return;
    state.selectedRecord = logRows[Number(row.dataset.index)];
    state.cursor = recX(state.selectedRecord);
    paintLog();
    draw();
  });
  $("stats-table").addEventListener("click", (e) => {
    const row = e.target.closest("tr[data-device]");
    if (!row) return;
    loadDevice(row.dataset.device).then(() => showTab("timeline")).catch(showError);
  });
  for (const button of document.querySelectorAll("[data-mode]")) {
    button.addEventListener("click", () => setMode(button.dataset.mode));
  }
  $("fit").addEventListener("click", () => { if (state.data) { state.view = fullRange(); renderLog(); draw(); } });
  $("reload").addEventListener("click", () => loadDevices(true).catch(showError));
  $("note-text").addEventListener("keydown", (e) => {
    if (e.key === "Escape") $("note-cancel").click();
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) $("note-editor").requestSubmit();
  });
  showSource();
  for (const button of document.querySelectorAll("[data-source]")) {
    button.addEventListener("click", () => {
      // The source already shown: back to its table.
      if (state.source === button.dataset.source) { showTab("stats"); return; }
      state.source = button.dataset.source;
      store("source", state.source);
      showSource();
      // Nothing of the other source stays on screen while this one loads (the
      // cloud takes a few seconds); then All devices shows what it holds.
      state.devices = [];
      clearDevice();
      for (const id of ["stats-table", "totals", "source"]) $(id).innerHTML = "";
      showNotice("");
      showTab("stats", false);
      loadDevices().catch(showError);
    });
  }

  canvas.addEventListener("wheel", (e) => {
    if (!state.data) return;
    e.preventDefault();
    const rect = canvas.getBoundingClientRect();
    const x = toX(e.clientX - rect.left);
    const [a, b] = state.view;
    const factor = Math.exp((e.deltaY || e.deltaX) * 0.0015);
    const span = Math.max(1, (b - a) * factor);
    const share = (x - a) / (b - a);
    state.view = [x - share * span, x - share * span + span];
    scheduleRedraw();
  }, { passive: false });
  canvas.addEventListener("pointerdown", (e) => {
    if (!state.data) return;
    const rect = canvas.getBoundingClientRect();
    const note = e.metaKey || e.ctrlKey;
    drag = { startPx: e.clientX - rect.left, lastPx: e.clientX - rect.left, view: state.view.slice(),
             select: e.shiftKey && !note, note, moved: false, py: e.clientY - rect.top };
    canvas.setPointerCapture(e.pointerId);
    canvas.classList.toggle("dragging", !e.shiftKey && !note);
  });
  canvas.addEventListener("pointermove", (e) => {
    const rect = canvas.getBoundingClientRect();
    const px = e.clientX - rect.left, py = e.clientY - rect.top;
    if (drag) {
      drag.lastPx = px;
      if (Math.abs(px - drag.startPx) > 3) drag.moved = true;
      if (!drag.select && !drag.note && drag.moved) {
        const [a, b] = drag.view;
        const shift = (px - drag.startPx) / plotWidth(canvas) * (b - a);
        state.view = [a - shift, b - shift];
      }
      hideTooltip();
      scheduleRedraw(!drag.select && !drag.note);
      return;
    }
    const hit = hitTest(px, py);
    hit ? showTooltip(describeHit(hit), px, py) : hideTooltip();
    canvas.style.cursor = hit ? "pointer" : "";
    if (state.data) {
      state.hover = px >= GUTTER ? toX(px) : null;
      scheduleRedraw(false);
    }
  });
  canvas.addEventListener("pointerup", (e) => {
    if (!drag) return;
    const finished = drag;
    drag = null;
    canvas.classList.remove("dragging");
    if (finished.note) {
      const a = Math.max(GUTTER, Math.min(finished.startPx, finished.lastPx));
      const b = Math.max(GUTTER, Math.max(finished.startPx, finished.lastPx));
      draw();
      editNote({ start: noteEnd(toX(a)), end: finished.moved ? noteEnd(toX(b)) : null, text: "" }, e.clientX, e.clientY);
      return;
    }
    const clicked = !finished.moved && hitTest(finished.startPx, finished.py);
    if (clicked && clicked.kind === "note") {
      draw();
      editNote(clicked.note, e.clientX, e.clientY);
      return;
    }
    if (finished.select && finished.moved) {
      const x0 = toX(Math.min(finished.startPx, finished.lastPx)), x1 = toX(Math.max(finished.startPx, finished.lastPx));
      if (x1 - x0 > 0.5) state.view = [x0, x1];
      renderLog();
      draw();
    } else if (!finished.moved) {
      onClick(hitTest(finished.startPx, finished.py), finished.startPx);
      renderLog();
      selectNearest(state.cursor, state.selectedRecord);
      draw();
    } else {
      renderLog();
    }
  });
  canvas.addEventListener("pointerleave", () => {
    hideTooltip();
    if (state.hover !== null) { state.hover = null; scheduleRedraw(false); }
  });
  canvas.addEventListener("dblclick", () => { if (state.data) { state.view = fullRange(); renderLog(); draw(); } });
  window.addEventListener("resize", () => draw());
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => draw());
  const savedMode = recall("mode");
  if (savedMode === "awake") setMode("awake", false);
}

function showSource() {
  for (const button of document.querySelectorAll("[data-source]")) {
    button.setAttribute("aria-pressed", button.dataset.source === state.source);
  }
}

function setMode(mode, redraw = true) {
  if (state.mode === mode) return;
  // Keep the same records in view when switching axes.
  const before = state.data ? visibleRecords() : [];
  state.mode = mode;
  store("mode", mode);
  for (const button of document.querySelectorAll("[data-mode]")) button.setAttribute("aria-pressed", button.dataset.mode === mode);
  if (!state.data || !redraw) return;
  if (before.length && before.length < state.data.records.length) {
    const xs = before.map(recX);
    const lo = Math.min(...xs), hi = Math.max(...xs), padding = Math.max(2, (hi - lo) * 0.05);
    state.view = [lo - padding, hi + padding];
  } else {
    state.view = fullRange();
  }
  if (state.selectedRecord) state.cursor = recX(state.selectedRecord);
  renderLog();
  draw();
}

let redrawPending = false, logPending = false;
function scheduleRedraw(updateLog = true) {
  logPending = logPending || updateLog;
  if (redrawPending) return;
  redrawPending = true;
  requestAnimationFrame(() => {
    redrawPending = false;
    draw();
    if (logPending) { logPending = false; renderLogSoon(); }
  });
}

let logTimer = null;
function renderLogSoon() { clearTimeout(logTimer); logTimer = setTimeout(renderLog, 120); }

function showTooltip(text, px, py) {
  const tip = $("tooltip");
  tip.textContent = text;
  tip.hidden = false;
  const wrap = tip.parentElement.getBoundingClientRect();
  const left = Math.min(px + 14, wrap.width - tip.offsetWidth - 6);
  tip.style.left = `${Math.max(6, left)}px`;
  tip.style.top = `${py + 16}px`;
}
function hideTooltip() { $("tooltip").hidden = true; }

setup();
// A link to a device (#device=...) opens its timeline; otherwise All devices.
const linked = new URLSearchParams(location.hash.slice(1)).get("device");
showTab(linked ? "timeline" : "stats", false);
loadDevices()
  .then(() => linked && state.devices.some((d) => d.device === linked) && loadDevice(linked))
  .catch(showError);

"use strict";

(function () {
  const $ = (s) => document.querySelector(s);
  const $$ = (s) => [...document.querySelectorAll(s)];
  const el = (tag, cls, html) => { const e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; };
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const uid = () => (crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random().toString(16).slice(2));
  const fmtDur = (ms) => { const s = Math.round(ms / 1000); return Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0"); };
  const fmtSize = (b) => b >= 1073741824 ? (b / 1073741824).toFixed(2) + " GB" : b >= 1048576 ? (b / 1048576).toFixed(1) + " MB" : b > 0 ? Math.max(1, Math.round(b / 1024)) + " KB" : "0 KB";
  const plural = (n, word) => n + " " + word + (n === 1 ? "" : "s");

  const storage = {
    getItem(k) { try { return localStorage.getItem(k); } catch { return null; } },
    setItem(k, v) { try { localStorage.setItem(k, v); } catch { /* private mode */ } }
  };

  let toastTimer;
  // Messages go in the browser's top layer (a manual popover, shown again
  // each time), so they are above every card and any open dialog.
  function toast(msg) {
    const t = $("#toast"); t.textContent = msg;
    if (t.showPopover) { try { if (t.matches(":popover-open")) t.hidePopover(); t.showPopover(); } catch { /* not supported */ } }
    requestAnimationFrame(() => t.classList.add("show"));
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      t.classList.remove("show");
      toastTimer = setTimeout(() => { try { t.hidePopover?.(); } catch { /* already hidden */ } }, 300);
    }, 2600);
  }
  document.addEventListener("click", (e) => {
    const t = e.target.closest("[data-toast]"); if (t && !t.disabled) toast(t.dataset.toast);
  });

  // ---- State -------------------------------------------------------------
  const S = {
    themes: [],      // working-area themes
    items: [],       // working-area songs and animal sounds
    animalsMeta: { id: "__animals__", shuffle: true, lang: "en", cleared: false, matches: {} },
    // Shared animal sounds and prompts from the content bucket (content.js).
    cloud: { loading: true, error: "", sounds: [], languages: [], prompts: [], promptsLang: "", promptsAttribution: null, soundsAttribution: null },
    // Shared song themes from the content bucket (songs/<theme>/).
    library: { loading: true, error: "", themes: [], adding: "", queue: [] },
    open: new Set(), // expanded theme rows
    device: { state: "off", name: "", themes: [], songs: {}, animals: [], animalsTheme: null, loading: false }
  };
  const content = SweetYaarContent.createContent(window.fetch.bind(window));
  const AM = SweetYaarAnimals;
  let store = null;
  try {
    store = SweetYaarStore.createStore(indexedDB, {
      onBlocked: () => toast("Studio is open in another tab with an older version. Close or reload that tab to load your work here.")
    });
  } catch (e) { store = null; }
  const client = SweetYaarDevice.createClient(navigator.bluetooth, storage, () => {
    S.device = { state: "off", name: "", themes: [], songs: {}, animals: [], loading: false };
    toast("The toy disconnected.");
    render();
  });

  async function saveItem(item) { if (store) await store.putItem(item); }

  // ---- Navigation --------------------------------------------------------
  let currentView = "library";
  // The shelves keep their scroll position while the editor is open, so
  // coming back lands where the user was; the editor opens at the top.
  let libraryScroll = 0;
  function show(view) {
    if (currentView === "editor" && view !== "editor" && isRecording()) stopRecording();
    stopAudio();
    pausePlayback();
    if (currentView === "editor" && view !== "editor") { E.item = null; E.ch = null; E.peaks = null; E.dirty = false; }
    if (currentView === "library" && view !== "library") libraryScroll = window.scrollY;
    const from = currentView;
    currentView = view;
    $$(".view").forEach((v) => v.classList.toggle("active", v.id === "view-" + view));
    if (view === "library" && from !== "library") {
      window.scrollTo(0, libraryScroll);
      requestAnimationFrame(() => window.scrollTo(0, libraryScroll));   // after any re-render
    } else if (view !== from) window.scrollTo(0, 0);
  }
  document.addEventListener("click", (e) => {
    const target = e.target.closest("[data-go]");
    if (target) { e.preventDefault(); show(target.dataset.go); }
  });

  // ---- Playback of working-area items -----------------------------------
  let audio = null, audioUrl = null, playingId = null;
  function stopAudio() {
    if (!audio) return;
    audio.pause(); if (audioUrl) URL.revokeObjectURL(audioUrl); audio = null; playingId = null;
    render();
  }
  function togglePlay(item) {
    const same = playingId === item.id;
    if (audio) { audio.pause(); if (audioUrl) URL.revokeObjectURL(audioUrl); audio = null; playingId = null; }
    if (same) { render(); return; }
    audioUrl = item.blob ? URL.createObjectURL(item.blob) : null;
    audio = new Audio(audioUrl || item.url);
    playingId = item.id;
    audio.onended = () => { playingId = null; render(); };
    audio.play().catch(() => { playingId = null; toast("Couldn't play that file."); render(); });
    render();
  }

  // ---- Adding files ------------------------------------------------------
  let decodeCtx = null;
  async function durationMs(file) {
    decodeCtx = decodeCtx || new (window.AudioContext || window.webkitAudioContext)();
    const buf = await decodeCtx.decodeAudioData(await file.arrayBuffer());
    return Math.round(buf.duration * 1000);
  }
  function pickFiles(multiple) {
    return new Promise((resolve) => {
      const input = el("input"); input.type = "file"; input.accept = "audio/*"; input.multiple = multiple;
      input.onchange = () => resolve([...input.files]);
      input.oncancel = () => resolve([]);
      input.click();
    });
  }
  // A strictly increasing time for addedAt, so items added in one go keep
  // their order after a reload.
  let lastStamp = 0;
  const stamp = () => (lastStamp = Math.max(Date.now(), lastStamp + 1));
  async function addFiles(kind, themeId, files) {
    const created = [];
    let added = 0, failed = 0;
    for (const file of files) {
      try {
        const item = {
          id: uid(), kind, themeId: kind === "song" ? themeId : "", name: file.name.replace(/\.\w+$/, ""),
          fileName: file.name, size: file.size, durationMs: await durationMs(file), blob: file, addedAt: stamp()
        };
        await saveItem(item); S.items.push(item); created.push(item); added++;
      } catch (e) { failed++; }
    }
    if (kind === "song") S.open.add(themeId);
    if (kind === "song") render(); else await rematch();
    toast(failed ? `Added ${added}, couldn't read ${failed} file${failed === 1 ? "" : "s"}.` : `Added ${plural(added, { song: "song", prompt: "prompt" }[kind] || "animal sound")}.`);
    return created;
  }
  async function newTheme(name) {
    const theme = { id: uid(), name: name.trim(), createdAt: Date.now(), enabled: true, shuffle: false, attribution: "" };
    if (store) await store.putTheme(theme);
    S.themes.push(theme); S.open.add(theme.id); render();
    return theme;
  }

  // ---- Rendering ---------------------------------------------------------
  function renderDeviceButton() {
    const b = $("#deviceBtn"), d = S.device;
    b.className = "device-btn" + (d.state === "on" ? " on" : "");
    b.disabled = d.state === "connecting" || !client.supported;
    const stoppable = d.state === "connecting" && !!deviceAbort;
    $("#deviceStop").hidden = !stoppable;
    $("#deviceSplit").classList.toggle("connecting", stoppable);
    if (d.state === "on") {
      b.innerHTML = `<span class="dot"></span>${esc(d.name)}`;
      b.title = "Connected. Click to disconnect.";
    } else {
      b.innerHTML = `<img src="../assets/icon-bluetooth.svg" alt="">${d.state === "connecting" ? "Connecting…" : "Connect to SweetYaar"}`;
      b.title = client.supported ? "" : "Needs Chrome or Edge (Web Bluetooth).";
    }
  }

  const svg = (body) => `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${body}</svg>`;
  const ICON_GEAR = svg('<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/>');
  const ICON_BAN = svg('<circle cx="12" cy="12" r="9"/><path d="M5.6 5.6l12.8 12.8"/>');
  const ICON_WAVE = svg('<path d="M4 10v4M8 6v12M12 3v18M16 7v10M20 10v4"/>');
  const ICON_TRASH = svg('<polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v6M14 11v6"/><path d="M9 6V4h6v2"/>');

  // ---- Drag and drop -----------------------------------------------------
  const DRAG_TYPE = "application/x-sweetyaar-item";
  // A whole library theme, dragged from the library onto My themes.
  const LIB_TYPE = "application/x-sweetyaar-library-theme";
  const isAudioFile = (f) => f.type.startsWith("audio/") || /\.(wav|mp3|m4a|aac|ogg|flac|aiff?)$/i.test(f.name);
  const byteLength = (s) => new TextEncoder().encode(s).length;

  // Files dropped from the computer are added; dragged song rows (one, or the
  // selection) are moved, to the place between rows the pointer shows; a
  // library theme is copied in, but only where libraryThemes is set (the top
  // of My themes), never into one theme.
  let hovered = null;
  let insMark = null;
  const clearIns = () => { if (insMark) insMark.classList.remove("ins-before", "ins-after"); insMark = null; };
  const clearHover = () => { if (hovered) hovered.classList.remove("over"); hovered = null; clearIns(); };
  // Where dragged songs would land in a target's own list: before the song
  // with the returned id, or at the end (""). Marks the gap it shows.
  function insertionPoint(e, themeId) {
    const row = e.target.closest && e.target.closest(".song[data-id]");
    const item = row && S.items.find((i) => i.id === row.dataset.id);
    if (!item || item.kind !== "song" || item.themeId !== themeId) { clearIns(); return ""; }
    const r = row.getBoundingClientRect(), after = e.clientY > r.top + r.height / 2;
    if (insMark !== row || !row.classList.contains(after ? "ins-after" : "ins-before")) {
      clearIns(); insMark = row; row.classList.add(after ? "ins-after" : "ins-before");
    }
    if (!after) return item.id;
    const next = row.nextElementSibling;
    return next && next.matches(".song[data-id]") ? next.dataset.id : "";
  }
  document.addEventListener("drop", clearHover);
  document.addEventListener("dragend", clearHover);
  function dropTarget(node, kind, themeId, libraryThemes) {
    const accepts = (e) => [...e.dataTransfer.types].some((t) => t === "Files" || t === DRAG_TYPE || (libraryThemes && t === LIB_TYPE));
    node.addEventListener("dragover", (e) => {
      if (!accepts(e)) return;
      e.preventDefault(); e.stopPropagation();
      if (hovered !== node) { clearHover(); hovered = node; node.classList.add("over"); }
      if ([...e.dataTransfer.types].includes(DRAG_TYPE)) insertionPoint(e, themeId); else clearIns();
    });
    node.addEventListener("dragleave", (e) => { if (!node.contains(e.relatedTarget) && hovered === node) clearHover(); });
    node.addEventListener("drop", async (e) => {
      if (!accepts(e)) return;   // let it reach the enclosing target
      e.preventDefault(); e.stopPropagation(); clearHover();
      const libId = libraryThemes && e.dataTransfer.getData(LIB_TYPE);
      if (libId) {
        const lt = S.library.themes.find((t) => t.id === libId);
        if (lt) addLibraryTheme(lt);
        return;
      }
      const ids = e.dataTransfer.getData(DRAG_TYPE);
      if (ids) {
        const before = insertionPoint(e, themeId); clearHover();
        const items = S.items.filter((i) => ids.split(",").includes(i.id));
        if (!items.length) return;
        if (items.some((i) => i.kind !== kind)) { toast("That can't go here."); return; }
        await placeSongs(items, themeId, before);
        if (themeId) S.open.add(themeId);
        render();
        return;
      }
      const files = [...e.dataTransfer.files].filter(isAudioFile);
      if (!files.length) { toast("Drop audio files (WAV, MP3, …)."); return; }
      addFiles(kind, themeId, files);
    });
  }

  // ---- Form pieces -------------------------------------------------------
  function checkbox(label, checked, disabled, onChange) {
    const l = el("label", "check");
    const i = el("input"); i.type = "checkbox"; i.checked = checked; i.disabled = !!disabled;
    if (onChange) i.onchange = () => onChange(i.checked);
    l.append(i, document.createTextNode(label));
    return l;
  }
  function textbox(label, value, disabled, onCommit) {
    const l = el("label", "field");
    const i = el("input"); i.type = "text"; i.value = value; i.disabled = !!disabled;
    if (onCommit) i.onchange = () => onCommit(i.value.trim(), i);
    l.append(document.createTextNode(label), i);
    return l;
  }

  // The settings a theme's metadata.json (and config.json) can hold.
  function themeSettings(t, readOnly, commit) {
    const box = el("div", "tmeta");
    if (readOnly) box.append(el("div", "hint", "Read-only for now. Changing the toy's settings needs the upcoming upload mode."));
    box.append(
      textbox("Display name", t.name, readOnly, (v, input) => {
        if (!v) { input.value = t.name; return; }
        commit({ name: v });
      }),
      textbox("Credit (one line, markdown links allowed, up to 160 bytes)", t.credit, readOnly, (v, input) => {
        if (byteLength(v) > 160 || /[\u0000-\u001f]/.test(v)) { toast("The credit must be one line of at most 160 bytes."); input.value = t.credit; return; }
        commit({ attribution: v });
      }),
      checkbox("Enable theme", t.enabled, readOnly, (v) => commit({ enabled: v })),
      checkbox("Shuffle songs", t.shuffle, readOnly, (v) => commit({ shuffle: v }))
    );
    return box;
  }

  // A name edited in place, like the track name in the editor: Enter or
  // leaving the field keeps it, Escape puts the old one back, empty is ignored.
  function nameInput(value, onRename) {
    const i = el("input", "name name-edit"); i.type = "text"; i.value = value; i.title = "Click to rename"; i.spellcheck = false;
    i.addEventListener("keydown", (e) => {
      if (e.key === "Escape") { i.value = value; i.blur(); }
      else if (e.key === "Enter") i.blur();
    });
    i.addEventListener("change", () => {
      const v = i.value.trim();
      if (!v) { i.value = value; return; }
      if (v !== value) onRename(v);
    });
    return i;
  }

  // The app's one way of showing an attribution (content.parseAttribution):
  // the short credit as a line and, when there is a long one, a small
  // "ⓘ Credits" after it whose tooltip holds the long credit. The tooltip
  // stays open while the pointer is on it, so its links can be clicked; it
  // also opens on keyboard focus.
  const ICON_INFO = '<svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="6.5" fill="none" stroke="currentColor" stroke-width="1.5"/><rect x="7.25" y="7" width="1.5" height="4.5" rx=".75" fill="currentColor"/><circle cx="8" cy="4.9" r=".95" fill="currentColor"/></svg>';
  function attributionEl(attribution) {
    const box = el("div", "acredit"), line = el("div", "ashort", attribution.short);
    box.append(line);
    if (attribution.long) {
      const tip = el("span", "atip", `${ICON_INFO}<span>Credits</span>`);
      tip.tabIndex = 0;
      const long = el("div", "along", attribution.long);
      long.setAttribute("role", "tooltip"); long.id = "credit-" + uid();
      tip.setAttribute("aria-describedby", long.id);
      tip.append(long);
      line.append(" ", tip);
    }
    return box;
  }

  // Replaces an edited library song's audio with the library's file again.
  // An edited file of the user's goes back to the file as it was added.
  async function restoreOriginal(item) {
    if (!item.original) return;
    if (playingId === item.id) togglePlay(item);
    const blob = item.original;
    Object.assign(item, { blob, size: blob.size, durationMs: await durationMs(blob), fileName: item.originalFileName || item.fileName, parts: [], edited: false });
    delete item.original; delete item.originalFileName;
    await saveItem(item);
    if (item.kind === "song") render(); else await rematch();
    toast(`Restored “${item.name}” to the file you added.`);
  }
  async function restoreSong(item) {
    if (!item.source) return restoreOriginal(item);
    const m = /^c:songs\/(.+)\/([^/]+)$/.exec(item.source || "");
    if (!m) return;
    const [, themeId, file] = m;
    const lt = S.library.themes.find((t) => t.id === themeId), s = lt && lt.songs.find((x) => x.file === file);
    try {
      const response = await fetch(content.songUrl(themeId, file));
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const blob = new File([await response.blob()], file, { type: "audio/wav" });
      if (playingId === item.id) togglePlay(item);
      Object.assign(item, { blob, size: blob.size, durationMs: await durationMs(blob), fileName: file, parts: [], edited: false });
      if (s) item.name = s.name;
      await saveItem(item); render();
      toast(`Restored “${item.name}” from the library.`);
    } catch (e) { toast("Couldn't restore it: " + e.message); }
  }

  // Puts songs (in their current order) into a theme ("" = not in a theme)
  // before the song beforeId, or at the end. The order within a theme is the
  // order of S.items; it is kept as each song's `pos` (start() sorts by it,
  // and songs added later, which have none, come after).
  async function placeSongs(items, themeId, beforeId) {
    const moving = new Set(items);
    const rest = S.items.filter((i) => !moving.has(i));
    const list = rest.filter((i) => i.kind === "song" && i.themeId === themeId);
    let at = beforeId ? list.findIndex((i) => i.id === beforeId) : -1;
    if (at < 0) at = list.length;
    const ordered = [...list.slice(0, at), ...items, ...list.slice(at)];
    const inList = new Set(ordered);
    S.items = [...rest.filter((i) => !inList.has(i)), ...ordered];
    for (const [n, i] of ordered.entries()) {
      if (i.pos === n && i.themeId === themeId) continue;
      i.pos = n; i.themeId = themeId; await saveItem(i);
    }
  }

  // Song selection: click a row to select it, Cmd/Ctrl-click to add or
  // remove one, Shift-click for a range in the same list; dragging a
  // selected row drags the whole selection. Escape or a click outside the
  // rows clears it.
  const sel = new Set();
  let selAnchor = null;
  const showSel = () => document.querySelectorAll(".song[data-id]").forEach((r) => r.classList.toggle("sel", sel.has(r.dataset.id)));
  function clickSelect(e, row, id) {
    if (e.shiftKey && selAnchor && row.parentNode.querySelector(`.song[data-id="${selAnchor}"]`)) {
      const rows = [...row.parentNode.querySelectorAll(".song[data-id]")].map((r) => r.dataset.id);
      const [a, b] = [rows.indexOf(selAnchor), rows.indexOf(id)].sort((x, y) => x - y);
      if (!(e.metaKey || e.ctrlKey)) sel.clear();
      rows.slice(a, b + 1).forEach((x) => sel.add(x));
    } else if (e.metaKey || e.ctrlKey) {
      if (sel.has(id)) sel.delete(id); else sel.add(id);
      selAnchor = id;
    } else {
      const only = sel.size === 1 && sel.has(id);
      sel.clear(); if (!only) sel.add(id);
      selAnchor = id;
    }
    showSel();
  }
  document.addEventListener("click", (e) => { if (sel.size && !e.target.closest(".song[data-id]")) { sel.clear(); showSel(); } });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && sel.size && !e.target.closest("input, dialog")) { sel.clear(); showSel(); } });

  // ---- Rows --------------------------------------------------------------
  function songRow(item) {
    const row = el("div", "song" + (item.enabled === false && item.themeId ? " off" : "") + (sel.has(item.id) ? " sel" : ""));
    row.dataset.id = item.id;
    row.draggable = true;
    row.addEventListener("click", (e) => { if (!e.target.closest("button, input, label")) clickSelect(e, row, item.id); });
    row.addEventListener("dragstart", (e) => {
      if (e.target !== row) return;
      const ids = sel.has(item.id) ? S.items.filter((i) => sel.has(i.id)).map((i) => i.id) : [item.id];
      e.dataTransfer.setData(DRAG_TYPE, ids.join(",")); e.dataTransfer.effectAllowed = "move";
      if (ids.length > 1) {
        const ghost = el("div", "drag-ghost", plural(ids.length, "song"));
        document.body.append(ghost); e.dataTransfer.setDragImage(ghost, 16, 16);
        setTimeout(() => ghost.remove());
      }
    });
    // Turning a song off (rare) is a button among the others: the toy skips
    // it, and its name is struck through.
    const off = item.enabled === false;
    const on = el("button", "icon-btn toggle-off" + (off ? " active" : ""), ICON_BAN);
    on.title = off ? "Turned off: the toy skips this song. Click to turn it on" : "Turn off: the toy skips this song";
    on.setAttribute("aria-pressed", String(off));
    on.onclick = async () => { item.enabled = off; await saveItem(item); render(); };
    const play = el("button", "icon-btn", playingId === item.id ? "■" : "▶"); play.title = "Play";
    play.onclick = () => togglePlay(item);
    const name = nameInput(item.name, async (value) => {
      item.name = value; item.fileName = value + ".wav"; await saveItem(item); render();
    });
    // Text can be selected in the name without dragging the row.
    name.addEventListener("focus", () => { row.draggable = false; });
    name.addEventListener("blur", () => { row.draggable = true; });
    const meta = el("span", "meta", `${fmtDur(item.durationMs)} · ${fmtSize(item.size)}`);
    const tag = item.edited ? el("span", "tag edited", "Edited") : null;
    if (tag) tag.title = item.source ? "Changed from the library version" : "Changed from the file you added";
    const edit = el("button", "icon-btn", ICON_WAVE); edit.title = "Edit audio";
    edit.onclick = () => openEditor(item);
    const del = el("button", "icon-btn", ICON_TRASH); del.title = "Remove";
    del.onclick = async () => {
      if (playingId === item.id) togglePlay(item);
      if (store) await store.deleteItem(item.id);
      sel.delete(item.id); S.items = S.items.filter((i) => i.id !== item.id); render();
    };
    // An edited song can go back to the library's file or the file as added.
    let restore = null;
    if (item.edited) {
      restore = el("button", "icon-btn revert", "↺"); restore.title = "Restore"; restore.setAttribute("aria-label", item.source ? "Restore the library version" : "Restore the file you added");
      restore.onclick = () => restoreSong(item);
    }
    // Songs outside a theme are not exported, so they cannot be turned off.
    row.append(play, name, meta, ...(tag ? [tag] : []), ...(item.themeId ? [on] : []), edit, ...(restore ? [restore] : []), del);
    return row;
  }

  function themeDetails(id, device, summaryHtml, bodyNodes, onOpen) {
    const d = el("details", "theme" + (device ? " device" : ""));
    d.dataset.id = id;
    d.open = S.open.has(id);
    const summary = el("summary"); summary.append(Object.assign(el("div", "srow"), { innerHTML: summaryHtml }));
    d.append(summary);
    const body = el("div", "songs"); body.append(...bodyNodes); d.append(body);
    d.addEventListener("toggle", () => {
      if (d.open) S.open.add(id); else S.open.delete(id);
      if (d.open && onOpen) onOpen();
    });
    return d;
  }

  function band(kind, label, count) {
    const b = el("div", "band " + kind);
    b.innerHTML = `<span>${esc(label)}</span><span class="count">${esc(count || "")}</span>`;
    return b;
  }

  // "On the toy": a blue card with what the connected toy's SD card holds,
  // read-only. |count| is the head's summary; |body| the listing nodes.
  function toyBox(count, body) {
    const dv = S.device, box = el("div", "toybox");
    const on = dv.state === "on";
    const sub = on ? (dv.loading ? "Reading the toy's SD card…" : count)
      : dv.state === "connecting" ? "Connecting…" : "Connect to your SweetYaar to see what is on its SD card.";
    box.append(Object.assign(el("div", "toyboxhead"), { innerHTML:
      `<img src="../assets/studio/toy.png" alt=""><div><b><img class="bt" src="../assets/icon-bluetooth.svg" alt="">On the toy${on ? " · " + esc(dv.name) : ""}</b><p>${esc(sub)}</p></div>` }));
    if (on) box.append(...body);
    return box;
  }
  const songTitle = (file) => file.replace(/\.wav$/i, "");
  const sumOf = (songs, k) => songs.reduce((n, s) => n + s[k], 0);
  // One song or sound on the toy: name, then length and size; turned-off
  // songs are dimmed, unplayable ones say why.
  function toyLeaf(song, meta) {
    const row = el("div", "tleaf" + (song.enabled ? "" : " off"));
    if (!song.enabled) row.title = "Turned off: the toy skips this song";
    row.append(Object.assign(el("span", "name"), { textContent: songTitle(song.file) }));
    if (!song.ok) row.append(el("span", "tag warn", esc(song.error || "can't play")));
    if (meta) row.append(el("span", "meta", `${song.durationMs ? fmtDur(song.durationMs) + " · " : ""}${fmtSize(song.sizeBytes)}`));
    return row;
  }

  // ---- Library themes ----------------------------------------------------
  // The shared song themes (content.themes) in a lavender box at the top of
  // the working area. Each can be opened to play its songs; "+ Add to my
  // themes" downloads it as a new working-area theme (name, shuffle, credit,
  // songs), which can then be edited like any other.
  async function loadLibrary() {
    const L = S.library;
    L.loading = true; L.error = ""; render();
    try { L.themes = await content.themes(); }
    catch (e) { L.error = "Couldn't load the shared themes (" + e.message + ")."; }
    L.loading = false; render();
  }
  // Adds a library theme to My themes. If a theme copied from it is already
  // there (same library folder), that theme is updated instead: its library
  // songs are replaced by the library's current files, missing ones are
  // added, and the user's own songs and settings stay as they are.
  // Copies run one at a time: a theme added (or dragged in) while another is
  // copying waits in |queue| and is copied when its turn comes.
  function addLibraryTheme(lt) {
    const L = S.library;
    if (L.adding === lt.id || L.queue.includes(lt.id)) return;
    L.queue.push(lt.id); render();
    if (!L.adding) runLibraryQueue();
  }
  async function runLibraryQueue() {
    const L = S.library;
    while (L.queue.length && !L.adding) {
      const lt = L.themes.find((t) => t.id === L.queue[0]);
      L.queue.shift();
      if (!lt) continue;
      try { await copyLibraryTheme(lt); } catch (e) { L.adding = ""; render(); toast(`Couldn't add “${lt.name}”: ${e.message}`); }
    }
  }
  async function copyLibraryTheme(lt) {
    const L = S.library;
    const source = "c:songs/" + lt.id;
    const existing = S.themes.find((t) => t.source === source);
    L.adding = lt.id; render();
    toast(existing ? `Updating “${existing.name}”: downloading ${plural(lt.songs.length, "song")}…` : `Downloading ${plural(lt.songs.length, "song")}…`);
    const songs = [];
    try {
      for (const s of lt.songs) {
        const response = await fetch(content.songUrl(lt.id, s.file));
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const file = new File([await response.blob()], s.file, { type: "audio/wav" });
        songs.push({ s, file, durationMs: await durationMs(file) });
      }
    } catch (e) {
      L.adding = ""; render(); toast("Couldn't download the theme: " + e.message); return;
    }
    if (existing) {
      let replaced = 0, added = 0;
      for (const { s, file, durationMs: ms } of songs) {
        const src = `${source}/${s.file}`;
        const old = S.items.find((i) => i.kind === "song" && i.themeId === existing.id && i.source === src);
        if (old) {
          if (playingId === old.id) togglePlay(old);
          Object.assign(old, { name: s.name, fileName: s.file, size: file.size, durationMs: ms, blob: file, parts: [], edited: false });
          await saveItem(old); replaced++;
        } else {
          const item = { id: uid(), kind: "song", themeId: existing.id, name: s.name, fileName: s.file, size: file.size, durationMs: ms, blob: file, addedAt: stamp(), source: src };
          await saveItem(item); S.items.push(item); added++;
        }
      }
      S.open.add(existing.id);
      L.adding = ""; render();
      toast(`Updated “${existing.name}”: ${plural(replaced, "song")} replaced${added ? `, ${added} added` : ""}; your own songs were kept.`);
      return;
    }
    const theme = { id: uid(), name: lt.name, createdAt: Date.now(), enabled: true, shuffle: lt.shuffle, attribution: lt.credit, source };
    if (store) await store.putTheme(theme);
    S.themes.push(theme); S.open.add(theme.id);
    for (const { s, file, durationMs: ms } of songs) {
      const item = { id: uid(), kind: "song", themeId: theme.id, name: s.name, fileName: s.file, size: file.size, durationMs: ms, blob: file, addedAt: stamp(), source: `c:songs/${lt.id}/${s.file}` };
      await saveItem(item); S.items.push(item);
    }
    L.adding = ""; render();
    toast(`Added “${lt.name}” to your themes.`);
  }
  function libraryBox() {
    const L = S.library, box = el("div", "alib tlib");
    box.append(Object.assign(el("div", "libhead"), { innerHTML:
      `<img src="../assets/studio/library.png" alt=""><div><b>SweetYaar library</b><p>Ready-made themes to borrow.</p></div>` }));
    if (L.error) { box.append(el("div", "hint warn", esc(L.error))); return box; }
    if (L.loading) { box.append(el("div", "hint", "Loading the shared themes…")); return box; }
    if (!L.themes.length) { box.append(el("div", "hint", "No shared themes yet.")); return box; }
    for (const lt of L.themes) {
      const total = lt.songs.reduce((n, s) => n + s.durationMs, 0);
      const added = S.themes.some((t) => t.source === "c:songs/" + lt.id);
      const body = [];
      if (lt.attribution) body.push(attributionEl(lt.attribution));
      for (const s of lt.songs) {
        const key = `c:songs/${lt.id}/${s.file}`;
        const row = el("div", "song lib");
        const play = el("button", "icon-btn", playingId === key ? "■" : "▶"); play.title = "Play";
        play.onclick = () => togglePlay({ id: key, url: content.songUrl(lt.id, s.file) });
        row.append(play, Object.assign(el("span", "name"), { textContent: s.name }), el("span", "meta", `${fmtDur(s.durationMs)} · ${fmtSize(s.size)}`));
        body.push(row);
      }
      const busy = L.adding === lt.id, waiting = L.queue.includes(lt.id);
      const d = themeDetails("lib:" + lt.id, false,
        `<span class="tname"><span class="name">${esc(lt.name)}</span><span class="meta">${plural(lt.songs.length, "song")} · ${fmtDur(total)}${lt.shuffle ? " · shuffled" : ""}</span></span>${added ? '<span class="tag lib">Added</span>' : ""}<button class="btn small" data-act="add" title="${added ? "Update your copy: replaces its library songs with these, keeps songs you added" : "Add to my themes: downloads its songs to this computer"}"${busy || waiting ? " disabled" : ""}>${busy ? (added ? "Updating…" : "Adding…") : waiting ? "Waiting…" : added ? "↻ Update" : "+ Add"}</button>`, body);
      d.classList.add("lib");
      const summary = d.querySelector("summary");
      summary.draggable = true;
      summary.title = "Drag into My themes to add it";
      summary.addEventListener("dragstart", (e) => { e.dataTransfer.setData(LIB_TYPE, lt.id); e.dataTransfer.effectAllowed = "copy"; });
      d.querySelector('[data-act="add"]').onclick = (e) => { e.preventDefault(); addLibraryTheme(lt); };
      box.append(d);
    }
    return box;
  }

  // The themes shelf: the user's own area ("My themes", on this computer,
  // where files are dropped) beside the shared library, then the toy.
  let newThemeBtn = null;
  function renderThemes() {
    const list = $("#themesList"); list.replaceChildren();
    newThemeBtn = newThemeBtn || $("#newThemeBtn");
    const split = el("div", "tsplit");
    const mine = el("div", "local mine"); dropTarget(mine, "song", "", true);
    const head = el("div", "minehead");
    head.innerHTML = `<img src="../assets/studio/drop.png" alt=""><div><b>My themes</b><span class="count">${plural(S.themes.length, "theme")} · on this computer</span><p>Your own themes. Drop songs here, add a theme from the library, or record yourself, for example a theme of you reading stories to your child.</p></div>`;
    head.append(newThemeBtn);
    const local = el("div", "mytiles");
    mine.append(head, local);
    for (const theme of S.themes) {
      const songs = S.items.filter((i) => i.kind === "song" && i.themeId === theme.id);
      const total = songs.reduce((n, s) => n + s.durationMs, 0);
      const settings = themeSettings({ name: theme.name, credit: theme.attribution || "", enabled: theme.enabled !== false, shuffle: !!theme.shuffle }, false, async (change) => {
        Object.assign(theme, change); if (store) await store.putTheme(theme); render();
      });
      const d = themeDetails(theme.id, false,
        `<span class="name">${esc(theme.name)}</span>${theme.enabled === false ? '<span class="tag">off</span>' : ""}<span class="meta">${plural(songs.length, "song")}${songs.length ? " · " + fmtDur(total) : ""}</span><button class="btn small" data-act="add" title="Add audio files from this computer">+ Upload songs</button><button class="btn small" data-act="record" title="Record with the microphone, for example a story read aloud">🎙️ Record</button><button class="icon-btn" data-act="settings" title="Settings">${ICON_GEAR}</button><button class="icon-btn" data-act="delete" title="Remove theme">${ICON_TRASH}</button>`,
        [settings, ...(songs.length ? songs.map(songRow) : [el("div", "hint", "Empty. Drop audio files on this theme, use “+ Upload songs”, or record one.")])]);
      dropTarget(d, "song", theme.id);
      const sum = d.firstChild;
      sum.querySelector('[data-act="add"]').onclick = async (e) => {
        e.preventDefault(); const files = await pickFiles(true); if (files.length) addFiles("song", theme.id, files);
      };
      sum.querySelector('[data-act="record"]').onclick = (e) => { e.preventDefault(); newRecording("song", theme.id); };
      sum.querySelector('[data-act="settings"]').onclick = (e) => { e.preventDefault(); d.open = !d.open; };
      sum.querySelector('[data-act="delete"]').onclick = async (e) => {
        e.preventDefault();
        if (store) { for (const s of songs) await store.deleteItem(s.id); await store.deleteTheme(theme.id); }
        S.items = S.items.filter((i) => i.themeId !== theme.id); S.themes = S.themes.filter((t) => t.id !== theme.id); render();
      };
      local.append(d);
    }
    const loose = S.items.filter((i) => i.kind === "song" && !i.themeId);
    if (loose.length) {
      local.append(el("div", "subhead", "Not in a theme"));
      const flat = el("div", "flat"); flat.append(...loose.map(songRow)); local.append(flat);
    }
    if (!S.themes.length && !loose.length) local.append(el("div", "hint", "No themes yet. Start one with “+ New theme” or add one from the library."));
    mine.append(el("div", "dropnote", "<span><b>Drop your audio files here</b><br>or onto a theme · drag songs to reorder or move them (Shift or ⌘ selects several) · drag a whole theme in from the library</span>"));
    split.append(mine, libraryBox());
    list.append(split);

    const dv = S.device, tree = el("div", "ttree");
    if (!dv.loading && !dv.themes.length) tree.append(el("div", "hint", "No themes on the toy."));
    for (const t of dv.themes) {
      const songs = dv.songs[t.id];
      const d = el("details", "tnode" + (t.disabledByUser ? " off" : ""));
      d.open = S.open.has("dev:" + t.id);
      d.addEventListener("toggle", () => { if (d.open) S.open.add("dev:" + t.id); else S.open.delete("dev:" + t.id); });
      const meta = songs ? `${plural(songs.length, "song")} · ${fmtDur(sumOf(songs, "durationMs"))} · ${fmtSize(sumOf(songs, "sizeBytes"))}` : plural(t.total, "song");
      const sum = el("summary");
      sum.append(Object.assign(el("span", "name"), { textContent: t.name }));
      if (t.disabledByUser) sum.append(el("span", "tag", "off"));
      if (t.errors) sum.append(el("span", "tag warn", plural(t.errors, "problem")));
      sum.append(el("span", "meta", meta));
      d.append(sum);
      const kids = el("div", "tkids");
      kids.append(...(songs ? (songs.length ? songs.map((x) => toyLeaf(x, true)) : [el("div", "hint", "No songs.")]) : [el("div", "hint", "Loading…")]));
      d.append(kids);
      tree.append(d);
    }
    list.append(toyBox(plural(dv.themes.length, "theme"), [tree]));
  }

  // ---- Animals: prompts matched to animal sounds -------------------------
  // Left: spoken prompts (shared ones in one language, plus the user's own
  // files); right: animal sounds (shared plus the user's). Each matched pair
  // becomes one toy file on export; unmatched cards are left out.
  const MATCH_TYPE = "application/x-sweetyaar-match";
  const LANG_NAMES = { ar: "العربية", en: "English", es: "Español", fr: "Français", he: "עברית" };
  // A library card the user edited is replaced by its local copy (item.source).
  const localCard = (item) => ({ key: "l:" + item.id, name: item.name, item, tag: item.source || item.edited ? "Edited" : "Mine" });
  // Library cards with edited copies in their place, then the user's own files.
  function withCopies(library, mine) {
    const bySource = new Map(mine.filter((i) => i.source).map((i) => [i.source, i]));
    const out = library.map((card) => bySource.has(card.key) ? localCard(bySource.get(card.key)) : card);
    const shown = new Set(out.map((c) => c.key));
    for (const item of mine) if (!shown.has("l:" + item.id)) out.push(localCard(item));
    return out;
  }
  function promptCards() {
    const c = S.cloud, meta = S.animalsMeta, out = [];
    const mine = S.items.filter((i) => i.kind === "prompt");
    if (!meta.cleared && c.promptsLang === meta.lang) {
      for (const f of c.prompts) out.push({ key: `c:${meta.lang}:${f.name}`, kind: "prompt", name: f.name, url: content.promptUrl(meta.lang, f.name), tag: meta.lang.toUpperCase() });
    }
    return withCopies(out, mine);
  }
  function soundCards() {
    const library = S.cloud.sounds.map((f) => ({ key: "c:" + f.name, kind: "animal", name: f.name, url: content.soundUrl(f.name) }));
    return withCopies(library, S.items.filter((i) => i.kind === "animal"));
  }
  // Edits a library prompt or sound: downloads a local copy that replaces the
  // library card (keeping its match) and opens it in the wave editor.
  async function editLibraryCard(card) {
    toast("Downloading a copy…");
    let blob;
    try {
      const response = await fetch(card.url);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      blob = await response.blob();
    } catch (e) { toast("Couldn't download it: " + e.message); return; }
    const fileName = card.name + ".wav", file = new File([blob], fileName, { type: "audio/wav" });
    // The copy is not kept until it is saved (like a new recording): leaving
    // the editor without saving leaves the library card as it was.
    const item = {
      id: uid(), kind: card.kind, themeId: "", name: card.name, fileName, size: file.size,
      durationMs: await durationMs(file), blob: file, addedAt: stamp(), source: card.key, unsaved: true
    };
    if (playingId === card.key) stopAudio();
    await openEditor(item);
  }
  // A saved library copy takes the library card's place, and its match.
  async function adoptLibraryCopy(item) {
    const m = S.animalsMeta.matches, key = item.source, newKey = "l:" + item.id;
    const partner = item.kind === "prompt" ? m[key] : Object.keys(m).find((p) => m[p] === key);
    let matches = AM.unlink(m, key);
    if (partner) matches = item.kind === "prompt" ? AM.link(matches, newKey, partner) : AM.link(matches, partner, newKey);
    if (isOff(key)) { markOff(key, false); markOff(newKey, true); }   // an unmatched sound's copy stays unmatched
    await setMatches(matches);
  }
  // How each animal file is built: [lead-in] question [pause] sound [tail].
  // Each question and sound can have its edge silence trimmed (at a fixed
  // level) and be levelled to one loudness shared by the whole pack, so every
  // file matches every other; |balance| makes questions louder (or quieter)
  // than sounds by that many dB. The joined file is then limited. The tail is
  // fixed.
  // Two steps, shown in this order: 1 cleans up each recording, 2 puts the
  // toy file together (its gaps are exact because step 1 cut the recordings'
  // own quiet edges).
  const BUILD_SETTINGS = [
    { key: "trimQuestion", step1: true, label: "Cut the quiet start and end of each question", def: true, check: true },
    { key: "trimSound", step1: true, label: "Cut the quiet start and end of each animal sound", def: true, check: true },
    { key: "evenVolume", step1: true, label: "Same volume for all", title: "Level every question and sound to one loudness, the same for all the animal files", def: true, check: true },
    // Shown on the Same volume row as "Sound <slider> Question": right is a louder question.
    { key: "balance", label: "Question louder than the sound by", def: 0, min: -6, max: 6, step: 1, unit: "dB", on: "evenVolume" },
    { key: "leadIn", label: "Wait before the question", def: 0.1, min: 0, max: 1, step: 0.1, unit: "s" },
    { key: "pause", label: "Gap between question and sound", def: 0.7, min: 0, max: 2, step: 0.1, unit: "s" }
  ];
  const BUILD_TAIL_SEC = 0.3;
  const BUILD_TRIM_DB = -50;          // Trim silence's Normal level
  const BUILD_TARGET_DB = -18;        // Volume level's Standard loudness, shared by the whole pack
  const BUILD_CEILING_DB = -1;        // limiter on each joined file
  const buildSettings = () => Object.fromEntries(BUILD_SETTINGS.map((d) => [d.key, S.animalsMeta.build?.[d.key] ?? d.def]));
  // Levelling targets for one question and one sound: the balance is split
  // between them so the pack's average loudness stays at BUILD_TARGET_DB.
  function buildTargets(settings = buildSettings()) {
    if (!settings.evenVolume) return null;
    return { questionDb: BUILD_TARGET_DB + settings.balance / 2, soundDb: BUILD_TARGET_DB - settings.balance / 2 };
  }
  function renderBuildSettings() {
    const box = el("div", "abuild");
    const head = el("div", "abuildhead", "<b>Building the animal files</b>");
    const values = buildSettings();
    const changed = BUILD_SETTINGS.some((d) => values[d.key] !== d.def);
    const reset = el("button", "btn small", "Reset all");
    reset.disabled = !changed;
    reset.onclick = async () => { S.animalsMeta.build = {}; await saveAnimalsMeta(); render(); };
    head.append(reset);
    box.append(head);
    // A setting's own ↺: shown only while it differs from its default.
    const backTo = (d, isDefault) => {
      const b = el("button", "icon-btn areset", "↺");
      b.type = "button"; b.title = `Back to the default (${d.check ? (d.def ? "on" : "off") : show(d, d.def)})`;
      b.setAttribute("aria-label", b.title);
      b.style.visibility = isDefault ? "hidden" : "visible";
      b.onclick = async (e) => {
        e.preventDefault();
        const build = { ...(S.animalsMeta.build || {}) }; delete build[d.key];
        S.animalsMeta.build = build; await saveAnimalsMeta(); render();
      };
      return b;
    };
    const save = async (key, value) => {
      S.animalsMeta.build = { ...(S.animalsMeta.build || {}), [key]: value };
      await saveAnimalsMeta();
    };
    const show = (d, v) => (d.step < 1 ? Number(v).toFixed(1) : (v > 0 ? "+" : "") + Number(v)) + " " + d.unit;
    // The finished file to scale: [wait] Question [gap] Sound [tail]. The
    // question and sound get a typical length; the gaps follow the sliders.
    const strip = el("div", "astrip");
    strip.setAttribute("aria-hidden", "true");
    const drawStrip = () => {
      const part = (cls, sec, text) => {
        const p = el("span", cls, esc(text)); p.style.flexGrow = String(Math.max(sec, 0.001)); return p;
      };
      // A gap of 0 s is left out, so the parts touch.
      const gap = (sec) => (Number(sec) > 0 ? [part("agapsec", sec, Number(sec).toFixed(1) + " s")] : []);
      strip.replaceChildren(...gap(values.leadIn), part("apart q", 1.4, "Question"), ...gap(values.pause), part("apart s", 1.6, "Sound"), ...gap(BUILD_TAIL_SEC));
    };
    const slider = (d, off = false) => {
      const i = el("input"); i.type = "range"; i.min = d.min; i.max = d.max; i.step = d.step; i.value = values[d.key]; i.disabled = off;
      // A tick under the track marks the default.
      const ticks = el("datalist"); ticks.id = "adef-" + d.key;
      ticks.append(Object.assign(document.createElement("option"), { value: String(d.def) }));
      i.setAttribute("list", ticks.id); box.append(ticks);
      const out = el("span", "unit", show(d, values[d.key]));
      const back = backTo(d, values[d.key] === d.def);
      i.oninput = () => {
        out.textContent = show(d, i.value); values[d.key] = Number(i.value); drawStrip();
        back.style.visibility = Number(i.value) === d.def ? "hidden" : "visible";
      };
      i.onchange = async () => { await save(d.key, Number(i.value)); reset.disabled = !BUILD_SETTINGS.some((x) => values[x.key] !== x.def); };
      return [i, out, back];
    };
    const step = (n, title, note) => {
      const g = el("div", "abuildstep");
      g.append(el("div", "abuildsub", `<span class="anum1">${n}</span><b>${esc(title)}</b><span class="meta">${esc(note)}</span>`));
      const grid = el("div", "abuildgrid"); g.append(grid); box.append(g);
      return grid;
    };
    const grid1 = step(1, "Clean up each recording", "before they are joined");
    let grid = grid1, grid2 = null;
    for (const d of BUILD_SETTINGS) {
      if (d.on) continue;   // drawn on its checkbox's row
      if (!d.step1 && !grid2) { grid2 = grid = step(2, "Put the toy file together", "what the child hears"); }
      if (d.check) {
        const row = el("div", "acheck");
        const l = el("label", "");
        if (d.title) l.title = d.title;
        const i = el("input"); i.type = "checkbox"; i.checked = !!values[d.key];
        i.onchange = async () => { await save(d.key, i.checked); render(); };
        l.append(i, el("span", "", esc(d.label)));
        row.append(l, backTo(d, values[d.key] === d.def));
        for (const sub of BUILD_SETTINGS.filter((x) => x.on === d.key)) {
          const [i2, out, back] = slider(sub, !values[d.key]);
          i2.title = sub.label; i2.setAttribute("aria-label", sub.label);
          const bal = el("span", "abalance" + (values[d.key] ? "" : " off"));
          bal.append(el("span", "", "Sound"), i2, el("span", "", "Question"), out, back);
          row.append(bal);
        }
        grid.append(row);
        continue;
      }
      const l = el("label", "anum");
      l.append(el("span", "", esc(d.label)), ...slider(d));
      grid.append(l);
    }
    drawStrip();
    grid2.parentNode.append(strip);
    return box;
  }
  async function saveAnimalsMeta() { if (store) await store.putTheme(S.animalsMeta); }
  async function setMatches(matches) { S.animalsMeta.matches = matches; await saveAnimalsMeta(); render(); }
  function rematch() { return setMatches(AM.autoMatch(promptCards(), soundCards(), S.animalsMeta.matches, S.animalsMeta.off || [])); }
  // Animal sounds the user unmatched (by sound key, the same in every
  // language): name matching leaves them alone until they are matched by hand.
  const isOff = (soundKey) => (S.animalsMeta.off || []).includes(soundKey);
  function markOff(soundKey, off) {
    if (!soundKey) return;
    const set = new Set(S.animalsMeta.off || []);
    if (off) set.add(soundKey); else set.delete(soundKey);
    S.animalsMeta.off = [...set];
  }

  async function loadCloud() {
    const c = S.cloud;
    c.loading = true; c.error = ""; render();
    try {
      const [sounds, languages, promptsAttribution] = await Promise.all([content.sounds(), content.languages(), content.promptsAttribution()]);
      c.sounds = sounds.files; c.languages = languages;
      c.soundsAttribution = sounds.attribution; c.promptsAttribution = promptsAttribution;
      if (!languages.includes(S.animalsMeta.lang) && languages.length) S.animalsMeta.lang = languages.includes("en") ? "en" : languages[0];
      await loadPrompts(S.animalsMeta.lang);
    } catch (e) {
      c.error = "Couldn't load the shared animal sounds (" + e.message + ").";
    }
    c.loading = false;
    await rematch();
  }
  async function loadPrompts(lang) {
    const c = S.cloud;
    c.prompts = await content.prompts(lang); c.promptsLang = lang;
  }
  async function chooseLanguage(lang) {
    S.animalsMeta.lang = lang; S.animalsMeta.cleared = false;
    try { await loadPrompts(lang); } catch (e) { toast("Couldn't load those prompts."); }
    await rematch();
  }
  // Hides the library prompts; the user's own and edited prompts stay.
  async function clearPrompts() {
    stopAudio();
    S.animalsMeta.cleared = true;
    await setMatches(AM.prune(S.animalsMeta.matches, promptCards(), soundCards()));
  }

  // A name that wraps after _ - . and spaces, and inside runs over 12 letters,
  // so a long name wraps whole words while the card's buttons stay on one line.
  const breakable = (name) => String(name).split(/(?<=[_.\- ])/).map((part) => part.match(/.{1,12}/gsu).map(esc).join("<wbr>")).join("<wbr>");
  function matchCard(card, side, partnerKey) {
    const row = el("div", "acard" + (partnerKey ? " matched" : "") + (card.item ? "" : " lib"));
    row.dataset.key = card.key; row.dataset.side = side;
    row.draggable = true;
    row.addEventListener("dragstart", (e) => { e.dataTransfer.setData(MATCH_TYPE, JSON.stringify({ side, key: card.key })); e.dataTransfer.effectAllowed = "link"; });
    row.addEventListener("dragover", (e) => {
      if (![...e.dataTransfer.types].includes(MATCH_TYPE)) return;
      e.preventDefault(); e.stopPropagation();
      if (hovered !== row) { clearHover(); hovered = row; row.classList.add("over"); }
    });
    row.addEventListener("dragleave", (e) => { if (!row.contains(e.relatedTarget) && hovered === row) clearHover(); });
    row.addEventListener("drop", (e) => {
      const raw = e.dataTransfer.getData(MATCH_TYPE);
      if (!raw) return;
      e.preventDefault(); e.stopPropagation(); clearHover();
      const from = JSON.parse(raw);
      if (from.side === side) { toast(side === "prompt" ? "Drop a prompt on an animal sound." : "Drop an animal sound on a prompt."); return; }
      const promptKey = side === "prompt" ? card.key : from.key, soundKey = side === "prompt" ? from.key : card.key;
      markOff(soundKey, false);
      setMatches(AM.link(S.animalsMeta.matches, promptKey, soundKey));
    });
    const play = el("button", "icon-btn", playingId === card.key ? "■" : "▶"); play.title = "Play";
    play.onclick = () => togglePlay(card.item ? { id: card.key, blob: card.item.blob } : { id: card.key, url: card.url });
    const name = el("span", "name", breakable(card.name));
    const acts = el("span", "acts");
    row.append(play, name, acts);
    // A matched animal sound can play the whole animal file (its prompt, then
    // the sound): a labelled pill, unlike the round ▶ that plays the sound alone.
    if (side === "sound" && partnerKey) {
      const id = "pair:" + partnerKey, on = playingId === id;
      const both = el("button", "pairplay" + (on ? " playing" : ""), on ? "■ Stop" : "▶ Play both");
      both.title = "Play the whole animal file: the prompt, then this sound";
      both.onclick = () => playPair(id, partnerKey, card.key);
      acts.append(both);
    }
    if (card.tag) acts.append(el("span", "tag" + (card.tag === "Edited" ? " edited" : card.item ? "" : " lib"), esc(card.tag)));
    if (card.item) {
      const edit = el("button", "icon-btn", ICON_WAVE); edit.title = "Edit audio"; edit.onclick = () => openEditor(card.item);
      // An edited library copy only goes back to the library version; the
      // user's own files are really removed.
      const back = !!card.item.source;
      const del = el("button", "icon-btn" + (back ? " revert" : ""), back ? "↺" : ICON_TRASH);
      del.title = back ? "Restore" : "Remove";
      del.setAttribute("aria-label", del.title);
      del.onclick = async () => {
        if (playingId === card.key) stopAudio();
        if (store) await store.deleteItem(card.item.id);
        S.items = S.items.filter((i) => i.id !== card.item.id);
        S.animalsMeta.matches = AM.unlink(S.animalsMeta.matches, card.key);
        if (back && isOff(card.key)) { markOff(card.key, false); markOff(card.item.source, true); }   // the library card stays unmatched too
        await rematch();
      };
      // The user's own edited file can also go back to the file as added.
      if (!back && card.item.edited) {
        const restore = el("button", "icon-btn revert", "↺"); restore.title = "Restore"; restore.setAttribute("aria-label", "Restore the file you added");
        restore.onclick = () => restoreOriginal(card.item);
        acts.append(edit, restore, del);
      } else acts.append(edit, del);
    } else {
      const edit = el("button", "icon-btn", ICON_WAVE); edit.title = "Edit a copy on this computer"; edit.onclick = () => editLibraryCard(card);
      acts.append(edit);
    }
    if (partnerKey) {
      const off = el("button", "icon-btn unlink", "×"); off.title = "Unmatch";
      // The sound stays unmatched (also after a language change or reload)
      // until the user matches it again.
      off.onclick = () => {
        markOff(side === "sound" ? card.key : partnerKey, true);
        setMatches(AM.unlink(S.animalsMeta.matches, card.key));
      };
      acts.append(off);
    }
    return row;
  }

  function drawLinks(box) {
    const svgEl = box.querySelector("svg.links");
    if (!svgEl) return;
    const base = box.getBoundingClientRect();
    svgEl.setAttribute("width", base.width); svgEl.setAttribute("height", base.height);
    let paths = "";
    for (const [p, s] of Object.entries(S.animalsMeta.matches)) {
      const a = box.querySelector(`.acard[data-side="prompt"][data-key="${CSS.escape(p)}"]`);
      const b = box.querySelector(`.acard[data-side="sound"][data-key="${CSS.escape(s)}"]`);
      if (!a || !b) continue;
      const ra = a.getBoundingClientRect(), rb = b.getBoundingClientRect();
      const x1 = ra.right - base.left, y1 = ra.top + ra.height / 2 - base.top;
      const x2 = rb.left - base.left, y2 = rb.top + rb.height / 2 - base.top, mx = (x1 + x2) / 2;
      paths += `<path d="M${x1} ${y1} C${mx} ${y1} ${mx} ${y2} ${x2} ${y2}"/><circle cx="${x1}" cy="${y1}" r="3"/><circle cx="${x2}" cy="${y2}" r="3"/>`;
    }
    svgEl.innerHTML = paths;
  }
  // Builds a matched pair the way export does (current build settings) and plays it.
  async function playPair(id, promptKey, soundKey) {
    if (playingId === id) { togglePlay({ id }); return; }
    const prompt = promptCards().find((c) => c.key === promptKey), sound = soundCards().find((c) => c.key === soundKey);
    if (!prompt || !sound) return;
    try {
      const [question, animal] = await Promise.all([cardChannels(prompt), cardChannels(sound)]);
      const blob = new Blob([A.encodeWav([X.buildAnimal(question, animal, buildSettings(), RATE)], RATE)], { type: "audio/wav" });
      togglePlay({ id, blob });
    } catch (e) { toast("Couldn't play it: " + e.message); }
  }
  window.addEventListener("resize", () => { const box = $(".amatch"); if (box) drawLinks(box); });
  // Anything that moves the cards (names wrapping, fonts
  // loading) changes the matching area's size: redraw the lines then too.
  const linksObserver = typeof ResizeObserver === "function" ? new ResizeObserver(() => { const box = $(".amatch"); if (box) drawLinks(box); }) : null;

  function renderAnimals() {
    const list = $("#animalsList"); list.replaceChildren();
    const meta = S.animalsMeta, c = S.cloud;
    const prompts = promptCards(), sounds = soundCards();
    const matches = AM.prune(meta.matches, prompts, sounds);
    const soundToPrompt = new Map(Object.entries(matches).map(([p, s]) => [s, p]));
    const local = el("div", "local");
    local.append(band("local", "On this computer", `${plural(Object.keys(matches).length, "animal")} matched`));

    const settings = el("div", "tmeta");
    settings.append(checkbox("Shuffle animal sounds", meta.shuffle, false, async (v) => { meta.shuffle = v; await saveAnimalsMeta(); render(); }));
    local.append(settings);

    if (c.error) local.append(el("div", "hint warn", esc(c.error)));
    else if (c.loading) local.append(el("div", "hint", "Loading the shared animal sounds…"));

    // Two columns: a top part each (title, library and add buttons), then the
    // cards, which start on the same line on both sides.
    const box = el("div", "amatch");
    const leftTop = el("div", "atop"), rightTop = el("div", "atop");
    const left = el("div", "acol"), right = el("div", "acol");
    const addBtn = (label, kind) => {
      const add = el("button", "btn small", label);
      add.onclick = async () => { const files = await pickFiles(true); if (files.length) addFiles(kind, "", files); };
      return add;
    };
    leftTop.append(el("div", "acolhead", `<b>Prompts</b><span class="meta">${prompts.length}</span>`));
    const lib = el("div", "alib");
    lib.append(el("div", "alabel", "Library prompts"));
    if (c.promptsAttribution) lib.append(attributionEl(c.promptsAttribution));
    const rec = el("button", "btn small", "🎙️ Record prompts");
    rec.title = "Record a prompt with the microphone"; rec.onclick = () => newRecording("prompt");
    const own = el("div", "abar"); own.append(addBtn("+ Add prompts", "prompt"), rec);
    leftTop.append(own);
    // Language chooser: one segmented control, nothing pressed once cleared.
    const langs = el("div", "abar");
    const seg = el("div", "segmented"); seg.setAttribute("role", "group"); seg.setAttribute("aria-label", "Language");
    for (const lang of c.languages) {
      const b = el("button", "", esc(LANG_NAMES[lang] || lang.toUpperCase()));
      b.setAttribute("aria-pressed", String(!meta.cleared && meta.lang === lang));
      b.onclick = () => chooseLanguage(lang);
      seg.append(b);
    }
    const clear = el("button", "btn small", ICON_TRASH + "<span>Clear library prompts</span>"); clear.onclick = clearPrompts;
    clear.disabled = !prompts.some((p) => !p.item);
    langs.append(seg, el("span", "spacer"), clear);
    lib.append(langs);
    leftTop.append(lib);
    rightTop.append(el("div", "acolhead", `<b>Animal sounds</b><span class="meta">${sounds.length}</span>`));
    const ownSounds = el("div", "abar"); ownSounds.append(addBtn("+ Add animal sounds", "animal"));
    rightTop.append(ownSounds);
    if (c.sounds.length) {
      const slib = el("div", "alib");
      slib.append(el("div", "alabel", "Library sounds"));
      if (c.soundsAttribution) slib.append(attributionEl(c.soundsAttribution));
      rightTop.append(slib);
    }
    for (const p of prompts) left.append(matchCard(p, "prompt", matches[p.key]));
    for (const s of sounds) right.append(matchCard(s, "sound", soundToPrompt.get(s.key)));
    if (!prompts.length) left.append(el("div", "hint", meta.cleared ? "No prompts. Pick a language, drop your own recordings here, or record them." : "Drop prompt recordings here."));
    if (!sounds.length && !c.loading) right.append(el("div", "hint", "Drop animal sounds here."));
    dropTarget(left, "prompt", ""); dropTarget(right, "animal", "");
    box.append(leftTop, el("div", "agap"), rightTop, left, el("div", "agap"), right);
    box.insertAdjacentHTML("beforeend", '<svg class="links" aria-hidden="true"></svg>');
    local.append(box);
    local.append(el("p", "anote", "Drag a prompt onto an animal sound (or the other way) to match them. Same-named files match by themselves. Only matched animals are exported."));
    local.append(renderBuildSettings());
    list.append(local);
    requestAnimationFrame(() => drawLinks(box));
    if (linksObserver) { linksObserver.disconnect(); linksObserver.observe(box); }

    const dv = S.device, chips = el("div", "tchips");
    chips.append(...dv.animals.map((x) => toyLeaf(x, false)));
    if (!dv.loading && !dv.animals.length) chips.append(el("div", "hint", "No animal sounds on the toy."));
    list.append(toyBox(`${plural(dv.animals.length, "animal")} · ${fmtSize(sumOf(dv.animals, "sizeBytes"))}${dv.animalsTheme?.shuffle ? " · shuffled" : ""}`, [chips]));
  }

  function render() {
    renderDeviceButton(); renderThemes(); renderAnimals(); renderToySettings();
  }

  // ---- Toy settings (config.json) ------------------------------------------
  // Kept in the settings store as "toyConfig", with Studio theme ids ("" until
  // one is chosen); export turns them into card folder ids.
  const TOY_DEFAULTS = SweetYaarExport.TOY_DEFAULTS;
  const toyValue = () => {
    const t = S.toy || {}, D = TOY_DEFAULTS;
    return { ...D, ...t, bedtime: { ...D.bedtime, ...(t.bedtime || {}) }, sleep: { ...D.sleep, ...(t.sleep || {}) } };
  };
  async function saveToy(change) {
    const v = toyValue();
    S.toy = { ...v, ...change, bedtime: { ...v.bedtime, ...(change.bedtime || {}) }, sleep: { ...v.sleep, ...(change.sleep || {}) } };
    if (store) { try { await store.putSetting("toyConfig", S.toy); } catch { /* kept for this visit only */ } }
    const reset = $("#toySettings .toyhead .btn");
    if (reset) reset.disabled = toyIsDefault();
  }
  // Every value equals the firmware default (theme choices left to the toy).
  function toyIsDefault() {
    const v = toyValue(), D = TOY_DEFAULTS;
    const same = (a, b) => Object.keys(b).every((k) => a[k] === b[k]);
    return v.defaultVolumePct === D.defaultVolumePct && v.defaultTheme === D.defaultTheme && same(v.bedtime, D.bedtime) && same(v.sleep, D.sleep);
  }
  // A theme choice always names one of the themes with songs: the chosen
  // one while it is there, else the Lullabies library theme, else the first.
  function toyTheme(id) {
    const themes = exportThemes();
    return (themes.find((t) => t.id === id) || themes.find((t) => t.source === "c:songs/lullabies") || themes[0])?.id || "";
  }
  // The config.json keys for an export, with the themes' card folder ids
  // (left out only when no theme is exported).
  function toyExportSettings(plan) {
    const v = toyValue(), folder = (id) => plan.themes.find((t) => t.theme.id === toyTheme(id))?.id || "";
    return SweetYaarExport.toySettings({ ...v, defaultTheme: folder(v.defaultTheme), bedtime: { ...v.bedtime, theme: folder(v.bedtime.theme) } });
  }
  function renderToySettings() {
    const box = $("#toySettings");
    if (!box || box.contains(document.activeElement)) return;   // don't rebuild under the user's hands
    const v = toyValue();
    const head = el("div", "toyhead"), reset = el("button", "btn small", "Back to the defaults");
    reset.disabled = toyIsDefault();
    reset.onclick = async () => { reset.blur(); S.toy = {}; if (store) { try { await store.putSetting("toyConfig", {}); } catch { /* none */ } } renderToySettings(); };
    head.append(reset);
    const row = (label, ...controls) => { const r = el("label", "toyrow"); r.append(el("span", "", esc(label)), ...controls); return r; };
    const slider = (value, onSave) => {
      const i = el("input"); i.type = "range"; i.min = 0; i.max = 100; i.step = 5; i.value = value;
      const out = el("span", "unit", value + "%");
      i.oninput = () => { out.textContent = i.value + "%"; };
      i.onchange = () => onSave(Number(i.value));
      return [i, out];
    };
    const themeSelect = (value, onSave) => {
      const sel = el("select"), themes = exportThemes();
      for (const t of themes) sel.append(Object.assign(document.createElement("option"), { value: t.id, textContent: t.name }));
      if (!themes.length) { sel.append(Object.assign(document.createElement("option"), { value: "", textContent: "Add a theme with songs first" })); sel.disabled = true; }
      sel.value = toyTheme(value);
      sel.onchange = () => onSave(sel.value);
      return [sel, el("span", "unit", "")];
    };
    const time = (value, onSave) => { const i = el("input"); i.type = "time"; i.value = value; i.onchange = () => i.value && onSave(i.value); return [i, el("span", "unit", "")]; };
    const minutes = (sec, onSave) => {
      const i = el("input"); i.type = "number"; i.min = 1; i.max = 1440; i.step = 1; i.value = Math.max(1, Math.round(sec / 60));
      i.onchange = () => { const m = Math.min(1440, Math.max(1, Math.round(Number(i.value) || 1))); i.value = m; onSave(m * 60); };
      const both = el("span", "toymin"); both.append(i, el("span", "unit", "min"));
      return [both, el("span", "", "")];
    };
    const check = (label, on, onSave) => {
      const l = el("label", "toycheck"), i = el("input"); i.type = "checkbox"; i.checked = on;
      i.onchange = () => { l.closest(".toycard").classList.toggle("off", !i.checked); onSave(i.checked); };
      l.append(i, el("span", "", esc(label)));
      return l;
    };
    const card = (title, hint, ...rows) => { const c = el("div", "toycard"); c.append(el("h3", "", esc(title)), el("p", "hint", esc(hint)), ...rows); return c; };

    const start = card("When the toy starts", "Volume and theme after it is switched on.",
      row("Volume", ...slider(v.defaultVolumePct, (n) => saveToy({ defaultVolumePct: n }))),
      row("Theme", ...themeSelect(v.defaultTheme, (id) => saveToy({ defaultTheme: id }))));
    const bed = card("Bedtime", "Between these times the toy plays the Bedtime theme, more quietly.",
      check("Use Bedtime", v.bedtime.enabled, (on) => saveToy({ bedtime: { enabled: on } })),
      row("From", ...time(v.bedtime.startTime, (t) => saveToy({ bedtime: { startTime: t } }))),
      row("Until", ...time(v.bedtime.endTime, (t) => saveToy({ bedtime: { endTime: t } }))),
      row("Theme", ...themeSelect(v.bedtime.theme, (id) => saveToy({ bedtime: { theme: id } }))),
      row("Volume at most", ...slider(v.bedtime.volumeCapPct, (n) => saveToy({ bedtime: { volumeCapPct: n } }))));
    bed.classList.toggle("off", !v.bedtime.enabled);
    const sleep = card("Sleep", "The toy sleeps to save its battery when nothing happens.",
      check("Sleep when idle", v.sleep.enabled, (on) => saveToy({ sleep: { enabled: on } })),
      row("After", ...minutes(v.sleep.normalIdleSec, (sec) => saveToy({ sleep: { normalIdleSec: sec } }))),
      row("After a shake only", ...minutes(v.sleep.vibrationWakeIdleSec, (sec) => saveToy({ sleep: { vibrationWakeIdleSec: sec } }))),
      row("With the remote idle", ...minutes(v.sleep.bleIdleSec, (sec) => saveToy({ sleep: { bleIdleSec: sec } }))));
    sleep.classList.toggle("off", !v.sleep.enabled);
    const grid = el("div", "toygrid");
    grid.append(start, bed, sleep);
    box.replaceChildren(head, grid);
  }

  // ---- Device ------------------------------------------------------------
  // Reads the theme list and the animal sounds, then every theme's songs
  // one by one (the tree shows each theme's length and size).
  async function loadDevice() {
    const dv = S.device = { state: "on", name: client.name, themes: [], songs: {}, animals: [], loading: true };
    render();
    try {
      const themes = await client.scanThemes();
      const special = themes.find((t) => t.special);
      dv.themes = themes.filter((t) => !t.special);
      dv.animalsTheme = special || null;
      if (special) dv.animals = await client.scanSongs(special.id);
    } catch (e) {
      toast(e.userMessage || "Couldn't read the toy's content.");
    }
    render();
    for (const t of dv.themes) {
      if (S.device !== dv) return;   // disconnected meanwhile
      try { dv.songs[t.id] = await client.scanSongs(t.id); } catch (e) { dv.songs[t.id] = []; toast(e.userMessage || "Couldn't read a theme on the toy."); }
      render();
    }
    dv.loading = false;
    render();
  }
  // Connecting (from the button, or to the remembered toy at startup) can be
  // stopped with the ✕ beside the button, as in the parent remote.
  let deviceAbort = null;
  async function connectDevice(how) {
    const abort = new AbortController();
    deviceAbort = abort; S.device.state = "connecting"; render();
    let dev = null;
    try {
      dev = how === "remembered" ? await client.reconnect({ signal: abort.signal, userAgent: navigator.userAgent || "" })
        : await client.connect({ signal: abort.signal });
    } catch (e) { if (!abort.signal.aborted) toast(e.userMessage || "Couldn't connect."); }
    if (deviceAbort === abort) deviceAbort = null;
    if (abort.signal.aborted) return;   // Stop already reset the button
    if (dev) { await loadDevice(); return; }
    S.device.state = "off"; render();
  }
  $("#deviceBtn").addEventListener("click", async () => {
    if (S.device.state === "on") { client.disconnect(); S.device = { state: "off", name: "", themes: [], songs: {}, animals: [], loading: false }; render(); return; }
    await connectDevice("chooser");
  });
  $("#deviceStop").addEventListener("click", () => {
    if (!deviceAbort) return;
    deviceAbort.abort(); deviceAbort = null;
    client.disconnect();
    S.device.state = "off"; render();
  });

  // ---- Buttons -----------------------------------------------------------
  // A new theme is created at once, opened, with its name selected for typing.
  $("#newThemeBtn").addEventListener("click", async () => {
    const names = new Set(S.themes.map((t) => t.name));
    let name = "New theme";
    for (let n = 2; names.has(name); n++) name = `New theme ${n}`;
    const theme = await newTheme(name);
    const input = $(`details[data-id="${theme.id}"] .tmeta input`);
    if (input) { input.scrollIntoView({ block: "nearest" }); input.focus(); input.select(); }
  });
  // ---- Export --------------------------------------------------------------
  // Writes the card layout into a chosen folder (the SD card in a reader, or
  // any folder): animals/ with one built file per matched pair and its
  // metadata.json, songs/<id>/ for each working-area theme with songs (its
  // settings in metadata.json, its songs as toy WAVs) and the off themes in
  // config.json's disabledThemes. The dialog lists what the folder holds and
  // what the export writes; everything else is kept or deleted as chosen.
  // The folder is remembered, so the next export only needs the browser's permission.
  const X = SweetYaarExport;
  const EX = { dir: null, remembered: false, busy: false, loaded: false, scan: null, scanError: "", access: "", scanRun: 0, progress: null };
  const themeSongs = (theme) => S.items.filter((i) => i.kind === "song" && i.themeId === theme.id);
  const exportThemes = () => S.themes.filter((t) => themeSongs(t).length);
  const exportPairs = () => AM.pairs(S.animalsMeta.matches, promptCards(), soundCards());
  async function cardChannels(card) {
    let blob = card.item?.blob;
    if (!blob) {
      const response = await fetch(card.url);
      if (!response.ok) throw new Error(`couldn't download ${card.name} (HTTP ${response.status})`);
      blob = await response.blob();
    }
    return decodeAudio(blob);
  }
  // Sizes before writing: a song already in WAV keeps about its size; other
  // formats become 44.1 kHz 16-bit (counted as stereo). An animal file is
  // mono: lead-in, both parts (1.5 s when not known yet), pause and tail.
  const songBytes = (x) => /\.wav$/i.test(x.fileName || "") || /wav/.test(x.blob?.type || "") ? x.size || 0 : Math.round((x.durationMs || 0) / 1000 * RATE) * 4 + 44;
  const animalBytes = (pair, s) => 44 + 2 * Math.round((s.leadIn + s.pause + X.TAIL_SEC) * RATE +
    ((pair.prompt.item?.durationMs || 1500) + (pair.sound.item?.durationMs || 1500)) / 1000 * RATE);
  // What an export writes: the animal files and the theme folders, with sizes.
  function exportPlan() {
    const pairs = exportPairs(), themes = exportThemes(), settings = buildSettings();
    const animalNames = X.fileNames(pairs.map((p) => p.sound.name));
    const animals = pairs.map((p, i) => ({ pair: p, name: animalNames[i], size: animalBytes(p, settings) }));
    const ids = X.themeIds(themes.map((t) => ({ name: t.name, libraryId: /^c:songs\/(.+)$/.exec(t.source || "")?.[1] })));
    const outThemes = themes.map((t, i) => {
      const items = themeSongs(t), names = X.songFileNames(items.map((x) => x.name));
      const songs = items.map((x, j) => ({ item: x, name: names[j], size: songBytes(x), off: x.enabled === false }));
      return { theme: t, id: ids[i], songs, size: songs.reduce((n, x) => n + x.size, 0) };
    });
    const config = $("#exportConfig").checked ? toyExportSettings({ themes: outThemes }) : null;
    const size = animals.reduce((n, a) => n + a.size, 0) + outThemes.reduce((n, t) => n + t.size, 0);
    return { pairs, animals, themes: outThemes, config, size, empty: !animals.length && !outThemes.length && !config, settings };
  }

  const xrow = (name, meta, tag, cls = "") => {
    const row = el("div", "xrow " + cls);
    row.append(Object.assign(el("span", "xname"), { textContent: name, title: name }), el("span", "xmeta", meta));
    if (tag) row.append(el("span", "tag " + tag[1], tag[0]));
    return row;
  };
  const xgroup = (name, meta, tag, rows, cls = "") => {
    const d = el("details", cls), sum = el("summary");
    sum.append(Object.assign(el("span", "xname"), { textContent: name, title: name }), el("span", "xmeta", meta));
    if (tag) sum.append(el("span", "tag " + tag[1], tag[0]));
    d.append(sum, ...rows);
    return d;
  };
  const xhead = (title, size) => { const h = el("h4"); h.append(el("span", "", title), el("span", "xsize", size)); return h; };
  const songsMeta = (n, size, word = "song") => `${plural(n, word)} · ${fmtSize(size)}`;

  // The chosen folder's contents as they are now.
  function renderCardNow() {
    const box = $("#cardNow"), dir = EX.dir;
    box.hidden = !dir;
    box.replaceChildren();
    if (!dir) return;
    if (EX.access === "prompt") {
      const ask = el("button", "btn", "Show what's in it");
      ask.onclick = () => refreshScan(true);
      box.append(xhead("Current content", ""), el("p", "xnote", "Studio needs your permission to open this folder again."), ask);
      return;
    }
    if (EX.scanError) { box.append(xhead("Current content", ""), el("p", "xnote", EX.scanError)); return; }
    const scan = EX.scan;
    if (!scan) { box.append(xhead("Current content", ""), el("p", "xnote", "Reading the folder…")); return; }
    box.append(xhead("Current content", fmtSize(scan.total)));
    const list = el("div", "xlist");
    if (scan.themes.length) {
      list.append(el("p", "xlabel", "Themes"));
      for (const t of scan.themes) list.append(xgroup(t.name, songsMeta(t.songs.length, t.size), null, t.songs.map((x) => xrow(x.name, fmtSize(x.size)))));
    }
    if (scan.animals) {
      list.append(el("p", "xlabel", "Animals"),
        xgroup("Animal sounds", songsMeta(scan.animals.files.length, scan.animals.size, "sound"), null, scan.animals.files.map((x) => xrow(x.name, fmtSize(x.size)))));
    }
    const other = otherEntries(scan);
    if (scan.config || other.length) {
      list.append(el("p", "xlabel", "Other files and folders"));
      if (scan.config) list.append(xrow("config.json (the toy's settings)", fmtSize(scan.config.size)));
      for (const o of other) list.append(xrow(o.name, fmtSize(o.size)));
    }
    if (!list.childElementCount) list.append(el("p", "xnote", "The folder is empty."));
    box.append(list);
  }
  const otherEntries = (scan) => [...scan.other.map((o) => ({ name: o.name + (o.kind === "directory" ? "/" : ""), size: o.size })),
    ...(scan.junk.count ? [{ name: `macOS junk files (${scan.junk.count})`, size: scan.junk.size }] : [])];

  // What the export writes, what stays from the folder and what it deletes,
  // and the folder's size afterwards. Inside an exported folder, files already
  // there are listed after the exported ones: kept with Keep on, deleted
  // (struck through) with it off; a same-named file is simply overwritten.
  function renderCardOut(plan, keep) {
    const box = $("#cardOut");
    box.hidden = plan.empty;
    box.replaceChildren();
    if (plan.empty) return;
    box.append(xhead("Exporting", "about " + fmtSize(plan.size)));
    const scan = EX.scan, list = el("div", "xlist");
    const KEPT = ["kept", ""], DEL = ["deleted", "del"];
    const extras = (existing, exported) => (existing || []).filter((x) => !exported.has(x.name));
    const extraRows = (rest) => rest.map((x) => keep ? xrow(x.name, fmtSize(x.size), KEPT, "kept") : xrow(x.name, fmtSize(x.size), DEL, "gone"));
    const extraTag = (rest) => !rest.length ? null : keep ? [`+${rest.length} kept`, ""] : [`${rest.length} deleted`, "del"];
    const exportedIds = new Set(plan.themes.map((t) => t.id));
    const goneThemes = scan && !keep ? scan.themes.filter((t) => !exportedIds.has(t.id)) : [];
    if (plan.themes.length || goneThemes.length) {
      list.append(el("p", "xlabel", "Themes"));
      for (const t of plan.themes) {
        const rest = extras(scan?.themes.find((c) => c.id === t.id)?.songs, new Set(t.songs.map((x) => x.name)));
        const tag = t.theme.enabled === false ? ["off", ""] : extraTag(rest) || (scan && !scan.themes.some((c) => c.id === t.id) ? ["new", "ok"] : null);
        list.append(xgroup(t.theme.name, songsMeta(t.songs.length, t.size), tag,
          [...t.songs.map((x) => xrow(x.name, fmtSize(x.size), x.off ? ["off", ""] : null, x.off ? "off" : "")), ...extraRows(rest)]));
      }
      for (const t of goneThemes) list.append(xgroup(t.name, songsMeta(t.songs.length, t.size), DEL, t.songs.map((x) => xrow(x.name, fmtSize(x.size))), "gone"));
    }
    if (plan.animals.length) {
      const rest = extras(scan?.animals?.files, new Set(plan.animals.map((a) => a.name)));
      list.append(el("p", "xlabel", "Animals"),
        xgroup("Animal sounds", songsMeta(plan.animals.length, plan.animals.reduce((n, a) => n + a.size, 0), "sound"), extraTag(rest),
          [...plan.animals.map((a) => xrow(a.name, fmtSize(a.size))), ...extraRows(rest)]));
    } else if (scan?.animals && !keep) {
      list.append(el("p", "xlabel", "Animals"),
        xgroup("Animal sounds", songsMeta(scan.animals.files.length, scan.animals.size, "sound"), DEL, scan.animals.files.map((x) => xrow(x.name, fmtSize(x.size))), "gone"));
    }
    const other = scan && !keep ? otherEntries(scan) : [];
    if (plan.config || other.length) {
      list.append(el("p", "xlabel", "Other files and folders"));
      if (plan.config) list.append(xrow("config.json (the toy's settings)", "1 KB", scan && !scan.config ? ["new", "ok"] : null));
      for (const o of other) list.append(xrow(o.name, fmtSize(o.size), DEL, "gone"));
    }
    box.append(list);
    if (scan) {
      const ids = new Set(plan.themes.map((t) => t.id));
      const stays = keep
        ? scan.total - scan.themes.filter((t) => ids.has(t.id)).reduce((n, t) => n +
            t.songs.filter((x) => plan.themes.find((o) => o.id === t.id).songs.some((y) => y.name === x.name)).reduce((m, x) => m + x.size, 0), 0) -
          (scan.animals?.files || []).filter((f) => plan.animals.some((a) => a.name === f.name)).reduce((n, f) => n + f.size, 0)
        : scan.config ? scan.config.size : 0;
      box.append(el("p", "xnote", `Afterwards the folder holds about ${fmtSize(stays + plan.size)}` +
        (keep ? ", with everything else in it kept." : ", and nothing else.")));
    }
  }

  // How many files and folders an export with Keep off deletes (0 with Keep on).
  function deleteCount(plan, keep, scan = EX.scan) {
    if (keep || !scan) return 0;
    let n = scan.other.length + scan.junk.count;
    for (const t of scan.themes) {
      const out = plan.themes.find((o) => o.id === t.id);
      n += out ? t.songs.filter((x) => !out.songs.some((y) => y.name === x.name)).length : 1 + t.songs.length;
    }
    if (scan.animals) {
      const names = new Set(plan.animals.map((a) => a.name));
      n += plan.animals.length ? scan.animals.files.filter((x) => !names.has(x.name)).length : 1 + scan.animals.files.length;
    }
    return n;
  }
  // A folder Studio writes without asking: one with songs/ or animals/, an
  // empty one, or the top of a card or drive.
  const cardLike = (scan) => scan.layout || scan.empty || scan.volume;

  function renderExport(status) {
    const dir = EX.dir, plan = exportPlan(), keep = $("#keepOther").checked;
    // The browser gives only the folder's name, not its path; the scan tells
    // whether it is the top of a card or drive.
    const volume = !!EX.scan?.volume;
    $("#dirCard").classList.toggle("none", !dir);
    $("#dirName").textContent = dir ? dir.name : "";
    $("#dirName").title = dir ? "Browsers show only a folder's name, not where it is." : "";
    $("#dirIcon").replaceChildren(volume ? Object.assign(el("img"), { src: "../assets/studio/sd-icon.png", alt: "" }) : "📁");
    const kind = !dir ? [] : [EX.scan ? (volume ? "SD card or drive" : "Folder") : "", EX.remembered ? "chosen last time" : ""].filter(Boolean);
    $("#dirKind").textContent = kind.join(" · ").replace(/^c/, "C");
    $("#pickDir").textContent = dir ? "Change folder…" : "Choose folder…";
    const inner = !!dir && /^(animals|songs)$/i.test(dir.name);
    $("#dirWarn").hidden = !inner;
    $("#dirWarn").textContent = inner ? `“${dir.name}” looks like a folder inside the card. Choose the card's top folder; Studio creates animals and songs in it.` : "";
    renderCardNow();
    renderCardOut(plan, keep);
    $("#exportWrite").disabled = EX.busy || !dir || plan.empty || !!EX.scanError;
    const doomed = dir && !plan.empty && !EX.busy ? deleteCount(plan, keep) : 0;
    $("#exportWarn").hidden = !doomed;
    $("#exportWarn").textContent = doomed ? `About to delete ${doomed} ${doomed === 1 ? "file or folder" : "files and folders"}.` : "";
    $("#pickDir").disabled = $("#keepOther").disabled = $("#exportConfig").disabled = $("#exportClose").disabled = EX.busy;
    $("#exportProgress").hidden = !EX.progress;
    if (EX.progress) $("#exportProgress > div").style.width = Math.round(100 * EX.progress.done / Math.max(1, EX.progress.total)) + "%";
    if (status !== undefined) $("#exportStatus").textContent = status;
  }
  // Reads what the chosen folder holds. A remembered folder needs permission
  // again after a restart; |ask| requests it (only from a click).
  async function refreshScan(ask) {
    const dir = EX.dir, run = ++EX.scanRun;
    Object.assign(EX, { scan: null, scanError: "", access: "" });
    if (!dir) { renderExport(); return; }
    const mode = { mode: "readwrite" };
    let perm = dir.queryPermission ? await dir.queryPermission(mode) : "granted";
    if (perm !== "granted" && ask) perm = await dir.requestPermission(mode).catch(() => "denied");
    if (run !== EX.scanRun) return;
    if (perm !== "granted") { EX.access = "prompt"; renderExport(); return; }
    renderExport();
    try {
      const scan = await X.scanCard(dir);
      if (run === EX.scanRun) EX.scan = scan;
    } catch {
      if (run === EX.scanRun) EX.scanError = `Couldn't open “${dir.name}”. If it's an SD card, check that it's in the reader, or choose the folder again.`;
    }
    if (run === EX.scanRun) renderExport();
  }
  $("#exportBtn").addEventListener("click", async () => {
    if (!EX.loaded && store) {
      EX.loaded = true;
      try { EX.dir = (await store.getSetting("exportDir")) || null; EX.remembered = !!EX.dir; } catch { /* none kept */ }
      try { const keep = await store.getSetting("exportKeepOther"); if (typeof keep === "boolean") $("#keepOther").checked = keep; } catch { /* default */ }
      try { const cfg = await store.getSetting("exportConfig"); if (typeof cfg === "boolean") $("#exportConfig").checked = cfg; } catch { /* default */ }
    }
    EX.progress = null;
    renderExport(!window.showDirectoryPicker ? "Writing to a folder needs Chrome or Edge on a computer."
      : exportPlan().empty ? "Add a theme with songs, match a prompt with an animal sound, or tick the toy settings below." : "");
    $("#exportDlg").showModal();
    if (!EX.busy) refreshScan(false);
  });
  $("#exportClose").addEventListener("click", () => { if (!EX.busy) $("#exportDlg").close(); });
  $("#exportDlg").addEventListener("cancel", (e) => { if (EX.busy) e.preventDefault(); });
  $("#exportConfig").addEventListener("change", () => {
    if (store) store.putSetting("exportConfig", $("#exportConfig").checked).catch(() => {});
    renderExport();
  });
  $("#keepOther").addEventListener("change", () => {
    if (store) store.putSetting("exportKeepOther", $("#keepOther").checked).catch(() => {});
    renderExport();
  });
  $("#pickDir").addEventListener("click", async () => {
    if (!window.showDirectoryPicker) { renderExport("Writing to a folder needs Chrome or Edge on a computer."); return; }
    let dir;
    try { dir = await showDirectoryPicker({ id: "sweetyaar-card", mode: "readwrite" }); } catch (_) { return; /* cancelled */ }
    EX.dir = dir; EX.remembered = false; EX.progress = null;
    if (store) { try { await store.putSetting("exportDir", dir); } catch { /* kept for this visit only */ } }
    renderExport("");
    refreshScan(false);
  });
  $("#exportWrite").addEventListener("click", async () => {
    const dir = EX.dir, plan = exportPlan(), keepOther = $("#keepOther").checked;
    if (!dir || plan.empty || EX.busy) return;
    const songCount = plan.themes.reduce((n, t) => n + t.songs.length, 0);
    EX.busy = true; EX.progress = { done: 0, total: Math.max(1, plan.animals.length * 2 + songCount) };
    renderExport("Asking for permission…");
    let writing = false, current = "";
    try {
      // Asked within the click: a remembered folder needs permission again after a restart.
      const mode = { mode: "readwrite" };
      if ((await dir.queryPermission?.(mode)) !== "granted" && (await dir.requestPermission(mode)) !== "granted") {
        throw Object.assign(new Error("denied"), { userMessage: "Studio wasn't allowed to write to that folder." });
      }
      // A folder that is not a toy card, not empty and not a card or drive
      // (Documents, say) is written to only once the parent confirms.
      const scan = await X.scanCard(dir);
      if (!cardLike(scan)) {
        const doomed = deleteCount(plan, keepOther, scan);
        if (!confirm(`“${dir.name}” doesn't look like a toy card: it has no songs or animals folder and isn't empty.` +
          (doomed ? ` ${doomed} ${doomed === 1 ? "file or folder" : "files and folders"} in it will be deleted.` : "") + " Export into it anyway?")) {
          EX.busy = false; EX.progress = null; renderExport("Nothing was written.");
          return;
        }
      }
      // Build the animal files first, so a failure leaves the folder as it was.
      const files = [];
      for (const [i, a] of plan.animals.entries()) {
        EX.progress.done = i;
        renderExport(`Building ${a.name} (${i + 1} of ${plan.animals.length})…`);
        const [question, sound] = await Promise.all([cardChannels(a.pair.prompt), cardChannels(a.pair.sound)]);
        files.push({ name: a.name, data: A.encodeWav([X.buildAnimal(question, sound, plan.settings, RATE)], RATE) });
      }
      // Songs are copied from this browser's storage as toy WAVs (44.1 kHz,
      // like the animal parts), each when its turn comes, so only one song is in memory.
      const cardThemes = plan.themes.map((t) => ({
        id: t.id, disabled: t.theme.enabled === false,
        metadata: X.themeMetadata({ name: t.theme.name, shuffle: t.theme.shuffle, attribution: t.theme.attribution }, t.songs.filter((x) => x.off).map((x) => x.name)),
        songs: t.songs.map((x) => ({ name: x.name, data: async () => A.encodeWav(await decodeAudio(x.item.blob), RATE) }))
      }));
      writing = true;
      const result = await X.writeCard(dir, {
        files: files.length ? files : null, metadata: X.animalsMetadata(S.animalsMeta.shuffle), themes: cardThemes, keepOther, settings: plan.config,
        onProgress: (i, n, name) => { current = name; EX.progress.done = plan.animals.length + i; renderExport(`Writing ${name} (${i + 1} of ${n})…`); }
      });
      EX.busy = false; EX.progress.done = EX.progress.total;
      const parts = [];
      if (files.length) parts.push(plural(files.length, "animal sound"));
      if (cardThemes.length) parts.push(plural(cardThemes.length, "theme"));
      if (plan.config) parts.push("the toy settings");
      const listed = parts.length > 1 ? parts.slice(0, -1).join(", ") + " and " + parts[parts.length - 1] : parts[0];
      renderExport(`Done: ${listed} exported to “${dir.name}”` +
        (result.removed.length ? `; ${plural(result.removed.length, "old item")} deleted.` : ".") +
        " If it's an SD card, eject it before you take it out.");
      refreshScan(false);
    } catch (e) {
      EX.busy = false; EX.progress = null;
      // A write error is shown as the browser gives it, with the file it stopped at.
      const why = e.name === "QuotaExceededError" ? "there is no space left" : e.message || e.name || "unknown error";
      renderExport(e.userMessage || (writing
        ? `Export stopped${current ? ` at “${current}”` : ""}: ${why}. The card may be full or no longer in the reader. The folder is partly written; fix that and export again.`
        : `Couldn't prepare the export (${why}). Nothing was written.`));
      refreshScan(false);
    }
  });

  // ---- Wave editor -------------------------------------------------------
  // The editor always works on a working-area item. Opening one converts it to
  // the toy's WAV format (44.1 kHz, 16-bit PCM) once, so later openings are
  // instant and what is edited is exactly what will be exported.
  const A = SweetYaarAudio;
  const RATE = A.OUTPUT_RATE;
  const canvas = $("#wave"), g = canvas.getContext("2d");
  const PT = SweetYaarParts;
  // E.bounds: the part edges (samples) inside the track; see parts.js.
  const E = { item: null, ch: null, bounds: [], peaks: null, abuf: null, history: [], dirty: false, cursor: 0, sel: null, view: { start: 0, span: 1 }, playing: null };
  let actx = null, gainNode = null, raf = 0;
  E.gainScope = null;   // {from, to} in seconds when the volume applies to a selection
  const audioCtx = () => actx || (actx = new AudioContext({ sampleRate: RATE }));
  const duration = () => (E.ch ? E.ch[0].length / RATE : 0);
  const len = () => (E.ch ? E.ch[0].length : 0);
  const samp = (t) => Math.max(0, Math.min(len(), Math.round(t * RATE)));
  const snapshot = () => ({ ch: E.ch, bounds: E.bounds });
  const gainDb = () => Number($("#gain").value) || 0;
  const lin = (d) => Math.pow(10, d / 20);
  const bake = () => E.ch;   // the volume knob edits E.ch directly

  async function persist(item, channels, message, bounds = []) {
    item.parts = bounds;
    // The user's own file is kept as added the first time Studio changes it
    // (converting or saving), so Restore can bring it back. Library copies
    // need no copy: the library has the original.
    if (!item.source && !item.recorded && item.blob && !item.original) { item.original = item.blob; item.originalFileName = item.fileName; }
    item.blob = new Blob([A.encodeWav(channels, RATE)], { type: "audio/wav" });
    item.fileName = item.fileName.replace(/\.\w+$/, "") + ".wav";
    item.size = item.blob.size;
    item.durationMs = Math.round(channels[0].length / RATE * 1000);
    if (item.unsaved) return;   // a new recording or library copy is stored only when saved
    await saveItem(item); render();
    if (message) toast(message);
  }

  async function decodeAudio(blob) {
    const decoded = await audioCtx().decodeAudioData(await blob.arrayBuffer());
    const channels = [];
    for (let c = 0; c < Math.min(2, decoded.numberOfChannels); c++) channels.push(decoded.getChannelData(c).slice());
    return channels;
  }
  // A new, empty recording (not in the working area until it is saved).
  // A song recording (a story read aloud, say) goes into the theme it was started from.
  async function newRecording(kind, themeId = "") {
    const n = S.items.filter((i) => i.kind === kind).length + 1;
    const name = kind === "prompt" ? `My prompt ${n}` : `My recording ${n}`;
    await openEditor({ id: uid(), kind, themeId, name, fileName: name + ".wav", size: 0, durationMs: 0, blob: null, addedAt: stamp(), unsaved: true, recorded: true });
  }
  // Renaming in the editor: kept at once (a new recording keeps it until it is saved).
  $("#trackName").addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === "Escape") { if (e.key === "Escape") e.target.value = E.item?.name || ""; e.target.blur(); } });
  $("#trackName").addEventListener("change", async (e) => {
    const item = E.item, name = e.target.value.trim();
    if (!item) return;
    if (!name) { e.target.value = item.name; return; }
    if (name === item.name) return;
    item.name = name; item.fileName = name + ".wav";
    if (item.unsaved) return;
    await saveItem(item); render();
    if (item.kind !== "song") await rematch();
    toast("Renamed.");
  });

  async function openEditor(item) {
    let channels = [new Float32Array(0)], ready = true;
    if (item.blob) {
      toast("Opening…");
      await new Promise((resolve) => setTimeout(resolve, 30));   // let the message paint before heavy work
      let ab;
      try {
        ab = await item.blob.arrayBuffer();
        channels = await decodeAudio(item.blob);
      } catch (e) { toast("Couldn't open that file: " + e.message); return; }
      const info = A.wavInfo(ab);
      ready = A.isToyWav(info) && info.channels === channels.length;
    }
    show("editor");
    const bounds = ready && Array.isArray(item.parts) ? PT.clean(item.parts, channels[0].length) : [];
    Object.assign(E, { item, ch: channels, bounds, abuf: null, history: [], dirty: false, cursor: 0, sel: null });
    setGain(0); selButtons();
    E.view = { start: 0, span: duration() };
    if (!ready) {
      await persist(item, channels, "Converted to the SweetYaar WAV format (44.1 kHz, 16-bit).");
    }
    refresh();
  }

  function refresh() {
    const it = E.item;
    if (document.activeElement !== $("#trackName")) $("#trackName").value = it.name;
    $("#trackTheme").textContent = { animal: "Animal sound", prompt: "Prompt" }[it.kind] || ((S.themes.find((t) => t.id === it.themeId) || {}).name || "No theme");
    E.peaks = A.buildPeaks(E.ch, 256); E.abuf = null;
    buildOverview(); selButtons();
    const d = duration();
    E.cursor = Math.min(E.cursor, d);
    setView(E.view.start, E.view.span || d, false);
    $("#playBtn").disabled = !len();
    $("#undoBtn").disabled = !E.history.length;
    $("#saveBtn").disabled = !E.dirty;
    updatePlayBtn(); draw();
  }

  // Every change goes through commit so it can be undone.
  function commit(channels, bounds = E.bounds, sel = null) {
    pausePlayback();
    const wasEmpty = !len();
    E.history.push(snapshot()); E.ch = channels; E.bounds = PT.clean(bounds, channels[0].length); E.dirty = true; E.sel = sel;
    if (wasEmpty) E.view = { start: 0, span: duration() };
    setGain(0); selButtons();
    refresh();
  }

  // ---- View: zoom and pan ----
  const minSpan = () => Math.min(10, duration());   // zoom stops at a 10 s window
  function setView(start, span, redraw = true) {
    const d = duration();
    if (!d) {
      E.view = { start: 0, span: 0 };
      $("#zoomIn").disabled = $("#zoomOut").disabled = true;
      $("#timeInfo").textContent = "0:00.0";
      if (redraw) draw();
      return;
    }
    span = Math.max(minSpan(), Math.min(d, span));
    start = Math.max(0, Math.min(d - span, start));
    E.view = { start, span };
    $("#zoomIn").disabled = span <= minSpan() + 0.001;
    $("#zoomOut").disabled = span >= d - 0.001;
    $("#timeInfo").textContent = `${fmtClock(E.view.start)} – ${fmtClock(E.view.start + E.view.span)} of ${fmtClock(d)}`;
    if (redraw) draw();
  }
  function zoom(factor, anchorTime) {
    const { start, span } = E.view, next = span * factor;
    const frac = (anchorTime - start) / span;
    setView(anchorTime - frac * Math.max(minSpan(), Math.min(duration(), next)), next);
  }
  function fmtClock(t) {
    const m = Math.floor(t / 60), s = t - m * 60;
    return `${m}:${s < 10 ? "0" : ""}${s.toFixed(1)}`;
  }
  const viewAnchor = () => (E.cursor >= E.view.start && E.cursor <= E.view.start + E.view.span ? E.cursor : E.view.start + E.view.span / 2);
  $("#zoomIn").addEventListener("click", () => zoom(0.5, viewAnchor()));
  $("#zoomOut").addEventListener("click", () => zoom(2, viewAnchor()));
  $("#zoomFit").addEventListener("click", () => setView(0, duration()));
  canvas.addEventListener("wheel", (e) => {
    if (!E.ch) return;
    if (e.ctrlKey || e.metaKey) { e.preventDefault(); zoom(Math.exp(e.deltaY * 0.01), timeAt(e)); }
    else if (E.view.span < duration() - 0.001) { e.preventDefault(); setView(E.view.start + (Math.abs(e.deltaX) > Math.abs(e.deltaY) ? e.deltaX : e.deltaY) / canvas.clientWidth * E.view.span, E.view.span); }
  }, { passive: false });

  // ---- Drawing ----
  const STEPS = [0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 1200];
  // Canvas colours come from the page's CSS (custom properties on the
  // canvas), so a page design can restyle them; the defaults are these.
  // --wave may list several colours; with --wave-bar (bar width in px) the
  // waveform is drawn as rounded bars that take the colours in turn.
  function cssColors(node, defaults) {
    const cs = getComputedStyle(node), out = {};
    for (const [k, def] of Object.entries(defaults)) out[k] = cs.getPropertyValue("--" + k).trim() || def;
    return out;
  }
  function draw() {
    if (!E.ch || !E.peaks) return;
    const dpr = window.devicePixelRatio || 1;
    const w = Math.round(canvas.clientWidth * dpr), h = Math.round(240 * dpr);
    if (!w) return;
    if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }
    const C = cssColors(canvas, { wave: "#34b8a9", "wave-bar": "0", "wave-sel": "#cdeee9", "wave-axis": "#d8ccbd", "wave-edge": "#d9a520", "wave-text": "#6b7678", "wave-cursor": "#d93e6f" });
    g.clearRect(0, 0, w, h);
    renderLane();
    if (!len()) {
      g.font = `${15 * dpr}px system-ui, sans-serif`; g.fillStyle = C["wave-text"]; g.textAlign = "center";
      g.fillText("Press Record, or drop audio files here", w / 2, h / 2);
      g.textAlign = "start";
      drawOverview();
      return;
    }
    const { start, span } = E.view, ruler = 22 * dpr, mid = (h - ruler) / 2, amp = mid * 0.92;
    const xOf = (t) => (t - start) / span * w;
    if (E.sel) { g.fillStyle = C["wave-sel"]; g.fillRect(xOf(E.sel[0]), 0, xOf(E.sel[1]) - xOf(E.sel[0]), h - ruler); }
    const { block, min, max } = E.peaks, spp = span * RATE / w;
    const colors = C.wave.split(",").map((c) => c.trim()).filter(Boolean);
    const barW = Math.max(0, parseFloat(C["wave-bar"]) || 0) * dpr;
    // One column, or one bar of |n| columns, from sample position s0.
    const peakAt = (s0, n) => {
      const b0 = Math.floor(s0 / block), b1 = Math.min(max.length, Math.max(b0 + 1, Math.ceil((s0 + n * spp) / block)));
      let lo = 0, hi = 0;
      for (let b = b0; b < b1; b++) { if (min[b] < lo) lo = min[b]; if (max[b] > hi) hi = max[b]; }
      return [lo, hi];
    };
    if (barW >= 2) {
      // Bars sit on a grid fixed to the track, so they don't shimmer while scrolling.
      const stride = Math.round(barW * 1.6), first = Math.floor(start / span * w / stride);
      for (let i = first; ; i++) {
        const x = i * stride - start / span * w;
        if (x > w) break;
        const [lo, hi] = peakAt(start * RATE + x * spp, stride);
        const top = mid - Math.max(hi * amp, barW / 2), bottom = mid + Math.max(-lo * amp, barW / 2);
        g.fillStyle = colors[((i % colors.length) + colors.length) % colors.length];
        g.beginPath(); g.roundRect(x, top, barW, bottom - top, barW / 2); g.fill();
      }
    } else {
      g.fillStyle = colors[0];
      for (let x = 0; x < w; x++) {
        const [lo, hi] = peakAt(start * RATE + x * spp, 1);
        g.fillRect(x, mid - hi * amp, 1, Math.max(1, (hi - lo) * amp));
      }
    }
    g.fillStyle = C["wave-axis"]; g.fillRect(0, mid, w, 1);
    // part edges
    g.strokeStyle = C["wave-edge"]; g.lineWidth = dpr; g.setLineDash([4 * dpr, 4 * dpr]);
    for (const b of E.bounds) {
      const x = Math.round(xOf(b / RATE)) + 0.5;
      if (x < 0 || x > w) continue;
      g.beginPath(); g.moveTo(x, 0); g.lineTo(x, h - ruler); g.stroke();
    }
    g.setLineDash([]);
    // time ruler
    const step = STEPS.find((s) => s >= span / 8) || STEPS[STEPS.length - 1];
    g.font = `${11 * dpr}px system-ui, sans-serif`; g.fillStyle = C["wave-text"]; g.strokeStyle = C["wave-axis"]; g.lineWidth = 1;
    for (let t = Math.ceil(start / step) * step; t <= start + span; t += step) {
      const x = Math.round(xOf(t)) + 0.5;
      g.beginPath(); g.moveTo(x, h - ruler); g.lineTo(x, h - ruler + 6 * dpr); g.stroke();
      g.fillText(step < 1 ? fmtClock(t) : fmtClock(t).replace(/\.0$/, ""), x + 3 * dpr, h - 5 * dpr);
    }
    g.fillStyle = C["wave-cursor"]; g.fillRect(xOf(currentPos()) - dpr, 0, 2 * dpr, h - ruler);
    drawOverview();
  }
  window.addEventListener("resize", () => { buildOverview(); draw(); });

  // ---- Playback ----
  const currentPos = () => (E.playing ? E.playing.from + (audioCtx().currentTime - E.playing.t0) : E.cursor);
  function audioBuffer() {
    if (!E.abuf) {
      E.abuf = audioCtx().createBuffer(E.ch.length, E.ch[0].length, RATE);
      E.ch.forEach((c, i) => E.abuf.copyToChannel(c, i));
    }
    return E.abuf;
  }
  function updatePlayBtn() { $("#playBtn").textContent = E.playing ? "❚❚ Pause" : "▶ Play"; }
  function startPlayback() {
    if (!len() || isRecording()) return;
    const ctx = audioCtx(); ctx.resume();
    let from = E.cursor, end = duration();
    if (E.sel) { if (from < E.sel[0] || from >= E.sel[1]) from = E.sel[0]; end = E.sel[1]; }
    else if (from >= end - 0.01) from = 0;
    const src = ctx.createBufferSource(); src.buffer = audioBuffer();
    gainNode = ctx.createGain();
    src.connect(gainNode).connect(ctx.destination);
    src.start(0, from, end - from);
    E.playing = { src, from, end, t0: ctx.currentTime };
    src.onended = () => {
      if (!E.playing || E.playing.src !== src) return;
      E.cursor = E.playing.end; E.playing = null; updatePlayBtn(); draw();
    };
    updatePlayBtn(); loop();
  }
  function pausePlayback() {
    if (!E.playing) return;
    const pos = currentPos();
    E.playing.src.onended = null;
    try { E.playing.src.stop(); } catch { /* already stopped */ }
    E.cursor = Math.max(0, Math.min(duration(), pos)); E.playing = null;
    cancelAnimationFrame(raf); updatePlayBtn(); draw();
  }
  function loop() {
    if (!E.playing) return;
    const pos = currentPos();
    if (pos < E.view.start || pos > E.view.start + E.view.span) setView(pos - E.view.span * 0.1, E.view.span, false);
    draw(); raf = requestAnimationFrame(loop);
  }
  $("#playBtn").addEventListener("click", () => (E.playing ? pausePlayback() : startPlayback()));
  document.addEventListener("keydown", (e) => {
    if (e.code !== "Space" || currentView !== "editor" || /^(INPUT|TEXTAREA|SELECT|BUTTON)$/.test(document.activeElement.tagName)) return;
    e.preventDefault(); if (E.ch) (E.playing ? pausePlayback() : startPlayback());
  });
  // Volume knob: drag up/down, scroll, arrow keys; double-click resets.
  const knob = $("#knob");
  function scopeLabel() {
    const sc = E.gainScope, range = (r) => `${fmtClock(r[0])}–${fmtClock(r[1])}`;
    if (gainDb() !== 0) $("#gainScope").textContent = sc ? `Applied to selection ${range([sc.from, sc.to])}` : "Applied to the whole track";
    else $("#gainScope").textContent = E.sel ? `Selection ${range(E.sel)} · turn to change only it` : "Whole track";
  }
  // Forgets the knob's starting point and sets it back to 0, keeping the audio
  // as it is, so the next turn is a new change (for example on a new selection).
  function settleGain() {
    E.gainBase = null; E.gainScope = null;
    setGain(0);
  }
  function setGain(v, fromUser) {
    v = Math.max(-12, Math.min(12, Math.round(v * 2) / 2));
    if (fromUser && E.ch) {
      if (v === gainDb()) return;
      if (!E.gainBase) {
        E.gainBase = E.ch; E.gainPrevDirty = E.dirty;
        E.history.push(snapshot());
        E.gainScope = E.sel ? { from: E.sel[0], to: E.sel[1] } : null;   // the selection, if any
      }
      E.ch = v ? A.applyGain(E.gainBase, v, E.gainScope, RATE) : E.gainBase;
      E.dirty = true;
      if (!v) { E.history.pop(); E.dirty = E.gainPrevDirty; E.gainBase = null; E.gainScope = null; }
    } else if (!fromUser) { E.gainBase = null; E.gainScope = null; }
    $("#gain").value = String(v);
    $("#gainVal").textContent = (v > 0 ? "+" : "") + v.toFixed(1) + " dB";
    knob.setAttribute("aria-valuenow", String(v));
    $("#knobTick").style.transform = `rotate(${-135 + (v + 12) / 24 * 270}deg)`;
    scopeLabel();
    if (fromUser && E.ch) {
      const pos = E.playing ? currentPos() : null;
      if (pos !== null) pausePlayback();
      refresh();
      if (pos !== null) { E.cursor = pos; startPlayback(); }
    }
  }
  let knobDrag = null;
  knob.addEventListener("pointerdown", (e) => { knob.setPointerCapture(e.pointerId); knobDrag = { x: e.clientX, y: e.clientY, v: gainDb() }; });
  knob.addEventListener("pointermove", (e) => { if (knobDrag) setGain(knobDrag.v + ((e.clientX - knobDrag.x) + (knobDrag.y - e.clientY)) * 0.1, true); });
  knob.addEventListener("pointerup", () => { knobDrag = null; });
  knob.addEventListener("wheel", (e) => { e.preventDefault(); setGain(gainDb() + (e.deltaY < 0 ? 0.5 : -0.5), true); }, { passive: false });
  knob.addEventListener("dblclick", () => setGain(0, true));
  knob.addEventListener("keydown", (e) => {
    const step = { ArrowUp: 0.5, ArrowRight: 0.5, ArrowDown: -0.5, ArrowLeft: -0.5 }[e.key];
    if (step) { e.preventDefault(); setGain(gainDb() + step, true); }
  });
  setGain(0);

  // ---- Overview: the whole track with the visible part boxed ----
  const ov = $("#overview"), og = ov.getContext("2d");
  let ovBase = null;
  const OV_PAD = 8;   // keeps the box outline clear of the rounded corners
  function buildOverview() {
    const dpr = window.devicePixelRatio || 1, w = Math.round(ov.clientWidth * dpr), h = Math.round(56 * dpr);
    if (!w || !E.peaks) return;
    const pad = OV_PAD * dpr, inner = w - 2 * pad;
    ov.width = w; ov.height = h;
    ovBase = document.createElement("canvas"); ovBase.width = w; ovBase.height = h;
    const c = ovBase.getContext("2d"), { min, max } = E.peaks, per = max.length / inner;
    c.fillStyle = cssColors(ov, { "ov-wave": "#9fd8cd" })["ov-wave"];
    for (let x = 0; x < inner; x++) {
      const b0 = Math.floor(x * per), b1 = Math.min(max.length, Math.max(b0 + 1, Math.ceil((x + 1) * per)));
      let lo = 0, hi = 0;
      for (let b = b0; b < b1; b++) { if (min[b] < lo) lo = min[b]; if (max[b] > hi) hi = max[b]; }
      c.fillRect(pad + x, h / 2 - hi * h * 0.45, 1, Math.max(1, (hi - lo) * h * 0.45));
    }
  }
  function drawOverview() {
    if (!ovBase || !E.ch) return;
    const dpr = window.devicePixelRatio || 1, w = ov.width, h = ov.height, d = duration();
    og.clearRect(0, 0, w, h);
    if (!d) return;
    og.drawImage(ovBase, 0, 0);
    const pad = OV_PAD * dpr, inner = w - 2 * pad;
    const x0 = pad + E.view.start / d * inner, x1 = pad + (E.view.start + E.view.span) / d * inner;
    const C = cssColors(ov, { "ov-dim": "rgba(234, 248, 245, 0.72)", "ov-box": "rgba(52, 184, 169, 0.14)", "ov-edge": "rgba(8, 115, 108, 0.45)", "wave-cursor": "#d93e6f" });
    og.fillStyle = C["ov-dim"]; og.fillRect(0, 0, x0, h); og.fillRect(x1, 0, w - x1, h);
    og.fillStyle = C["ov-box"]; og.fillRect(x0, 0, x1 - x0, h);
    // Thin, rounded and inset so the outline is never clipped at the edges.
    og.strokeStyle = C["ov-edge"]; og.lineWidth = dpr;
    og.beginPath(); og.roundRect(x0, 3 * dpr, Math.max(4 * dpr, x1 - x0), h - 6 * dpr, 6 * dpr); og.stroke();
    og.fillStyle = C["wave-cursor"]; og.fillRect(pad + currentPos() / d * inner - dpr / 2, 3 * dpr, dpr, h - 6 * dpr);
  }
  const ovTime = (e) => { const r = ov.getBoundingClientRect(), p = OV_PAD; return Math.min(1, Math.max(0, (e.clientX - r.left - p) / (r.width - 2 * p))) * duration(); };
  let ovDrag = null;
  ov.addEventListener("pointerdown", (e) => {
    if (!len()) return;
    ov.setPointerCapture(e.pointerId);
    const t = ovTime(e), { start, span } = E.view;
    if (t >= start && t <= start + span) ovDrag = { offset: t - start };
    else { ovDrag = { offset: span / 2 }; setView(t - span / 2, span); }
    ov.style.cursor = "grabbing";
  });
  ov.addEventListener("pointermove", (e) => { if (ovDrag) setView(ovTime(e) - ovDrag.offset, E.view.span); });
  ov.addEventListener("pointerup", () => { ovDrag = null; ov.style.cursor = ""; });

  // Click pauses and sets the position; dragging scrubs, with a short sound
  // at the pointer so the exact point can be found by ear. Shift-drag selects.
  const timeAt = (e) => {
    const r = canvas.getBoundingClientRect();
    return E.view.start + Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)) * E.view.span;
  };
  let drag = null, lastGrain = 0;
  function grain(t) {
    const now = performance.now();
    if (now - lastGrain < 45 || t >= duration()) return;
    lastGrain = now;
    const ctx = audioCtx(); ctx.resume();
    const src = ctx.createBufferSource(), gn = ctx.createGain();
    src.buffer = audioBuffer(); gn.gain.value = 1;
    src.connect(gn).connect(ctx.destination); src.start(0, t, 0.08);
  }
  canvas.addEventListener("pointerdown", (e) => {
    if (!len() || taking()) return;   // with the recorder open, clicks still place the position
    canvas.setPointerCapture(e.pointerId);
    pausePlayback();
    const t = timeAt(e);
    if (e.shiftKey) { drag = { mode: "scrub" }; E.cursor = t; grain(t); }
    else drag = { mode: "select", from: t, x: e.clientX, moved: false };
    draw();
  });
  canvas.addEventListener("pointermove", (e) => {
    if (!drag) return;
    const t = timeAt(e);
    if (drag.mode === "select") {
      if (!drag.moved && Math.abs(e.clientX - drag.x) < 4) return;   // still a click
      if (!drag.moved) { drag.moved = true; if (E.gainBase) settleGain(); }
      E.sel = [Math.min(drag.from, t), Math.max(drag.from, t)];
    } else { E.cursor = t; grain(t); }
    draw();
  });
  canvas.addEventListener("pointerup", () => {
    if (drag && drag.mode === "select") {
      if (!drag.moved) {   // a click: marker here (snapped to a nearby part edge), no selection
        if (E.sel && E.gainBase) settleGain();
        E.sel = null; E.cursor = drag.from;
        const edge = PT.nearestEdge(E.bounds, len(), samp(drag.from)) / RATE;
        if (Math.abs(edge - drag.from) / E.view.span * canvas.clientWidth < 8) E.cursor = edge;
      }
      else if (E.sel[1] - E.sel[0] < 0.02) E.sel = null;
    }
    drag = null; selButtons(); draw();
  });
  const boundsInSel = () => (E.sel ? E.bounds.filter((b) => b > samp(E.sel[0]) && b < samp(E.sel[1])) : []);
  function selButtons() {
    $("#clearSel").disabled = !E.sel; $("#cutBtn").disabled = !E.sel;
    $("#partBtn").disabled = !E.sel; $("#fuseBtn").disabled = !boundsInSel().length;
    $("#fixScope").textContent = E.sel ? `Apply to the selection ${fmtClock(E.sel[0])}–${fmtClock(E.sel[1])}` : "Apply to the whole track (select a range to fix only that)";
    scopeLabel();
  }
  $("#clearSel").addEventListener("click", () => { if (E.gainBase) settleGain(); E.sel = null; selButtons(); draw(); });
  function cutSelection() {
    if (!E.ch || !E.sel || isRecording()) return;
    const [from, to] = E.sel, n = len(), out = A.cutRange(bake(), RATE, from, to);
    // cutRange cross-fades the join, so a few more samples than the range go
    const removed = n - out[0].length, at = samp(from) - (removed - (samp(to) - samp(from)));
    E.cursor = from; commit(out, PT.afterRemoval(E.bounds, n, at, removed)); toast(`Cut ${(to - from).toFixed(1)} s.`);
  }

  // ---- Parts: make, fuse, reorder (drag in the strip above the waveform) ----
  $("#partBtn").addEventListener("click", () => {
    if (!E.sel || isRecording()) return;
    const a = samp(E.sel[0]), b = samp(E.sel[1]), next = PT.split(E.bounds, len(), a, b);
    if (next.length === E.bounds.length) { toast("That is already a part."); return; }
    commit(E.ch, next, [a / RATE, b / RATE]); toast("Made a part. Drag it in the strip above the waveform.");
  });
  $("#fuseBtn").addEventListener("click", () => {
    if (!E.sel || isRecording()) return;
    const inside = boundsInSel().length, sel = E.sel;
    commit(E.ch, PT.fuse(E.bounds, samp(sel[0]), samp(sel[1])), sel); toast(`Fused ${inside + 1} parts.`);
  });
  const lane = $("#lane");
  let laneDrag = null, partAnchor = null;
  const coversPart = ([a, b]) => E.sel && samp(E.sel[0]) <= a + 1 && samp(E.sel[1]) >= b - 1;
  function renderLane() {
    if (laneDrag) return;
    lane.replaceChildren();
    if (!E.ch || !len()) return;
    const { start, span } = E.view, w = lane.clientWidth, parts = PT.spans(E.bounds, len());
    parts.forEach(([a, b], i) => {
      const x0 = (a / RATE - start) / span * w, x1 = (b / RATE - start) / span * w;
      if (x1 < 0 || x0 > w) return;
      const chip = el("div", "part" + (coversPart([a, b]) ? " sel" : ""), `<b>${i + 1}</b><span>${((b - a) / RATE).toFixed(1)} s</span>`);
      chip.style.left = x0 + 1 + "px"; chip.style.width = Math.max(6, x1 - x0 - 2) + "px";
      chip.dataset.i = String(i);
      chip.title = parts.length > 1 ? "Drag to reorder. Click to select it, Shift+click to select several."
        : "The whole track is one part. Select a range and press Make part.";
      lane.append(chip);
    });
  }
  const laneTime = (e) => { const r = lane.getBoundingClientRect(); return E.view.start + Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)) * E.view.span; };
  lane.addEventListener("pointerdown", (e) => {
    const chip = e.target.closest(".part");
    if (!chip || isRecording()) return;
    e.preventDefault(); lane.setPointerCapture(e.pointerId); pausePlayback();
    laneDrag = { i: Number(chip.dataset.i), chip, x: e.clientX, left: chip.offsetLeft, moved: false, to: Number(chip.dataset.i) };
  });
  lane.addEventListener("pointermove", (e) => {
    if (!laneDrag) return;
    const dx = e.clientX - laneDrag.x;
    if (!laneDrag.moved && Math.abs(dx) < 4) return;
    const parts = PT.spans(E.bounds, len());
    if (parts.length < 2) return;
    laneDrag.moved = true;
    laneDrag.chip.classList.add("dragging"); laneDrag.chip.style.left = laneDrag.left + dx + "px";
    // Where it would land: after every other part whose middle is left of the pointer.
    const t = samp(laneTime(e)), others = parts.filter((_, j) => j !== laneDrag.i);
    const k = others.filter(([a, b]) => (a + b) / 2 < t).length;
    laneDrag.to = k;
    const edge = k < others.length ? others[k][0] : others[others.length - 1][1];
    let slot = lane.querySelector(".slot");
    if (!slot) { slot = el("div", "slot"); lane.append(slot); }
    slot.style.left = (edge / RATE - E.view.start) / E.view.span * lane.clientWidth + "px";
  });
  lane.addEventListener("pointerup", (e) => {
    if (!laneDrag) return;
    const { i, to, moved } = laneDrag;
    laneDrag = null;
    if (moved) {
      if (to !== i) {
        const r = PT.move(E.ch, E.bounds, i, to), [a, b] = PT.spans(r.bounds, len())[to];
        commit(r.channels, r.bounds, [a / RATE, b / RATE]); E.cursor = a / RATE; partAnchor = to;
        toast(`Moved part ${i + 1} to place ${to + 1}.`);
      }
      draw(); return;
    }
    // A click selects the part; Shift+click selects the run of parts from the last one clicked.
    const parts = PT.spans(E.bounds, len());
    const from = e.shiftKey && partAnchor !== null && partAnchor < parts.length ? Math.min(partAnchor, i) : i;
    const until = e.shiftKey && partAnchor !== null && partAnchor < parts.length ? Math.max(partAnchor, i) : i;
    if (!e.shiftKey) partAnchor = i;
    if (E.gainBase) settleGain();
    E.sel = [parts[from][0] / RATE, parts[until][1] / RATE]; E.cursor = E.sel[0];
    selButtons(); draw();
  });

  // ---- Adding audio: files (Insert file…, or dropped on the waveform) ----
  async function insertAudio(list, at) {
    pausePlayback();
    let ch = E.ch, bounds = E.bounds, pos = at, added = 0, failed = 0;
    for (const audio of list) {
      try {
        const channels = audio instanceof Blob ? await decodeAudio(audio) : audio;
        if (!channels[0].length) throw new Error("empty");
        const r = PT.insert(ch, bounds, pos, channels);
        ch = r.channels; bounds = r.bounds; pos += channels[0].length; added++;
      } catch (e) { failed++; }
    }
    if (added) {
      commit(ch, bounds); E.cursor = pos / RATE;
      if (E.cursor > E.view.start + E.view.span) setView(E.cursor - E.view.span * 0.9, E.view.span, false);
      draw();
    }
    return { added, failed };
  }
  $("#insertBtn").addEventListener("click", async () => {
    if (!E.ch || isRecording()) return;
    const files = await pickFiles(true);
    if (!files.length) return;
    const r = await insertAudio(files, samp(E.cursor));
    toast(r.failed ? `Added ${r.added} part${r.added === 1 ? "" : "s"}, couldn't read ${r.failed}.` : `Added ${r.added} part${r.added === 1 ? "" : "s"}.`);
  });
  const wavebox = $("#wavebox"), dropline = $("#dropline");
  const hasFiles = (e) => [...e.dataTransfer.types].includes("Files");
  const dropEdge = (e) => PT.nearestEdge(E.bounds, len(), samp(timeAt(e)));
  wavebox.addEventListener("dragover", (e) => {
    if (!E.ch || !hasFiles(e) || isRecording()) return;
    e.preventDefault(); e.stopPropagation();
    wavebox.classList.add("over"); dropline.hidden = false;
    dropline.style.left = (len() ? (dropEdge(e) / RATE - E.view.start) / E.view.span * canvas.clientWidth : 0) + "px";
  });
  wavebox.addEventListener("dragleave", (e) => { if (!wavebox.contains(e.relatedTarget)) { wavebox.classList.remove("over"); dropline.hidden = true; } });
  wavebox.addEventListener("drop", async (e) => {
    if (!E.ch || !hasFiles(e) || isRecording()) return;
    e.preventDefault(); e.stopPropagation();
    wavebox.classList.remove("over"); dropline.hidden = true;
    const r = await insertAudio([...e.dataTransfer.files], dropEdge(e));
    toast(r.failed ? `Added ${r.added} part${r.added === 1 ? "" : "s"}, couldn't read ${r.failed}.` : `Added ${r.added} part${r.added === 1 ? "" : "s"}.`);
  });

  // ---- Recording panel: at the position, as a new part ----
  // Record opens the panel at once and starts listening: the scope shows what
  // the microphone hears, before and while recording. Start records, Pause
  // holds, Stop adds the take at the position as a new part. The microphone
  // runs at its own rate; an AudioWorklet collects mono samples, which are
  // resampled to 44.1 kHz when a take is added.
  const R = { open: false, ctx: null, node: null, src: null, stream: null, state: "off", chunks: [], samples: 0, rate: 0,
    level: 0, heard: 0, opened: 0, at: 0, timer: 0, hist: [], acc: 0, accN: 0 };
  function isRecording() { return R.open; }
  const taking = () => R.state === "recording" || R.state === "paused";
  const REC_WORKLET = `registerProcessor("sweetyaar-rec", class extends AudioWorkletProcessor {
    process(inputs) { const ch = inputs[0] && inputs[0][0]; if (ch) this.port.postMessage(ch.slice(0)); return true; }
  });`;
  const scope = $("#recScope"), sg = scope.getContext("2d");
  function recUi() {
    const st = R.state, rec = st === "recording", paused = st === "paused", taking = rec || paused;
    $("#recPanel").classList.toggle("live", rec);
    $("#recStart").hidden = taking; $("#recStart").disabled = st !== "listening";
    $("#recPause").hidden = !taking; $("#recPause").textContent = paused ? "● Resume" : "❚❚ Pause";
    $("#recStop").hidden = !taking; $("#recDiscard").hidden = !taking;
    $("#recTime").hidden = !taking;
    $("#recState").textContent = { asking: "Asking for the microphone…", listening: "Listening (not recording)", recording: "● Recording", paused: "Paused", off: "" }[st] || "";
  }
  function drawScope() {
    const dpr = window.devicePixelRatio || 1, w = Math.round(scope.clientWidth * dpr), h = Math.round(70 * dpr);
    if (!w) return;
    if (scope.width !== w || scope.height !== h) { scope.width = w; scope.height = h; }
    sg.clearRect(0, 0, w, h);
    const C = cssColors(scope, { "scope-axis": "#e4ddd3", "scope-idle": "#9aa7a9", "scope-rec": "#d93e6f" });
    sg.fillStyle = C["scope-axis"]; sg.fillRect(0, h / 2, w, 1);
    const col = 3 * dpr, n = Math.floor(w / col), hist = R.hist.slice(-n);
    hist.forEach(([peak, rec], i) => {
      const x = w - (hist.length - i) * col, v = Math.min(1, peak * 1.6) * (h / 2 - 2 * dpr);
      sg.fillStyle = rec ? C["scope-rec"] : C["scope-idle"];
      sg.fillRect(x, h / 2 - v, col - dpr, Math.max(dpr, 2 * v));
    });
  }
  async function connectMic(deviceId) {
    R.state = "asking"; recUi();
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: {
        ...(deviceId ? { deviceId: { exact: deviceId } } : {}), echoCancellation: false, noiseSuppression: false, autoGainControl: false } });
    } catch (err) {
      R.state = "off"; recUi();
      $("#recHint").textContent = "Microphone unavailable: " + err.message;
      return;
    }
    if (!R.open) { stream.getTracks().forEach((t) => t.stop()); return; }
    if (R.src) R.src.disconnect();
    if (R.stream) R.stream.getTracks().forEach((t) => t.stop());
    R.stream = stream; R.src = R.ctx.createMediaStreamSource(stream); R.src.connect(R.node);
    R.heard = 0; R.opened = performance.now();
    R.state = "listening"; recUi();
    $("#recHint").textContent = "";
    // List the microphones (names are only shown once access is granted).
    const sel = $("#micSelect"), current = stream.getAudioTracks()[0]?.getSettings().deviceId;
    const mics = (await navigator.mediaDevices.enumerateDevices()).filter((d) => d.kind === "audioinput");
    sel.replaceChildren(...mics.map((d, i) => { const o = el("option", "", esc(d.label || `Microphone ${i + 1}`)); o.value = d.deviceId; return o; }));
    if (current) sel.value = current;
    sel.hidden = mics.length < 2;
  }
  async function openRecorder() {
    if (R.open || !E.ch) return;
    pausePlayback();
    // Created inside the click, so the browser lets it run.
    const ctx = new AudioContext(); ctx.resume();
    Object.assign(R, { open: true, ctx, node: null, src: null, stream: null, state: "asking", chunks: [], samples: 0, rate: ctx.sampleRate, level: 0, hist: [], acc: 0, accN: 0 });
    $("#recPanel").hidden = false; $("#recordBtn").disabled = true; $("#recHint").textContent = "";
    $("#view-editor").classList.add("recording");
    recUi(); drawScope();
    const url = URL.createObjectURL(new Blob([REC_WORKLET], { type: "text/javascript" }));
    try { await ctx.audioWorklet.addModule(url); }
    catch (err) { $("#recHint").textContent = "Recording isn't supported in this browser: " + err.message; R.state = "off"; recUi(); return; }
    finally { URL.revokeObjectURL(url); }
    if (!R.open) return;
    const node = new AudioWorkletNode(ctx, "sweetyaar-rec");
    const block = Math.round(ctx.sampleRate * 0.025);   // one scope column per 25 ms
    node.port.onmessage = (ev) => {
      const d = ev.data, rec = R.state === "recording";
      let peak = 0; for (let i = 0; i < d.length; i++) { const v = Math.abs(d[i]); if (v > peak) peak = v; }
      R.level = Math.max(peak, R.level * 0.92);
      if (peak > 0.003) R.heard = performance.now();
      R.acc = Math.max(R.acc, peak); R.accN += d.length;
      if (R.accN >= block) { R.hist.push([R.acc, rec]); if (R.hist.length > 2000) R.hist.splice(0, 1000); R.acc = 0; R.accN = 0; }
      if (rec) { R.chunks.push(d); R.samples += d.length; }
    };
    const mute = ctx.createGain(); mute.gain.value = 0;
    node.connect(mute).connect(ctx.destination);
    R.node = node;
    R.timer = setInterval(() => {
      $("#recTime").textContent = fmtClock(R.samples / R.rate);
      $("#recMeter").style.width = Math.min(100, R.level * 130) + "%";
      if (R.state === "listening" && performance.now() - R.heard > 2500 && performance.now() - R.opened > 2500)
        $("#recHint").textContent = "No sound from this microphone. Check that it is on, or pick another one.";
      else if (R.state === "listening" && $("#recHint").textContent.startsWith("No sound")) $("#recHint").textContent = "";
      drawScope();
    }, 50);
    await connectMic("");
  }
  // Adds the take so far at the position as a new part.
  async function addTake() {
    const { chunks, samples, rate, at } = R;
    R.chunks = []; R.samples = 0;
    if (samples < rate * 0.1) { toast("Nothing recorded."); return; }
    let mono = new Float32Array(samples), o = 0;
    for (const c of chunks) { mono.set(c, o); o += c.length; }
    if (rate !== RATE) {
      const off = new OfflineAudioContext(1, Math.ceil(samples * RATE / rate), RATE);
      const buf = off.createBuffer(1, samples, rate); buf.copyToChannel(mono, 0);
      const src = off.createBufferSource(); src.buffer = buf; src.connect(off.destination); src.start();
      mono = (await off.startRendering()).getChannelData(0).slice();
    }
    await insertAudio([[mono]], Math.min(at, len()));
    toast(`Added ${(mono.length / RATE).toFixed(1)} s as a new part.`);
  }
  function closeRecorder() {
    if (!R.open) return;
    clearInterval(R.timer);
    if (R.stream) R.stream.getTracks().forEach((t) => t.stop());
    if (R.node) { R.node.port.onmessage = null; R.node.disconnect(); }
    if (R.ctx) R.ctx.close();
    Object.assign(R, { open: false, ctx: null, node: null, src: null, stream: null, state: "off", chunks: [], samples: 0 });
    $("#recPanel").hidden = true; $("#recordBtn").disabled = false; $("#recMeter").style.width = "0";
    $("#view-editor").classList.remove("recording");
  }
  // Leaving the editor: an unfinished take is dropped.
  function stopRecording() { closeRecorder(); }
  $("#recordBtn").addEventListener("click", openRecorder);
  $("#recStart").addEventListener("click", () => {
    if (R.state !== "listening") return;
    Object.assign(R, { state: "recording", chunks: [], samples: 0, at: samp(E.cursor) }); recUi();
  });
  $("#recPause").addEventListener("click", () => {
    if (R.state === "recording") R.state = "paused";
    else if (R.state === "paused") R.state = "recording";
    recUi();
  });
  $("#recStop").addEventListener("click", async () => {
    if (R.state !== "recording" && R.state !== "paused") return;
    R.state = "listening"; recUi();
    await addTake();
    closeRecorder();
  });
  $("#recDiscard").addEventListener("click", () => {
    Object.assign(R, { state: "listening", chunks: [], samples: 0 }); recUi();
  });
  $("#recClose").addEventListener("click", async () => {
    if ((R.state === "recording" || R.state === "paused") && R.samples > R.rate * 0.1) {
      R.state = "listening"; await addTake();   // Close keeps what was recorded; Discard throws it away
    }
    closeRecorder();
  });
  $("#micSelect").addEventListener("change", () => {
    if (R.state === "recording" || R.state === "paused") { toast("Stop the take before switching microphones."); return; }
    connectMic($("#micSelect").value);
  });
  $("#cutBtn").addEventListener("click", cutSelection);
  document.addEventListener("keydown", (e) => {
    if ((e.key !== "Delete" && e.key !== "Backspace") || currentView !== "editor" || /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName)) return;
    e.preventDefault(); cutSelection();
  });

  // ---- Quick fixes, save, undo ----
  // Quick fixes work on the selection when there is one, else on the whole track.
  const fixRange = () => (E.sel ? E.sel : [0, duration()]);
  const scopeWord = () => (E.sel ? "selection" : "track");
  $("#fixTrim").addEventListener("click", () => {
    if (!len()) return;
    const thresholdDb = Number($('#trimLevel [aria-pressed="true"]').dataset.db), [from, to] = fixRange(), n = len();
    let res = null;
    const r = A.processRange(bake(), RATE, from, to, (slice) => { res = A.trimSilence(slice, RATE, { thresholdDb }); return res.channels; });
    if (res.silent) { toast(`The ${scopeWord()} is all silence at this level.`); return; }
    if (res.removedSec < 0.01) { toast("Nothing to trim."); return; }
    // the end of the range first, then its start
    const tail = (r.b - r.a) - res.to, head = res.from;
    let bounds = PT.afterRemoval(E.bounds, n, r.a + res.to, tail);
    bounds = PT.afterRemoval(bounds, n - tail, r.a, head);
    const sel = E.sel ? [r.a / RATE, (r.a + r.length) / RATE] : null;
    commit(r.channels, bounds, sel); toast(`Trimmed ${res.removedSec.toFixed(1)} s of silence.`);
  });
  $("#fixFade").addEventListener("click", () => {
    if (!len()) return;
    const fin = Math.max(0, Number($("#fadeIn").value) || 0), fout = Math.max(0, Number($("#fadeOut").value) || 0);
    if (!fin && !fout) { toast("Set a fade length first."); return; }
    const [from, to] = fixRange(), sel = E.sel;
    const r = E.sel ? A.processRange(bake(), RATE, from, to, (slice) => A.applyFade(slice, RATE, fin, fout)).channels : A.applyFade(bake(), RATE, fin, fout);
    commit(r, E.bounds, sel); toast(`Fades applied to the ${scopeWord()}.`);
  });
  $("#fixNorm").addEventListener("click", () => {
    if (!E.ch) return;
    const mode = document.querySelector('input[name="loud"]:checked').value;
    const [from, to] = fixRange(), sel = E.sel, word = scopeWord();
    let res = null;
    const r = A.processRange(bake(), RATE, from, to, (slice) => { res = A.normalize(slice, RATE, mode); return res.channels; });
    if (!isFinite(A.gatedRmsDb(r.channels.map((c) => c.subarray(r.a, r.b)), RATE))) { toast(`The ${word} is silent.`); return; }
    commit(r.channels, E.bounds, sel); toast(`Volume of the ${word} ${res.gainDb >= 0 ? "+" : ""}${res.gainDb.toFixed(1)} dB, peaks limited.`);
  });
  $("#undoBtn").addEventListener("click", () => {
    if (!E.history.length || isRecording()) return;
    pausePlayback();
    const h = E.history.pop(); E.ch = h.ch; E.bounds = h.bounds; E.dirty = E.history.length > 0; E.sel = null;
    setGain(0);
    refresh();
  });
  $("#saveBtn").addEventListener("click", async () => {
    if (!E.ch || isRecording()) return;
    if (!len()) { toast("Nothing to save yet."); return; }
    pausePlayback();
    const channels = bake(), item = E.item, isNew = !!item.unsaved;
    if (isNew) { delete item.unsaved; S.items.push(item); if (item.themeId) S.open.add(item.themeId); }   // a new recording joins the working area when it is first saved
    // Shows Edited and Restore: a library song, or a file of the user's whose original is kept.
    if ((item.kind === "song" && item.source) || item.original) item.edited = true;
    await persist(item, channels, "Saved.", E.bounds);
    if (isNew && item.source && item.kind !== "song") await adoptLibraryCopy(item);
    if (isNew && item.kind !== "song") await rematch();
    E.ch = channels; E.history = []; E.dirty = false;
    setGain(0);
    show("library");   // saving finishes the edit: back to the shelves
  });
  [["fadeIn", "fadeInVal"], ["fadeOut", "fadeOutVal"]].forEach(([i, o]) => {
    $("#" + i).addEventListener("input", () => { $("#" + o).textContent = Number($("#" + i).value).toFixed(1) + " s"; });
  });
  // The quick fixes' level choosers: one pressed button each.
  for (const seg of $$(".fix .segmented")) seg.addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (b) for (const x of seg.querySelectorAll("button")) x.setAttribute("aria-pressed", String(x === b));
  });
  $("#fixSpeaker").addEventListener("click", () => {
    if (!len() || isRecording()) return;
    const [from, to] = fixRange(), sel = E.sel, word = scopeWord();
    const out = sel ? A.processRange(bake(), RATE, from, to, (slice) => A.dollSpeaker(slice, RATE)).channels : A.dollSpeaker(bake(), RATE);
    commit(out, E.bounds, sel); toast(`Doll speaker preset applied to the ${word}.`);
  });
  $("#fixNoise").addEventListener("click", async () => {
    if (!len() || isRecording()) return;
    const choice = $('#noiseLevel [aria-pressed="true"]'), amount = choice.dataset.amount;
    toast("Reducing background noise…");
    await new Promise((resolve) => setTimeout(resolve, 30));   // let the message paint
    // The noise is learned from the whole track, so a short selection works too.
    const source = bake(), profile = A.noiseProfile(source, RATE);
    if (!profile) { toast("The track is too short or silent to learn its noise."); return; }
    const [from, to] = fixRange(), sel = E.sel, word = scopeWord();
    const out = sel ? A.processRange(source, RATE, from, to, (slice) => A.reduceNoise(slice, RATE, profile, amount)).channels
      : A.reduceNoise(source, RATE, profile, amount);
    commit(out, E.bounds, sel);
    toast(profile.contrastDb < 8
      ? `Noise reduced (${choice.textContent}), but the track has no clear pause, so the noise estimate is rough. Undo if it sounds worse.`
      : `Background noise reduced in the ${word} (${choice.textContent}).`);
  });

  // ---- Start -------------------------------------------------------------
  async function start() {
    if (!store) toast("This browser can't keep a working area (no IndexedDB).");
    else {
      try {
        try { S.toy = (await store.getSetting("toyConfig")) || {}; } catch { S.toy = {}; }
        const rows = await store.themes();
        S.animalsMeta = Object.assign(S.animalsMeta, rows.find((t) => t.id === S.animalsMeta.id) || {});
        S.themes = rows.filter((t) => t.id !== S.animalsMeta.id).sort((a, b) => a.createdAt - b.createdAt);
        // Songs keep the order set by dragging (pos); the rest, as added.
        S.items = (await store.items()).sort((a, b) => (a.pos ?? a.addedAt) - (b.pos ?? b.addedAt) || a.addedAt - b.addedAt || String(a.fileName).localeCompare(String(b.fileName), undefined, { numeric: true }));
        // Library songs saved in the editor before `edited` existed: library
        // files are already toy WAVs, so only a save gave them `parts`.
        for (const i of S.items) if (i.kind === "song" && i.source && i.edited === undefined && Array.isArray(i.parts)) i.edited = true;
        if (navigator.storage && navigator.storage.persist) navigator.storage.persist();
      } catch (e) { toast("Couldn't open the working area: " + e.message); }
    }
    render();
    loadCloud();
    loadLibrary();
    // Like the remote: try the toy this browser used last, without a prompt.
    if (client.supported && client.hasRemembered()) await connectDevice("remembered");
  }
  start();
})();

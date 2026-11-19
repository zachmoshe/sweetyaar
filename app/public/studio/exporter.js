"use strict";

// Export: builds the animal files from the matched pairs and writes a folder
// laid out like the toy's SD card (see "Content on the microSD card" in
// docs/engineering/firmware.md):
//
//   animals/<animal>.wav       one file per matched question and sound
//   animals/metadata.json      {"schemaVersion": 2, "name": "Animals", "shuffle", "disabledSongs"}
//   songs/<theme>/*.wav        the working area's themes, one folder each
//   songs/<theme>/metadata.json {"schemaVersion": 2, name, shuffle, disabledSongs, attribution}
//   config.json                "disabledThemes", plus the toy settings when asked; other keys kept
//
// Files of the same name are overwritten; everything else on the card (other
// songs and animal files, themes, folders, files, macOS junk) is kept or
// deleted as asked. scanCard lists what a folder holds. Works on plain
// Float32Array channels and FileSystemDirectoryHandle-like objects, so it
// runs in tests.
(function (root) {
  const A = typeof module !== "undefined" && module.exports ? require("./audio.js") : root.SweetYaarAudio;
  const RATE = A.OUTPUT_RATE;
  const TAIL_SEC = 0.3;          // silence after the sound, fixed
  const TRIM_DB = -50;           // Trim silence's Normal level
  const TARGET_DB = -18;         // the pack's loudness (Volume level's Standard)
  const CEILING_DB = -1;         // limiter on each joined file
  const DEFAULTS = { leadIn: 0.1, pause: 0.7, trimQuestion: true, trimSound: true, evenVolume: true, balance: 0 };

  function mono(channels) {
    if (channels.length === 1) return channels[0].slice();
    const n = channels[0].length, out = new Float32Array(n);
    for (const ch of channels) for (let i = 0; i < n; i++) out[i] += ch[i] / channels.length;
    return out;
  }
  function level(x, rate, targetDb) {
    const rms = A.gatedRmsDb([x], rate);
    if (!isFinite(rms)) return x;
    return A.applyGain([x], Math.max(-24, Math.min(24, targetDb - rms)))[0];
  }
  function trim(x, rate) {
    const r = A.trimSilence([x], rate, { thresholdDb: TRIM_DB });
    return r.silent ? x : r.channels[0];
  }

  // One animal file, mono: [lead-in] question [pause] sound [tail], limited.
  function buildAnimal(question, sound, settings = {}, rate = RATE) {
    const s = { ...DEFAULTS, ...settings };
    let q = mono(question), snd = mono(sound);
    if (s.trimQuestion) q = trim(q, rate);
    if (s.trimSound) snd = trim(snd, rate);
    if (s.evenVolume) {
      q = level(q, rate, TARGET_DB + s.balance / 2);
      snd = level(snd, rate, TARGET_DB - s.balance / 2);
    }
    const gap = (sec) => Math.round(Math.max(0, sec) * rate);
    const lead = gap(s.leadIn), pause = gap(s.pause), tail = gap(TAIL_SEC);
    const out = new Float32Array(lead + q.length + pause + snd.length + tail);
    out.set(q, lead);
    out.set(snd, lead + q.length + pause);
    return A.limit([out], rate, CEILING_DB)[0];
  }

  // Card-safe file names (FAT32): lower case letters, digits, - and _; the
  // same name twice gets -2, -3, ...
  function fileNames(names) {
    const used = new Set();
    return names.map((name) => {
      const base = String(name).toLowerCase().normalize("NFKD").replace(/[^a-z0-9_-]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 40) || "animal";
      let candidate = base;
      for (let n = 2; used.has(candidate); n++) candidate = `${base}-${n}`;
      used.add(candidate);
      return candidate + ".wav";
    });
  }

  function animalsMetadata(shuffle) {
    return JSON.stringify({ schemaVersion: 2, name: "Animals", shuffle: !!shuffle, disabledSongs: [] }, null, 2) + "\n";
  }

  // Theme folder ids: a library theme keeps its library id, others are named
  // after the theme in card-safe letters; each id is used once.
  function themeIds(themes) {
    const used = new Set();
    return themes.map((t) => {
      const base = (t.libraryId || String(t.name).toLowerCase().normalize("NFKD").replace(/[^a-z0-9_-]+/g, "-").replace(/^-+|-+$/g, "")).slice(0, 40) || "theme";
      let id = base;
      for (let n = 2; used.has(id) || id === "animals"; n++) id = `${base}-${n}`;
      used.add(id);
      return id;
    });
  }

  // Song file names for one theme, in the order shown: the song's name with
  // characters a FAT card refuses replaced, unique ignoring case. The toy plays
  // a folder in file-name order, so when that would differ from the order
  // shown every name gets a number: "01 - Name.wav".
  function songFileNames(names) {
    const used = new Set();
    let files = names.map((name) => {
      const base = String(name).replace(/[\x00-\x1f\\/:*?"<>|]+/g, "-").replace(/\.wav$/i, "").trim().replace(/[. ]+$/, "").slice(0, 60) || "song";
      let candidate = base;
      for (let n = 2; used.has(candidate.toLowerCase()); n++) candidate = `${base} ${n}`;
      used.add(candidate.toLowerCase());
      return candidate;
    });
    const sorted = [...files].sort((a, b) => (a < b ? -1 : a > b ? 1 : 0));
    if (files.some((f, i) => f !== sorted[i])) {
      const width = Math.max(2, String(files.length).length);
      files = files.map((f, i) => `${String(i + 1).padStart(width, "0")} - ${f.replace(/^\d+\s*-\s*/, "")}`);
    }
    return files.map((f) => f + ".wav");
  }

  function themeMetadata({ name, shuffle, attribution }, disabledSongs) {
    const meta = { schemaVersion: 2, name, shuffle: !!shuffle, disabledSongs };
    if (attribution) meta.attribution = attribution;
    return JSON.stringify(meta, null, 2) + "\n";
  }

  // The toy settings Studio edits, with the firmware's defaults (see
  // "/config.json" in docs/engineering/firmware.md). Theme fields hold a
  // card theme folder id, or "" for the firmware's choice.
  const TOY_DEFAULTS = {
    defaultVolumePct: 75, defaultTheme: "",
    bedtime: { enabled: true, startTime: "18:30", endTime: "06:30", theme: "", volumeCapPct: 65 },
    sleep: { enabled: true, normalIdleSec: 600, vibrationWakeIdleSec: 120, bleIdleSec: 120 }
  };
  // The config.json keys for |toy| (missing values take the defaults; an
  // empty theme is left out, so the firmware picks it).
  function toySettings(toy = {}) {
    const t = { ...TOY_DEFAULTS, ...toy, bedtime: { ...TOY_DEFAULTS.bedtime, ...(toy.bedtime || {}) }, sleep: { ...TOY_DEFAULTS.sleep, ...(toy.sleep || {}) } };
    const out = { defaultVolumePct: t.defaultVolumePct };
    if (t.defaultTheme) out.defaultTheme = t.defaultTheme;
    out.bedtime = { ...t.bedtime };
    if (!out.bedtime.theme) delete out.bedtime.theme;
    out.sleep = { ...t.sleep };
    return out;
  }

  // config.json with "disabledThemes" set (the other keys kept), or null when
  // there is no config.json and nothing is disabled. |keptIds| are theme
  // folders left on the card: their earlier off setting is kept. |settings|
  // (from toySettings) replaces those keys; keys inside bedtime and sleep
  // that Studio does not know are kept. Throws on a config.json that is not
  // a JSON object, so it is never overwritten.
  function configWith(text, disabledThemes, keptIds = [], settings = null) {
    if (text == null) {
      if (!settings && !disabledThemes.length) return null;
      return JSON.stringify({ schemaVersion: 2, ...(settings || {}), disabledThemes }, null, 2) + "\n";
    }
    let config;
    try { config = JSON.parse(text); } catch { config = null; }
    if (!config || typeof config !== "object" || Array.isArray(config)) {
      throw Object.assign(new Error("config.json is not valid"), { userMessage: "The card's config.json isn't valid JSON, so Studio didn't write anything. Fix or remove it, then export again." });
    }
    const kept = new Set(keptIds);
    const earlier = Array.isArray(config.disabledThemes) ? config.disabledThemes.filter((id) => kept.has(id) && !disabledThemes.includes(id)) : [];
    const out = { ...config };
    if (settings) {
      const obj = (v) => (v && typeof v === "object" && !Array.isArray(v) ? v : {});
      // The theme keys Studio leaves to the firmware are removed, not kept.
      delete out.defaultTheme;
      Object.assign(out, settings, {
        bedtime: { ...obj(config.bedtime), ...settings.bedtime },
        sleep: { ...obj(config.sleep), ...settings.sleep }
      });
      if (!settings.bedtime.theme) delete out.bedtime.theme;
    }
    out.disabledThemes = [...earlier, ...disabledThemes];
    return JSON.stringify(out, null, 2) + "\n";
  }
  async function readText(dir, name) {
    try { return await (await (await dir.getFileHandle(name)).getFile()).text(); } catch { return null; }
  }

  const isJunk = (name) => name.startsWith("._") || name === ".DS_Store" || name.endsWith(".crswap");
  // Folders the operating system keeps on a card: never listed or deleted.
  const SYSTEM = new Set(["System Volume Information", "$RECYCLE.BIN", ".Spotlight-V100", ".fseventsd", ".Trashes", ".TemporaryItems"]);

  async function writeFile(dir, name, data) {
    const handle = await dir.getFileHandle(name, { create: true });
    const writable = await handle.createWritable();
    await writable.write(data);
    await writable.close();
  }

  async function entriesOf(dir) {
    const out = [];
    for await (const [name, handle] of dir.entries()) if (!SYSTEM.has(name)) out.push([name, handle]);
    return out;
  }
  async function sizeOf(handle) {
    try {
      if (handle.kind === "file") return (await handle.getFile()).size;
      let n = 0;
      for (const [, h] of await entriesOf(handle)) n += await sizeOf(h);
      return n;
    } catch { return 0; }
  }
  async function hasEntry(dir, name) {
    for (const [n] of await entriesOf(dir)) if (n === name) return true;
    return false;
  }

  // What a chosen folder holds, in the card's terms: the themes in songs/
  // (name from metadata.json), the animal files, config.json and everything
  // else (macOS junk counted together). Sizes in bytes. |volume|: the folder
  // is the top of a card or drive (only those hold the system's own folders;
  // the browser does not say where a folder is). |layout|: it has a songs/ or
  // animals/ folder, like a toy card. |empty|: nothing in it but system folders.
  async function scanCard(rootDir) {
    const out = { total: 0, volume: false, layout: false, empty: true, themes: [], animals: null, config: null, other: [], junk: { count: 0, size: 0 } };
    for await (const [name] of rootDir.entries()) if (SYSTEM.has(name)) out.volume = true;
    const wavs = async (dir) => {
      const files = [];
      for (const [name, h] of await entriesOf(dir)) if (h.kind === "file" && /\.wav$/i.test(name) && !isJunk(name)) files.push({ name, size: await sizeOf(h) });
      return files.sort((a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0));
    };
    const addOther = async (name, h) => {
      const size = await sizeOf(h);
      if (isJunk(name)) { out.junk.count++; out.junk.size += size; } else out.other.push({ name, kind: h.kind, size });
    };
    for (const [name, h] of await entriesOf(rootDir)) {
      out.empty = false;
      if ((name === "songs" || name === "animals") && h.kind === "directory") out.layout = true;
      if (name === "songs" && h.kind === "directory") {
        for (const [id, t] of await entriesOf(h)) {
          if (t.kind !== "directory") { await addOther("songs/" + id, t); continue; }
          let meta = null;
          try { meta = JSON.parse(await readText(t, "metadata.json")); } catch { /* no name */ }
          out.themes.push({ id, name: (meta && typeof meta.name === "string" && meta.name) || id, size: await sizeOf(t), songs: await wavs(t) });
        }
        out.total += await sizeOf(h);
      } else if (name === "animals" && h.kind === "directory") {
        out.animals = { size: await sizeOf(h), files: await wavs(h) };
        out.total += out.animals.size;
      } else if (name === "config.json" && h.kind === "file") {
        out.config = { size: await sizeOf(h) };
        out.total += out.config.size;
      } else {
        await addOther(name, h);
      }
    }
    out.total += out.other.reduce((n, o) => n + o.size, 0) + out.junk.size;
    return out;
  }

  // Leaves |dir| holding only |keep|; adds the removed paths to |removed|.
  async function removeAllBut(dir, keep, removed, path = "") {
    for (const [name] of await entriesOf(dir)) {
      if (keep.has(name)) continue;
      await dir.removeEntry(name, { recursive: true });
      removed.push(path + name);
    }
  }
  // |files|: [{name, data}] for animals/, or null when no animals are
  // exported; |metadata|: text of animals/metadata.json. |themes|: [{id,
  // metadata, disabled, songs: [{name, data: async () => Blob}]}] for
  // songs/<id>/ (a song's data is made only when written). With |keepOther|
  // files of the same name are overwritten and everything else on the card
  // stays, other songs in an exported theme and other animal files included;
  // without it the card ends up holding only the export and config.json
  // (everything else, macOS junk included, is deleted; the system's own
  // folders are not).
  // config.json is read first; an invalid one stops the export before
  // anything is written. |settings| (from toySettings, or null) also writes
  // the toy settings into config.json. |onProgress|(i, n, name) counts every file.
  // Returns {written, removed} (paths relative to |rootDir|).
  async function writeCard(rootDir, { files = null, metadata, themes = null, keepOther = true, settings = null, onProgress = () => {} }) {
    themes = themes || [];
    const ids = new Set(themes.map((t) => t.id));
    const songsExists = await hasEntry(rootDir, "songs");
    const songsDir = songsExists || themes.length || !keepOther ? await rootDir.getDirectoryHandle("songs", { create: true }) : null;
    const kept = [];
    if (songsDir && keepOther) for (const [id, h] of await entriesOf(songsDir)) if (h.kind === "directory" && !ids.has(id)) kept.push(id);
    const config = themes.length || !keepOther || settings
      ? configWith(await readText(rootDir, "config.json"), themes.filter((t) => t.disabled).map((t) => t.id), kept, settings) : null;
    const removed = [], written = [];
    if (!keepOther) {
      await removeAllBut(rootDir, new Set(["songs", "config.json", ...(files ? ["animals"] : [])]), removed);
      await removeAllBut(songsDir, ids, removed, "songs/");
    }
    const total = (files ? files.length : 0) + themes.reduce((n, t) => n + t.songs.length, 0);
    let done = 0;
    if (files) {
      const animals = await rootDir.getDirectoryHandle("animals", { create: true });
      if (!keepOther) await removeAllBut(animals, new Set([...files.map((f) => f.name), "metadata.json"]), removed, "animals/");
      for (const f of files) {
        onProgress(done++, total, f.name);
        await writeFile(animals, f.name, f.data);
        written.push("animals/" + f.name);
      }
      await writeFile(animals, "metadata.json", metadata);
      written.push("animals/metadata.json");
    }
    for (const theme of themes) {
      const dir = await songsDir.getDirectoryHandle(theme.id, { create: true }), path = `songs/${theme.id}/`;
      if (!keepOther) await removeAllBut(dir, new Set([...theme.songs.map((x) => x.name), "metadata.json"]), removed, path);
      for (const song of theme.songs) {
        onProgress(done++, total, song.name);
        await writeFile(dir, song.name, await song.data());
        written.push(path + song.name);
      }
      await writeFile(dir, "metadata.json", theme.metadata);
      written.push(path + "metadata.json");
    }
    if (config != null) { await writeFile(rootDir, "config.json", config); written.push("config.json"); }
    return { written, removed };
  }

  const api = { buildAnimal, fileNames, animalsMetadata, themeIds, songFileNames, themeMetadata, TOY_DEFAULTS, toySettings, configWith, scanCard, writeCard, DEFAULTS, TAIL_SEC, TRIM_DB, TARGET_DB, CEILING_DB };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.SweetYaarExport = api;
})(typeof self !== "undefined" ? self : globalThis);

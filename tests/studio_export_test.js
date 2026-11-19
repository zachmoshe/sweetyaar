"use strict";

// Studio export: building animal files and writing the SD-card folder.
const assert = require("assert");
const A = require("../app/public/studio/audio.js");
const X = require("../app/public/studio/exporter.js");

const RATE = A.OUTPUT_RATE;
const tone = (sec, amp, freq = 440) => Float32Array.from({ length: Math.round(sec * RATE) }, (_, i) => amp * Math.sin(2 * Math.PI * freq * i / RATE));
const silence = (sec) => new Float32Array(Math.round(sec * RATE));
const join = (...parts) => { const out = new Float32Array(parts.reduce((n, p) => n + p.length, 0)); let o = 0; for (const p of parts) { out.set(p, o); o += p.length; } return out; };
const rmsDb = (x, from, to) => { let s = 0; for (let i = from; i < to; i++) s += x[i] * x[i]; return 10 * Math.log10(s / (to - from)); };
const near = (a, b, tol, msg) => assert.ok(Math.abs(a - b) <= tol, `${msg}: ${a} vs ${b}`);

// Layout: [lead-in] question [pause] sound [0.3 s], edges trimmed (30 ms kept).
{
  const question = [join(silence(0.5), tone(1, 0.05), silence(0.4))];
  const sound = [join(silence(0.2), tone(0.8, 0.5, 300), silence(0.6)), join(silence(0.2), tone(0.8, 0.5, 300), silence(0.6))];
  const out = X.buildAnimal(question, sound, { leadIn: 0.2, pause: 0.5 });
  const expected = 0.2 + (1 + 0.06) + 0.5 + (0.8 + 0.06) + X.TAIL_SEC;
  near(out.length / RATE, expected, 0.03, "file length");
  // Both parts levelled to the same loudness (balance 0); stereo is mixed to mono.
  const qMid = Math.round((0.2 + 0.53) * RATE), sMid = Math.round((0.2 + 1.06 + 0.5 + 0.43) * RATE);
  near(rmsDb(out, qMid, qMid + 4410), X.TARGET_DB, 1, "question loudness");
  near(rmsDb(out, sMid, sMid + 4410), X.TARGET_DB, 1, "sound loudness");
  assert.ok(A.peakOf([out]) <= Math.pow(10, X.CEILING_DB / 20) + 1e-3, "limited to the ceiling");
  // Balance +4 dB: the question is 4 dB louder than the sound, split around the target.
  const louder = X.buildAnimal(question, sound, { leadIn: 0.2, pause: 0.5, balance: 4 });
  near(rmsDb(louder, qMid, qMid + 4410) - rmsDb(louder, sMid, sMid + 4410), 4, 1, "balance");
  // Trimming and levelling off: the parts are joined as they are.
  const raw = X.buildAnimal(question, [sound[0]], { leadIn: 0, pause: 0, trimQuestion: false, trimSound: false, evenVolume: false });
  near(raw.length / RATE, 1.9 + 1.6 + X.TAIL_SEC, 0.001, "untrimmed length");
  near(rmsDb(raw, Math.round(0.6 * RATE), Math.round(0.7 * RATE)), 20 * Math.log10(0.05 / Math.SQRT2), 0.5, "question level unchanged");
}

// File names are card-safe and unique; metadata matches the SD-card template.
assert.deepStrictEqual(X.fileNames(["Dog", "dog", "Big Cat!", "קוף", "owl_2"]), ["dog.wav", "dog-2.wav", "big-cat.wav", "animal.wav", "owl_2.wav"]);
assert.deepStrictEqual(JSON.parse(X.animalsMetadata(true)), { schemaVersion: 2, name: "Animals", shuffle: true, disabledSongs: [] });

// A directory handle like Chrome's File System Access API.
const file = (data = "x") => {
  const f = { kind: "file", data };
  f.getFile = async () => ({ size: String(f.data ?? "").length, text: async () => String(f.data ?? "") });
  f.createWritable = async () => { let d; return { write: async (x) => { d = x; }, close: async () => { f.data = d; } }; };
  return f;
};
class Dir {
  constructor() { this.kind = "directory"; this.children = new Map(); }
  async getDirectoryHandle(name, { create = false } = {}) {
    if (!this.children.has(name)) { if (!create) throw new Error("NotFoundError"); this.children.set(name, new Dir()); }
    return this.children.get(name);
  }
  async getFileHandle(name, { create = false } = {}) {
    if (!this.children.has(name)) { if (!create) throw new Error("NotFoundError"); this.children.set(name, file(null)); }
    return this.children.get(name);
  }
  async removeEntry(name) { if (!this.children.delete(name)) throw new Error("NotFoundError"); }
  async *entries() { for (const [name, handle] of [...this.children]) yield [name, handle]; }
}
const keys = (dir) => [...dir.children.keys()].sort();

// A card with a theme, animals, settings, another folder and junk.
async function makeCard() {
  const card = new Dir();
  card.children.set("config.json", file('{"defaultVolumePct": 40, "disabledThemes": ["lullabies", "night"]}'));
  card.children.set("._config.json", file("j"));
  card.children.set(".DS_Store", file("jj"));
  card.children.set("System Volume Information", new Dir());
  card.children.set("notes.txt", file("hello"));
  const songs = await card.getDirectoryHandle("songs", { create: true });
  const lullabies = await songs.getDirectoryHandle("lullabies", { create: true });
  lullabies.children.set("01.wav", file("song"));
  lullabies.children.set("._01.wav", file("j"));
  lullabies.children.set("metadata.json", file('{"name":"Lullabies 🌙"}'));
  const night = await songs.getDirectoryHandle("night", { create: true });
  night.children.set("old.wav", file("old"));
  const animals = await card.getDirectoryHandle("animals", { create: true });
  animals.children.set("old-goat.wav", file("goat"));
  animals.children.set("cat.wav", file("old cat"));
  return card;
}
const song = (name, data, made = []) => ({ name, data: async () => { made.push(name); return data; } });

(async () => {
  // scanCard: themes with their names, animal files, settings, other entries and junk; system folders left out.
  const scan = await X.scanCard(await makeCard());
  assert.deepStrictEqual(scan.themes.map((t) => [t.id, t.name, t.size, t.songs.map((s) => s.name)]),
    [["lullabies", "Lullabies 🌙", 4 + 1 + '{"name":"Lullabies 🌙"}'.length, ["01.wav"]], ["night", "night", 3, ["old.wav"]]]);
  assert.deepStrictEqual(scan.animals, { size: 11, files: [{ name: "cat.wav", size: 7 }, { name: "old-goat.wav", size: 4 }] });
  assert.deepStrictEqual(scan.other, [{ name: "notes.txt", kind: "file", size: 5 }]);
  assert.deepStrictEqual(scan.junk, { count: 2, size: 3 });
  assert.strictEqual(scan.volume, true, "System Volume Information marks the top of a card");
  assert.strictEqual(scan.layout, true);
  assert.strictEqual(scan.empty, false);
  const bare = await X.scanCard(new Dir());
  assert.deepStrictEqual([bare.volume, bare.layout, bare.empty], [false, false, true]);
  const docs = new Dir();
  docs.children.set("taxes.pdf", file("x"));
  assert.deepStrictEqual([(await X.scanCard(docs)).layout, (await X.scanCard(docs)).empty], [false, false], "not card-like: export asks first");
  assert.strictEqual(scan.total, scan.themes[0].size + 3 + 11 + scan.config.size + 5 + 3);

  // Keeping the rest: songs and animal files of the same name are overwritten;
  // a theme's other songs, other animal files, themes, files, junk and their
  // off settings stay.
  {
    const card = await makeCard(), made = [], steps = [];
    const result = await X.writeCard(card, {
      files: [{ name: "cat.wav", data: "new cat" }, { name: "dog.wav", data: "dog" }], metadata: X.animalsMetadata(false),
      themes: [{ id: "night", disabled: false, metadata: '{"name":"Night"}', songs: [song("01 - Moon.wav", "moon", made)] },
               { id: "farm", disabled: true, metadata: '{"name":"Farm"}', songs: [song("cow.wav", "moo", made)] }],
      onProgress: (i, n, name) => steps.push(`${i + 1}/${n} ${name}`)
    });
    const animals = card.children.get("animals"), songs = card.children.get("songs");
    assert.deepStrictEqual(keys(animals), ["cat.wav", "dog.wav", "metadata.json", "old-goat.wav"]);
    assert.strictEqual(animals.children.get("cat.wav").data, "new cat");
    assert.deepStrictEqual(keys(songs), ["farm", "lullabies", "night"]);
    assert.deepStrictEqual(keys(songs.children.get("night")), ["01 - Moon.wav", "metadata.json", "old.wav"]);
    assert.deepStrictEqual(keys(songs.children.get("lullabies")), ["._01.wav", "01.wav", "metadata.json"]);
    assert.deepStrictEqual(keys(card), [".DS_Store", "._config.json", "System Volume Information", "animals", "config.json", "notes.txt", "songs"]);
    assert.deepStrictEqual(JSON.parse(card.children.get("config.json").data), { defaultVolumePct: 40, disabledThemes: ["lullabies", "farm"] },
      "a kept theme stays off; an exported one takes its new setting");
    assert.deepStrictEqual(made, ["01 - Moon.wav", "cow.wav"]);
    assert.deepStrictEqual(steps, ["1/4 cat.wav", "2/4 dog.wav", "3/4 01 - Moon.wav", "4/4 cow.wav"]);
    assert.deepStrictEqual(result.removed, []);
  }

  // Not keeping: animals/ and an exported theme hold exactly the exported files.
  {
    const card = await makeCard();
    const result = await X.writeCard(card, { files: [{ name: "dog.wav", data: "dog" }], metadata: X.animalsMetadata(true), keepOther: false,
      themes: [{ id: "night", disabled: false, metadata: "{}", songs: [song("01 - Moon.wav", "moon")] }] });
    assert.deepStrictEqual(keys(card.children.get("animals")), ["dog.wav", "metadata.json"]);
    assert.deepStrictEqual(keys(card.children.get("songs").children.get("night")), ["01 - Moon.wav", "metadata.json"]);
    assert.ok(result.removed.includes("animals/old-goat.wav") && result.removed.includes("animals/cat.wav"));
  }

  // Not keeping: the card holds only the export and config.json (system folders are never touched).
  {
    const card = await makeCard();
    const result = await X.writeCard(card, {
      themes: [{ id: "farm", disabled: false, metadata: "{}", songs: [song("cow.wav", "moo")] }], keepOther: false
    });
    assert.deepStrictEqual(keys(card), ["System Volume Information", "config.json", "songs"]);
    assert.deepStrictEqual(keys(card.children.get("songs")), ["farm"]);
    assert.deepStrictEqual(keys(card.children.get("songs").children.get("farm")), ["cow.wav", "metadata.json"]);
    assert.deepStrictEqual(JSON.parse(card.children.get("config.json").data), { defaultVolumePct: 40, disabledThemes: [] });
    assert.deepStrictEqual(result.removed.sort(), [".DS_Store", "._config.json", "animals", "notes.txt", "songs/lullabies", "songs/night"]);
  }

  // Keeping with only animals: songs/ and config.json are untouched; an empty folder gets animals/ only.
  {
    const card = await makeCard();
    await X.writeCard(card, { files: [{ name: "dog.wav", data: "dog" }], metadata: X.animalsMetadata(true) });
    assert.deepStrictEqual(keys(card.children.get("songs")), ["lullabies", "night"]);
    assert.strictEqual(card.children.get("config.json").data, '{"defaultVolumePct": 40, "disabledThemes": ["lullabies", "night"]}');
    const empty = new Dir();
    await X.writeCard(empty, { files: [], metadata: X.animalsMetadata(true) });
    assert.deepStrictEqual(keys(empty), ["animals"]);
    assert.deepStrictEqual(keys(empty.children.get("animals")), ["metadata.json"]);
  }

  // Names, ids and metadata.
  assert.deepStrictEqual(X.themeIds([{ name: "Classical 🎻" }, { name: "שירים" }, { name: "x", libraryId: "my-day" }, { name: "Classical" }, { name: "Animals" }]),
    ["classical", "theme", "my-day", "classical-2", "animals-2"]);
  assert.deepStrictEqual(X.songFileNames(["01 - Piano", "02 - Violin"]), ["01 - Piano.wav", "02 - Violin.wav"], "already in order: kept");
  assert.deepStrictEqual(X.songFileNames(["Zebra", "apple", "a/b?", "Apple"]), ["01 - Zebra.wav", "02 - apple.wav", "03 - a-b-.wav", "04 - Apple 2.wav"]);
  assert.deepStrictEqual(JSON.parse(X.themeMetadata({ name: "Night", shuffle: true, attribution: "" }, ["b.wav"])),
    { schemaVersion: 2, name: "Night", shuffle: true, disabledSongs: ["b.wav"] });
  assert.strictEqual(X.configWith(null, []), null);
  assert.deepStrictEqual(JSON.parse(X.configWith(null, ["x"])), { schemaVersion: 2, disabledThemes: ["x"] });
  assert.throws(() => X.configWith("[1]", []), /not valid/);

  // Toy settings: defaults from the firmware; an empty theme is left to the firmware.
  assert.deepStrictEqual(X.toySettings(), {
    defaultVolumePct: 75,
    bedtime: { enabled: true, startTime: "18:30", endTime: "06:30", volumeCapPct: 65 },
    sleep: { enabled: true, normalIdleSec: 600, vibrationWakeIdleSec: 120, bleIdleSec: 120 }
  });
  const toy = X.toySettings({ defaultVolumePct: 40, defaultTheme: "my-day", bedtime: { theme: "lullabies", enabled: false } });
  assert.deepStrictEqual([toy.defaultTheme, toy.bedtime.theme, toy.bedtime.enabled, toy.bedtime.startTime], ["my-day", "lullabies", false, "18:30"]);
  // A new config.json; merging into one keeps unknown keys, drops a theme left to the firmware.
  assert.deepStrictEqual(JSON.parse(X.configWith(null, [], [], X.toySettings())), { schemaVersion: 2, ...X.toySettings(), disabledThemes: [] });
  assert.deepStrictEqual(JSON.parse(X.configWith('{"schemaVersion":2,"custom":1,"defaultTheme":"old","bedtime":{"theme":"old","extra":true},"sleep":"bad"}', ["x"], [], toy)),
    { schemaVersion: 2, custom: 1, defaultVolumePct: 40, defaultTheme: "my-day",
      bedtime: { theme: "lullabies", extra: true, enabled: false, startTime: "18:30", endTime: "06:30", volumeCapPct: 65 },
      sleep: { enabled: true, normalIdleSec: 600, vibrationWakeIdleSec: 120, bleIdleSec: 120 }, disabledThemes: ["x"] });
  assert.ok(!("defaultTheme" in JSON.parse(X.configWith('{"defaultTheme":"old"}', [], [], X.toySettings()))));

  // Settings alone write config.json, with nothing else exported.
  {
    const card = new Dir();
    const result = await X.writeCard(card, { settings: X.toySettings() });
    assert.deepStrictEqual(result.written, ["config.json"]);
    assert.strictEqual(JSON.parse(card.children.get("config.json").data).defaultVolumePct, 75);
  }

  // An invalid config.json stops the export before anything is written.
  {
    const card = await makeCard();
    card.children.set("config.json", file("{oops"));
    await assert.rejects(X.writeCard(card, { themes: [{ id: "new", metadata: "{}", songs: [] }], keepOther: false }), /not valid/);
    assert.ok(!card.children.get("songs").children.has("new"));
    assert.ok(card.children.has("notes.txt"), "nothing deleted either");
  }
  console.log("studio export tests passed");
})().catch((e) => { console.error(e); process.exit(1); });

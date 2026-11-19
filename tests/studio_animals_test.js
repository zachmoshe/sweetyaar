"use strict";
// Prompt-to-animal matching (app/public/studio/animals.js) and the content client (content.js).
const assert = require("assert");
const path = require("path");
const A = require(path.join(__dirname, "../app/public/studio/animals.js"));
const C = require(path.join(__dirname, "../app/public/studio/content.js"));

const sounds = ["cat", "dog", "owl"].map((n) => ({ key: "c:" + n, name: n }));
const prompts = [
  { key: "c:en:dog", name: "dog" }, { key: "c:en:cat", name: "cat" },
  { key: "l:1", name: "Owl question (take 2)" }, { key: "l:2", name: "my recording" }
];

assert.deepStrictEqual(A.words("Owl question (take 2).wav"), ["owl", "question", "take", "2"]);
assert.deepStrictEqual(A.words("איך עושה כלב"), ["איך", "עושה", "כלב"]);

// Auto-match by name, then by a word of the prompt's name.
let m = A.autoMatch(prompts, sounds, {});
assert.deepStrictEqual(m, { "c:en:dog": "c:dog", "c:en:cat": "c:cat", "l:1": "c:owl" });

// Existing pairs are kept; a manual link replaces both sides' earlier partners.
m = A.link(m, "l:2", "c:dog");
assert.deepStrictEqual(m, { "c:en:cat": "c:cat", "l:1": "c:owl", "l:2": "c:dog" });
assert.deepStrictEqual(A.autoMatch(prompts, sounds, m), m, "auto-match does not undo a manual link");

// Unlink by either side; prune drops pairs whose cards are gone.
assert.deepStrictEqual(A.unlink(m, "c:owl"), { "c:en:cat": "c:cat", "l:2": "c:dog" });
assert.deepStrictEqual(A.prune(m, prompts.slice(0, 2), sounds), { "c:en:cat": "c:cat" });

// A sound the user unmatched is not matched by name again, also after the
// prompts change language (their keys change, the sound's does not).
const hePrompts = [{ key: "c:he:dog", name: "dog" }, { key: "c:he:cat", name: "cat" }];
assert.deepStrictEqual(A.autoMatch(hePrompts, sounds, {}, ["c:dog"]), { "c:he:cat": "c:cat" });
assert.deepStrictEqual(A.autoMatch(hePrompts, sounds, {}), { "c:he:dog": "c:dog", "c:he:cat": "c:cat" });

// Ambiguous names do not match.
assert.strictEqual(A.findSound({ name: "dog and cat" }, sounds), null);

// Export list: matched animals only, in sound order.
assert.deepStrictEqual(A.pairs(m, prompts, sounds).map((p) => [p.sound.name, p.prompt.key]),
  [["cat", "c:en:cat"], ["dog", "l:2"], ["owl", "l:1"]]);

// Content client: Cloud Storage JSON API listings and public file URLs.
const B = "https://storage.googleapis.com";
const listings = {
  "animal-sounds/": { items: [{ name: "animal-sounds/" }, { name: "animal-sounds/dog.wav" }, { name: "animal-sounds/ATTRIBUTION.txt" }, { name: "animal-sounds/Bad Name.wav" }] },
  "animal-prompts/": { prefixes: ["animal-prompts/he/", "animal-prompts/en/", "animal-prompts/../"] },
  "animal-prompts/en/": { items: [{ name: "animal-prompts/en/dog.wav" }], nextPageToken: "p2" },
  "animal-prompts/en/p2": { items: [{ name: "animal-prompts/en/cat.wav" }] }
};
const calls = [];
const fakeFetch = async (url) => {
  calls.push(url);
  const u = new URL(url);
  if (u.pathname.endsWith("/ATTRIBUTION.txt")) return { ok: true, text: async () => "Sounds from [Freesound](https://freesound.org).\n\ndog: Single Dog Bark - CC0\n" };
  const key = u.searchParams.get("prefix") + (u.searchParams.get("pageToken") || "");
  return { ok: true, json: async () => listings[key] };
};
const client = C.createContent(fakeFetch);
assert.strictEqual(client.soundUrl("dog"), B + "/sweetyaar-studio-resources/animal-sounds/dog.wav");
assert.strictEqual(client.promptUrl("he", "dog"), B + "/sweetyaar-studio-resources/animal-prompts/he/dog.wav");
(async () => {
  assert.deepStrictEqual(await client.sounds(), {
    files: [{ name: "dog" }],
    attribution: { short: 'Sounds from <a href="https://freesound.org" target="_blank" rel="noopener">Freesound</a>.', long: "<p>dog: Single Dog Bark - CC0</p>" }
  });
  assert.deepStrictEqual(await client.languages(), ["en", "he"]);
  assert.deepStrictEqual(await client.prompts("en"), [{ name: "cat" }, { name: "dog" }]);
  assert.ok(calls.every((u) => u.startsWith(B)));

  // The one attribution format: first line short, the rest (blank edges dropped) long.
  const L = (url, text = url) => `<a href="${url}" target="_blank" rel="noopener">${text}</a>`;
  assert.deepStrictEqual(C.parseAttribution("Spoken questions by [ElevenLabs](https://elevenlabs.io), **free** *tier*.\n"),
    { short: `Spoken questions by ${L("https://elevenlabs.io", "ElevenLabs")}, <b>free</b> <i>tier</i>.`, long: "" });
  assert.deepStrictEqual(C.parseAttribution("# Short\n\n\nline one https://a.org/x.\nline two\n\nnext paragraph\n\n"),
    { short: "Short", long: `<p>line one ${L("https://a.org/x")}.<br>line two</p><p>next paragraph</p>` });
  assert.deepStrictEqual(C.parseAttribution('<img src=x onerror="a()"> [x](javascript:a())'),
    { short: "&lt;img src=x onerror=&quot;a()&quot;&gt; [x](javascript:a())", long: "" });
  assert.strictEqual(C.parseAttribution("\nonly a long part"), null);
  assert.strictEqual(C.parseAttribution(""), null);
  const withCredit = C.createContent(async (url) => url.endsWith("animal-prompts/ATTRIBUTION.txt")
    ? { ok: true, text: async () => "Made with [ElevenLabs](https://elevenlabs.io)." } : { ok: false, status: 404 });
  assert.deepStrictEqual(await withCredit.promptsAttribution(), { short: `Made with ${L("https://elevenlabs.io", "ElevenLabs")}.`, long: "" });
  assert.strictEqual(await C.createContent(async () => ({ ok: false, status: 404 })).promptsAttribution(), null);

  // Library song themes: songs/<id>/ with metadata.json, ATTRIBUTION.txt and WAVs (length from size).
  const songLists = {
    "songs/": { prefixes: ["songs/my-day/", "songs/empty/", "songs/Bad Theme/"] },
    "songs/my-day/": { items: [
      { name: "songs/my-day/10 - Tidy Up.wav", size: "88244" }, { name: "songs/my-day/02 - Dressed.wav", size: "176444" },
      { name: "songs/my-day/._02 - Dressed.wav", size: "4096" }, { name: "songs/my-day/metadata.json", size: "90" },
      { name: "songs/my-day/ATTRIBUTION.txt", size: "40" }] },
    "songs/empty/": { items: [{ name: "songs/empty/metadata.json", size: "20" }] }
  };
  const themeFetch = async (url) => {
    const u = new URL(url);
    if (u.pathname.endsWith("/metadata.json")) return { ok: true, json: async () => ({ name: "✨ My Day", shuffle: false, attribution: "Made with [Eleven Music](https://elevenlabs.io/music)" }) };
    if (u.pathname.endsWith("/ATTRIBUTION.txt")) return { ok: true, text: async () => "Made with music.\n\nsong credits" };
    return { ok: true, json: async () => songLists[u.searchParams.get("prefix")] || {} };
  };
  const lib = C.createContent(themeFetch);
  assert.deepStrictEqual(await lib.themes(), [{
    id: "my-day", name: "✨ My Day", shuffle: false, credit: "Made with [Eleven Music](https://elevenlabs.io/music)",
    attribution: { short: "Made with music.", long: "<p>song credits</p>" },
    songs: [{ file: "02 - Dressed.wav", name: "02 - Dressed", size: 176444, durationMs: 2000 },
            { file: "10 - Tidy Up.wav", name: "10 - Tidy Up", size: 88244, durationMs: 1000 }]
  }], "an empty theme and a bad folder name are left out; ._ files are skipped; songs sort by number");
  assert.strictEqual(lib.songUrl("my-day", "02 - Dressed.wav"), B + "/sweetyaar-studio-resources/songs/my-day/02%20-%20Dressed.wav");
  console.log("studio animals tests passed");
})().catch((e) => { console.error(e); process.exit(1); });

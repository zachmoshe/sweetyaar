"use strict";

// Matching spoken prompts ("How does a dog sound?") to animal sounds in the
// Studio's Animals panel. Every matched pair becomes one toy file; unmatched
// cards are ignored on export. Pure logic, so it can be tested without a page.
(function (root) {
  // The words of a name: "Dog question (take 2).wav" -> ["dog", "question", "take", "2"].
  function words(name) {
    return String(name).toLowerCase().replace(/\.\w{2,4}$/, "").split(/[^\p{L}\p{N}]+/u).filter(Boolean);
  }

  // A prompt matches a sound when their names are equal, or when the sound's
  // name is one of the prompt's words and no other sound's name is.
  function findSound(prompt, sounds) {
    const pw = words(prompt.name), full = pw.join(" ");
    const exact = sounds.filter((s) => words(s.name).join(" ") === full);
    if (exact.length === 1) return exact[0];
    const byWord = sounds.filter((s) => { const sw = words(s.name); return sw.length === 1 && pw.includes(sw[0]); });
    return byWord.length === 1 ? byWord[0] : null;
  }

  // Adds name matches for prompts and sounds that are not matched yet.
  // |matches| maps prompt key -> sound key; a new object is returned.
  // |off| lists sound keys the user unmatched: they are never matched by
  // name (sound keys stay the same when the prompts' language changes).
  function autoMatch(prompts, sounds, matches, off = []) {
    const out = prune(matches, prompts, sounds);
    const taken = new Set([...Object.values(out), ...off]);
    for (const p of prompts) {
      if (out[p.key]) continue;
      const s = findSound(p, sounds.filter((x) => !taken.has(x.key)));
      if (s) { out[p.key] = s.key; taken.add(s.key); }
    }
    return out;
  }

  // Pairs one prompt with one sound, dropping their earlier partners.
  function link(matches, promptKey, soundKey) {
    const out = {};
    for (const [p, s] of Object.entries(matches)) if (p !== promptKey && s !== soundKey) out[p] = s;
    out[promptKey] = soundKey;
    return out;
  }

  function unlink(matches, key) {
    const out = {};
    for (const [p, s] of Object.entries(matches)) if (p !== key && s !== key) out[p] = s;
    return out;
  }

  // Keeps only pairs whose prompt and sound both still exist.
  function prune(matches, prompts, sounds) {
    const pk = new Set(prompts.map((p) => p.key)), sk = new Set(sounds.map((s) => s.key));
    const out = {};
    for (const [p, s] of Object.entries(matches || {})) if (pk.has(p) && sk.has(s)) out[p] = s;
    return out;
  }

  // The animals the toy files are built for, in sound order.
  function pairs(matches, prompts, sounds) {
    const byPrompt = new Map(prompts.map((p) => [p.key, p]));
    const bySound = new Map(sounds.map((s) => [s.key, s]));
    const soundToPrompt = new Map(Object.entries(matches).map(([p, s]) => [s, p]));
    return sounds.filter((s) => soundToPrompt.has(s.key) && byPrompt.has(soundToPrompt.get(s.key)))
      .map((s) => ({ sound: bySound.get(s.key), prompt: byPrompt.get(soundToPrompt.get(s.key)) }));
  }

  const api = { words, findSound, autoMatch, link, unlink, prune, pairs };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.SweetYaarAnimals = api;
})(typeof self !== "undefined" ? self : globalThis);

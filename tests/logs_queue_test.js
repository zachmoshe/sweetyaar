"use strict";

// app/public/logs-queue.js against fake Cache Storage and fetch.
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const source = fs.readFileSync(path.join(__dirname, "..", "app", "public", "logs-queue.js"), "utf8");

function createContext(answers) {
  const store = new Map();
  const cache = {
    async put(url, response) { store.set(url, response); },
    async match(url) { return store.get(url); },
    async keys() { return [...store.keys()]; },
    async delete(url) { return store.delete(url); },
  };
  const requests = [];
  const context = {
    URL, URLSearchParams, Response, Uint8Array, console, Promise, JSON, String,
    caches: { open: async () => cache, keys: async () => ["sweetyaar-logs", "sweetyaar-parent-v62"] },
    async fetch(url, options = {}) {
      requests.push({ url, method: options.method || "GET", body: options.body });
      const answer = answers.shift();
      if (answer instanceof Error) throw answer;
      return new Response(JSON.stringify(answer.body), { status: answer.status });
    },
  };
  context.self = context;
  context.location = { origin: "https://sweetyaar.zachmoshe.com" };
  vm.runInNewContext(source, context);
  return { logs: context.SweetYaarLogs, requests, store };
}

// Values from the script's own context: compare as plain data.
function plain(value) {
  return JSON.parse(JSON.stringify(value));
}

function sector(seq) {
  const bytes = new Uint8Array(4096).fill(0xff);
  bytes[8] = seq;
  return bytes;
}

async function testQueueAndUpload() {
  const server = { history: 1, seq: 4, open: true, header: "00", last_upload: "2026-11-01T12:00:00+00:00" };
  const { logs, requests } = createContext([{ status: 200, body: { ...server, accepted: 3 } }]);
  await logs.put("aabbccddeeff", 2, sector(2), { auto: true });
  await logs.put("aabbccddeeff", 1, sector(1), { auto: true });
  await logs.put("aabbccddeeff", 4, sector(3), { open: true });
  await logs.put("aabbccddeeff", 4, sector(4), { open: true });  // grew: replaces the copy
  assert.deepStrictEqual(plain((await logs.queued("aabbccddeeff")).map((entry) => entry.seq)), [1, 2, 4]);

  const outcome = await logs.uploadAll("v1");
  assert.strictEqual(outcome.uploaded, 3);
  assert.deepStrictEqual(plain(outcome.states.aabbccddeeff), server);
  // One request in sequence order, marking the sector still being written.
  assert.strictEqual(requests.length, 1);
  assert.match(requests[0].url, /\/v1\/devices\/aabbccddeeff\/sectors\?app=v1&open=4$/);
  assert.strictEqual(requests[0].body.length, 3 * 4096);
  assert.deepStrictEqual([0, 1, 2].map((i) => requests[0].body[i * 4096 + 8]), [1, 2, 4]);
  assert.deepStrictEqual(plain(await logs.queued("aabbccddeeff")), []);
  assert.deepStrictEqual(plain(await logs.cachedState("aabbccddeeff")), server);
}

async function testOfflineKeepsSectorsAndDiscardAuto() {
  const { logs } = createContext([new TypeError("Failed to fetch"), new TypeError("Failed to fetch")]);
  await logs.put("aabbccddeeff", 7, sector(7), { auto: true });
  await logs.put("aabbccddeeff", 8, sector(8), { open: true });
  await assert.rejects(logs.uploadAll(""));
  assert.strictEqual((await logs.queued("aabbccddeeff")).length, 2);
  await assert.rejects(logs.latest("aabbccddeeff"));
  assert.strictEqual(await logs.cachedState("aabbccddeeff"), undefined);
  // Sharing turned off: only the parent's own send stays.
  await logs.discardAuto("aabbccddeeff");
  assert.deepStrictEqual(plain((await logs.queued("aabbccddeeff")).map((entry) => entry.seq)), [8]);
}

async function testLimitsAndRefusals() {
  const { logs, requests } = createContext([
    { status: 429, body: { error: "daily upload limit" } },
    { status: 404, body: { error: "nothing uploaded yet" } },
  ]);
  for (let seq = 1; seq <= 3; seq += 1) await logs.put("aabbccddeeff", seq, sector(seq));
  const outcome = await logs.uploadAll();
  assert.strictEqual(outcome.uploaded, 0);
  assert.match(requests[0].url, /app=sweetyaar-parent-v62/);  // the app's release by default
  assert.strictEqual((await logs.queued("aabbccddeeff")).length, 3);  // kept for later
  assert.strictEqual(await logs.latest("aabbccddeeff"), null);
  assert.strictEqual(await logs.cachedState("aabbccddeeff"), null);
  assert.strictEqual(requests.length, 2);
}

function testBatches() {
  const { logs } = createContext([]);
  const entry = (seq, extra = {}) => ({ meta: { seq, open: false, replaces: null, ...extra } });
  const list = [];
  for (let seq = 1; seq <= 70; seq += 1) list.push(entry(seq));
  assert.deepStrictEqual(plain(logs.batches(list).map((batch) => batch.length)), [64, 6]);
  // A new history starts its own request.
  const restarted = [entry(9), entry(1, { replaces: 1 }), entry(2, { replaces: 1 })];
  assert.deepStrictEqual(plain(logs.batches(restarted).map((batch) => batch.map((e) => e.meta.seq))), [[9], [1, 2]]);
  // Nothing follows the sector still being written in one request.
  const open = [entry(3, { open: true }), entry(4)];
  assert.deepStrictEqual(plain(logs.batches(open).map((batch) => batch.length)), [1, 1]);
}

(async () => {
  await testQueueAndUpload();
  await testOfflineKeepsSectorsAndDiscardAuto();
  await testLimitsAndRefusals();
  testBatches();
  console.log("logs queue tests passed");
})().catch((error) => {
  console.error(error);
  process.exit(1);
});

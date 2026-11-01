"use strict";

// Diagnostic log sectors on their way from the toy to the logs API. The page
// reads sectors from the toy over BLE and queues them here; the page, or the
// service worker's Background Sync once the phone is online again, uploads
// them. Both load this file, so they share one queue in Cache Storage. See
// "Sending logs to the cloud" in docs/logging-and-debugging.md.
(function (root) {
  const API = "https://me-west1-sweetyaar.cloudfunctions.net/logs-api";
  const CACHE = "sweetyaar-logs";
  const SYNC_TAG = "sweetyaar-logs";
  const BATCH_SECTORS = 64;  // the API's limit per request

  function prefix() {
    return new URL("/__sweetyaar-logs/", root.location.origin).href;
  }

  function queueUrl(device, seq) {
    return `${prefix()}queue/${device}/${String(seq).padStart(10, "0")}`;
  }

  function stateUrl(device) {
    return `${prefix()}state/${device}`;
  }

  // A newer copy of the same sector (the one still being written) replaces it.
  async function put(device, seq, bytes, meta = {}) {
    const cache = await caches.open(CACHE);
    const entry = { device, seq, open: !!meta.open, auto: !!meta.auto, replaces: meta.replaces ?? null };
    await cache.put(queueUrl(device, seq), new Response(bytes, {
      headers: { "Content-Type": "application/octet-stream", "X-Sector": JSON.stringify(entry) }
    }));
  }

  async function entries(device = null) {
    const cache = await caches.open(CACHE);
    const result = [];
    for (const request of await cache.keys()) {
      const url = typeof request === "string" ? request : request.url;
      if (!url.startsWith(`${prefix()}queue/`)) continue;
      const response = await cache.match(url);
      if (!response) continue;
      let meta = null;
      try {
        meta = JSON.parse(response.headers.get("X-Sector") || "null");
      } catch {
        meta = null;
      }
      if (!meta) {
        await cache.delete(url);
        continue;
      }
      if (device === null || meta.device === device) result.push({ url, meta, response });
    }
    return result.sort((a, b) => a.meta.device.localeCompare(b.meta.device) || a.meta.seq - b.meta.seq);
  }

  async function queued(device) {
    return (await entries(device)).map((entry) => entry.meta);
  }

  // Sharing turned off: automatic sectors that have not left the phone go.
  async function discardAuto(device) {
    const cache = await caches.open(CACHE);
    for (const entry of await entries(device)) {
      if (entry.meta.auto) await cache.delete(entry.url);
    }
  }

  async function saveState(device, server) {
    const cache = await caches.open(CACHE);
    await cache.put(stateUrl(device), new Response(JSON.stringify(server), {
      headers: { "Content-Type": "application/json" }
    }));
  }

  // The last answer the API gave for this toy, for offline use; undefined if none.
  async function cachedState(device) {
    const cache = await caches.open(CACHE);
    const response = await cache.match(stateUrl(device));
    if (!response) return undefined;
    try {
      return await response.json();
    } catch {
      return undefined;
    }
  }

  // Where the toy's uploads stand: null when it never sent any. Throws offline.
  async function latest(device) {
    const response = await fetch(`${API}/v1/devices/${device}/latest`, { cache: "no-store" });
    if (response.status === 404) {
      await saveState(device, null);
      return null;
    }
    if (!response.ok) throw new Error(`Logs API answered ${response.status}`);
    const server = await response.json();
    await saveState(device, server);
    return server;
  }

  // Groups a toy's queued sectors into requests: in sequence order, at most
  // BATCH_SECTORS each, and a new request where a new history begins.
  function batches(list) {
    const result = [];
    for (const entry of list) {
      const last = result[result.length - 1];
      const startsHistory = entry.meta.replaces !== null &&
        (!last || last[0].meta.replaces !== entry.meta.replaces);
      if (!last || last.length >= BATCH_SECTORS || startsHistory ||
          last[last.length - 1].meta.open) {
        result.push([entry]);
      } else {
        last.push(entry);
      }
    }
    return result;
  }

  // Uploads every queued sector. Returns { uploaded, states: {device: server} };
  // throws when the phone is offline (the sectors stay queued).
  // |app| defaults to the app's cache version, which names the release.
  async function uploadAll(app = "") {
    if (!app) app = (await caches.keys()).find((name) => name.startsWith("sweetyaar-parent-v")) || "";
    const cache = await caches.open(CACHE);
    const all = await entries();
    const devices = [...new Set(all.map((entry) => entry.meta.device))];
    const outcome = { uploaded: 0, states: {} };
    for (const device of devices) {
      for (const batch of batches(all.filter((entry) => entry.meta.device === device))) {
        const parts = await Promise.all(batch.map((entry) => entry.response.clone().arrayBuffer()));
        const body = new Uint8Array(parts.reduce((total, part) => total + part.byteLength, 0));
        let offset = 0;
        for (const part of parts) {
          body.set(new Uint8Array(part), offset);
          offset += part.byteLength;
        }
        const params = new URLSearchParams({ app });
        const last = batch[batch.length - 1].meta;
        if (last.open) params.set("open", String(last.seq));
        if (batch[0].meta.replaces !== null) params.set("replaces", String(batch[0].meta.replaces));
        const response = await fetch(`${API}/v1/devices/${device}/sectors?${params}`, {
          method: "POST",
          headers: { "Content-Type": "application/octet-stream" },
          body
        });
        if (response.status === 429 || response.status >= 500) break;  // later
        if (response.ok) {
          const server = await response.json();
          delete server.accepted;
          await saveState(device, server);
          outcome.states[device] = server;
          outcome.uploaded += batch.length;
        } else {
          // Never accepted as it is: keeping it would block the queue.
          console.warn(`[SweetYaar logs] Upload refused (${response.status}); dropping ${batch.length} sectors`);
        }
        for (const entry of batch) await cache.delete(entry.url);
      }
    }
    return outcome;
  }

  root.SweetYaarLogs = { API, SYNC_TAG, put, queued, discardAuto, cachedState, latest, batches, uploadAll };
})(self);

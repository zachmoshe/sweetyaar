"use strict";

// Finding and linking SweetYaar over Web Bluetooth, shared by the parent
// remote (index.html) and Studio (studio/device.js), so both reconnect to the
// remembered toy the same way and explain a refusal with the same words.
// What happens after the link (access check, pairing, controls) stays with
// each page.
(function (root) {
  // The toy this browser used last: its browser-assigned device id.
  const LAST_DEVICE_KEY = "sweetyaar-last-device-id";
  const OLD_KEYS = ["sweetyaar.lastDeviceId"];   // Studio's earlier key, read once

  // The automatic reconnect finds the toy with a scan of up to |findMs| and
  // then makes at most |attempts| connects.
  // - On a Mac a scan that has heard nothing within a couple of seconds
  //   usually stays deaf, while a restarted one often hears the toy at once,
  //   so the scan is restarted every |hearMs|.
  // - Android ignores a scan, without an error, once an app has started
  //   more than five within 30 seconds. Restarting every two seconds used
  //   that up in one slow attempt and left the page deaf to a toy that was
  //   advertising, so Android gets a single scan (and one notification).
  const TIMING = { findMs: 15000, hearMs: 2000, attemptMs: 10000, retryMs: 500, attempts: 2 };

  // What the toy's access byte means for someone it refuses (see "access" in
  // docs/engineering/firmware.md).
  const MESSAGES = {
    pairingRequired: "Device not approved. Hold both buttons for 3 seconds to open pairing mode, then reconnect.",
    audioBusy: "Can't pair while a phone is connected to SweetYaar as a speaker. Disconnect the speaker, hold both buttons for 3 seconds to open pairing mode, then reconnect.",
    remoteBusy: "Another remote is connected while SweetYaar plays music. Close it there, or stop the music, then connect.",
    toyBusy: "SweetYaar is busy right now. Try again in a moment.",
    takeover: "Someone else took control.",
    pairingHint: "Couldn't connect. If this is a new device, hold both buttons for 3 seconds to open pairing mode."
  };
  const REFUSALS = { 0: MESSAGES.pairingRequired, 5: MESSAGES.audioBusy, 6: MESSAGES.remoteBusy, 7: MESSAGES.toyBusy };

  function rememberedId(storage) {
    try {
      for (const key of [LAST_DEVICE_KEY, ...OLD_KEYS]) {
        const id = storage.getItem(key);
        if (id) return id;
      }
    } catch (error) { /* private mode */ }
    return "";
  }
  function remember(storage, id) {
    try {
      storage.setItem(LAST_DEVICE_KEY, id);
      for (const key of OLD_KEYS) if (typeof storage.removeItem === "function") storage.removeItem(key);
    } catch (error) { /* private mode */ }
  }

  // The remembered toy, if the browser still grants it (no chooser); null otherwise.
  async function rememberedDevice(bluetooth, storage) {
    const id = rememberedId(storage);
    if (!id || !bluetooth || typeof bluetooth.getDevices !== "function") return null;
    try {
      return (await bluetooth.getDevices()).find((granted) => granted.id === id) || null;
    } catch (error) {
      return null;
    }
  }

  function withTimeout(promise, ms, timeoutValue) {
    let timer;
    const limit = new Promise((resolve) => { timer = setTimeout(() => resolve(timeoutValue), ms); });
    return Promise.race([promise, limit]).finally(() => clearTimeout(timer));
  }
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  // Rejects with a `stopped` error as soon as |signal| aborts (Stop pressed).
  function orStop(promise, signal) {
    if (!signal) return promise;
    const stopped = new Promise((_, reject) => {
      const fail = () => reject(Object.assign(new Error("stopped"), { stopped: true }));
      if (signal.aborted) fail(); else signal.addEventListener("abort", fail, { once: true });
    });
    return Promise.race([promise, stopped]);
  }

  // Starts the browser's advertisement scan for the toy. `heard` resolves true
  // at its first advertisement (or at once when the browser cannot watch
  // advertisements, then connect directly). Stop it when done: while it runs,
  // the browser keeps the toy "in range" for gatt.connect().
  function watchToy(device) {
    let markHeard;
    const heard = new Promise((resolve) => { markHeard = resolve; });
    if (typeof device.watchAdvertisements !== "function") {
      markHeard(true);
      return { heard, stop() {} };
    }
    const abort = new AbortController();
    const onAdvertisement = () => markHeard(true);
    device.addEventListener("advertisementreceived", onAdvertisement);
    device.watchAdvertisements({ signal: abort.signal }).catch(() => markHeard(true));
    return {
      heard,
      stop() {
        device.removeEventListener("advertisementreceived", onAdvertisement);
        abort.abort();
      }
    };
  }

  // Links a remembered toy without the chooser: scan until it is heard, then
  // connect (scan still running), retrying once. Resolves with the GATT
  // server; rejects with a `quiet` error when the toy is not found or refuses
  // the link, or a `stopped` one when |signal| aborts.
  async function connectWithRetries(device, options = {}) {
    const t = { ...TIMING, ...options };
    const signal = options.signal || null;
    const android = /Android/i.test(options.userAgent || "");
    const deadline = Date.now() + t.findMs;
    let scan = null;
    try {
      let heard = false;
      while (!heard && Date.now() < deadline) {
        scan = watchToy(device);
        const scanMs = android ? t.findMs : t.hearMs;
        heard = await orStop(withTimeout(scan.heard, Math.min(scanMs, deadline - Date.now()), false), signal);
        if (!heard) {
          scan.stop();
          scan = null;
        }
      }
      if (!heard) throw Object.assign(new Error("not in range"), { quiet: true });

      // Connecting to a toy the browser has not heard fails at once, so the
      // scan keeps running through the connect and stops after it.
      let lastError;
      for (let attempt = 1; attempt <= t.attempts; attempt += 1) {
        try {
          const server = await orStop(withTimeout(device.gatt.connect(), t.attemptMs, null), signal);
          if (!server) throw new Error("connect timed out");
          return server;
        } catch (error) {
          if (error && error.stopped) throw error;
          lastError = error;
          // Drops a pending connect too, so the next attempt starts clean.
          if (device.gatt) device.gatt.disconnect();
          if (attempt < t.attempts) await orStop(sleep(t.retryMs), signal);
        }
      }
      lastError.quiet = true;
      throw lastError;
    } finally {
      if (scan) scan.stop();
    }
  }

  const api = {
    LAST_DEVICE_KEY, TIMING, MESSAGES, REFUSALS,
    rememberedId, remember, rememberedDevice, withTimeout, orStop, watchToy, connectWithRetries
  };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.SweetYaarBle = api;
})(typeof self !== "undefined" ? self : globalThis);

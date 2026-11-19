"use strict";

// Read-only BLE client for SweetYaar Studio: connects to the toy and lists its
// themes, songs and animal sounds with the same scanThemes / scanSongs
// commands the parent remote uses (see "Configuration transport" in
// docs/engineering/firmware.md). It never writes content. Finding the toy,
// remembering it and the refusal messages come from ../ble-connect.js, shared
// with the parent remote.
(function (root) {
  const BLE = typeof module !== "undefined" && module.exports ? require("../ble-connect.js") : root.SweetYaarBle;
  const prefix = "a1b2c3d4-e5f6-7890-abcd-ef123456";
  const UUIDS = {
    service: prefix + "7890",
    configCommand: prefix + "7897",
    configResponse: prefix + "7898",
    access: prefix + "78a1"
  };
  const LAST_DEVICE_KEY = BLE.LAST_DEVICE_KEY;
  const M = BLE.MESSAGES;

  const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  function friendly(message) {
    const error = new Error(message);
    error.userMessage = message;
    return error;
  }

  function normalizeThemes(themes) {
    if (!Array.isArray(themes)) return [];
    return themes
      .filter((theme) => theme && typeof theme.id === "string")
      .map((theme) => ({
        id: theme.id,
        name: typeof theme.name === "string" && theme.name ? theme.name : theme.id,
        credit: typeof theme.credit === "string" ? theme.credit : "",
        enabled: !!theme.enabled,
        special: !!theme.special,
        shuffle: !!theme.shuffle,
        disabledByUser: !!theme.disabledByUser,
        activeValid: Number(theme.activeValid) || 0,
        total: Number(theme.total) || 0,
        errors: Number(theme.errors) || 0
      }));
  }

  function normalizeSongs(songs) {
    if (!Array.isArray(songs)) return [];
    return songs
      .filter((song) => song && typeof song.file === "string")
      .map((song) => ({
        file: song.file,
        enabled: !!song.enabled,
        ok: !!song.ok,
        sizeBytes: Number(song.sizeBytes) || 0,
        durationMs: Number(song.durationMs) || 0,
        error: typeof song.error === "string" ? song.error : ""
      }));
  }

  // |bluetooth| is navigator.bluetooth, |storage| a localStorage-like object.
  function createClient(bluetooth, storage, onDisconnect) {
    const encoder = new TextEncoder();
    const decoder = new TextDecoder("utf-8");
    let device = null;
    let chars = null;
    let requestId = 0;
    let queue = Promise.resolve();

    function serialized(operation) {
      const result = queue.then(operation);
      queue = result.catch(() => {});
      return result;
    }

    function handleDisconnected(event) {
      if (event.target !== device) return;
      device = null;
      chars = null;
      if (onDisconnect) onDisconnect();
    }

    async function checkAccess(service, dev) {
      const access = await service.getCharacteristic(UUIDS.access);
      const deadline = Date.now() + 30000;
      while (dev.gatt.connected) {
        const value = await access.readValue();
        if (value.byteLength !== 1) throw friendly("Couldn't check device access. Please reconnect.");
        const state = value.getUint8(0);
        if (state === 2) return;
        if (BLE.REFUSALS[state]) throw friendly(BLE.REFUSALS[state]);
        if (state === 3) throw friendly("Couldn't authenticate. Reconnect and check for a Bluetooth pairing request.");
        if (state === 4) throw friendly(M.takeover);
        if (state !== 1 || Date.now() >= deadline) {
          throw friendly("Pairing did not finish. Reconnect and check for a Bluetooth pairing request.");
        }
        await delay(150);
      }
      throw friendly(M.pairingHint);
    }

    async function open(dev, signal = null) {
      dev.addEventListener("gattserverdisconnected", handleDisconnected);
      device = dev;
      try {
        const server = await BLE.orStop(dev.gatt.connect(), signal);
        const service = await server.getPrimaryService(UUIDS.service);
        await checkAccess(service, dev);
        chars = {
          command: await service.getCharacteristic(UUIDS.configCommand),
          response: await service.getCharacteristic(UUIDS.configResponse)
        };
        BLE.remember(storage, dev.id);
      } catch (error) {
        const failed = dev;
        device = null;
        chars = null;
        failed.removeEventListener("gattserverdisconnected", handleDisconnected);
        failed.gatt.disconnect();   // also drops a connect still pending
        throw error.userMessage || error.stopped ? error : friendly(M.pairingHint);
      }
      return dev;
    }

    async function request(payload) {
      if (!chars) throw friendly("Not connected to a SweetYaar.");
      return serialized(async () => {
        const current = chars;
        const id = ++requestId;
        const command = JSON.stringify({ id, ...payload });
        if (encoder.encode(command).length > 383) throw friendly("That name is too long for the toy.");
        await current.command.writeValueWithResponse(encoder.encode(command));
        const deadline = Date.now() + 15000;
        while (Date.now() < deadline) {
          await delay(80);
          if (chars !== current) throw friendly("The toy disconnected.");
          let reply = null;
          try { reply = JSON.parse(decoder.decode(await current.response.readValue()) || "{}"); } catch { reply = null; }
          if (!reply || !Number.isSafeInteger(reply.id) || typeof reply.ok !== "boolean") {
            throw friendly("The toy returned an invalid reply. Please try again.");
          }
          if (reply.id !== id) continue;
          if (!reply.ok) throw friendly(reply.error || "The toy rejected the command.");
          return reply;
        }
        throw friendly("The toy did not reply in time. Please try again.");
      });
    }

    async function scan(op, extra, key, normalize) {
      const rows = [];
      let cursor = 0;
      for (;;) {
        const reply = await request({ op, ...extra, cursor });
        rows.push(...normalize(reply[key]));
        if (!reply.hasMore) return rows;
        if (!Number.isSafeInteger(reply.nextCursor) || reply.nextCursor <= cursor) {
          throw friendly("The toy returned a scan page without progress.");
        }
        cursor = reply.nextCursor;
      }
    }

    return {
      supported: !!bluetooth,
      get connected() { return !!device && device.gatt.connected; },
      get name() { return (device && device.name) || "SweetYaar"; },

      // Is there a toy to try without a prompt? (remembered and still granted)
      hasRemembered: () => !!BLE.rememberedId(storage),

      // Opens the browser's chooser; must run from a click. |signal| (an
      // AbortSignal) stops the link being set up afterwards.
      async connect({ signal = null } = {}) {
        let dev;
        try {
          dev = await bluetooth.requestDevice({ filters: [{ services: [UUIDS.service] }] });
        } catch (error) {
          if (error && error.name === "NotFoundError") return null;
          throw error;
        }
        try { return await open(dev, signal); } catch (error) { if (error.stopped) return null; throw error; }
      },

      // Reconnects without a prompt to the toy this browser used last, the
      // same way the parent remote does (listen for it, then link, retrying
      // once). Null when there is none, it is not found or |signal| stops it;
      // throws, with a userMessage, when the toy refuses.
      async reconnect({ signal = null, userAgent = "" } = {}) {
        const known = await BLE.rememberedDevice(bluetooth, storage);
        if (!known) return null;
        try {
          await BLE.connectWithRetries(known, { signal, userAgent });
          return await open(known, signal);
        } catch (error) {
          known.gatt.disconnect();
          if (error.userMessage) throw error;
          return null;
        }
      },

      disconnect() {
        const dev = device;
        device = null;
        chars = null;
        if (dev) {
          dev.removeEventListener("gattserverdisconnected", handleDisconnected);
          if (dev.gatt.connected) dev.gatt.disconnect();
        }
      },

      scanThemes: () => scan("scanThemes", {}, "themes", normalizeThemes),
      scanSongs: (themeId) => scan("scanSongs", { theme: themeId }, "songs", normalizeSongs)
    };
  }

  const api = { createClient, normalizeThemes, normalizeSongs, UUIDS, LAST_DEVICE_KEY };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.SweetYaarDevice = api;
})(typeof self !== "undefined" ? self : globalThis);

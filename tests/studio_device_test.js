"use strict";

// app/public/studio/device.js against a fake Web Bluetooth device.
const assert = require("assert");
const { createClient, UUIDS, LAST_DEVICE_KEY } = require("../app/public/studio/device.js");

const encoder = new TextEncoder();
const decoder = new TextDecoder();

// The toy: answers scanThemes and scanSongs in pages of two rows.
function fakeToy({ accessStates = [2], pageSize = 2 } = {}) {
  const themes = [
    { id: "lullabies", name: "Lullabies", enabled: true, total: 3, activeValid: 3 },
    { id: "bedtime", name: "Bedtime", enabled: false, total: 1, errors: 1 },
    { id: "animals", name: "Animals", enabled: true, special: true, total: 3 }
  ];
  const songs = {
    lullabies: ["a.wav", "b.wav", "c.wav"].map((file) => ({ file, enabled: true, ok: true, sizeBytes: 1000, durationMs: 60000 })),
    bedtime: [{ file: "x.wav", enabled: false, ok: false, error: "bad format" }],
    animals: ["cat.wav", "dog.wav", "cow.wav"].map((file) => ({ file, enabled: true, ok: true, sizeBytes: 50, durationMs: 2000 }))
  };
  let reply = "{}";
  const states = [...accessStates];
  const characteristics = {
    [UUIDS.access]: { async readValue() { return new DataView(Uint8Array.of(states.length > 1 ? states.shift() : states[0]).buffer); } },
    [UUIDS.configCommand]: {
      async writeValueWithResponse(bytes) {
        const cmd = JSON.parse(decoder.decode(bytes));
        const rows = cmd.op === "scanThemes" ? themes : songs[cmd.theme] || [];
        const key = cmd.op === "scanThemes" ? "themes" : "songs";
        const next = cmd.cursor + pageSize;
        reply = JSON.stringify({ id: cmd.id, ok: true, op: cmd.op, cursor: cmd.cursor, nextCursor: next, hasMore: next < rows.length, [key]: rows.slice(cmd.cursor, next) });
      }
    },
    [UUIDS.configResponse]: { async readValue() { return encoder.encode(reply); } }
  };
  const listeners = {};
  const device = {
    id: "dev-1", name: "SweetYaar-ABCD",
    gatt: {
      connected: false,
      async connect() { this.connected = true; return { getPrimaryService: async () => ({ getCharacteristic: async (uuid) => characteristics[uuid] }) }; },
      disconnect() { this.connected = false; }
    },
    addEventListener(name, fn) { listeners[name] = fn; },
    removeEventListener() {}
  };
  return { device, drop: () => { device.gatt.connected = false; listeners.gattserverdisconnected({ target: device }); } };
}

function memoryStorage() {
  const m = new Map();
  return { getItem: (k) => (m.has(k) ? m.get(k) : null), setItem: (k, v) => m.set(k, v) };
}

async function main() {
  // connect, remember the toy, scan with pagination
  {
    const toy = fakeToy();
    const storage = memoryStorage();
    let lost = 0;
    const client = createClient({ requestDevice: async () => toy.device }, storage, () => lost++);
    assert.ok(await client.connect());
    assert.strictEqual(client.name, "SweetYaar-ABCD");
    assert.strictEqual(storage.getItem(LAST_DEVICE_KEY), "dev-1");
    const themes = await client.scanThemes();
    assert.deepStrictEqual(themes.map((t) => t.id), ["lullabies", "bedtime", "animals"]);
    assert.ok(themes[2].special);
    assert.strictEqual((await client.scanSongs("lullabies")).length, 3);
    assert.strictEqual((await client.scanSongs("bedtime"))[0].error, "bad format");
    toy.drop();
    assert.strictEqual(lost, 1);
    assert.strictEqual(client.connected, false);
    await assert.rejects(() => client.scanThemes(), /Not connected/);
  }

  // pairing pending then approved
  {
    const toy = fakeToy({ accessStates: [1, 2] });
    const client = createClient({ requestDevice: async () => toy.device }, memoryStorage());
    assert.ok(await client.connect());
  }

  // unapproved toy: friendly message, link dropped
  {
    const toy = fakeToy({ accessStates: [0] });
    const client = createClient({ requestDevice: async () => toy.device }, memoryStorage());
    await assert.rejects(() => client.connect(), /not approved/);
    assert.strictEqual(toy.device.gatt.connected, false);
  }

  // chooser cancelled
  {
    const client = createClient({ requestDevice: async () => { const e = new Error("none"); e.name = "NotFoundError"; throw e; } }, memoryStorage());
    assert.strictEqual(await client.connect(), null);
  }

  // silent reconnect only for a remembered, granted toy
  {
    const toy = fakeToy();
    const storage = memoryStorage();
    const bluetooth = { getDevices: async () => [toy.device] };
    assert.strictEqual(await createClient(bluetooth, storage).reconnect(), null);
    storage.setItem(LAST_DEVICE_KEY, "dev-1");
    const client = createClient(bluetooth, storage);
    assert.ok(await client.reconnect());
    assert.ok(client.connected);
    assert.strictEqual(await createClient({}, storage).reconnect(), null);
  }

  // Shared with the parent remote: one "last toy" key, Studio's old key read once.
  {
    const BLE = require("../app/public/ble-connect.js");
    assert.strictEqual(LAST_DEVICE_KEY, BLE.LAST_DEVICE_KEY);
    assert.strictEqual(LAST_DEVICE_KEY, "sweetyaar-last-device-id");
    const toy = fakeToy();
    const storage = memoryStorage();
    storage.removeItem = (k) => storage.setItem(k, "");
    storage.setItem("sweetyaar.lastDeviceId", "dev-1");
    const client = createClient({ getDevices: async () => [toy.device] }, storage);
    assert.strictEqual(client.hasRemembered(), true);
    assert.ok(await client.reconnect());
    assert.strictEqual(storage.getItem(LAST_DEVICE_KEY), "dev-1");
    assert.strictEqual(storage.getItem("sweetyaar.lastDeviceId"), "");
  }

  // Reconnect listens for the toy first; Stop ends it without a link.
  {
    const toy = fakeToy();
    let scans = 0, connects = 0;
    toy.device.watchAdvertisements = async () => { scans += 1; };   // never hears it
    const connect = toy.device.gatt.connect.bind(toy.device.gatt);
    toy.device.gatt.connect = () => { connects += 1; return connect(); };
    const storage = memoryStorage(); storage.setItem(LAST_DEVICE_KEY, "dev-1");
    const client = createClient({ getDevices: async () => [toy.device] }, storage);
    const abort = new AbortController();
    const attempt = client.reconnect({ signal: abort.signal });
    await new Promise((resolve) => setTimeout(resolve, 50));
    abort.abort();
    assert.strictEqual(await attempt, null);
    assert.strictEqual(scans, 1);
    assert.strictEqual(connects, 0);
    assert.strictEqual(client.connected, false);
  }

  // A refusal is explained with the remote's words, including the newer ones.
  {
    const BLE = require("../app/public/ble-connect.js");
    for (const [state, message] of [[6, BLE.MESSAGES.remoteBusy], [7, BLE.MESSAGES.toyBusy], [5, BLE.MESSAGES.audioBusy]]) {
      const toy = fakeToy({ accessStates: [state] });
      const storage = memoryStorage(); storage.setItem(LAST_DEVICE_KEY, "dev-1");
      const client = createClient({ getDevices: async () => [toy.device] }, storage);
      await assert.rejects(client.reconnect(), (e) => e.userMessage === message);
      assert.strictEqual(client.connected, false);
    }
  }

  console.log("studio device tests passed");
}

main().catch((error) => { console.error(error); process.exit(1); });

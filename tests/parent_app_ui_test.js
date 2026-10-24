"use strict";

const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const { TextDecoder, TextEncoder } = require("util");

const root = path.resolve(__dirname, "..");
const html = fs.readFileSync(path.join(root, "app", "public", "index.html"), "utf8");
const match = html.match(/<script>\s*([\s\S]*?)\s*<\/script>/);
assert(match, "app/public/index.html must contain the parent app script");
const appScript = match[1];

class FakeClassList {
  constructor(owner) {
    this.owner = owner;
    this.values = new Set();
  }

  setFromString(value) {
    this.values = new Set(String(value || "").split(/\s+/).filter(Boolean));
  }

  toggle(name, force) {
    const enabled = force === undefined ? !this.values.has(name) : !!force;
    if (enabled) {
      this.values.add(name);
    } else {
      this.values.delete(name);
    }
    this.owner._className = [...this.values].join(" ");
    return enabled;
  }

  add(...names) {
    for (const name of names) this.values.add(name);
    this.owner._className = [...this.values].join(" ");
  }

  remove(...names) {
    for (const name of names) this.values.delete(name);
    this.owner._className = [...this.values].join(" ");
  }

  contains(name) {
    return this.values.has(name);
  }
}

class FakeElement {
  constructor(selector) {
    this.selector = selector;
    this.attributes = {};
    this.children = [];
    this.parentElement = null;
    this.dataset = {};
    this.hidden = false;
    this.disabled = false;
    this.checked = false;
    this.value = "";
    this.textContent = "";
    this.innerHTML = "";
    this.clientWidth = selector === ".app" ? 390 : 0;
    this.clientHeight = selector === ".app" ? 844 : 0;
    this._className = "";
    this.classList = new FakeClassList(this);
    this.style = {
      values: {},
      setProperty: (name, value) => {
        this.style.values[name] = value;
      },
    };
    this.listeners = {};
  }

  get className() {
    return this._className;
  }

  set className(value) {
    this._className = String(value || "");
    this.classList.setFromString(this._className);
  }

  querySelector(selector) {
    return getElement(`${this.selector} ${selector}`);
  }

  setAttribute(name, value) {
    this.attributes[name] = String(value);
    if (name === "id") {
      this.id = String(value);
    }
  }

  getAttribute(name) {
    return this.attributes[name];
  }

  addEventListener(name, handler) {
    this.listeners[name] ??= [];
    this.listeners[name].push(handler);
  }

  async dispatch(name, extra = {}, existingEvent = null) {
    const event = existingEvent || {
      target: this,
      currentTarget: this,
      cancelBubble: false,
      stopPropagation() {
        this.cancelBubble = true;
      },
      preventDefault() {},
      ...extra,
    };
    event.currentTarget = this;
    const listeners = this.listeners[name] || [];
    for (const listener of listeners) {
      await listener(event);
    }
    if (!event.cancelBubble && this.parentElement) {
      await this.parentElement.dispatch(name, extra, event);
    }
  }

  async click() {
    await this.dispatch("click");
    // Let fire-and-forget DOM handlers finish their queued GATT microtasks.
    await new Promise((resolve) => setTimeout(resolve, 0));
  }

  async input(value) {
    this.value = String(value);
    await this.dispatch("input");
  }

  async change(value) {
    if (typeof value === "boolean") {
      this.checked = value;
    } else if (value !== undefined) {
      this.value = String(value);
    }
    await this.dispatch("change");
  }

  replaceChildren(...children) {
    this.children = [];
    this.append(...children);
  }

  append(...children) {
    for (const child of children) {
      if (child instanceof FakeElement) {
        child.parentElement = this;
      }
      this.children.push(child);
    }
  }

  appendChild(child) {
    this.append(child);
  }

  closest(selector) {
    if (selector.startsWith(".") && this.classList.contains(selector.slice(1))) {
      return this;
    }
    if (selector.startsWith("#") && this.id === selector.slice(1)) {
      return this;
    }
    return this.parentElement?.closest(selector) || null;
  }

  getBoundingClientRect() {
    return { width: this.clientWidth || 390, height: this.selector === ".hero" ? 174 : 0 };
  }
}

let elements;

function getElement(selector) {
  if (!elements.has(selector)) {
    elements.set(selector, new FakeElement(selector));
  }
  return elements.get(selector);
}

function createContext() {
  elements = new Map();
  const document = {
    activeElement: null,
    documentElement: getElement("documentElement"),
    querySelector: getElement,
    createElement: (tag) => new FakeElement(tag),
  };
  const window = {
    innerWidth: 390,
    innerHeight: 844,
    isSecureContext: true,
    addEventListener() {},
    matchMedia: () => ({ matches: false }),
  };
  const consoleOutput = [];
  return {
    assert,
    console: {
      info: (...args) => consoleOutput.push(["info", ...args]),
      warn: (...args) => consoleOutput.push(["warn", ...args]),
      error: (...args) => consoleOutput.push(["error", ...args]),
    },
    DataView,
    Date,
    Math,
    Number,
    Object,
    Promise,
    JSON,
    Array,
    String,
    Error,
    TextDecoder,
    TextEncoder,
    Uint8Array,
    URL,
    setTimeout,
    clearTimeout,
    crypto: require("crypto").webcrypto,
    localStorage: (() => {
      const values = new Map();
      return {
        getItem: (key) => (values.has(key) ? values.get(key) : null),
        setItem: (key, value) => values.set(key, String(value)),
      };
    })(),
    setInterval: () => 0,
    clearInterval: () => {},
    requestAnimationFrame: () => 0,
    document,
    window,
    navigator: { bluetooth: {} },
    __consoleOutput: consoleOutput,
  };
}

async function runInApp(testSource, bindings = {}) {
  const context = Object.assign(createContext(), bindings);
  const source = `${appScript}\n${appTestHelpers}\n(async () => {\n${testSource}\n})()`;
  return vm.runInNewContext(source, context, { filename: "app/public/index.html" });
}

const appTestHelpers = String.raw`
function assertVisible(visibleEl, hiddenEls = []) {
  assert.strictEqual(visibleEl.hidden, false);
  for (const el of hiddenEls) {
    assert.strictEqual(el.hidden, true);
  }
}

function bytesView(bytes) {
  const data = bytes instanceof Uint8Array ? bytes : Uint8Array.from(bytes);
  return new DataView(data.buffer, data.byteOffset, data.byteLength);
}

function textView(text) {
  const bytes = textEncoder.encode(text);
  return bytesView(bytes);
}

function uint8View(value) {
  return bytesView([value]);
}

function uint16View(value) {
  return bytesView([value & 0xff, (value >> 8) & 0xff]);
}

function textFromValue(value) {
  return textDecoder.decode(value);
}

class FakeCharacteristic {
  constructor(name, initialValue, hooks = {}) {
    this.name = name;
    this.value = initialValue;
    this.hooks = hooks;
    this.writes = [];
    this.listeners = {};
    this.properties = {
      read: true,
      write: true,
      writeWithoutResponse: false,
      notify: true,
      indicate: false
    };
  }

  async readValue() {
    if (this.hooks.beforeRead) {
      await this.hooks.beforeRead(this.name);
    }
    try {
      const value = typeof this.value === "number" ? uint8View(this.value)
        : this.value instanceof DataView ? this.value : textView(String(this.value ?? ""));
      // Web Bluetooth fires this event for reads as well as notifications.
      for (const listener of this.listeners.characteristicvaluechanged || []) {
        listener({ target: { value } });
      }
      return value;
    } finally {
      if (this.hooks.afterRead) {
        this.hooks.afterRead(this.name);
      }
    }
  }

  async writeValueWithResponse(value) {
    this.write(value);
  }

  async writeValue(value) {
    this.write(value);
  }

  async writeValueWithoutResponse(value) {
    this.write(value);
  }

  write(value) {
    this.writes.push(value);
    this.value = value;
  }

  addEventListener(name, handler) {
    this.listeners[name] ??= [];
    this.listeners[name].push(handler);
  }

  removeEventListener(name, handler) {
    this.listeners[name] = (this.listeners[name] || []).filter((item) => item !== handler);
  }

  async startNotifications() {
    if (this.hooks.onStartNotifications) {
      this.hooks.onStartNotifications(this.name);
    }
  }

  invalidate() {
    for (const listener of this.listeners.characteristicvaluechanged || []) {
      listener({ target: { value: uint8View(1) } });
    }
  }

  emit(value) {
    this.value = value;
    const data = typeof value === "number" ? uint8View(value)
      : value instanceof DataView ? value : textView(String(value));
    for (const listener of this.listeners.characteristicvaluechanged || []) {
      listener({ target: { value: data } });
    }
  }
}

function makeBleHarness(options = {}) {
  const writes = {
    subscriptionsAtConfigWrite: [],
    command: [],
    volume: [],
    theme: [],
    killswitch: [],
    config: []
  };
  const config = {
    deviceName: options.deviceName || "SweetYaar",
    defaultVolumePct: 75,
    defaultTheme: "lullabies",
    activeTheme: "lullabies",
    loop: options.loop ?? false,
    sleep: {
      enabled: true,
      normalIdleSec: 600,
      vibrationWakeIdleSec: 120,
      bleIdleSec: 120
    },
    bedtime: {
      enabled: true,
      startTime: "18:30",
      endTime: "06:30",
      theme: "lullabies",
      volumeCapPct: 45,
      timeKnown: false,
      currentTime: "",
      currentSecondOfDay: null,
      active: false,
      autoActive: false,
      override: "none",
      effectiveVolumePct: 75,
      effectiveTheme: "lullabies"
    },
    ...(options.config || {})
  };
  config.sleep = {
    enabled: true,
    normalIdleSec: 600,
    vibrationWakeIdleSec: 120,
    bleIdleSec: 120,
    ...(options.config?.sleep || {})
  };
  config.bedtime = {
    enabled: true,
    startTime: "18:30",
    endTime: "06:30",
    theme: "lullabies",
    volumeCapPct: 45,
    timeKnown: false,
    active: false,
    autoActive: false,
    override: "none",
    effectiveVolumePct: 75,
    effectiveTheme: "lullabies",
    ...(options.config?.bedtime || {})
  };

  const themes = options.themes || [
    { id: "lullabies", name: "Lullabies", enabled: true, disabledByUser: false, shuffle: false, canSetDefault: true, activeValid: 2, total: 2, errors: 0 },
    { id: "nature", name: "Nature", enabled: true, disabledByUser: false, shuffle: true, canSetDefault: true, activeValid: 1, total: 1, errors: 0 }
  ];
  const songs = options.songs || {
    lullabies: [{ file: "moon.wav", enabled: true, ok: true, sizeBytes: 1000, durationMs: 1000 }],
    nature: [{ file: "rain.wav", enabled: true, ok: true, sizeBytes: 1200, durationMs: 1100 }]
  };

  function configResponse(payload) {
    if (payload.op === "syncTime") {
      if (options.rejectSyncTime) {
        return { id: payload.id, ok: false, error: "Unknown config command" };
      }
      config.bedtime.timeKnown = true;
      config.bedtime.currentTime = options.deviceTime || config.bedtime.currentTime || "21:05";
      config.bedtime.currentSecondOfDay = options.deviceSecondOfDay ?? config.bedtime.currentSecondOfDay ?? 75907;
      return { id: payload.id, ok: true, op: payload.op };
    }
    if (payload.op === "setConfig") {
      if (Object.prototype.hasOwnProperty.call(payload, "deviceName")) config.deviceName = payload.deviceName;
      if (Object.prototype.hasOwnProperty.call(payload, "defaultVolumePct")) config.defaultVolumePct = payload.defaultVolumePct;
      if (Object.prototype.hasOwnProperty.call(payload, "defaultTheme")) {
        config.defaultTheme = payload.defaultTheme;
      }
      if (payload.sleep) config.sleep = { ...config.sleep, ...payload.sleep };
      if (payload.bedtime) config.bedtime = { ...config.bedtime, ...payload.bedtime };
      return { id: payload.id, ok: true, op: payload.op };
    }
    if (payload.op === "setBedtimeMode") {
      config.bedtime.active = !!payload.active && config.bedtime.enabled && config.bedtime.timeKnown;
      config.bedtime.override = payload.active ? "on" : "off";
      config.bedtime.effectiveVolumePct = config.bedtime.active
        ? Math.min(config.defaultVolumePct, config.bedtime.volumeCapPct)
        : config.defaultVolumePct;
      config.bedtime.effectiveTheme = config.bedtime.active ? config.bedtime.theme : config.activeTheme;
      return { id: payload.id, ok: true, op: payload.op };
    }
    if (payload.op === "scanThemes") {
      return { id: payload.id, ok: true, op: "scanThemes", cursor: payload.cursor || 0, nextCursor: 0, hasMore: false, themes };
    }
    if (payload.op === "scanSongs") {
      return {
        id: payload.id,
        ok: true,
        op: "scanSongs",
        theme: payload.theme,
        name: themes.find((theme) => theme.id === payload.theme)?.name || payload.theme,
        cursor: payload.cursor || 0, nextCursor: 0,
        hasMore: false,
        songs: songs[payload.theme] || []
      };
    }
    if (payload.op === "setTheme" || payload.op === "setSong") {
      return { id: payload.id, ok: true, op: payload.op };
    }
    return { id: payload.id, ok: false, error: "unknown op" };
  }

  function publishConfigResponse(characteristic) {
    if (options.synchronousConfigNotify) {
      characteristic.emit(characteristic.value);
    } else {
      setTimeout(() => characteristic.emit(characteristic.value), 0);
    }
  }

  let response = { id: 0, ok: true };
  let activeReads = 0;
  let maxConcurrentReads = 0;
  const reads = [];
  const notifications = [];
  const readHooks = {
    async beforeRead(name) {
      // Only access-focused tests set accessState and assert its reads.
      if (name === "access" && options.accessState === undefined) return;
      reads.push(name);
      if (!options.trackConcurrentReads) return;
      activeReads += 1;
      maxConcurrentReads = Math.max(maxConcurrentReads, activeReads);
      await delay(5);
    },
    afterRead(name) {
      if (name === "access" && options.accessState === undefined) return;
      if (!options.trackConcurrentReads) return;
      activeReads -= 1;
    },
    onStartNotifications(name) {
      notifications.push(name);
    }
  };
  const chars = {
    volume: new FakeCharacteristic("volume", options.volume ?? 75, readHooks),
    killswitch: new FakeCharacteristic("killswitch", uint16View(options.quietSeconds ?? 0), readHooks),
    theme: new FakeCharacteristic("theme", options.theme || "lullabies", readHooks),
    status: new FakeCharacteristic("status", options.status || "Idle", readHooks),
    themes: new FakeCharacteristic("themes", JSON.stringify(themes.filter((theme) => theme.enabled).map((theme) => ({ id: theme.id, name: theme.name }))), readHooks),
    command: new FakeCharacteristic("command", "", readHooks),
    configCommand: new FakeCharacteristic("configCommand", "{}", readHooks),
    configResponse: new FakeCharacteristic("configResponse", JSON.stringify(response), readHooks),
    notice: new FakeCharacteristic("notice", "{}", readHooks),
    battery: new FakeCharacteristic("battery", options.battery ?? 1, readHooks),
    charger: new FakeCharacteristic("charger", bytesView(options.charger ?? [1, 4, 3, 0, 0, 0]), readHooks)
  };
  chars.access = new FakeCharacteristic("access", options.accessState ?? 2, readHooks);

  // A toy that implements the firmware-update protocol: restarts between
  // normal and update mode, accepts only the next expected offset, and
  // reports progress in the 18-byte status.
  const ota = {
    mode: options.firmwareMode || "normal",
    version: options.firmwareVersion || "1.0.0",
    board: options.board || "sweetyaar",
    state: options.firmwareMode === "update" ? 1 : 0,
    error: 0,
    received: 0,
    total: 0,
    sha: "",
    image: [],
    begins: [],
    commands: [],
    restarts: [],
    packets: 0,
    mtu: options.otaMtu ?? 185
  };
  function otaStatusView() {
    const bytes = new Uint8Array(18);
    const view = new DataView(bytes.buffer);
    bytes[0] = 1;
    bytes[1] = ota.state;
    bytes[2] = ota.error;
    view.setUint32(4, ota.received, true);
    view.setUint32(8, ota.total, true);
    view.setUint16(16, ota.mtu, true);
    return bytesView(bytes);
  }
  function firmwareJson() {
    return JSON.stringify({ version: ota.version, board: ota.board, mode: ota.mode });
  }
  chars.firmware = new FakeCharacteristic("firmware", firmwareJson(), readHooks);
  chars.otaControl = new FakeCharacteristic("otaControl", "", readHooks);
  chars.otaData = new FakeCharacteristic("otaData", "", readHooks);
  chars.otaStatus = new FakeCharacteristic("otaStatus", otaStatusView(), readHooks);
  function dropLink() {
    device.gatt.connected = false;
    device.listeners.gattserverdisconnected?.({ target: device });
  }
  function restartToy(mode) {
    ota.restarts.push(mode);
    setTimeout(() => {
      ota.mode = mode;
      ota.state = mode === "update" ? 1 : 0;
      ota.error = 0;
      ota.received = 0;
      ota.total = 0;
      chars.firmware.value = firmwareJson();
      chars.otaStatus.value = otaStatusView();
      dropLink();
    }, 5);
  }
  chars.otaControl.write = (value) => {
    const bytes = Uint8Array.from(value);
    if (bytes[0] === 2 && options.failBegins > 0) {
      options.failBegins -= 1;
      throw new Error("GATT operation failed for unknown reason.");
    }
    ota.commands.push(bytes[0]);
    if (bytes[0] === 1) {
      if (options.enterResponseLost) {
        restartToy("update");
        throw new Error("GATT operation failed for unknown reason.");
      }
      if (options.otaRefuse) {
        ota.error = 1;
        chars.otaStatus.value = otaStatusView();
      } else {
        restartToy("update");
      }
    } else if (bytes[0] === 2) {
      const view = new DataView(bytes.buffer);
      const total = view.getUint32(2, true);
      const sha = Array.from(bytes.slice(10)).join(",");
      ota.begins.push({ total, received: ota.received });
      if (!(ota.state === 2 && ota.sha === sha && ota.total === total)) {
        ota.received = 0;
        ota.image = [];
      }
      Object.assign(ota, { state: 2, error: 0, total, sha });
      chars.otaStatus.value = otaStatusView();
    } else if (bytes[0] === 3) {
      if (ota.state === 2 && ota.received === ota.total) {
        ota.state = 4;
        chars.otaStatus.value = otaStatusView();
        ota.version = options.versionAfterInstall ?? "1.1.0";
        restartToy("normal");
      }
    } else if (bytes[0] === 4 && ota.mode === "update") {
      restartToy("normal");
    }
  };
  chars.otaData.write = (value) => {
    const bytes = Uint8Array.from(value);
    ota.packets += 1;
    if (ota.packets === options.dropOtaPacket) return; // lost on the air
    if (ota.packets === options.disconnectAtPacket) {
      dropLink();
      return;
    }
    const offset = new DataView(bytes.buffer).getUint32(0, true);
    if (ota.state === 2 && offset === ota.received) {
      for (const byte of bytes.slice(4)) ota.image.push(byte);
      ota.received += bytes.length - 4;
    }
    chars.otaStatus.emit(otaStatusView());
  };

  function configValues() {
    const { enabled, startTime, endTime, theme, volumeCapPct, ...runtime } = config.bedtime;
    return {
      configGeneral: { deviceName: config.deviceName, defaultVolumePct: config.defaultVolumePct,
        defaultTheme: config.defaultTheme, sdReady: true,
        ...(options.configFileError ? { error: options.configFileError } : {}) },
      configSleep: config.sleep,
      configBedtime: { enabled, startTime, endTime, theme, volumeCapPct },
      configRuntime: { ...runtime, loop: config.loop, activeTheme: config.activeTheme },
      catalogNotice: { message: options.catalogWarning || "" }
    };
  }
  for (const [name, value] of Object.entries(configValues())) {
    chars[name] = new FakeCharacteristic(name, JSON.stringify(value), readHooks);
  }

  function publishConfigValues() {
    for (const [name, value] of Object.entries(configValues())) {
      const next = JSON.stringify(value);
      if (chars[name].value === next) continue;
      chars[name].value = next;
      if (options.dropConfigNotifications) continue;
      if (options.synchronousConfigNotify) chars[name].invalidate();
      else setTimeout(() => chars[name].invalidate(), options.configNotifyDelay || 0);
    }
  }

  chars.command.write = (value) => {
    assert.strictEqual(value.length, 1, "command only accepts one-byte playback commands");
    const command = value[0];
    assert(command >= 1 && command <= 5);
    writes.command.push(command);
    if (command === 4) config.loop = true;
    if (command === 2 || command === 3 || command === 5) config.loop = false;
    chars.command.value = value;
  };
  chars.configCommand.write = (value) => {
    const payload = JSON.parse(textFromValue(value));
    writes.config.push(payload);
    writes.subscriptionsAtConfigWrite.push(notifications.slice());
    response = configResponse(payload);
    if (response.ok && !payload.op.startsWith("scan")) publishConfigValues();
    chars.configResponse.value = JSON.stringify(response);
    publishConfigResponse(chars.configResponse);
  };
  chars.volume.write = (value) => {
    writes.volume.push(value[0]);
    chars.volume.value = value[0];
  };
  chars.theme.write = (value) => {
    const text = textFromValue(value);
    writes.theme.push(text);
    chars.theme.value = text;
    config.activeTheme = text;
    if (config.bedtime.active) {
      config.bedtime.effectiveTheme = text;
    }
  };
  chars.killswitch.write = (value) => {
    const seconds = value[0] | (value[1] << 8);
    writes.killswitch.push(seconds);
    chars.killswitch.value = uint16View(seconds);
  };

  const charByUuid = new Map(Object.entries(UUIDS).map(([name, uuid]) => [uuid, chars[name]]));
  let releaseRemoteInitialization = () => {};
  const remoteInitializationGate = options.deferRemoteInitialization
    ? new Promise((resolve) => { releaseRemoteInitialization = resolve; })
    : null;
  const service = {
    async getCharacteristic(uuid) {
      const characteristic = charByUuid.get(uuid);
      if (!characteristic || (options.missingCharacteristics || []).includes(characteristic.name)) {
        const error = new Error("missing characteristic");
        error.name = "NotFoundError";
        throw error;
      }
      const handshake = ["status", "access", "firmware", "otaControl", "otaData", "otaStatus"];
      if (remoteInitializationGate && !handshake.includes(characteristic.name)) {
        await remoteInitializationGate;
      }
      return characteristic;
    },
    async getCharacteristics() {
      return Object.values(chars);
    }
  };
  const server = {
    async getPrimaryService(uuid) {
      if (options.serviceError) {
        if (options.disconnectDuringDiscovery) {
          device.gatt.connected = false;
          device.listeners.gattserverdisconnected?.({ target: device });
        }
        throw options.serviceError;
      }
      if (options.missingService) {
        const error = new Error("missing service");
        error.name = "NotFoundError";
        throw error;
      }
      assert.strictEqual(uuid, UUIDS.service);
      return service;
    },
    async getPrimaryServices() {
      if (options.serviceListError) throw options.serviceListError;
      return [];
    }
  };
  const device = {
    name: options.deviceName || "SweetYaar",
    id: "fake-device",
    listeners: {},
    addEventListener(name, handler) {
      this.listeners[name] = handler;
    },
    gatt: {
      connected: false,
      async connect() {
        this.connected = true;
        return server;
      },
      disconnect() {
        this.connected = false;
      }
    }
  };
  let requestCount = 0;
  navigator.bluetooth.requestDevice = async (request) => {
    requestCount += 1;
    if (options.requestError) throw options.requestError;
    return device;
  };

  return {
    chars,
    writes,
    config,
    publishConfigValues,
    device,
    ota,
    reads,
    notifications,
    releaseRemoteInitialization,
    get maxConcurrentReads() { return maxConcurrentReads; },
    get requestCount() { return requestCount; }
  };
}

async function connectWithFakeBle(options = {}) {
  const ble = makeBleHarness(options);
  await els.connectButton.click();
  if (options.waitForRemoteInitialization !== false && state.remoteInitializing) {
    await waitUntil(() => !state.remoteInitializing, "remote initialization");
  }
  return ble;
}

function payloadsWithoutIds(payloads) {
  return JSON.parse(JSON.stringify(payloads.map(({ id, ...payload }) => payload)));
}

function assertJsonEqual(actual, expected) {
  assert.strictEqual(JSON.stringify(actual), JSON.stringify(expected));
}

async function waitUntil(predicate, label, timeoutMs = 2500) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (predicate()) return;
    await delay(20);
  }
  throw new Error("Timed out waiting for " + label);
}

async function makeRelease({ version = "1.1.0", notes = "Bedtime songs fade out gently.", size = 6000, board = "sweetyaar" } = {}) {
  const encoded = new Uint8Array(size);
  for (let i = 0; i < size; i++) encoded[i] = (i * 31 + 7) & 255;
  const fileSha256 = bytesHex(await crypto.subtle.digest("SHA-256", encoded));
  const file = board + "-" + version + ".bin.z";
  const manifest = {
    format: 1, version, notes,
    images: { [board]: { file, encoding: "zlib", size: size * 2, encodedSize: size, sha256: "ab".repeat(32), fileSha256 } }
  };
  const requests = [];
  globalThis.fetch = async (url) => {
    requests.push(url);
    if (url === "firmware/manifest.json") return { ok: true, status: 200, json: async () => manifest };
    if (url === "firmware/" + file) return { ok: true, status: 200, arrayBuffer: async () => encoded.slice().buffer };
    return { ok: false, status: 404 };
  };
  return { manifest, encoded, requests };
}

async function waitForUpdatePhase(phase, timeoutMs = 8000) {
  await waitUntil(() => state.update.phase === phase, "update phase " + phase, timeoutMs);
}

// An optional update is offered on the Doll tab, never on the Ready screen.
async function openOptionalUpdate() {
  assert.strictEqual(els.updateCard.hidden, true);
  await els.tabDoll.click();
  await els.settingsUpdateButton.click();
}

async function waitForSettingsLoaded() {
  await waitUntil(() => state.view === "settings" && state.settings.loading === false, "settings load");
}
`;

const tests = [
  ["bottom tabs switch between Doll, Remote and Settings only while connected", String.raw`
    assert.strictEqual(els.ground.hidden, true);
    const ble = await connectWithFakeBle();
    assert.strictEqual(els.ground.hidden, false);
    assert(els.app.classList.contains("has-tabs"));
    const tabs = [[els.tabDoll, els.chargerView], [els.tabRemote, els.readyView], [els.tabSettings, els.settingsView]];
    const checkActive = (current) => {
      for (const [tab, view] of tabs) {
        assert.strictEqual(tab.classList.contains("active"), tab === current);
        assert.strictEqual(tab.getAttribute("aria-current"), tab === current ? "page" : "false");
        assert.strictEqual(view.hidden, tab !== current);
      }
    };
    checkActive(els.tabRemote);
    await els.tabSettings.click();
    await waitForSettingsLoaded();
    checkActive(els.tabSettings);
    await els.tabDoll.click();
    checkActive(els.tabDoll);
    await els.tabRemote.click();
    checkActive(els.tabRemote);
    assert.strictEqual(els.tabDollDot.hidden, true);
    ble.chars.battery.emit(3);
    assert.strictEqual(els.tabDollDot.hidden, false); // low battery needs a look
    ble.chars.battery.emit(1);
    assert.strictEqual(els.tabDollDot.hidden, true);
    ble.chars.charger.emit(bytesView([1, 4, 3, 0, 0, 1]));
    assert.strictEqual(els.tabDollDot.hidden, false); // charger fault
    ble.device.gatt.disconnect();
    ble.device.listeners.gattserverdisconnected({ target: ble.device });
    assert.strictEqual(els.ground.hidden, true);
    assert(!els.app.classList.contains("has-tabs"));
  `],
  ["newer release puts a bead on the Doll tab until seen, and the Doll tab offers the update", String.raw`
    const release = await makeRelease();
    await connectWithFakeBle();
    await waitUntil(() => state.releaseStatus === "ready", "release manifest");
    assert.strictEqual(els.updateCard.hidden, true); // optional: the remote stays uncluttered
    assert.strictEqual(els.tabDollDot.hidden, false);
    assert.strictEqual(els.tabDoll.getAttribute("aria-label"), "Doll, needs attention");
    assert.strictEqual(els.playSongButton.disabled, false);
    await els.tabDoll.click();
    assertVisible(els.chargerView, [els.readyView, els.settingsView]);
    assert.strictEqual(els.tabDollDot.hidden, true);
    assert.strictEqual(els.tabDoll.getAttribute("aria-label"), "Doll");
    assert.strictEqual(els.settingsFirmwareVersion.textContent, "1.0.0");
    assert.strictEqual(els.settingsLatestVersion.textContent, "1.1.0");
    assert.strictEqual(els.settingsUpdateButton.hidden, false);
    assert.strictEqual(els.settingsUpdateButton.textContent, "Update to 1.1.0");
    assert(els.settingsUpdateNote.textContent.includes("Bedtime songs fade out gently."));
    await els.settingsUpdateButton.click();
    assertVisible(els.updateView, [els.chargerView, els.readyView, els.openingView]);
    assert.strictEqual(els.updateConfirmVersion.textContent, "Version 1.1.0: Bedtime songs fade out gently.");
    await els.updateSecondaryButton.click(); // Not now
    assertVisible(els.chargerView, [els.updateView]);
    await els.tabRemote.click();
    assertVisible(els.readyView, [els.chargerView]);
    assert.strictEqual(els.tabDollDot.hidden, true); // seen stays seen
    assert(release.requests.includes("firmware/manifest.json"));
  `],
  ["current version offers only a reinstall, on the Doll tab", String.raw`
    await makeRelease();
    await connectWithFakeBle({ firmwareVersion: "1.1.0" });
    await waitUntil(() => state.releaseStatus === "ready", "release manifest");
    assert.strictEqual(els.updateCard.hidden, true);
    assert.strictEqual(els.tabDollDot.hidden, true);
    await els.tabDoll.click();
    assert.strictEqual(els.settingsUpdateButton.textContent, "Reinstall 1.1.0");
    await els.settingsUpdateButton.click();
    assert.strictEqual(els.updateConfirmVersion.textContent, "Reinstall version 1.1.0.");
    assert.strictEqual(els.updatePrimaryButton.textContent, "Reinstall");
  `],
  ["no published release leaves the Doll tab without an update button", String.raw`
    globalThis.fetch = async () => ({ ok: false, status: 404 });
    await connectWithFakeBle();
    await waitUntil(() => state.releaseStatus === "none", "missing manifest");
    assert.strictEqual(els.updateCard.hidden, true);
    await els.tabDoll.click();
    assert.strictEqual(els.settingsLatestVersion.textContent, "None published");
    assert.strictEqual(els.settingsUpdateButton.hidden, true);
    assert.strictEqual(els.settingsUpdateNote.hidden, true);
  `],
  ["firmware older than the app supports locks the remote until updated", String.raw`
    await makeRelease();
    await connectWithFakeBle({ firmwareVersion: "0.9.0" });
    await waitUntil(() => state.releaseStatus === "ready", "release manifest");
    assert.strictEqual(els.updateCard.hidden, false);
    assert.strictEqual(els.updateCardButton.hidden, false);
    assert.strictEqual(els.playSongButton.disabled, true);
    assert.strictEqual(els.volumeRange.disabled, true);
  `],
  ["low battery blocks starting an update until the doll charges", String.raw`
    await makeRelease();
    const ble = await connectWithFakeBle({ battery: 3 });
    await waitUntil(() => state.releaseStatus === "ready", "release manifest");
    await openOptionalUpdate();
    assert.strictEqual(els.updatePrimaryButton.disabled, true);
    assert.strictEqual(els.updateBatteryWarning.hidden, false);
    assert.strictEqual(els.updateBatteryText.textContent, "Battery too low, connect a charger");
    assert(els.updateBatteryItem.classList.contains("battery-low"));
    await els.updatePrimaryButton.click();
    assert.strictEqual(state.update.active, false);
    ble.chars.battery.emit(4);
    assert.strictEqual(els.updatePrimaryButton.disabled, false);
    assert.strictEqual(els.updateBatteryWarning.hidden, true);
    assert.strictEqual(els.updateBatteryText.textContent, "Charging, all good");
    assert(els.updateBatteryItem.classList.contains("battery-charging"));
    assert(!els.updateBatteryItem.classList.contains("battery-low"));
  `],
  ["update restarts into update mode, resends a lost chunk, installs and reconnects", String.raw`
    const release = await makeRelease();
    const wakeLocks = [];
    navigator.wakeLock = { request: async () => {
      const lock = { released: false, release: async () => { lock.released = true; } };
      wakeLocks.push(lock);
      return lock;
    } };
    const ble = await connectWithFakeBle({ dropOtaPacket: 3 });
    await waitUntil(() => state.releaseStatus === "ready", "release manifest");
    await openOptionalUpdate();
    await els.updatePrimaryButton.click();
    assert.strictEqual(state.update.active, true);
    await waitForUpdatePhase("sending");
    assert.strictEqual(els.updateKeepOpen.hidden, false);
    assert(els.updateBackButton.classList.contains("placeholder"));
    assert.strictEqual(els.updateBackButton.disabled, true);
    await waitForUpdatePhase("done", 12000);
    assertJsonEqual(ble.ota.commands, [1, 2, 3]);
    assertJsonEqual(ble.ota.restarts, ["update", "normal"]);
    assert.strictEqual(ble.ota.image.length, release.encoded.length);
    assert(ble.ota.image.every((byte, i) => byte === release.encoded[i]), "image bytes in order");
    assert(ble.ota.packets > Math.ceil(release.encoded.length / 178), "the lost chunk was resent");
    assert.strictEqual(els.updateResultTitle.textContent, "SweetYaar is up to date");
    assert.strictEqual(els.updateResultMessage.textContent, "Version 1.1.0");
    assert.strictEqual(els.updateNotesText.textContent, "Bedtime songs fade out gently.");
    assert.strictEqual(wakeLocks.length, 1);
    assert.strictEqual(wakeLocks[0].released, true);
    await waitUntil(() => state.connected && !state.remoteInitializing, "remote after update");
    assert.strictEqual(state.firmware.version, "1.1.0");
    await els.updatePrimaryButton.click(); // Done
    assertVisible(els.chargerView, [els.updateView, els.openingView, els.readyView]); // back where it started
    assert.strictEqual(els.updateCard.hidden, true);
  `],
  ["a lost response to enter update mode still continues the update", String.raw`
    await makeRelease();
    const ble = await connectWithFakeBle({ enterResponseLost: true });
    await waitUntil(() => state.releaseStatus === "ready", "release manifest");
    await openOptionalUpdate();
    await els.updatePrimaryButton.click();
    await waitForUpdatePhase("done", 15000);
    assertJsonEqual(ble.ota.commands, [1, 2, 3]); // the toy acted on enter despite the lost reply
    assertJsonEqual(ble.ota.restarts, ["update", "normal"]);
  `],
  ["a generic Bluetooth error right after reconnecting is retried, not fatal", String.raw`
    await makeRelease();
    const ble = await connectWithFakeBle({ failBegins: 2 });
    await waitUntil(() => state.releaseStatus === "ready", "release manifest");
    await openOptionalUpdate();
    await els.updatePrimaryButton.click();
    await waitForUpdatePhase("done", 15000);
    assert.strictEqual(state.update.linkRetries, 2);
    assertJsonEqual(ble.ota.commands, [1, 2, 3]);
  `],
  ["repeated Bluetooth errors end the update with the toy restarted", String.raw`
    await makeRelease();
    const ble = await connectWithFakeBle({ failBegins: 10 });
    await waitUntil(() => state.releaseStatus === "ready", "release manifest");
    await openOptionalUpdate();
    await els.updatePrimaryButton.click();
    await waitForUpdatePhase("failed", 15000);
    assert.strictEqual(state.update.linkRetries, 3);
    await waitUntil(() => ble.ota.commands.at(-1) === 4, "cancel restarts normal firmware");
  `],
  ["dropped connection pauses the update and resumes from the toy's offset", String.raw`
    await makeRelease();
    const ble = await connectWithFakeBle({ disconnectAtPacket: 12 });
    await waitUntil(() => state.releaseStatus === "ready", "release manifest");
    await openOptionalUpdate();
    await els.updatePrimaryButton.click();
    await waitForUpdatePhase("paused");
    assert.strictEqual(els.updateProgressTitle.textContent.startsWith("Update paused at"), true);
    assert.strictEqual(els.updatePrimaryButton.textContent, "Resume");
    assert.strictEqual(els.updatePrimaryButton.hidden, false);
    assertVisible(els.updateView, [els.openingView]);
    await waitForUpdatePhase("done", 12000);
    assert.strictEqual(ble.ota.begins.length, 2);
    assert(ble.ota.begins[1].received > 0, "the second begin kept the received prefix");
  `],
  ["cancelling restarts the toy on its current version", String.raw`
    await makeRelease({ size: 40000 });
    const ble = await connectWithFakeBle();
    const sendChunk = ble.chars.otaData.writeValueWithoutResponse.bind(ble.chars.otaData);
    ble.chars.otaData.writeValueWithoutResponse = async (value) => {
      await delay(2); // leave time to cancel mid-transfer
      return sendChunk(value);
    };
    await waitUntil(() => state.releaseStatus === "ready", "release manifest");
    await openOptionalUpdate();
    await els.updatePrimaryButton.click();
    await waitUntil(() => state.update.phase === "sending" && state.update.received > 0, "transfer");
    await els.updateSecondaryButton.click(); // Cancel update
    assert.strictEqual(els.updateCancelConfirm.hidden, false);
    assert.strictEqual(els.updateCancelMessage.textContent,
      "SweetYaar keeps version 1.0.0 and restarts normally. You can update later.");
    await els.updateSecondaryButton.click(); // confirm
    assert.strictEqual(state.update.phase, "cancelled");
    assert.strictEqual(els.updateResultTitle.textContent, "Update cancelled");
    // Cancel is queued behind the chunk already being written.
    await waitUntil(() => ble.ota.commands.at(-1) === 4, "cancel command");
    await waitUntil(() => state.connected && state.firmware?.mode === "normal", "normal firmware");
    assert.strictEqual(state.firmware.version, "1.0.0");
    await els.updatePrimaryButton.click(); // Done
    assertVisible(els.chargerView, [els.updateView, els.readyView]);
  `],
  ["reconnecting to a toy waiting in update mode resumes the update", String.raw`
    await makeRelease();
    const ble = await connectWithFakeBle({ firmwareMode: "update", waitForRemoteInitialization: false });
    assertVisible(els.updateView, [els.openingView, els.readyView]);
    await waitForUpdatePhase("done", 12000);
    assertJsonEqual(ble.ota.commands, [2, 3]);
    assert.strictEqual(els.updateResultTitle.textContent, "SweetYaar is up to date");
  `],
  ["toy refusing update mode for its battery reports why", String.raw`
    await makeRelease();
    const ble = await connectWithFakeBle({ otaRefuse: true });
    await waitUntil(() => state.releaseStatus === "ready", "release manifest");
    await openOptionalUpdate();
    await els.updatePrimaryButton.click();
    await waitForUpdatePhase("failed", 8000);
    assert.strictEqual(els.updateResultMessage.textContent, "Battery low. Connect a charger, then try again.");
    assertJsonEqual(ble.ota.restarts, []);
    assert.strictEqual(els.updatePrimaryButton.textContent, "Try again");
    await els.updateSecondaryButton.click(); // Not now
    assertVisible(els.chargerView, [els.updateView, els.readyView]);
  `],
  ["damaged download never reaches the toy", String.raw`
    const release = await makeRelease();
    release.manifest.images.sweetyaar.fileSha256 = "00".repeat(32);
    const ble = await connectWithFakeBle();
    await waitUntil(() => state.releaseStatus === "ready", "release manifest");
    await openOptionalUpdate();
    await els.updatePrimaryButton.click();
    await waitForUpdatePhase("failed");
    assert.strictEqual(els.updateResultMessage.textContent, "The downloaded update is damaged. Try again.");
    assertJsonEqual(ble.ota.commands, []);
  `],
  ["battery opens live diagnostics with warning priority and independent level color", String.raw`
    const ble = await connectWithFakeBle({ battery: 1, charger: [1, 4, 3, 0x60, 0, 0] });
    assert(ble.notifications.includes("charger"));
    assert(ble.reads.includes("charger"));
    assert(els.batteryIndicator.classList.contains("good"));
    assert(els.batteryIndicator.classList.contains("charger-warning"));
    assert(!els.batteryIndicator.classList.contains("charger-error"));
    await els.batteryIndicator.click();
    assertVisible(els.chargerView, [els.readyView, els.settingsView, els.streamingView, els.openingView]);
    assert.strictEqual(els.chargerStatusText.textContent, "Charging");
    assert.strictEqual(els.chargerWarnings.children[0].textContent, "Charging reduced because the charger is hot.");
    assert.strictEqual(els.chargerDetails.children[0].textContent, "Power-supply voltage is dropping.");
    ble.reads.length = 0;
    ble.chars.charger.emit(bytesView([1, 4, 3, 0x60, 0, 1]));
    assert.strictEqual(els.chargerErrors.children[0].textContent, "Battery overcurrent detected.");
    assert.strictEqual(els.chargerErrors.children[0].children.length, 0);
    assert(els.batteryIndicator.classList.contains("charger-error"));
    assert(!els.batteryIndicator.classList.contains("charger-warning"));
    assert(els.batteryIndicator.classList.contains("good"));
    assert.strictEqual(els.chargerWarningsSection.hidden, false);
    assert.strictEqual(els.chargerDetailsSection.hidden, false);
    assertJsonEqual(ble.reads, []); // no extra GATT work per notification
    // Clear overcurrent without changing the charge activity or other conditions.
    ble.chars.charger.emit(bytesView([1, 4, 3, 0x60, 0, 0]));
    assert.strictEqual(els.chargerStatusText.textContent, "Charging");
    assert.strictEqual(els.chargerErrorsSection.hidden, true);
    assert(!els.batteryIndicator.classList.contains("charger-error"));
    assert(els.batteryIndicator.classList.contains("charger-warning"));
    ble.chars.charger.emit(bytesView([1, 5, 3, 0, 0, 0]));
    assert.strictEqual(els.chargerStatusText.textContent, "Charging finished");
    assert.strictEqual(els.chargerErrorsSection.hidden, true);
    assert.strictEqual(els.chargerNoWarnings.hidden, false);
    assert(!els.batteryIndicator.classList.contains("charger-error"));
    assert(!els.batteryIndicator.classList.contains("charger-warning"));
    await els.tabRemote.click();
    assertVisible(els.readyView, [els.chargerView]);
  `],
  ["every charger activity and condition has a human description and severity", String.raw`
    const ble = await connectWithFakeBle();
    const names = ["Unknown", "No external power", "Charging disabled", "Not charging", "Charging", "Charging finished"];
    for (let activity = 0; activity < names.length; activity++) {
      ble.chars.charger.emit(bytesView([1, activity, 3, 0, 0, 0]));
      assert.strictEqual(els.chargerStatusText.textContent, names[activity]);
    }
    const warningBits = [0, 2, 6, 7, 8, 9];
    const detailBits = [1, 3, 4, 5];
    for (let bit = 0; bit <= 10; bit++) {
      const mask = 1 << bit;
      ble.chars.charger.emit(bytesView([1, bit === 10 ? 0 : 4, bit === 10 ? 1 : 3, mask & 255, mask >> 8, 0]));
      assert.strictEqual(els.chargerWarnings.children.length, warningBits.includes(bit) ? 1 : 0);
      assert.strictEqual(els.chargerDetails.children.length, detailBits.includes(bit) ? 1 : 0);
      assert.strictEqual(els.chargerErrors.children.length, bit === 10 ? 1 : 0);
      assert.strictEqual(els.batteryIndicator.classList.contains("charger-warning"), warningBits.includes(bit));
    }
    ble.chars.charger.emit(bytesView([1, 4, 3, 0xff, 3, 0]));
    assert.strictEqual(els.chargerWarnings.children.length, 6);
    assert.strictEqual(els.chargerDetails.children.length, 4);
  `],
  ["charger reads fail visibly without disconnecting controls and Refresh recovers", String.raw`
    const ble = await connectWithFakeBle();
    ble.chars.charger.readValue = async () => { throw new Error("read failed"); };
    await els.chargerRefreshButton.click();
    assert(state.connected);
    assert.strictEqual(state.charger, null);
    assert(!els.batteryIndicator.classList.contains("charger-error"));
    assert.strictEqual(els.appConnectionError.hidden, false);
    assert.strictEqual(els.appConnectionErrorMessage.textContent, "Could not read charger status.");
    assert.strictEqual(els.chargerErrorsSection.hidden, true);
    assert.strictEqual(els.chargerWarningsSection.hidden, true);
    assert.strictEqual(els.chargerStatusCard.hidden, true);
    ble.chars.charger.readValue = async () => bytesView([1, 4, 3, 0x20, 0, 0]);
    await els.chargerRefreshButton.click();
    assert.strictEqual(els.chargerStatusText.textContent, "Charging");
    assert.strictEqual(els.chargerStatusCard.hidden, false);
    assert.strictEqual(els.appConnectionError.hidden, true);
    assert.strictEqual(els.chargerErrorsSection.hidden, true);
    assert.strictEqual(els.chargerDetails.children.length, 1);
    assert(!els.batteryIndicator.classList.contains("charger-error"));
  `],
  ["malformed charger notifications discard stale state and recover on valid input", String.raw`
    const ble = await connectWithFakeBle();
    for (const bytes of [[1], [2,4,3,0,0,0], [1,6,3,0,0,0], [1,4,2,0,0,0], [1,0,3,0,8,0], [1,0,0,1,0,0], [1,4,3,0,0,2]]) {
      ble.chars.charger.emit(bytesView(bytes));
      assert.strictEqual(state.charger, null);
      assert.strictEqual(els.chargerStatusCard.hidden, true);
      assert.strictEqual(els.appConnectionError.hidden, false);
      assert.strictEqual(els.chargerErrorsSection.hidden, true);
      assert(!els.batteryIndicator.classList.contains("charger-error"));
      ble.chars.charger.emit(bytesView([1, 4, 3, 0, 0, 0]));
      assert.strictEqual(state.chargerTransportError, "");
      assert.strictEqual(els.appConnectionError.hidden, true);
      assert.strictEqual(els.chargerStatusCard.hidden, false);
      assert(!els.batteryIndicator.classList.contains("charger-error"));
    }
  `],
  ["failed charger notification subscription preserves controls and manual readings", String.raw`
    const ble = makeBleHarness({ charger: [1, 4, 3, 0x40, 0, 0] });
    ble.chars.charger.startNotifications = async () => { throw new Error("notify unavailable"); };
    await els.connectButton.click();
    await waitUntil(() => !state.remoteInitializing, "remote initialization");
    assert(state.connected && state.charger.valid);
    assert.strictEqual(state.chargerSubscribed, false);
    assert(!els.batteryIndicator.classList.contains("charger-error"));
    assert(els.batteryIndicator.classList.contains("charger-warning"));
    assert.strictEqual(els.chargerErrorsSection.hidden, true);
    assert.strictEqual(els.chargerStatusCard.hidden, false);
    assert.strictEqual(els.appConnectionError.hidden, false);
    assert.strictEqual(els.appConnectionErrorMessage.textContent, "Live charger updates are unavailable.");
    ble.chars.charger.value = bytesView([1, 5, 3, 0, 0, 0]);
    await els.chargerRefreshButton.click();
    assert.strictEqual(els.chargerStatusText.textContent, "Charging finished");
    assert(!els.batteryIndicator.classList.contains("charger-warning"));
    assert(els.chargerUpdateNote.textContent.includes("Refresh"));
    onDisconnected();
    assert.strictEqual(els.appConnectionError.hidden, true);
  `],
  ["charger supervision failures remain device errors rather than app connection errors", String.raw`
    const ble = await connectWithFakeBle({ charger: [1, 0, 1, 0, 4, 0] });
    assert.strictEqual(els.appConnectionError.hidden, true);
    assert.strictEqual(els.chargerStatusCard.hidden, false);
    assert.strictEqual(els.chargerStatusText.textContent, "Unknown");
    assert.strictEqual(els.chargerErrors.children[0].textContent, "Charger communication or configuration failed. Charging is disabled.");
    assert(els.batteryIndicator.classList.contains("charger-error"));
    ble.chars.charger.emit(bytesView([1, 4, 3, 0, 0, 0]));
    assert.strictEqual(els.chargerErrorsSection.hidden, true);
    assert(!els.batteryIndicator.classList.contains("charger-error"));
  `],
  ["generic boards report charger diagnostics unavailable without false assurance", String.raw`
    await connectWithFakeBle({ charger: [1, 0, 0, 0, 0, 0] });
    assert(state.connected);
    await els.batteryIndicator.click();
    assert.strictEqual(els.chargerStatusText.textContent, "Unavailable");
    assert.strictEqual(els.chargerWarningsSection.hidden, true);
    assert.strictEqual(els.chargerDetailsSection.hidden, true);
    assert(!els.batteryIndicator.classList.contains("charger-error"));
  `],
  ["disconnect prevents a pending charger read or old notification leaking into reconnect", String.raw`
    const ble = await connectWithFakeBle();
    let finishRead;
    ble.chars.charger.readValue = () => new Promise((resolve) => { finishRead = resolve; });
    const pending = readChargerStatus();
    await waitUntil(() => !!finishRead, "charger read starts");
    onDisconnected();
    assert.strictEqual(state.charger, null);
    assert.strictEqual(els.chargerView.hidden, true);
    finishRead(bytesView([1, 4, 3, 0xff, 3, 1]));
    await pending;
    await connectWithFakeBle({ charger: [1, 1, 3, 0, 0, 0] });
    ble.chars.charger.emit(bytesView([1, 4, 3, 0xff, 3, 1]));
    assert.strictEqual(els.chargerStatusText.textContent, "No external power");
    assert.strictEqual(els.chargerErrorsSection.hidden, true);
  `],
  ["config subscriptions precede every update and replies are acknowledgments", String.raw`
    const ble = await connectWithFakeBle({ synchronousConfigNotify: true, trackConcurrentReads: true });
    await toggleBedtimeMode();
    for (const subscribed of ble.writes.subscriptionsAtConfigWrite) {
      for (const name of CONFIG_ATTRIBUTES) assert(subscribed.includes(name), name);
    }
    assertJsonEqual(Object.keys(JSON.parse(ble.chars.configResponse.value)).sort(), ["id", "ok", "op"]);
    assert.strictEqual(state.bedtime.active, true);
    assert.strictEqual(state.bedtime.override, "on");
    assert.strictEqual(els.volumeValue.textContent, "45%");
    assert.strictEqual(ble.maxConcurrentReads, 1);
  `],
  ["unsolicited config notifications update every saved and runtime field", String.raw`
    const ble = await connectWithFakeBle({ trackConcurrentReads: true });
    Object.assign(ble.config, { deviceName: "New name", defaultVolumePct: 31, defaultTheme: "nature", activeTheme: "nature", loop: true });
    ble.config.sleep = { enabled: false, normalIdleSec: 901, vibrationWakeIdleSec: 41, bleIdleSec: 52 };
    Object.assign(ble.config.bedtime, { enabled: true, startTime: "19:45", endTime: "07:15",
      theme: "nature", volumeCapPct: 22, active: true, autoActive: true, override: "none",
      effectiveVolumePct: 22, effectiveTheme: "nature", currentTime: "19:46", currentSecondOfDay: 71160 });
    const commandsBefore = ble.writes.config.length;
    ble.publishConfigValues();
    await waitUntil(() => state.bedtime.currentSecondOfDay === 71160, "unsolicited config refresh");
    assert.strictEqual(state.deviceName, "New name");
    assert.strictEqual(state.settings.deviceName, "New name");
    assert.strictEqual(state.settings.defaultVolumePct, 31);
    assert.strictEqual(state.settings.defaultTheme, "nature");
    assert.strictEqual(state.settings.sleepEnabled, false);
    assert.strictEqual(state.settings.sleepNormalIdleSec, 901);
    assert.strictEqual(state.settings.sleepVibrationWakeIdleSec, 41);
    assert.strictEqual(state.settings.sleepBleIdleSec, 52);
    assert.strictEqual(state.settings.bedtimeStartTime, "19:45");
    assert.strictEqual(state.settings.bedtimeEndTime, "07:15");
    assert.strictEqual(state.settings.bedtimeTheme, "nature");
    assert.strictEqual(state.settings.bedtimeVolumeCapPct, 22);
    assert.strictEqual(state.bedtime.autoActive, true);
    assert.strictEqual(state.bedtime.override, "none");
    assert.strictEqual(state.bedtime.effectiveTheme, "nature");
    assert.strictEqual(state.bedtime.effectiveVolumePct, 22);
    assert.strictEqual(state.theme, "nature");
    assert.strictEqual(state.loop, true);
    assert.strictEqual(els.bedtimeTitle.textContent, "Bedtime");
    assert.strictEqual(els.volumeValue.textContent, "22%");
    assert.strictEqual(ble.writes.config.length, commandsBefore);
    assert.strictEqual(ble.maxConcurrentReads, 1);
  `],
  ["runtime notifications preserve dirty settings drafts and failed saves", String.raw`
    const ble = await connectWithFakeBle();
    await openSettings();
    await waitForSettingsLoaded();
    await els.settingsDeviceName.input("Unsaved name");
    await els.settingsBedtimeStartTime.input("20:15");
    Object.assign(ble.config.bedtime, { active: true, autoActive: true, volumeCapPct: 21 });
    ble.publishConfigValues();
    await waitUntil(() => state.bedtime.active, "automatic bedtime");
    assert.strictEqual(state.settings.deviceName, "Unsaved name");
    assert.strictEqual(state.settings.bedtimeStartTime, "20:15");
    assert.strictEqual(state.settings.bedtimeVolumeCapPct, 45);
    assert.strictEqual(state.settings.dirty, true);
    assert.strictEqual(state.bedtime.volumeCapPct, 21);
    ble.chars.configCommand.write = (value) => {
      const request = JSON.parse(textFromValue(value));
      ble.chars.configResponse.emit(JSON.stringify({ id: request.id, ok: false, error: "SD write failed" }));
    };
    await saveSettings();
    assert.strictEqual(state.settings.message, "SD write failed");
    assert.strictEqual(state.settings.deviceName, "Unsaved name");
    assert.strictEqual(state.settings.dirty, true);
  `],
  ["a name save finishes on its ACK while its state notification is withheld", String.raw`
    const options = { synchronousConfigNotify: true };
    const ble = await connectWithFakeBle(options);
    await openSettings();
    await waitForSettingsLoaded();
    options.dropConfigNotifications = true;
    await els.settingsDeviceName.input("Saved name");
    const commandsBefore = ble.writes.config.length;
    ble.reads.length = 0;
    await saveSettings();
    assertJsonEqual(payloadsWithoutIds(ble.writes.config.slice(commandsBefore)), [
      { op: "setConfig", deviceName: "Saved name" }
    ]);
    assertJsonEqual(ble.reads, ["configResponse"]);
    assert.strictEqual(state.settings.message, "Settings saved.");
    assert.strictEqual(state.settings.originalDeviceName, "Saved name");
    assert.strictEqual(state.settings.dirty, false);
    assert.strictEqual(state.busy, false);
    assert.strictEqual(state.deviceName, "SweetYaar", "Live state waits for its notification, not a verification read");
    ble.chars.configGeneral.invalidate();
    await waitUntil(() => state.deviceName === "Saved name", "delayed name notification");
    assertJsonEqual(ble.reads, ["configResponse", "configGeneral"]);
    await saveSettings();
    assert.strictEqual(ble.writes.config.length, commandsBefore + 1, "An acknowledged edit is no longer dirty");
  `],
  ["a settings timeout reports the missing reply without extra reads", String.raw`
    const options = { synchronousConfigNotify: true };
    const ble = await connectWithFakeBle(options);
    await openSettings();
    await waitForSettingsLoaded();
    options.dropConfigNotifications = true;
    await els.settingsVolumeRange.input("37");
    const previousId = state.requestId;
    const read = ble.chars.configResponse.readValue.bind(ble.chars.configResponse);
    let now = Date.now();
    const realNow = Date.now;
    Date.now = () => now;
    ble.chars.configResponse.readValue = async () => {
      // The write succeeds, but the response remains an older command's reply.
      ble.chars.configResponse.value = JSON.stringify({ id: previousId, op: "scanSongs", ok: true });
      const value = await read();
      now += 15001;
      return value;
    };
    const commandsBefore = ble.writes.config.length;
    ble.reads.length = 0;
    try { await saveSettings(); } finally { Date.now = realNow; }
    assert.strictEqual(state.settings.message, "The toy did not reply in time. Please try again.");
    assert.strictEqual(state.settings.dirty, true);
    assert.strictEqual(state.settings.originalDefaultVolumePct, 75);
    assert.strictEqual(ble.writes.config.length, commandsBefore + 1);
    assertJsonEqual(ble.reads, ["configResponse"]);
  `],
  ["a rejected SD save and a failed Bluetooth write preserve the pending settings", String.raw`
    const ble = await connectWithFakeBle({ synchronousConfigNotify: true });
    await openSettings();
    await waitForSettingsLoaded();
    await els.settingsVolumeRange.input("37");
    const write = ble.chars.configCommand.write.bind(ble.chars.configCommand);
    ble.chars.configCommand.write = (value) => {
      const request = JSON.parse(textFromValue(value));
      ble.chars.configResponse.emit(JSON.stringify({ id: request.id, ok: false, error: "SD write failed" }));
    };
    await saveSettings();
    assert.strictEqual(state.settings.message, "SD write failed");
    assert.strictEqual(state.settings.originalDefaultVolumePct, 75);
    const transportError = new Error("GATT operation failed for unknown reason.");
    transportError.name = "NetworkError";
    ble.chars.configCommand.write = () => { throw transportError; };
    await saveSettings();
    assert(__consoleOutput.some((entry) => entry[2] === transportError));
    assert.strictEqual(state.settings.dirty, true);
    ble.chars.configCommand.write = write;
    await saveSettings();
    assert.strictEqual(state.settings.message, "Settings saved.");
    assert.strictEqual(state.settings.originalDefaultVolumePct, 37);
  `],
  ["an empty firmware reply fails immediately without losing the pending save", String.raw`
    const options = { synchronousConfigNotify: true };
    const ble = await connectWithFakeBle(options);
    await openSettings();
    await waitForSettingsLoaded();
    options.dropConfigNotifications = true;
    await els.settingsDeviceName.input("Pending name");
    await els.settingsVolumeRange.input("37");
    const write = ble.chars.configCommand.write.bind(ble.chars.configCommand);
    ble.chars.configCommand.write = () => ble.chars.configResponse.emit("{}");
    const started = Date.now();
    ble.reads.length = 0;
    await saveSettings();
    assert(Date.now() - started < 500, "An invalid reply must not spend 15 seconds polling the same data");
    assert.strictEqual(state.settings.message, "The toy returned an invalid reply. Please try again.");
    assert.strictEqual(state.settings.dirty, true);
    assert.strictEqual(state.settings.originalDeviceName, "SweetYaar");
    assert.strictEqual(state.settings.originalDefaultVolumePct, 75);
    assertJsonEqual(ble.reads, ["configResponse"]);
    ble.chars.configCommand.write = write;
    await saveSettings();
    assert.strictEqual(state.settings.message, "Settings saved.");
    assert.strictEqual(state.settings.originalDeviceName, "Pending name");
    assert.strictEqual(state.settings.originalDefaultVolumePct, 37);
  `],
  ["every single settings field sends only its changed value and reads only its ACK", String.raw`
    const edits = [
      ["settingsDeviceName", "input", "One name", { deviceName: "One name" }],
      ["settingsVolumeRange", "input", "34", { defaultVolumePct: 34 }],
      ["defaultTheme", "state", "nature", { defaultTheme: "nature" }],
      ["settingsSleepEnabled", "change", false, { sleep: { enabled: false } }],
      ["settingsNormalIdleSec", "input", "777", { sleep: { normalIdleSec: 777 } }],
      ["settingsWakeIdleSec", "input", "91", { sleep: { vibrationWakeIdleSec: 91 } }],
      ["settingsBleIdleSec", "input", "101", { sleep: { bleIdleSec: 101 } }],
      ["settingsBedtimeEnabled", "change", false, { bedtime: { enabled: false } }],
      ["settingsBedtimeStartTime", "input", "19:15", { bedtime: { startTime: "19:15" } }],
      ["settingsBedtimeEndTime", "input", "07:15", { bedtime: { endTime: "07:15" } }],
      ["bedtimeTheme", "state", "nature", { bedtime: { theme: "nature" } }],
      ["settingsBedtimeVolumeRange", "input", "23", { bedtime: { volumeCapPct: 23 } }]
    ];
    for (const [field, event, value, patch] of edits) {
      const options = { synchronousConfigNotify: true };
      const ble = await connectWithFakeBle(options);
      await openSettings();
      await waitForSettingsLoaded();
      options.dropConfigNotifications = true;
      if (event === "state") { state.settings[field] = value; markSettingsDirty(); }
      else await els[field][event](value);
      const commandsBefore = ble.writes.config.length;
      ble.reads.length = 0;
      await saveSettings();
      assertJsonEqual(payloadsWithoutIds(ble.writes.config.slice(commandsBefore)), [{ op: "setConfig", ...patch }]);
      assertJsonEqual(ble.reads, ["configResponse"]);
      assert.strictEqual(state.settings.message, "Settings saved.", field);
      assert.strictEqual(state.settings.dirty, false, field);
      ble.device.gatt.disconnect();
      onDisconnected();
    }
  `],
  ["save reads only notified attributes once, without scans or verification reads", String.raw`
    const ble = await connectWithFakeBle({ synchronousConfigNotify: true });
    await openSettings();
    await waitForSettingsLoaded();
    await els.settingsDeviceName.input("Saved name");
    await els.settingsNormalIdleSec.input("777");
    const commandsBefore = ble.writes.config.length;
    ble.reads.length = 0;
    await saveSettings();
    await gattQueue;
    assertJsonEqual(payloadsWithoutIds(ble.writes.config.slice(commandsBefore)), [
      { op: "setConfig", deviceName: "Saved name", sleep: { normalIdleSec: 777 } }
    ]);
    assertJsonEqual(ble.reads.slice().sort(), ["configGeneral", "configResponse", "configSleep"]);
    assert.strictEqual(state.deviceName, "Saved name");
    assert.strictEqual(state.settings.originalDeviceName, "Saved name");
    assert.strictEqual(state.settings.originalSleepNormalIdleSec, 777);
    assert.strictEqual(state.settings.message, "Settings saved.");
  `],
  ["clock sync and bedtime toggle finish on ACKs without verifying config", String.raw`
    const options = { synchronousConfigNotify: true };
    const ble = await connectWithFakeBle(options);
    options.dropConfigNotifications = true;
    ble.reads.length = 0;
    const commandsBefore = ble.writes.config.length;
    await refreshDeviceClock();
    await toggleBedtimeMode();
    assertJsonEqual(ble.writes.config.slice(commandsBefore).map((p) => p.op), ["syncTime", "setBedtimeMode"]);
    assertJsonEqual(ble.reads, ["configResponse", "configResponse"]);
    assert.strictEqual(state.busy, false);
    assert.strictEqual(state.bedtime.active, false);
    ble.chars.configRuntime.invalidate();
    await waitUntil(() => state.bedtime.active, "delayed runtime notification");
    assertJsonEqual(ble.reads, ["configResponse", "configResponse", "configRuntime"]);
  `],
  ["theme and song saves update the session cache without rescanning", String.raw`
    const ble = await connectWithFakeBle({ synchronousConfigNotify: true });
    await openSettings();
    await waitForSettingsLoaded();
    await selectSettingsTheme("nature");
    setThemeShuffle("nature", false);
    setSongEnabled("rain.wav", false);
    const commandsBefore = ble.writes.config.length;
    ble.reads.length = 0;
    await saveSettings();
    assertJsonEqual(payloadsWithoutIds(ble.writes.config.slice(commandsBefore)), [
      { op: "setTheme", theme: "nature", shuffle: false },
      { op: "setSong", theme: "nature", file: "rain.wav", enabled: false }
    ]);
    assertJsonEqual(ble.reads, ["configResponse", "configResponse"]);
    assert.strictEqual(state.settings.message, "Settings saved.");
    assert.strictEqual(state.settings.themes.find((t) => t.id === "nature").activeValid, 0);
    assert.strictEqual(state.settings.themes.find((t) => t.id === "nature").shuffle, false);
    assert(!state.themes.some((t) => t.id === "nature"), "An empty theme leaves the remote selector");
    await selectSettingsTheme("lullabies");
    await selectSettingsTheme("nature");
    assert.strictEqual(state.settings.songs[0].enabled, false);
    assert.strictEqual(ble.writes.config.length, commandsBefore + 2, "Revisiting cached themes must not scan");
    setSongEnabled("rain.wav", true);
    await saveSettings();
    assert(state.themes.some((t) => t.id === "nature"), "Re-enabling the song restores its theme");
    setThemeEnabled("nature", false);
    await saveSettings();
    assert(!state.themes.some((t) => t.id === "nature"));
    assert.strictEqual(state.settings.themes.find((t) => t.id === "nature").disabledByUser, true);
    assertJsonEqual(ble.writes.config.slice(commandsBefore).map((p) => p.op),
      ["setTheme", "setSong", "setSong", "setTheme"]);
  `],
  ["a partial save retries only commands that were not acknowledged", String.raw`
    const ble = await connectWithFakeBle({ synchronousConfigNotify: true });
    await openSettings();
    await waitForSettingsLoaded();
    await selectSettingsTheme("nature");
    await els.settingsDeviceName.input("Accepted name");
    setThemeShuffle("nature", false);
    setSongEnabled("rain.wav", false);
    const write = ble.chars.configCommand.write.bind(ble.chars.configCommand);
    let rejectSong = true;
    ble.chars.configCommand.write = (value) => {
      const command = JSON.parse(textFromValue(value));
      if (command.op === "setSong" && rejectSong) {
        ble.chars.configResponse.emit(JSON.stringify({ id: command.id, ok: false, error: "SD write failed" }));
      } else write(value);
    };
    await saveSettings();
    assert.strictEqual(state.settings.message, "SD write failed");
    assert.strictEqual(state.settings.dirty, true);
    assert.strictEqual(state.settings.originalDeviceName, "Accepted name");
    assertJsonEqual(state.settings.pendingThemeChanges, {});
    assertJsonEqual(state.settings.pendingSongChanges, { nature: { "rain.wav": false } });
    const commandsBefore = ble.writes.config.length;
    ble.reads.length = 0;
    rejectSong = false;
    await saveSettings();
    assertJsonEqual(payloadsWithoutIds(ble.writes.config.slice(commandsBefore)), [
      { op: "setSong", theme: "nature", file: "rain.wav", enabled: false }
    ]);
    assertJsonEqual(ble.reads, ["configResponse"]);
    assert.strictEqual(state.settings.message, "Settings saved.");
    assert.strictEqual(state.settings.dirty, false);
  `],
  ["an unchanged settings draft saves without any Bluetooth requests", String.raw`
    const ble = await connectWithFakeBle({ synchronousConfigNotify: true });
    await openSettings();
    await waitForSettingsLoaded();
    await els.settingsDeviceName.input("Temporary name");
    await els.settingsDeviceName.input("SweetYaar");
    const commandsBefore = ble.writes.config.length;
    ble.reads.length = 0;
    await saveSettings();
    assert.strictEqual(ble.writes.config.length, commandsBefore);
    assertJsonEqual(ble.reads, []);
    assert.strictEqual(state.settings.dirty, false);
    assert.strictEqual(state.settings.message, "Settings saved.");
  `],
  ["multi-field saves pack UTF-8 and escaped names within the command limit", String.raw`
    const longTheme = '"'.repeat(63);
    const options = { synchronousConfigNotify: true, themes: [
      { id: "lullabies", name: "Lullabies", enabled: true, canSetDefault: true, activeValid: 1 },
      { id: longTheme, name: "Long theme", enabled: true, canSetDefault: true, activeValid: 1 }
    ] };
    const ble = await connectWithFakeBle(options);
    await openSettings();
    await waitForSettingsLoaded();
    options.dropConfigNotifications = true;
    await els.settingsDeviceName.input('"'.repeat(24) + "😀😀");
    await els.settingsVolumeRange.input("34");
    state.settings.defaultTheme = longTheme;
    state.settings.bedtimeTheme = longTheme;
    await els.settingsSleepEnabled.change(false);
    await els.settingsNormalIdleSec.input("86400");
    await els.settingsWakeIdleSec.input("86399");
    await els.settingsBleIdleSec.input("86398");
    await els.settingsBedtimeEnabled.change(false);
    await els.settingsBedtimeStartTime.input("20:15");
    await els.settingsBedtimeEndTime.input("08:15");
    await els.settingsBedtimeVolumeRange.input("19");
    const commandsBefore = ble.writes.config.length;
    ble.reads.length = 0;
    await saveSettings();
    const commands = ble.writes.config.slice(commandsBefore);
    assert(commands.length > 1 && commands.length < 5);
    for (const command of commands) {
      assert.strictEqual(command.op, "setConfig");
      assert(Object.keys(command).length > 2, "No empty updates");
      assert(textEncoder.encode(JSON.stringify(command)).length <= 383);
    }
    assertJsonEqual(ble.reads, commands.map(() => "configResponse"));
    assert.strictEqual(ble.config.deviceName, '"'.repeat(24) + "😀😀");
    assert.strictEqual(ble.config.defaultTheme, longTheme);
    assert.strictEqual(ble.config.bedtime.theme, longTheme);
    assert.strictEqual(ble.config.sleep.bleIdleSec, 86398);
    assert.strictEqual(ble.config.bedtime.volumeCapPct, 19);
    assert.strictEqual(state.settings.message, "Settings saved.");
  `],
  ["oversized settings fail before sending any part of a save", String.raw`
    const ble = await connectWithFakeBle({ synchronousConfigNotify: true });
    await openSettings();
    await waitForSettingsLoaded();
    await els.settingsDeviceName.input('"'.repeat(200));
    const commandsBefore = ble.writes.config.length;
    ble.reads.length = 0;
    await saveSettings();
    assert.strictEqual(ble.writes.config.length, commandsBefore);
    assertJsonEqual(ble.reads, []);
    assert.strictEqual(state.settings.dirty, true);
    assert(state.settings.message.includes("too long"));
  `],
  ["config reconnect reads missed changes and registers one listener per attribute", String.raw`
    const ble = await connectWithFakeBle();
    ble.device.gatt.disconnect();
    onDisconnected();
    ble.config.deviceName = "Changed while away";
    ble.config.sleep.bleIdleSec = 333;
    ble.publishConfigValues();
    await els.connectButton.click();
    await waitUntil(() => !state.remoteInitializing, "reconnection");
    assert.strictEqual(state.deviceName, "Changed while away");
    assert.strictEqual(state.settings.sleepBleIdleSec, 333);
    for (const name of CONFIG_ATTRIBUTES) assert.strictEqual(ble.chars[name].listeners.characteristicvaluechanged.length, 1);
  `],
  ["config command queue preserves concurrent acknowledgments", String.raw`
    const ble = await connectWithFakeBle({ synchronousConfigNotify: true });
    const replies = await Promise.all([
      configRequest({ op: "setConfig", defaultVolumePct: 32 }),
      configRequest({ op: "setBedtimeMode", active: true })
    ]);
    assert.strictEqual(replies[0].op, "setConfig");
    assert.strictEqual(replies[1].op, "setBedtimeMode");
    assert(replies[1].id > replies[0].id);
    await gattQueue;
    assert.strictEqual(state.settings.defaultVolumePct, 32);
    assert.strictEqual(state.bedtime.active, true);
  `],
  ["catalog warning is read on connect and retained until dismissed", String.raw`
    await connectWithFakeBle({ catalogWarning: "Ignored oversized song שיר…; full details in boot log." });
    assert.strictEqual(els.noticeBanner.hidden, false);
    assert(els.noticeMessage.textContent.includes("שיר…"));
    assert.strictEqual(state.notice.severity, "error");
    dismissNotice();
    await refreshConfigAttributes();
    assert.strictEqual(state.notice, null);
  `],
  ["rereading a stored clock sample preserves its elapsed time", String.raw`
    await connectWithFakeBle();
    state.bedtime.currentTimeReceivedAtMs -= 600000;
    const before = deviceWatchText();
    await refreshConfigAttributes();
    assert.strictEqual(deviceWatchText(), before);
  `],
  ["config notification during a read converges to the newer state", String.raw`
    const ble = await connectWithFakeBle({ trackConcurrentReads: true });
    const characteristic = ble.chars.configRuntime;
    const originalRead = characteristic.readValue.bind(characteristic);
    let entered;
    let release;
    const readingStarted = new Promise((resolve) => { entered = resolve; });
    const readingReleased = new Promise((resolve) => { release = resolve; });
    let first = true;
    characteristic.readValue = async () => {
      const snapshot = await originalRead();
      if (first) {
        first = false;
        entered();
        await readingReleased;
      }
      return snapshot;
    };
    const initialRead = readConfigAttribute("configRuntime");
    await readingStarted;
    const next = { ...JSON.parse(characteristic.value), active: true, autoActive: true, override: "none" };
    characteristic.value = JSON.stringify(next);
    characteristic.invalidate();
    release();
    await initialRead;
    await waitUntil(() => state.bedtime.active && els.bedtimeTitle.textContent === "Bedtime", "newer notification");
    assert.strictEqual(state.bedtime.autoActive, true);
    assert.strictEqual(ble.maxConcurrentReads, 1);
  `],
  ["initial opening screen is usable", String.raw`
    assertVisible(els.openingView, [els.readyView, els.streamingView, els.settingsView]);
    assert.strictEqual(els.connectButton.disabled, false);
    assert.strictEqual(els.connectButtonLabel.textContent, "Connect to SweetYaar");
    assert.strictEqual(els.openingMessage.textContent, "New phone? Hold both buttons on the toy for 3 seconds, then connect.");
    assert.strictEqual(els.brandName.textContent, "SweetYaar");
  `],
  ["connect success shows ready remote", String.raw`
    const ble = await connectWithFakeBle({
      deviceName: "SweetYaar Test",
      volume: 42,
      theme: "nature",
      config: { activeTheme: "nature", defaultTheme: "nature" }
    });
    assert.strictEqual(ble.requestCount, 1);
    assert.strictEqual(state.connected, true);
    assertVisible(els.readyView, [els.openingView, els.streamingView, els.settingsView]);
    assert.strictEqual(els.brandName.textContent, "SweetYaar Test");
    assert.strictEqual(els.readyStatusText.textContent, "Ready to play");
    assert.strictEqual(els.volumeValue.textContent, "42%");
    assert.strictEqual(els.themeCurrent.textContent, "Nature");
    assert.strictEqual(state.loop, false);
    assert.strictEqual(els.loopToggle.getAttribute("aria-checked"), "false");
    assert.strictEqual(els.loopBadge.hidden, true);
    assertJsonEqual(payloadsWithoutIds(ble.writes.config).map((payload) => payload.op), ["syncTime"]);
    assert.strictEqual(els.bedtimeTitle.textContent, "Daytime");
    assert.strictEqual(els.bedtimeMessage.textContent, "(ends at 18:30)");
    assert.strictEqual(els.deviceWatch.textContent, "Toy clock 21:05");
  `],
  ["connect opens remote before controls finish loading", String.raw`
    const ble = await connectWithFakeBle({
      deferRemoteInitialization: true,
      waitForRemoteInitialization: false
    });
    assert.strictEqual(state.connected, true);
    assert.strictEqual(state.remoteInitializing, true);
    assertVisible(els.readyView, [els.openingView, els.streamingView, els.settingsView]);
    assert.strictEqual(els.readyView.getAttribute("aria-busy"), "true");
    assert.strictEqual(els.readyMessage.textContent, "Loading controls...");
    assert.strictEqual(els.playSongButton.disabled, true);
    assert.strictEqual(els.volumeRange.disabled, true);
    assert.strictEqual(els.tabSettings.disabled, true);
    assert.deepStrictEqual(ble.reads, ["firmware", "status"]);
    assert.deepStrictEqual(ble.notifications, ["status"]);

    ble.releaseRemoteInitialization();
    await waitUntil(() => !state.remoteInitializing, "deferred remote initialization");
    assert.strictEqual(els.readyView.getAttribute("aria-busy"), "false");
    assert.strictEqual(els.readyMessage.hidden, true);
    assert.strictEqual(els.playSongButton.disabled, false);
    assert.strictEqual(els.volumeRange.disabled, false);
    assert.strictEqual(els.tabSettings.disabled, false);
    assertJsonEqual(payloadsWithoutIds(ble.writes.config).map((payload) => payload.op), ["syncTime"]);
  `],
  ["early config notification avoids the polling fallback", String.raw`
    const startedAt = Date.now();
    const ble = await connectWithFakeBle({ synchronousConfigNotify: true });
    assert(Date.now() - startedAt < 500, "synchronous config response should not wait for fallback timer");
    assertJsonEqual(payloadsWithoutIds(ble.writes.config).map((payload) => payload.op), ["syncTime"]);
  `],
  ["bedtime card shows time unknown when sync is unavailable", String.raw`
    await connectWithFakeBle({ rejectSyncTime: true });
    assert.strictEqual(state.connected, true);
    assert.strictEqual(state.bedtime.timeKnown, false);
    assert.strictEqual(els.bedtimeTitle.textContent, "Daytime");
    assert.strictEqual(els.bedtimeMessage.textContent, "clock not set");
    assert.strictEqual(els.bedtimeToggleButton.disabled, true);
    assert.strictEqual(els.deviceWatch.textContent, "Toy clock not set");
  `],
  ["failed clock sync does not block settings and recovery needs no config refresh", String.raw`
    const options = { synchronousConfigNotify: true, rejectSyncTime: true };
    const ble = await connectWithFakeBle(options);
    await openSettings();
    await waitForSettingsLoaded();
    assert.strictEqual(state.settings.sessionScanned, true);
    assert.strictEqual(state.configError, null);
    options.rejectSyncTime = false;
    ble.reads.length = 0;
    await refreshDeviceClock();
    await gattQueue;
    assert.strictEqual(state.bedtime.timeKnown, true);
    assertJsonEqual(ble.reads.slice().sort(), ["configResponse", "configRuntime"]);
  `],
  ["bedtime card toggles runtime mode", String.raw`
    const ble = await connectWithFakeBle({
      theme: "nature",
      config: { activeTheme: "nature", defaultTheme: "nature" }
    });
    assert.strictEqual(state.theme, "nature");
    assert.strictEqual(els.themeCurrent.textContent, "Nature");
    await els.bedtimeToggleButton.click();
    const payloads = payloadsWithoutIds(ble.writes.config);
    assert(payloads.some((payload) => payload.op === "setBedtimeMode" && payload.active === true));
    assert.strictEqual(state.bedtime.active, true);
    assert.strictEqual(state.theme, "nature");
    assert.strictEqual(els.themeCurrent.textContent, "Lullabies");
    assert.strictEqual(els.themeHelper.hidden, false);
    assert.strictEqual(els.themeHelper.textContent.trim(), "☾ bedtime mode");
    assert.strictEqual(state.volume, 75);
    assert.strictEqual(els.volumeRange.value, "45");
    assert.strictEqual(els.volumeValue.textContent, "45%");
    assert.strictEqual(els.volumeCapMarker.hidden, false);
    assert.strictEqual(els.volumeRange.style.values["--volume-cap"], "45%");
    assert.strictEqual(els.bedtimeTitle.textContent, "Bedtime");
    assert.strictEqual(els.bedtimeMessage.textContent, "(ends at 06:30)");
  `],
  ["bedtime volume slider clamps writes to the volume cap", String.raw`
    const ble = await connectWithFakeBle();
    await els.bedtimeToggleButton.click();
    assert.strictEqual(state.bedtime.active, true);
    await els.volumeRange.input(90);
    assert.strictEqual(state.volume, 45);
    assert.strictEqual(els.volumeRange.value, "45");
    await els.volumeRange.change(90);
    assertJsonEqual(ble.writes.volume, [45]);
    assert.strictEqual(state.volume, 45);
    assert.strictEqual(els.volumeValue.textContent, "45%");
  `],
  ["empty compact theme list leaves remote picker empty", String.raw`
    const ble = await connectWithFakeBle({
      themes: [],
      theme: "nature",
      config: { activeTheme: "nature", defaultTheme: "nature" }
    });
    assert.strictEqual(state.connected, true);
    assert.strictEqual(state.themes.length, 0);
    assert.strictEqual(els.themeCurrent.textContent, "");
    assert.strictEqual(els.themeTrigger.disabled, true);
    assert.strictEqual(els.themeOptions.children.length, 0);
    assertJsonEqual(payloadsWithoutIds(ble.writes.config).map((payload) => payload.op), ["syncTime"]);
  `],
  ["connect requires the config, notice, battery and charger characteristics", String.raw`
    for (const name of ["configCommand", "configResponse", ...CONFIG_ATTRIBUTES, "notice", "battery", "charger"]) {
      const ble = await connectWithFakeBle({ missingCharacteristics: [name] });
      assert.strictEqual(state.connected, false);
      assert.strictEqual(ble.device.gatt.connected, false);
      assertVisible(els.openingView, [els.readyView, els.streamingView, els.settingsView]);
      assert.strictEqual(els.openingMessage.textContent, "Please upgrade device firmware.");
      assert.strictEqual(ble.writes.config.length, 0);
      assert.strictEqual(ble.writes.command.length, 0);
    }
  `],
  ["reconnect retains theme choices after clock sync and config requests", String.raw`
    const ble = await connectWithFakeBle({
      theme: "nature",
      config: { activeTheme: "nature", defaultTheme: "nature" }
    });
    const themes = ble.chars.themes.value;
    await refreshConfigAttributes();
    assert.strictEqual(ble.chars.themes.value, themes);
    assert.strictEqual(ble.writes.command.length, 0);

    ble.device.gatt.disconnect();
    ble.device.listeners.gattserverdisconnected();
    assert.strictEqual(state.connected, false);
    assert.strictEqual(els.connectButton.disabled, false);
    await els.connectButton.click();
    await waitUntil(() => !state.remoteInitializing, "reconnect initialization");

    assert.strictEqual(state.connected, true);
    assert.strictEqual(ble.requestCount, 2);
    assertJsonEqual(state.themes, JSON.parse(themes));
    assert.strictEqual(els.themeTrigger.disabled, false);
    assert.strictEqual(els.themeOptions.children.length, 2);
    assert.strictEqual(els.themeCurrent.textContent, "Nature");
    assertJsonEqual(payloadsWithoutIds(ble.writes.config).map((payload) => payload.op), ["syncTime", "syncTime"]);
  `],
  ["initial BLE reads are serialized for Android Chrome", String.raw`
    const ble = await connectWithFakeBle({ trackConcurrentReads: true });
    assert.strictEqual(state.connected, true);
    assert.strictEqual(ble.maxConcurrentReads, 1);
  `],
  ["connect cancel stays on opening screen", String.raw`
    const error = new Error("User cancelled");
    error.name = "NotFoundError";
    makeBleHarness({ requestError: error });
    await els.connectButton.click();
    assert.strictEqual(state.connected, false);
    assertVisible(els.openingView, [els.readyView, els.streamingView, els.settingsView]);
    assert.strictEqual(els.openingMessage.textContent, "SweetYaar was not selected.");
  `],
  ["missing BLE service asks for firmware upgrade", String.raw`
    await connectWithFakeBle({ missingService: true });
    assert.strictEqual(state.connected, false);
    assertVisible(els.openingView, [els.readyView, els.streamingView, els.settingsView]);
    assert.strictEqual(els.openingMessage.textContent, "Please upgrade device firmware.");
  `],
  ["unapproved device gets the physical pairing instruction before any controls load", String.raw`
    const ble = await connectWithFakeBle({ accessState: 0 });
    assert.strictEqual(state.connected, false);
    assert.strictEqual(ble.device.gatt.connected, false);
    assert.strictEqual(els.openingMessage.textContent, PAIRING_REQUIRED_MESSAGE);
    assert.deepStrictEqual(ble.reads, ["access"]);
    assert.deepStrictEqual(ble.notifications, []);
    assert.strictEqual(ble.writes.config.length, 0);
    onDisconnected({ target: ble.device });
    assert.strictEqual(els.openingMessage.textContent, PAIRING_REQUIRED_MESSAGE);
  `],
  ["authenticated approved device connects without requesting pairing mode", String.raw`
    const ble = await connectWithFakeBle({ accessState: 2 });
    assert.strictEqual(state.connected, true);
    assert.strictEqual(ble.reads[0], "access");
    assert.strictEqual(state.disconnectReason, "");
  `],
  ["authentication must finish before the app accesses controls", String.raw`
    const ble = makeBleHarness({ accessState: 1 });
    const connection = connect();
    await waitUntil(() => ble.reads.includes("access"), "access handshake");
    assert.strictEqual(state.connected, false);
    assert.deepStrictEqual(ble.notifications, []);
    ble.chars.access.value = 2;
    await connection;
    await waitUntil(() => !state.remoteInitializing, "remote initialization");
    assert.strictEqual(state.connected, true);
  `],
  ["failed authentication is not reported as missing firmware", String.raw`
    await connectWithFakeBle({ accessState: 3 });
    assert.strictEqual(state.connected, false);
    assert.strictEqual(els.openingMessage.textContent, "Couldn't authenticate. Reconnect and check for a Bluetooth pairing request.");
  `],
  ["Android authentication requests an encrypted read before waiting for approval", String.raw`
    const ble = makeBleHarness({ accessState: 1, trackConcurrentReads: true });
    const originalRead = ble.chars.status.readValue.bind(ble.chars.status);
    let pairingReads = 0;
    ble.chars.status.readValue = async () => {
      if (ble.chars.access.value === 1) {
        pairingReads++;
        assert.strictEqual(state.connected, false);
        assert.deepStrictEqual(ble.notifications, []);
        assert.strictEqual(ble.writes.config.length, 0);
        ble.chars.access.value = 2; // Android bonds only after this protected read.
      }
      return originalRead();
    };
    await connect();
    await waitUntil(() => !state.remoteInitializing, "remote initialization");
    assert.strictEqual(pairingReads, 1);
    assert.deepStrictEqual(ble.reads.slice(0, 3), ["access", "status", "access"]);
    assert.strictEqual(state.connected, true);
    assert.strictEqual(ble.maxConcurrentReads, 1);
  `],
  ["successful protected read alone cannot bypass pending or rejected approval", String.raw`
    const ble = makeBleHarness({ accessState: 1 });
    const connection = connect();
    await waitUntil(() => ble.reads.filter(name => name === "access").length >= 3, "pending access recheck");
    assert.strictEqual(ble.reads.filter(name => name === "status").length, 1);
    assert.strictEqual(state.connected, false);
    assert.strictEqual(ble.writes.config.length, 0);
    assert.deepStrictEqual(ble.notifications, []);
    ble.chars.access.value = 0; // window closed while pending
    await connection;
    assert.strictEqual(state.connected, false);
    assert.strictEqual(els.openingMessage.textContent, PAIRING_REQUIRED_MESSAGE);
  `],
  ["rejected protected read keeps authentication closed without repeated pairing probes", String.raw`
    const ble = makeBleHarness({ accessState: 1 });
    let probes = 0;
    ble.chars.status.readValue = async () => {
      probes++;
      ble.chars.access.value = 3;
      throw new Error("Insufficient encryption");
    };
    await connect();
    assert.strictEqual(probes, 1);
    assert.strictEqual(state.connected, false);
    assert.strictEqual(ble.writes.config.length, 0);
    assert.strictEqual(els.openingMessage.textContent, "Couldn't authenticate. Reconnect and check for a Bluetooth pairing request.");
  `],
  ["service-discovery rejection and disconnect retain a pairing hint", String.raw`
    for (const name of ["NetworkError", "NotFoundError"]) {
      await connectWithFakeBle({ serviceError: Object.assign(new Error("GATT Server is disconnected"), { name }), disconnectDuringDiscovery: true });
      assert.strictEqual(state.connected, false);
      assert.strictEqual(els.openingMessage.textContent, CONNECTION_PAIRING_HINT);
    }
    await connectWithFakeBle({ serviceError: Object.assign(new Error("GATT operation failed"), { name: "NetworkError" }) });
    assert.strictEqual(els.openingMessage.textContent, CONNECTION_PAIRING_HINT);
    await connectWithFakeBle({ missingService: true, serviceListError: Object.assign(new Error("GATT Server is disconnected"), { name: "NetworkError" }) });
    assert.strictEqual(els.openingMessage.textContent, CONNECTION_PAIRING_HINT);
    await connectWithFakeBle({ serviceError: Object.assign(new Error("Insufficient authentication"), { name: "NetworkError" }) });
    assert.strictEqual(els.openingMessage.textContent, PAIRING_REQUIRED_MESSAGE);
  `],
  ["BT streaming status shows streaming screen and disables remote", String.raw`
    const ble = await connectWithFakeBle();
    ble.chars.status.emit("BT connected");
    assertVisible(els.streamingView, [els.openingView, els.readyView, els.settingsView]);
    assert.strictEqual(els.playSongButton.disabled, true);
    assert.strictEqual(els.volumeRange.disabled, true);
  `],
  ["BT streaming also subscribes to all config attributes", String.raw`
    const ble = await connectWithFakeBle({ status: "BT connected" });
    assert.strictEqual(state.connected, true);
    assertVisible(els.streamingView, [els.openingView, els.readyView, els.settingsView]);
    for (const name of CONFIG_ATTRIBUTES) {
      assert(ble.notifications.includes(name));
      assert(ble.reads.includes(name));
    }
    assertJsonEqual(payloadsWithoutIds(ble.writes.config).map((p) => p.op), ["syncTime"]);
    assert.strictEqual(els.playSongButton.disabled, true);
    assert.strictEqual(els.volumeRange.disabled, true);
  `],
  ["BT streaming config subscription remains active after BT disconnects", String.raw`
    const ble = await connectWithFakeBle({
      status: "BT connected",
      volume: 31,
      theme: "nature",
      config: { activeTheme: "nature", defaultTheme: "nature" }
    });
    ble.chars.status.emit("Idle");
    await waitUntil(() => ble.writes.config.length === 2, "clock refresh after streaming");
    assertVisible(els.readyView, [els.openingView, els.streamingView, els.settingsView]);
    assert.strictEqual(els.volumeValue.textContent, "31%");
    assert.strictEqual(els.themeCurrent.textContent, "Nature");
    assertJsonEqual(payloadsWithoutIds(ble.writes.config).map((payload) => payload.op), ["syncTime", "syncTime"]);
    assert.deepStrictEqual(ble.notifications, ["status", "notice", "configResponse", ...CONFIG_ATTRIBUTES, "volume", "killswitch", "theme", "battery", "charger"]);
  `],
  ["remote playback buttons write command values", String.raw`
    const ble = await connectWithFakeBle();
    await els.playSongButton.click();
    await els.playAnimalButton.click();
    await els.stopButton.click();
    assertJsonEqual(ble.writes.command, [1, 2, 3]);
  `],
  ["song loop toggle defaults off and writes compact commands", String.raw`
    const ble = await connectWithFakeBle();
    assert.strictEqual(state.loop, false);
    assert.strictEqual(els.loopCard.classList.contains("active"), false);
    assert.strictEqual(els.loopSub.textContent, "Off · play one song at a time");

    await els.loopToggle.click();
    assertJsonEqual(ble.writes.command, [4]);
    assert.strictEqual(state.loop, true);
    assert.strictEqual(els.loopToggle.getAttribute("aria-checked"), "true");
    assert.strictEqual(els.loopCard.classList.contains("active"), true);
    assert.strictEqual(els.loopBadge.hidden, false);
    assert.strictEqual(els.loopSub.textContent, "On · plays the next song automatically");

    await els.loopToggle.click();
    assertJsonEqual(ble.writes.command, [4, 5]);
    assert.strictEqual(state.loop, false);
    assert.strictEqual(els.loopBadge.hidden, true);
  `],
  ["song loop hydrates from firmware and clears for animal playback", String.raw`
    const ble = await connectWithFakeBle({ loop: true });
    assert.strictEqual(state.loop, true);
    assert.strictEqual(els.loopBadge.hidden, false);

    await els.playAnimalButton.click();
    assertJsonEqual(ble.writes.command, [2]);
    assert.strictEqual(state.loop, false);
    assert.strictEqual(els.loopBadge.hidden, true);
  `],
  ["runtime config keeps the loop indicator synchronized", String.raw`
    const ble = await connectWithFakeBle();
    ble.config.loop = true;
    ble.publishConfigValues();
    await waitUntil(() => state.loop, "runtime loop notification");
    assert.strictEqual(state.loop, true);
    assert.strictEqual(els.loopCard.classList.contains("active"), true);
    ble.chars.status.emit("Playing animal - cat.wav");
    assert.strictEqual(state.loop, false);
    assert.strictEqual(els.loopToggle.disabled, true);
  `],
  ["remote theme picker writes selected theme", String.raw`
    const ble = await connectWithFakeBle();
    await els.themeTrigger.click();
    assert.strictEqual(els.themeOptions.hidden, false);
    const nature = els.themeOptions.children.find((child) => child.dataset.themeId === "nature");
    assert(nature, "nature theme option should render");
    await nature.click();
    assertJsonEqual(ble.writes.theme, ["nature"]);
    assert.strictEqual(state.theme, "nature");
    assert.strictEqual(els.themeOptions.hidden, true);
  `],
  ["theme picker shows attribution links from the theme scan", String.raw`
    const creditText = (el) => el.children.map((c) => (typeof c === "string" ? c : c.textContent)).join("");
    const anchors = (el) => el.children.filter((c) => typeof c !== "string");
    const ble = await connectWithFakeBle({ themes: [
      { id: "classical", name: "Classical", enabled: true, canSetDefault: true, activeValid: 1,
        credit: "[Baby Mozart](https://www.babymozart.example/classical) · [IMSLP](https://imslp.org) & more" },
      { id: "lullabies", name: "Lullabies", enabled: true, canSetDefault: true, activeValid: 1,
        credit: "Public domain" },
      { id: "nature", name: "Nature", enabled: true, canSetDefault: true, activeValid: 1 }
    ], theme: "classical", config: { activeTheme: "classical", defaultTheme: "classical" }, songs: {} });
    // Credits are not in the quick theme characteristic: nothing is shown until the picker first opens.
    assert.strictEqual(els.themeCredit.hidden, true);
    assert(!payloadsWithoutIds(ble.writes.config).some((p) => p.op === "scanThemes"), "connecting must not scan themes");
    await els.themeTrigger.click();
    assertJsonEqual(payloadsWithoutIds(ble.writes.config).filter((p) => p.op === "scanThemes"),
      [{ op: "scanThemes", cursor: 0 }]);
    // Collapsed card: each markdown link is its own anchor that opens in a new tab; text around them stays text.
    assert.strictEqual(els.themeCredit.hidden, false);
    const links = anchors(els.themeCredit);
    assert.strictEqual(links.length, 2);
    assert.strictEqual(links[0].href, "https://www.babymozart.example/classical");
    assert.strictEqual(links[0].textContent, "Baby Mozart");
    assert.strictEqual(links[0].target, "_blank");
    assert.strictEqual(links[0].rel, "noopener noreferrer");
    assert.strictEqual(links[1].href, "https://imslp.org/");
    assert.strictEqual(creditText(els.themeCredit), "Baby Mozart · IMSLP & more");
    // Expanded list: plain options only; credits belong to the selected theme, not the list.
    assertJsonEqual(els.themeOptions.children.map((c) => c.dataset.themeId), ["classical", "lullabies", "nature"]);
    assert(els.themeOptions.children.every((c) => c.classList.contains("theme-option") && c.children.length === 0));
    // Choosing another theme swaps the shown credit; a credit without a link is plain text.
    const option = (id) => els.themeOptions.children.find((c) => c.dataset.themeId === id);
    await option("lullabies").click();
    assertJsonEqual(ble.writes.theme, ["lullabies"]);
    assert.strictEqual(anchors(els.themeCredit).length, 0);
    assert.strictEqual(creditText(els.themeCredit), "Public domain");
    await els.themeTrigger.click();
    await option("nature").click();
    assert.strictEqual(els.themeCredit.hidden, true);
    assert.strictEqual(payloadsWithoutIds(ble.writes.config).filter((p) => p.op === "scanThemes").length, 1);
  `],
  ["theme attribution never becomes an unsafe link", String.raw`
    const creditText = (el) => el.children.map((c) => (typeof c === "string" ? c : c.textContent)).join("");
    const anchors = (el) => el.children.filter((c) => typeof c !== "string");
    const ble = await connectWithFakeBle({ themes: [
      { id: "a", name: "A", enabled: true, canSetDefault: true, activeValid: 1,
        credit: "[Bad](javascript:alert(1)) [Data](data:text/html,x)" },
      { id: "b", name: "B", enabled: true, canSetDefault: true, activeValid: 1,
        credit: "[Insecure](http://example.com/x) <b>bold</b>" },
      { id: "c", name: "C", enabled: true, canSetDefault: true, activeValid: 1,
        credit: "[Relative](/etc/passwd) [Mixed](https://ok.example/) **x**" }
    ], theme: "a", config: { activeTheme: "a", defaultTheme: "a" }, songs: {} });
    await els.themeTrigger.click();
    assert.strictEqual(anchors(els.themeCredit).length, 0, "a must render as text, not a link");
    assert.strictEqual(creditText(els.themeCredit), "[Bad](javascript:alert(1)) [Data](data:text/html,x)");
    const choose = async (id) => {
      await els.themeOptions.children.find((c) => c.dataset.themeId === id).click();
      await els.themeTrigger.click();
    };
    await choose("b");
    assert.strictEqual(anchors(els.themeCredit).length, 0, "b must render as text, not a link");
    assert.strictEqual(creditText(els.themeCredit), "[Insecure](http://example.com/x) <b>bold</b>");
    // Only the well-formed https link in a mixed credit becomes an anchor; the rest stays visible text.
    await choose("c");
    assert.strictEqual(anchors(els.themeCredit).length, 1);
    assert.strictEqual(anchors(els.themeCredit)[0].href, "https://ok.example/");
    assert.strictEqual(creditText(els.themeCredit), "[Relative](/etc/passwd) Mixed **x**");
  `],
  ["theme picker still works when the credit scan fails", String.raw`
    const ble = await connectWithFakeBle();
    const write = ble.chars.configCommand.write;
    ble.chars.configCommand.write = (value) => {
      const request = JSON.parse(textFromValue(value));
      if (request.op !== "scanThemes") return write(value);
      ble.chars.configResponse.emit(JSON.stringify({ id: request.id, ok: false, error: "scan failed" }));
    };
    await els.themeTrigger.click();
    assert.strictEqual(els.themeOptions.hidden, false);
    assert.strictEqual(els.themeOptions.children.length, 2);
    assert.strictEqual(els.themeCredit.hidden, true);
    assert.strictEqual(state.themeCreditsLoading, false);
  `],
  ["remote theme picker overrides theme without leaving bedtime", String.raw`
    const ble = await connectWithFakeBle({
      theme: "nature",
      config: { activeTheme: "nature", defaultTheme: "nature" }
    });
    await els.bedtimeToggleButton.click();
    assert.strictEqual(state.bedtime.active, true);
    assert.strictEqual(els.bedtimeTitle.textContent, "Bedtime");
    assert.strictEqual(els.themeCurrent.textContent, "Lullabies");
    await els.themeTrigger.click();
    const nature = els.themeOptions.children.find((child) => child.dataset.themeId === "nature");
    assert(nature, "nature theme option should render");
    await nature.click();
    assertJsonEqual(ble.writes.theme, ["nature"]);
    assert.strictEqual(state.theme, "nature");
    assert.strictEqual(state.bedtime.active, true);
    assert.strictEqual(state.bedtime.effectiveTheme, "nature");
    assert.strictEqual(els.bedtimeTitle.textContent, "Bedtime");
    assert.strictEqual(els.themeCurrent.textContent, "Nature");
    assert.strictEqual(els.themeHelper.hidden, false);
  `],
  ["quiet-time toggle writes optimistic values", String.raw`
    const ble = await connectWithFakeBle();
    await els.killswitchToggle.click();
    assertJsonEqual(ble.writes.killswitch, [600]);
    assert.strictEqual(state.quietSeconds, 600);
    assert.strictEqual(els.killswitchToggle.getAttribute("aria-checked"), "true");
    assert.strictEqual(els.quietCard.classList.contains("active"), true);
    assert.strictEqual(els.quietSub.textContent, "Paused · 10:00 left");
    await els.killswitchToggle.click();
    assertJsonEqual(ble.writes.killswitch, [600, 0]);
    assert.strictEqual(state.quietSeconds, 0);
    assert.strictEqual(els.killswitchToggle.getAttribute("aria-checked"), "false");
  `],
  ["quiet-time countdown comes from the seconds value, not the status text", String.raw`
    const ble = await connectWithFakeBle();
    ble.chars.status.emit("Quiet time");
    ble.chars.killswitch.emit(new DataView(new Uint8Array([572 & 0xff, 572 >> 8]).buffer));
    assert.strictEqual(els.quietCard.classList.contains("active"), true);
    assert.strictEqual(els.quietSub.textContent, "Paused · 9:32 left");
    assert.strictEqual(els.readyStatusText.textContent, "Quiet time");
    assert.strictEqual(els.readyMessage.hidden, true);
    assert.strictEqual(els.readyStatusIcon.classList.contains("tint-quiet"), true);
    assert.strictEqual(els.readyStatusIllus.hidden, false);
  `],
  ["playing song shows song icon, prettified headline, theme subline", String.raw`
    const ble = await connectWithFakeBle();
    ble.chars.status.emit("Playing song - Lullabies / 01_twinkle_twinkle.wav");
    assert.strictEqual(els.readyStatusText.textContent, "Twinkle Twinkle");
    assert.strictEqual(els.readyStatusText.dir, "ltr");
    assert.strictEqual(els.readyMessage.textContent, "Lullabies");
    assert.strictEqual(els.readyMessage.hidden, false);
    assert.strictEqual(els.readyStatusIcon.classList.contains("tint-song"), true);
    assert.strictEqual(els.readyStatusIllus.hidden, false);
    assert.ok(els.readyStatusIllus.src.endsWith("icon-song.png"));
    assert.strictEqual(els.playSongButton.classList.contains("playing"), true);
  `],
  ["playing animal shows animal icon and prettified headline only", String.raw`
    const ble = await connectWithFakeBle();
    ble.chars.status.emit("Playing animal - cat.wav");
    assert.strictEqual(els.readyStatusText.textContent, "Cat");
    assert.strictEqual(els.readyMessage.hidden, true);
    assert.strictEqual(els.readyStatusIcon.classList.contains("tint-animal"), true);
    assert.ok(els.readyStatusIllus.src.endsWith("icon-animal.png"));
    assert.strictEqual(els.playAnimalButton.classList.contains("playing"), true);
  `],
  ["RTL song name sets right-to-left direction on the headline", String.raw`
    const ble = await connectWithFakeBle();
    ble.chars.status.emit("Playing song - Lullabies / שיר_ערש.wav");
    assert.strictEqual(els.readyStatusText.textContent, "שיר ערש");
    assert.strictEqual(els.readyStatusText.dir, "rtl");
    assert.strictEqual(els.readyStatusText.classList.contains("rtl-text"), true);
  `],
  ["prettifyName strips track prefixes while preserving numbers in titles", String.raw`
    assert.strictEqual(prettifyName("twinkle_twinkle.wav"), "Twinkle Twinkle");
    assert.strictEqual(prettifyName("cow.wav"), "Cow");
    for (const [file, expected] of [
      ["01_twinkle.wav", "Twinkle"],
      ["01 Twinkle Twinkle.wav", "Twinkle Twinkle"],
      ["01. Twinkle.wav", "Twinkle"],
      ["02 - lullaby.wav", "Lullaby"],
      ["001 ._- ) twinkle.wav", "Twinkle"],
      ["1 - twinkle.wav", "Twinkle"],
      ["3 little pigs.wav", "3 Little Pigs"],
      ["3. Little Pigs.wav", "Little Pigs"],
      ["3_little_pigs.wav", "Little Pigs"],
      ["1_song.wav", "Song"],
      ["13 Song.wav", "13 Song"],
      ["13-song.wav", "Song"],
      ["13 ._- ) song.wav", "Song"],
      ["13)song.wav", "Song"],
      ["0 song.wav", "0 Song"],
      ["01Twinkle.wav", "01Twinkle"],
      ["01 שיר_ערש.wav", "שיר ערש"],
      ["3 שירים.wav", "3 שירים"],
      ["3. שירים.wav", "שירים"]
    ]) assert.strictEqual(prettifyName(file), expected, file);
    assert.strictEqual(prettifyName("שיר_ערש.wav"), "שיר ערש");
    assert.strictEqual(prettifyName("Lullaby (slow).WAV"), "Lullaby (slow)");
    assert.strictEqual(isRtlText("שיר"), true);
    assert.strictEqual(isRtlText("Twinkle"), false);
  `],
  ["prettifyName keeps numeric prefixes when no title follows", String.raw`
    for (const [file, expected] of [
      ["10.wav", "10"],
      ["01.wav", "01"],
      ["01 -", "01 -"],
      ["01 - .wav", "01 -"],
      ["13. .wav", "13."],
      ["01__ .wav", "01"],
      ["13 _-.) .wav", "13 -.)"],
      ["01 - " + String.fromCharCode(0x200B) + ".wav", "01 -"]
    ]) assert.strictEqual(prettifyName(file), expected, file);
  `],
  ["prettifyName strips reserved and invisible characters", String.raw`
    const zwsp = String.fromCharCode(0x200B), zwnj = String.fromCharCode(0x200C);
    assert.strictEqual(prettifyName("a" + zwsp + "b" + zwnj + "c.wav"), "Abc");
    const rlm = String.fromCharCode(0x200F), repl = String.fromCharCode(0xFFFD), pua = String.fromCharCode(0xE000);
    assert.strictEqual(prettifyName("שיר" + rlm + " " + repl + "ערש" + pua + ".wav"), "שיר ערש");
    assert.strictEqual(prettifyName("rock|roll.wav"), "Rock Roll");
    assert.strictEqual(prettifyName("cleansong.wav"), "Cleansong");
  `],
  ["returning to ready restores green checkmark", String.raw`
    const ble = await connectWithFakeBle();
    ble.chars.status.emit("Playing song - Lullabies / twinkle.wav");
    ble.chars.status.emit("Idle");
    assert.strictEqual(els.readyStatusText.textContent, "Ready to play");
    assert.strictEqual(els.readyStatusIcon.classList.contains("green"), true);
    assert.strictEqual(els.readyStatusGlyph.hidden, false);
    assert.strictEqual(els.readyStatusGlyph.textContent, "✓");
    assert.strictEqual(els.readyStatusIllus.hidden, true);
  `],
  ["device error notice shows a persistent banner until dismissed", String.raw`
    const ble = await connectWithFakeBle();
    ble.chars.notice.emit(JSON.stringify({ severity: "error", message: "SD card not found." }));
    assert.strictEqual(els.noticeBanner.hidden, false);
    assert.strictEqual(els.noticeMessage.textContent, "SD card not found.");
    assert.strictEqual(els.noticeBanner.classList.contains("error"), true);
    assert.strictEqual(state.noticeTimer, null);
    await els.noticeDismiss.click();
    assert.strictEqual(els.noticeBanner.hidden, true);
    assert.strictEqual(state.notice, null);
  `],
  ["device warning notice shows a banner and schedules auto-dismiss", String.raw`
    const ble = await connectWithFakeBle();
    ble.chars.notice.emit(JSON.stringify({ severity: "warn", message: "No songs in this theme." }));
    assert.strictEqual(els.noticeBanner.hidden, false);
    assert.strictEqual(els.noticeBanner.classList.contains("warn"), true);
    assert.notStrictEqual(state.noticeTimer, null);
  `],
  ["BLE takeover shows its reason after disconnect without stealing control back", String.raw`
    const ble = await connectWithFakeBle();
    const requests = ble.requestCount;
    ble.chars.notice.emit(JSON.stringify({ type: "takeover" }));
    assert.strictEqual(state.connected, false);
    assert.strictEqual(ble.device.gatt.connected, false);
    assert.strictEqual(state.message, "Someone else took control.");
    assert.strictEqual(els.openingMessage.textContent, "Someone else took control.");
    assert.strictEqual(els.connectButton.disabled, false);
    onDisconnected({ target: ble.device }); // delayed device disconnect event
    assert.strictEqual(state.message, "Someone else took control.");
    await safeWrite(async () => { throw new Error("GATT Server is disconnected"); });
    assert.strictEqual(state.message, "Someone else took control.");
    assert.strictEqual(ble.requestCount, requests);
    await connect();
    await waitUntil(() => !state.remoteInitializing, "remote initialization");
    assert.strictEqual(state.connected, true);
    assert.strictEqual(state.disconnectReason, "");
  `],
  ["disconnect event from an older phone cannot clear a new session", String.raw`
    await connectWithFakeBle();
    onDisconnected({ target: { id: "old-device" } });
    assert.strictEqual(state.connected, true);
  `],
  ["failed connection does not suppress the next session's disconnect", String.raw`
    for (const options of [{ accessState: 0 }, { missingCharacteristics: ["volume"] }]) {
      for (const synchronous of [false, true]) {
        const failed = makeBleHarness(options);
        const deliverOldDisconnect = () => failed.device.listeners.gattserverdisconnected({ target: failed.device });
        failed.device.gatt.disconnect = function () {
          this.connected = false;
          if (synchronous) deliverOldDisconnect();
        };
        await connect();
        await waitUntil(() => !state.remoteInitializing, "failed initialization cleanup");
        assert.strictEqual(state.connected, false);
        const reason = options.accessState === 0 ? PAIRING_REQUIRED_MESSAGE : "Please upgrade device firmware.";
        assert.strictEqual(state.message, reason);
        if (!synchronous) deliverOldDisconnect();
        assert.strictEqual(state.message, reason);

        const approved = await connectWithFakeBle({ accessState: 2 });
        assert.strictEqual(state.connected, true);
        deliverOldDisconnect();
        assert.strictEqual(state.connected, true);
        approved.device.gatt.disconnect();
        approved.device.listeners.gattserverdisconnected({ target: approved.device });
        assert.strictEqual(state.connected, false);
        assertVisible(els.openingView, [els.readyView, els.streamingView, els.settingsView]);
        assert.strictEqual(state.message, "Remote disconnected.");
        assert.strictEqual(subscriptions.size, 0);
      }
    }
  `],
  ["failed initialization removes subscriptions immediately", String.raw`
    const ble = await connectWithFakeBle({ missingCharacteristics: ["volume"] });
    assert.strictEqual(state.connected, false);
    assert.strictEqual(subscriptions.size, 0);
    assert.strictEqual(state.configNotifyResolve, null);
    ble.chars.status.emit("BT connected");
    assert.strictEqual(state.status, "Disconnected");
    assert.strictEqual(state.message, "Please upgrade device firmware.");
  `],
  ["malformed notice payload is ignored", String.raw`
    const ble = await connectWithFakeBle();
    ble.chars.notice.emit("not json");
    assert.strictEqual(els.noticeBanner.hidden, true);
    ble.chars.notice.emit(JSON.stringify({ severity: "error" }));
    assert.strictEqual(els.noticeBanner.hidden, true);
  `],
  ["battery state renders the compact indicator and persistent warning", String.raw`
    const ble = await connectWithFakeBle({ battery: 2 });
    assert.strictEqual(state.battery, "medium");
    assert.strictEqual(els.batteryIndicator.classList.contains("medium"), true);
    assert.strictEqual(els.batteryIndicator.getAttribute("aria-label"), "Battery medium");
    assert.strictEqual(els.batteryWarning.hidden, false);
    assert.strictEqual(els.batteryWarning.classList.contains("medium"), true);
    assert.strictEqual(els.batteryWarningTitle.textContent, "Charge SweetYaar soon");
    assert.strictEqual(els.batteryWarningArt.src, "assets/battery-medium-art.png");

    ble.chars.battery.emit(3);
    assert.strictEqual(state.battery, "low");
    assert.strictEqual(els.batteryIndicator.classList.contains("low"), true);
    assert.strictEqual(els.batteryWarning.classList.contains("low"), true);
    assert.strictEqual(els.batteryWarningTitle.textContent, "Charge SweetYaar now");
    assert.strictEqual(els.batteryWarningArt.src, "assets/battery-low-art.png");

    ble.chars.battery.emit(4);
    assert.strictEqual(state.battery, "charging");
    assert.strictEqual(els.batteryWarning.hidden, true);
    assert.strictEqual(els.batteryIndicator.getAttribute("aria-label"), "Battery charging");
  `],
  ["settings screen loads config and content scans", String.raw`
    const ble = await connectWithFakeBle();
    await els.tabSettings.click();
    await waitForSettingsLoaded();
    assertVisible(els.settingsView, [els.openingView, els.readyView, els.streamingView]);
    assert.strictEqual(state.settings.loading, false);
    assert.strictEqual(els.settingsDeviceName.value, "SweetYaar");
    assert.strictEqual(els.settingsVolumeValue.textContent, "75%");
    assert.strictEqual(els.settingsBedtimeStartTime.value, "18:30");
    assert.strictEqual(els.settingsBedtimeEndTime.value, "06:30");
    assert.strictEqual(els.settingsBedtimeVolumeValue.textContent, "45%");
    assert.strictEqual(els.settingsNormalIdleSec.value, "600");
    assert(els.settingsThemeList.children.length >= 2, "settings themes should render");
    assert(els.settingsSongList.children.length >= 1, "settings songs should render");
    assert.strictEqual(els.settingsSaveButton.disabled, true);
    assertJsonEqual(payloadsWithoutIds(ble.writes.config).slice(-2), [
      { op: "scanThemes", cursor: 0 },
      { op: "scanSongs", theme: "lullabies", cursor: 0 }
    ]);
  `],
  ["settings are cached for the session and not re-scanned on reopen", String.raw`
    const ble = await connectWithFakeBle();
    await els.tabSettings.click();
    await waitForSettingsLoaded();
    const scansAfterFirstOpen = payloadsWithoutIds(ble.writes.config)
      .filter((p) => p.op === "scanThemes" || p.op === "scanSongs").length;
    await els.tabRemote.click();
    await els.tabSettings.click();
    assert.strictEqual(state.settings.loading, false);
    assertVisible(els.settingsView, [els.openingView, els.readyView, els.streamingView]);
    const scansAfterReopen = payloadsWithoutIds(ble.writes.config)
      .filter((p) => p.op === "scanThemes" || p.op === "scanSongs").length;
    assert.strictEqual(scansAfterReopen, scansAfterFirstOpen, "reopening settings must not re-scan");
    assert(els.settingsSongList.children.length >= 1, "cached songs should still render");
  `],
  ["settings lists keep their rows across unrelated renders so taps are not lost", String.raw`
    const ble = await connectWithFakeBle();
    await els.tabSettings.click();
    await waitForSettingsLoaded();
    const themeRows = () => els.settingsThemeList.children;
    const songRows = () => els.settingsSongList.children;
    const firstTheme = themeRows()[0], firstSong = songRows()[0];
    // Notifications render the whole app; unchanged lists must keep their nodes.
    handleStatusUpdate("Idle");
    ble.chars.charger.emit(bytesView([1, 4, 3, 0x60, 0, 1]));
    assert.strictEqual(themeRows()[0], firstTheme, "theme rows must survive an unrelated render");
    assert.strictEqual(songRows()[0], firstSong, "song rows must survive an unrelated render");

    // The whole song row is the checkbox's label.
    assert.strictEqual(firstSong.selector, "label");
    const songBox = firstSong.children[0];
    await songBox.change(false);
    assert.strictEqual(state.settings.songs[0].enabled, false);
    assert.strictEqual(songRows()[0].children[0].checked, false);

    // A theme's checkbox sits in its own label; tapping it must not select the theme.
    const selected = state.settings.selectedThemeId;
    const other = themeRows().find((row) => row.dataset.themeId !== selected);
    const hit = other.children[0];
    assert(hit.classList.contains("settings-check-hit"));
    await hit.click();
    assert.strictEqual(state.settings.selectedThemeId, selected, "the checkbox tap must not select the theme");
    await hit.children[0].change(false);
    assert.strictEqual(state.settings.themes.find((t) => t.id === other.dataset.themeId).enabled, false);

    // A refused change re-syncs the box with the real state.
    const again = themeRows().find((row) => row.dataset.themeId === other.dataset.themeId).children[0].children[0];
    state.busy = true;
    await again.change(true);
    const resynced = themeRows().find((row) => row.dataset.themeId === other.dataset.themeId).children[0].children[0];
    assert.strictEqual(resynced.checked, false);
    assert.strictEqual(resynced.disabled, true);
    state.busy = false;
  `],
  ["theme pickers keep their options across unrelated renders so taps are not lost", String.raw`
    const ble = await connectWithFakeBle({ themes: [
      { id: "classical", name: "Classical", enabled: true, canSetDefault: true, activeValid: 1,
        credit: "[IMSLP](https://imslp.org) & more" },
      { id: "nature", name: "Nature", enabled: true, canSetDefault: true, activeValid: 1 }
    ], theme: "classical", config: { activeTheme: "classical", defaultTheme: "classical" }, songs: {} });
    await els.themeTrigger.click();
    const option = els.themeOptions.children[1];
    const link = els.themeCredit.children[0];
    handleStatusUpdate("Playing song - Classical / A.wav");
    ble.chars.charger.emit(bytesView([1, 4, 3, 0x60, 0, 1]));
    assert.strictEqual(els.themeOptions.children[1], option, "main-screen theme options must survive renders");
    assert.strictEqual(els.themeCredit.children[0], link, "credit links must survive renders");
    // A real change still rebuilds: choosing another theme moves the selection.
    await option.click();
    assertJsonEqual(ble.writes.theme, ["nature"]);
    assert.strictEqual(els.themeOptions.children[1].getAttribute("aria-selected"), "true");
    assert.strictEqual(els.themeCredit.hidden, true);

    await els.tabSettings.click();
    await waitForSettingsLoaded();
    state.settings.defaultThemeOpen = true;
    state.settings.bedtimeThemeOpen = true;
    render();
    const defaultOption = els.settingsDefaultThemeOptions.children[0];
    const bedtimeOption = els.settingsBedtimeThemeOptions.children[0];
    handleStatusUpdate("Idle");
    assert.strictEqual(els.settingsDefaultThemeOptions.children[0], defaultOption);
    assert.strictEqual(els.settingsBedtimeThemeOptions.children[0], bedtimeOption);
  `],
  ["song list shows a loading spinner while a theme's songs are scanned", String.raw`
    await connectWithFakeBle();
    await els.tabSettings.click();
    await waitForSettingsLoaded();
    const songs = state.settings.songs;
    state.settings.songs = [];
    state.settings.loading = true;
    render();
    const loader = els.settingsSongList.children[0];
    assert.strictEqual(els.settingsSongList.children.length, 1);
    assert(loader.classList.contains("settings-list-loading"));
    assert(loader.children[0].classList.contains("spinner"));
    assert.strictEqual(loader.children[1].textContent, "Loading songs…");
    state.settings.songs = songs;
    state.settings.loading = false;
    render();
    assert(!els.settingsSongList.children.some((c) => c.classList.contains("settings-list-loading")));
  `],
  ["returning to remote refreshes the device clock", String.raw`
    const ble = await connectWithFakeBle();
    assert.strictEqual(els.deviceWatch.textContent, "Toy clock 21:05");
    await els.tabSettings.click();
    await waitForSettingsLoaded();
    ble.config.bedtime.currentTime = "22:14";
    ble.config.bedtime.currentSecondOfDay = 80040;
    await els.tabRemote.click();
    await waitUntil(() => els.deviceWatch.textContent === "Toy clock 22:14", "device clock refresh");
    assertVisible(els.readyView, [els.openingView, els.streamingView, els.settingsView]);
    const syncPayloads = payloadsWithoutIds(ble.writes.config).filter((payload) => payload.op === "syncTime");
    assert.strictEqual(syncPayloads.length, 2);
  `],
  ["settings save writes config, theme, and song payloads", String.raw`
    const ble = await connectWithFakeBle();
    await els.tabSettings.click();
    await waitForSettingsLoaded();
    await els.settingsDeviceName.input("SweetYaar Night");
    await els.settingsVolumeRange.input("42");
    state.settings.defaultTheme = "nature";
    state.settings.bedtimeTheme = "nature";
    await els.settingsBedtimeStartTime.input("15:00");
    await els.settingsBedtimeEndTime.input("13:00");
    await els.settingsBedtimeVolumeRange.input("33");
    await els.settingsSleepEnabled.change(false);
    await els.settingsNormalIdleSec.input("901");
    await els.settingsWakeIdleSec.input("181");
    await els.settingsBleIdleSec.input("301");
    state.settings.pendingThemeChanges = { nature: { enabled: false, shuffle: true } };
    state.settings.pendingSongChanges = { nature: { "rain.wav": false } };
    await els.settingsSaveButton.click();
    const payloads = payloadsWithoutIds(ble.writes.config);
    assert(payloads.some((payload) => payload.op === "setConfig" && payload.deviceName === "SweetYaar Night"));
    assert(payloads.some((payload) => payload.op === "setConfig" && payload.defaultVolumePct === 42));
    assert(payloads.some((payload) => payload.op === "setConfig" && payload.defaultTheme === "nature"));
    assert(payloads.some((payload) => payload.op === "setConfig" && payload.sleep &&
      payload.sleep.enabled === false &&
      payload.sleep.normalIdleSec === 901 &&
      payload.sleep.vibrationWakeIdleSec === 181 &&
      payload.sleep.bleIdleSec === 301));
    assert(payloads.some((payload) => payload.op === "setConfig" && payload.bedtime &&
      payload.bedtime.startTime === "15:00" &&
      payload.bedtime.endTime === "13:00" &&
      payload.bedtime.theme === "nature" &&
      payload.bedtime.volumeCapPct === 33));
    assert(payloads.some((payload) => payload.op === "setTheme" && payload.theme === "nature" && payload.enabled === false && payload.shuffle === true));
    assert(payloads.some((payload) => payload.op === "setSong" && payload.theme === "nature" && payload.file === "rain.wav" && payload.enabled === false));
    assert.strictEqual(state.settings.dirty, false);
    assert.strictEqual(state.settings.message, "Settings saved.");
    assert.strictEqual(els.settingsSaveButton.disabled, true);
  `],
  ["saving startup defaults preserves the remote volume and theme", String.raw`
    const ble = await connectWithFakeBle({ volume: 20 });
    chooseTheme("nature");
    await waitUntil(() => !state.busy && ble.config.activeTheme === "nature", "live theme change");
    await els.tabSettings.click();
    await waitForSettingsLoaded();
    await els.settingsVolumeRange.input("42");
    await els.settingsSaveButton.click();
    assert.strictEqual(ble.config.defaultVolumePct, 42);
    assert.strictEqual(state.volume, 20);
    assert.strictEqual(state.theme, "nature");

    await els.tabRemote.click();
    chooseTheme("lullabies");
    await waitUntil(() => !state.busy && ble.config.activeTheme === "lullabies", "second live theme change");
    await els.tabSettings.click();
    await waitForSettingsLoaded();
    state.settings.defaultTheme = "nature";
    await els.settingsDeviceName.input("SweetYaar Night");
    await els.settingsSaveButton.click();
    assert.strictEqual(ble.config.defaultTheme, "nature");
    assert.strictEqual(state.volume, 20);
    assert.strictEqual(state.theme, "lullabies");
    assertJsonEqual(ble.writes.volume, []);
    await els.tabRemote.click();
    assert.strictEqual(state.volume, 20);
    assert.strictEqual(state.theme, "lullabies");
  `],
  ["config.json load failure is shown in Settings", String.raw`
    const message = "Settings file is missing or invalid. Restore config.json on the SD card and restart the toy.";
    await connectWithFakeBle({ configFileError: message });
    assert.strictEqual(state.connected, true);
    assert.strictEqual(state.configError.message, message);
    await els.tabSettings.click();
    await waitForSettingsLoaded();
    assert.strictEqual(state.settings.message, message);
    assert.strictEqual(state.settings.sessionScanned, false);
  `],
  ["setTheme SD write failure surfaces error to app", String.raw`
    const ble = await connectWithFakeBle();
    await els.tabSettings.click();
    await waitForSettingsLoaded();

    // Stage a pending theme change so the save flow emits a setTheme command.
    state.settings.pendingThemeChanges = { lullabies: { enabled: false } };
    state.settings.dirty = true;
    render();

    // Override configCommand.write to reject setTheme with ok:false.
    const originalConfigCommandWrite = ble.chars.configCommand.write.bind(ble.chars.configCommand);
    ble.chars.configCommand.write = (value) => {
      const payload = JSON.parse(textFromValue(value));
      if (payload.op === "setTheme") {
        const errorResponse = JSON.stringify({ id: payload.id, ok: false, error: "SD write failed" });
        ble.chars.configResponse.value = errorResponse;
        setTimeout(() => ble.chars.configResponse.emit(errorResponse), 0);
        return;
      }
      originalConfigCommandWrite(value);
    };

    await els.settingsSaveButton.click();

    assert.strictEqual(state.settings.message, "SD write failed");
    assert.strictEqual(state.settings.dirty, true, "Expected settings to remain dirty after failed save");
  `],
];

if (require.main === module) (async () => {
  const selected = tests.filter(([name]) => !process.env.TEST_FILTER || new RegExp(process.env.TEST_FILTER).test(name));
  let failures = 0;
  for (const [name, source] of selected) {
    try {
      await runInApp(source);
      console.log(`ok - ${name}`);
    } catch (error) {
      failures += 1;
      console.error(`FAIL - ${name}`, error);
    }
  }
  if (failures) throw new Error(`${failures} of ${selected.length} app tests failed`);
  console.log(`parent app UI tests passed (${selected.length})`);
})().catch((error) => {
  console.error(error);
  process.exit(1);
});

module.exports = { runInApp };

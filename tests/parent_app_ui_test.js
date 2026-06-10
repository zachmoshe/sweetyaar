"use strict";

const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const { TextDecoder, TextEncoder } = require("util");

const root = path.resolve(__dirname, "..");
const html = fs.readFileSync(path.join(root, "docs", "index.html"), "utf8");
const match = html.match(/<script>\s*([\s\S]*?)\s*<\/script>/);
assert(match, "docs/index.html must contain the parent app script");
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

  add(name) {
    this.values.add(name);
    this.owner._className = [...this.values].join(" ");
  }

  remove(name) {
    this.values.delete(name);
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
    setTimeout,
    clearTimeout,
    setInterval: () => 0,
    clearInterval: () => {},
    document,
    window,
    navigator: { bluetooth: {} },
    __consoleOutput: consoleOutput,
  };
}

async function runInApp(testSource) {
  const context = createContext();
  const source = `${appScript}\n${appTestHelpers}\n(async () => {\n${testSource}\n})()`;
  return vm.runInNewContext(source, context, { filename: "docs/index.html" });
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
      if (typeof this.value === "number") return uint8View(this.value);
      if (this.value instanceof DataView) return this.value;
      return textView(String(this.value ?? ""));
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

  write(value) {
    this.writes.push(value);
    this.value = value;
  }

  addEventListener(name, handler) {
    this.listeners[name] ??= [];
    this.listeners[name].push(handler);
  }

  async startNotifications() {
    if (this.hooks.onStartNotifications) {
      this.hooks.onStartNotifications(this.name);
    }
  }

  emit(value) {
    this.value = value;
    const data = typeof value === "number" ? uint8View(value) : textView(String(value));
    for (const listener of this.listeners.characteristicvaluechanged || []) {
      listener({ target: { value: data } });
    }
  }
}

function makeBleHarness(options = {}) {
  const writes = {
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
      return { id: payload.id, ok: true, op: "getConfig", sdReady: true, ...config };
    }
    if (payload.op === "getConfig") {
      return { id: payload.id, ok: true, op: "getConfig", sdReady: true, ...config };
    }
    if (payload.op === "setConfig") {
      if (Object.prototype.hasOwnProperty.call(payload, "deviceName")) config.deviceName = payload.deviceName;
      if (Object.prototype.hasOwnProperty.call(payload, "defaultVolumePct")) config.defaultVolumePct = payload.defaultVolumePct;
      if (Object.prototype.hasOwnProperty.call(payload, "defaultTheme")) {
        config.defaultTheme = payload.defaultTheme;
        config.activeTheme = payload.defaultTheme;
      }
      if (payload.sleep) config.sleep = { ...config.sleep, ...payload.sleep };
      if (payload.bedtime) config.bedtime = { ...config.bedtime, ...payload.bedtime };
      return { id: payload.id, ok: true, op: "getConfig", sdReady: true, ...config };
    }
    if (payload.op === "setBedtimeMode") {
      config.bedtime.active = !!payload.active && config.bedtime.enabled && config.bedtime.timeKnown;
      config.bedtime.override = payload.active ? "on" : "off";
      config.bedtime.effectiveVolumePct = config.bedtime.active
        ? Math.min(config.defaultVolumePct, config.bedtime.volumeCapPct)
        : config.defaultVolumePct;
      config.bedtime.effectiveTheme = config.bedtime.active ? config.bedtime.theme : config.activeTheme;
      return { id: payload.id, ok: true, op: "getConfig", sdReady: true, ...config };
    }
    if (payload.op === "scanThemes") {
      return { id: payload.id, ok: true, op: "scanThemes", page: payload.page || 0, hasMore: false, themes };
    }
    if (payload.op === "scanSongs") {
      return {
        id: payload.id,
        ok: true,
        op: "scanSongs",
        theme: payload.theme,
        name: themes.find((theme) => theme.id === payload.theme)?.name || payload.theme,
        page: payload.page || 0,
        hasMore: false,
        songs: songs[payload.theme] || []
      };
    }
    if (payload.op === "setTheme" || payload.op === "setSong") {
      return { id: payload.id, ok: true, op: payload.op };
    }
    return { id: payload.id, ok: false, error: "unknown op" };
  }

  let response = { id: 0, ok: true };
  let activeReads = 0;
  let maxConcurrentReads = 0;
  const reads = [];
  const notifications = [];
  const readHooks = {
    async beforeRead(name) {
      reads.push(name);
      if (!options.trackConcurrentReads) return;
      activeReads += 1;
      maxConcurrentReads = Math.max(maxConcurrentReads, activeReads);
      await delay(5);
    },
    afterRead() {
      if (!options.trackConcurrentReads) return;
      activeReads -= 1;
    },
    onStartNotifications(name) {
      notifications.push(name);
    }
  };
  const chars = {
    volume: new FakeCharacteristic("volume", options.volume ?? 75, readHooks),
    killswitch: new FakeCharacteristic("killswitch", options.killswitch ? 1 : 0, readHooks),
    theme: new FakeCharacteristic("theme", options.theme || "lullabies", readHooks),
    status: new FakeCharacteristic("status", options.status || "Idle", readHooks),
    themes: new FakeCharacteristic("themes", JSON.stringify(themes.filter((theme) => theme.enabled).map((theme) => ({ id: theme.id, name: theme.name }))), readHooks),
    command: new FakeCharacteristic("command", "", readHooks),
    configCommand: new FakeCharacteristic("configCommand", "{}", readHooks),
    configResponse: new FakeCharacteristic("configResponse", JSON.stringify(response), readHooks)
  };

  function isJsonConfigWrite(value) {
    return textFromValue(value).trimStart().startsWith("{");
  }

  chars.command.write = (value) => {
    if (isJsonConfigWrite(value)) {
      const payload = JSON.parse(textFromValue(value));
      writes.config.push(payload);
      response = configResponse(payload);
      chars.configResponse.value = JSON.stringify(response);
      chars.themes.value = JSON.stringify(response);
    } else {
      writes.command.push(value[0]);
      chars.command.value = value;
    }
  };
  chars.configCommand.write = (value) => {
    const payload = JSON.parse(textFromValue(value));
    writes.config.push(payload);
    response = configResponse(payload);
    chars.configResponse.value = JSON.stringify(response);
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
    writes.killswitch.push(value[0]);
    chars.killswitch.value = value[0];
  };

  const charByUuid = new Map(Object.entries(UUIDS).map(([name, uuid]) => [uuid, chars[name]]));
  const service = {
    async getCharacteristic(uuid) {
      const characteristic = charByUuid.get(uuid);
      if (!characteristic || (options.missingCharacteristics || []).includes(characteristic.name)) {
        const error = new Error("missing characteristic");
        error.name = "NotFoundError";
        throw error;
      }
      return characteristic;
    },
    async getCharacteristics() {
      return Object.values(chars);
    }
  };
  const server = {
    async getPrimaryService(uuid) {
      if (options.missingService) {
        const error = new Error("missing service");
        error.name = "NotFoundError";
        throw error;
      }
      assert.strictEqual(uuid, UUIDS.service);
      return service;
    },
    async getPrimaryServices() {
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
    device,
    reads,
    notifications,
    get maxConcurrentReads() { return maxConcurrentReads; },
    get requestCount() { return requestCount; }
  };
}

async function connectWithFakeBle(options = {}) {
  const ble = makeBleHarness(options);
  await els.connectButton.click();
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

async function waitForSettingsLoaded() {
  await waitUntil(() => state.view === "settings" && state.settings.loading === false, "settings load");
}
`;

const tests = [
  ["initial opening screen is usable", String.raw`
    assertVisible(els.openingView, [els.readyView, els.streamingView, els.settingsView]);
    assert.strictEqual(els.connectButton.disabled, false);
    assert.strictEqual(els.connectButtonLabel.textContent, "Connect to SweetYaar");
    assert.strictEqual(els.openingMessage.textContent, "Connect to play songs and animal sounds, set the volume, and more.");
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
    assertJsonEqual(payloadsWithoutIds(ble.writes.config).map((payload) => payload.op), ["syncTime", "scanThemes"]);
    assert.strictEqual(els.bedtimeTitle.textContent, "Daytime");
    assert.strictEqual(els.bedtimeMessage.textContent, "(ends at 18:30)");
    assert.strictEqual(els.deviceWatch.textContent, "Toy clock 21:05");
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
  ["empty theme scan leaves remote picker empty", String.raw`
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
    assertJsonEqual(payloadsWithoutIds(ble.writes.config).map((payload) => payload.op), ["syncTime", "scanThemes"]);
  `],
  ["connect loads themes through legacy config transport", String.raw`
    const ble = await connectWithFakeBle({
      missingCharacteristics: ["configCommand", "configResponse"],
      theme: "nature",
      config: { activeTheme: "nature", defaultTheme: "nature" }
    });
    assert.strictEqual(state.connected, true);
    assert.strictEqual(state.configAvailable, false);
    assert.strictEqual(els.themeCurrent.textContent, "Nature");
    assertJsonEqual(payloadsWithoutIds(ble.writes.config).map((payload) => payload.op), ["syncTime", "scanThemes"]);
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
  ["BT streaming status shows streaming screen and disables remote", String.raw`
    const ble = await connectWithFakeBle();
    ble.chars.status.emit("BT connected");
    assertVisible(els.streamingView, [els.openingView, els.readyView, els.settingsView]);
    assert.strictEqual(els.playSongButton.disabled, true);
    assert.strictEqual(els.volumeRange.disabled, true);
  `],
  ["BT streaming initial status uses status-only connection", String.raw`
    const ble = await connectWithFakeBle({ status: "BT connected" });
    assert.strictEqual(state.connected, true);
    assert.strictEqual(state.statusOnlyConnection, true);
    assertVisible(els.streamingView, [els.openingView, els.readyView, els.settingsView]);
    assert.deepStrictEqual(ble.reads, ["status"]);
    assert.deepStrictEqual(ble.notifications, ["status"]);
    assertJsonEqual(payloadsWithoutIds(ble.writes.config), []);
    assert.strictEqual(els.playSongButton.disabled, true);
    assert.strictEqual(els.volumeRange.disabled, true);
  `],
  ["BT streaming status-only connection hydrates after BT disconnects", String.raw`
    const ble = await connectWithFakeBle({
      status: "BT connected",
      volume: 31,
      theme: "nature",
      config: { activeTheme: "nature", defaultTheme: "nature" }
    });
    ble.chars.status.emit("Idle");
    await waitUntil(() => state.connected && !state.statusOnlyConnection && !state.busy, "status-only hydration");
    assertVisible(els.readyView, [els.openingView, els.streamingView, els.settingsView]);
    assert.strictEqual(els.volumeValue.textContent, "31%");
    assert.strictEqual(els.themeCurrent.textContent, "Nature");
    assertJsonEqual(payloadsWithoutIds(ble.writes.config).map((payload) => payload.op), ["syncTime", "scanThemes"]);
    assert.deepStrictEqual(ble.notifications, ["status", "volume", "killswitch", "theme"]);
  `],
  ["remote playback buttons write command values", String.raw`
    const ble = await connectWithFakeBle();
    await els.playSongButton.click();
    await els.playAnimalButton.click();
    await els.stopButton.click();
    assertJsonEqual(ble.writes.command, [1, 2, 3]);
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
    assertJsonEqual(ble.writes.killswitch, [1]);
    assert.strictEqual(state.killswitch, true);
    assert.strictEqual(els.killswitchToggle.getAttribute("aria-checked"), "true");
    assert.strictEqual(els.quietCard.classList.contains("active"), true);
    await els.killswitchToggle.click();
    assertJsonEqual(ble.writes.killswitch, [1, 0]);
    assert.strictEqual(state.killswitch, false);
    assert.strictEqual(els.killswitchToggle.getAttribute("aria-checked"), "false");
  `],
  ["quiet-time toggle shows live countdown from status", String.raw`
    const ble = await connectWithFakeBle();
    ble.chars.status.emit("Killswitch active (9:32 left)");
    assert.strictEqual(els.quietCard.classList.contains("active"), true);
    assert.strictEqual(els.quietSub.textContent, "Paused · 9:32 left");
    assert.strictEqual(els.readyStatusText.textContent, "Quiet time (9:32 left)");
  `],
  ["settings screen loads config and content scans", String.raw`
    const ble = await connectWithFakeBle();
    await els.openSettingsButton.click();
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
    assertJsonEqual(payloadsWithoutIds(ble.writes.config).slice(-3), [
      { op: "getConfig" },
      { op: "scanThemes", page: 0 },
      { op: "scanSongs", theme: "lullabies", page: 0 }
    ]);
  `],
  ["returning to remote refreshes the device clock", String.raw`
    const ble = await connectWithFakeBle();
    assert.strictEqual(els.deviceWatch.textContent, "Toy clock 21:05");
    await els.openSettingsButton.click();
    await waitForSettingsLoaded();
    ble.config.bedtime.currentTime = "22:14";
    ble.config.bedtime.currentSecondOfDay = 80040;
    await els.settingsBackButton.click();
    await waitUntil(() => els.deviceWatch.textContent === "Toy clock 22:14", "device clock refresh");
    assertVisible(els.readyView, [els.openingView, els.streamingView, els.settingsView]);
    const syncPayloads = payloadsWithoutIds(ble.writes.config).filter((payload) => payload.op === "syncTime");
    assert.strictEqual(syncPayloads.length, 2);
  `],
  ["settings save writes config, theme, and song payloads", String.raw`
    const ble = await connectWithFakeBle();
    await els.openSettingsButton.click();
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
];

(async () => {
  for (const [name, source] of tests) {
    await runInApp(source);
    console.log(`ok - ${name}`);
  }
  console.log(`parent app UI tests passed (${tests.length})`);
})().catch((error) => {
  console.error(error);
  process.exit(1);
});

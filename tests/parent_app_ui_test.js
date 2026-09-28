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
    const data = typeof value === "number" ? uint8View(value) : textView(String(value));
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
    configResponse: new FakeCharacteristic("configResponse", JSON.stringify(response), readHooks),
    notice: new FakeCharacteristic("notice", "{}", readHooks),
    battery: new FakeCharacteristic("battery", options.battery ?? 1, readHooks)
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
    writes.killswitch.push(value[0]);
    chars.killswitch.value = value[0];
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
      if (remoteInitializationGate && characteristic.name !== "status") {
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
    publishConfigValues,
    device,
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

async function waitForSettingsLoaded() {
  await waitUntil(() => state.view === "settings" && state.settings.loading === false, "settings load");
}
`;

const tests = [
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
    assert.strictEqual(els.openSettingsButton.disabled, true);
    assert.deepStrictEqual(ble.reads, ["status"]);
    assert.deepStrictEqual(ble.notifications, ["status"]);

    ble.releaseRemoteInitialization();
    await waitUntil(() => !state.remoteInitializing, "deferred remote initialization");
    assert.strictEqual(els.readyView.getAttribute("aria-busy"), "false");
    assert.strictEqual(els.readyMessage.hidden, true);
    assert.strictEqual(els.playSongButton.disabled, false);
    assert.strictEqual(els.volumeRange.disabled, false);
    assert.strictEqual(els.openSettingsButton.disabled, false);
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
  ["connect requires both dedicated config characteristics", String.raw`
    for (const name of ["configCommand", "configResponse", ...CONFIG_ATTRIBUTES]) {
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
    assert.deepStrictEqual(ble.notifications, ["status", "configResponse", ...CONFIG_ATTRIBUTES, "volume", "killswitch", "theme", "notice", "battery"]);
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
  ["firmware loop events keep the indicator synchronized", String.raw`
    const ble = await connectWithFakeBle();
    ble.chars.notice.emit(JSON.stringify({ type: "loop", active: true }));
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
  ["prettifyName derives friendly names with zero-padded number stripping", String.raw`
    assert.strictEqual(prettifyName("twinkle_twinkle.wav"), "Twinkle Twinkle");
    assert.strictEqual(prettifyName("cow.wav"), "Cow");
    assert.strictEqual(prettifyName("01_twinkle.wav"), "Twinkle");
    assert.strictEqual(prettifyName("02 - lullaby.wav"), "Lullaby");
    assert.strictEqual(prettifyName("3 little pigs.wav"), "3 Little Pigs");
    assert.strictEqual(prettifyName("10.wav"), "10");
    assert.strictEqual(prettifyName("שיר_ערש.wav"), "שיר ערש");
    assert.strictEqual(prettifyName("Lullaby (slow).WAV"), "Lullaby (slow)");
    assert.strictEqual(isRtlText("שיר"), true);
    assert.strictEqual(isRtlText("Twinkle"), false);
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
  ["older firmware without battery state remains usable", String.raw`
    await connectWithFakeBle({ missingCharacteristics: ["battery"] });
    assert.strictEqual(state.connected, true);
    assert.strictEqual(state.battery, "unknown");
    assert.strictEqual(els.batteryWarning.hidden, true);
    assert.strictEqual(els.batteryIndicator.classList.contains("unknown"), true);
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
    assertJsonEqual(payloadsWithoutIds(ble.writes.config).slice(-2), [
      { op: "scanThemes", cursor: 0 },
      { op: "scanSongs", theme: "lullabies", cursor: 0 }
    ]);
  `],
  ["settings are cached for the session and not re-scanned on reopen", String.raw`
    const ble = await connectWithFakeBle();
    await els.openSettingsButton.click();
    await waitForSettingsLoaded();
    const scansAfterFirstOpen = payloadsWithoutIds(ble.writes.config)
      .filter((p) => p.op === "scanThemes" || p.op === "scanSongs").length;
    await els.settingsBackButton.click();
    await els.openSettingsButton.click();
    assert.strictEqual(state.settings.loading, false);
    assertVisible(els.settingsView, [els.openingView, els.readyView, els.streamingView]);
    const scansAfterReopen = payloadsWithoutIds(ble.writes.config)
      .filter((p) => p.op === "scanThemes" || p.op === "scanSongs").length;
    assert.strictEqual(scansAfterReopen, scansAfterFirstOpen, "reopening settings must not re-scan");
    assert(els.settingsSongList.children.length >= 1, "cached songs should still render");
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
  ["saving startup defaults preserves the remote volume and theme", String.raw`
    const ble = await connectWithFakeBle({ volume: 20 });
    chooseTheme("nature");
    await waitUntil(() => !state.busy && ble.config.activeTheme === "nature", "live theme change");
    await els.openSettingsButton.click();
    await waitForSettingsLoaded();
    await els.settingsVolumeRange.input("42");
    await els.settingsSaveButton.click();
    assert.strictEqual(ble.config.defaultVolumePct, 42);
    assert.strictEqual(state.volume, 20);
    assert.strictEqual(state.theme, "nature");

    await els.settingsBackButton.click();
    chooseTheme("lullabies");
    await waitUntil(() => !state.busy && ble.config.activeTheme === "lullabies", "second live theme change");
    await els.openSettingsButton.click();
    await waitForSettingsLoaded();
    state.settings.defaultTheme = "nature";
    await els.settingsDeviceName.input("SweetYaar Night");
    await els.settingsSaveButton.click();
    assert.strictEqual(ble.config.defaultTheme, "nature");
    assert.strictEqual(state.volume, 20);
    assert.strictEqual(state.theme, "lullabies");
    assertJsonEqual(ble.writes.volume, []);
    await els.settingsBackButton.click();
    assert.strictEqual(state.volume, 20);
    assert.strictEqual(state.theme, "lullabies");
  `],
  ["config.json load failure is shown in Settings", String.raw`
    const message = "Settings file is missing or invalid. Restore config.json on the SD card and restart the toy.";
    await connectWithFakeBle({ configFileError: message });
    assert.strictEqual(state.connected, true);
    assert.strictEqual(state.configError.message, message);
    await els.openSettingsButton.click();
    await waitForSettingsLoaded();
    assert.strictEqual(state.settings.message, message);
    assert.strictEqual(state.settings.sessionScanned, false);
  `],
  ["setTheme SD write failure surfaces error to app", String.raw`
    const ble = await connectWithFakeBle();
    await els.openSettingsButton.click();
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

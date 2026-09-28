"use strict";

// The child runs the production config handlers, JSON builders, persistence
// and Bedtime rules. Only its clock, SD backend and radio are substituted.
const { spawn } = require("node:child_process");
const { createInterface } = require("node:readline");
const { runInApp } = require("./parent_app_ui_test");
const firmware = spawn(process.argv[2], ["bridge"], { stdio: ["pipe", "pipe", "inherit"] });
const pending = [];
createInterface({ input: firmware.stdout }).on("line", (line) => {
  const next = pending.shift();
  if (next) next.resolve(JSON.parse(line));
});
firmware.on("exit", (code) => {
  for (const next of pending.splice(0)) next.reject(new Error(`Firmware test exited: ${code}`));
});
function firmwareRequest(command) {
  return new Promise((resolve, reject) => {
    pending.push({ resolve, reject });
    firmware.stdin.write(JSON.stringify(command) + "\n");
  });
}

runInApp(String.raw`
  const ble = await connectWithFakeBle();
  function deliver(batch) {
    for (let i = 0; i < CONFIG_ATTRIBUTES.length; ++i) {
      ble.chars[CONFIG_ATTRIBUTES[i]].value = JSON.stringify(batch.attributes[i]);
    }
    for (const index of batch.changed) ble.chars[CONFIG_ATTRIBUTES[index]].invalidate();
    ble.chars.volume.emit(batch.volume);
  }
  deliver(await firmwareRequest({ op: "snapshot" }));
  await refreshConfigAttributes({ replaceDraft: true });
  assert.strictEqual(state.bedtime.timeKnown, false);
  const mockWrite = ble.chars.configCommand.writeValueWithResponse.bind(ble.chars.configCommand);
  const commands = [];
  const notified = [];
  ble.chars.configCommand.writeValueWithResponse = async (value) => {
    const command = JSON.parse(textFromValue(value));
    commands.push(command);
    if (command.op.startsWith("scan")) return mockWrite(value);
    const batch = await firmwareRequest(command);
    notified.push(...batch.changed.map((i) => CONFIG_ATTRIBUTES[i]));
    deliver(batch); // State can notify before the write or ACK resolves.
    assertJsonEqual(Object.keys(batch.reply).sort(), ["id", "ok", "op"]);
    ble.chars.configResponse.emit(JSON.stringify({ ...batch.reply, id: command.id }));
  };
  await refreshDeviceClock();
  assert.strictEqual(state.bedtime.timeKnown, true);

  // Automatic transitions occur without any config request from the app.
  await firmwareRequest({ op: "advance", second: 12 * 3600, expireOverride: true }).then(deliver);
  await gattQueue;
  await toggleBedtimeMode();
  assert.strictEqual(state.bedtime.active, true);
  assert.strictEqual(state.bedtime.override, "on");
  assert.strictEqual(state.bedtime.effectiveVolumePct, 20);
  assert.strictEqual(state.bedtime.effectiveTheme, "lullabies");

  // Save sends only changed fields; actual firmware notifications drive state.
  await openSettings();
  await waitForSettingsLoaded();
  await els.settingsDeviceName.input("צעצוע");
  await els.settingsVolumeRange.input("41");
  state.settings.defaultTheme = "nature";
  await els.settingsNormalIdleSec.input("811");
  await els.settingsWakeIdleSec.input("91");
  await els.settingsBleIdleSec.input("101");
  await els.settingsBedtimeStartTime.input("19:30");
  await els.settingsBedtimeEndTime.input("07:30");
  await els.settingsBedtimeVolumeRange.input("17");
  state.settings.bedtimeTheme = "nature";
  const commandsBefore = commands.length;
  const notifiedBefore = notified.length;
  ble.reads.length = 0;
  await saveSettings();
  assertJsonEqual(commands.slice(commandsBefore).map((p) => p.op), ["setConfig"]);
  assertJsonEqual(ble.reads.slice().sort(),
    [...notified.slice(notifiedBefore), "configResponse"].sort());
  assert.strictEqual(state.settings.message, "Settings saved.");
  assert.strictEqual(state.settings.dirty, false);
  assert.strictEqual(state.deviceName, "צעצוע");
  assert.strictEqual(state.settings.originalDeviceName, "צעצוע");
  assert.strictEqual(state.settings.defaultVolumePct, 41);
  assert.strictEqual(state.settings.defaultTheme, "nature");
  assert.strictEqual(state.settings.sleepNormalIdleSec, 811);
  assert.strictEqual(state.settings.sleepVibrationWakeIdleSec, 91);
  assert.strictEqual(state.settings.sleepBleIdleSec, 101);
  assert.strictEqual(state.bedtime.startTime, "19:30");
  assert.strictEqual(state.bedtime.endTime, "07:30");
  assert.strictEqual(state.bedtime.theme, "nature");
  assert.strictEqual(state.bedtime.active, false); // schedule edit clears override
  assert.strictEqual(state.bedtime.override, "none");
  assert.strictEqual(state.theme, "nature");
  assert.strictEqual(state.volume, 20); // startup default doesn't change live volume
  state.view = "remote";
  render();

  const evening = await firmwareRequest({ op: "advance", second: 19 * 3600 + 30 * 60 });
  assert(evening.changed.includes(3), "Firmware must notify the scheduled boundary");
  deliver(evening);
  await gattQueue;
  await waitUntil(() => els.bedtimeTitle.textContent === "Bedtime", "scheduled bedtime display");
  assert.strictEqual(state.bedtime.active, true);
  assert.strictEqual(state.bedtime.autoActive, true);
  assert.strictEqual(state.bedtime.effectiveVolumePct, 17);
  assert.strictEqual(els.bedtimeTitle.textContent, "Bedtime");

  // Override expires into an already active schedule: active stays true, but
  // autoActive/override must still update in the app.
  deliver(await firmwareRequest({ op: "advance", second: 12 * 3600 }));
  await gattQueue;
  await toggleBedtimeMode();
  const boundary = await firmwareRequest({ op: "advance", second: 20 * 3600, expireOverride: true });
  assert(boundary.changed.includes(3));
  deliver(boundary);
  await gattQueue;
  assert.strictEqual(state.bedtime.active, true);
  assert.strictEqual(state.bedtime.override, "none");
  assert.strictEqual(state.bedtime.autoActive, true);

  deliver(await firmwareRequest({ op: "advance", second: 8 * 3600 }));
  await gattQueue;
  await waitUntil(() => els.bedtimeTitle.textContent === "Daytime", "scheduled daytime display");
  assert.strictEqual(state.bedtime.active, false);
  assert.strictEqual(state.bedtime.effectiveVolumePct, 20);
  assert.strictEqual(els.bedtimeTitle.textContent, "Daytime");
`, { firmwareRequest }).then(() => {
  console.log("Production firmware-to-app config updates passed");
}).catch((error) => {
  console.error(error);
  process.exitCode = 1;
}).finally(() => firmware.stdin.end());

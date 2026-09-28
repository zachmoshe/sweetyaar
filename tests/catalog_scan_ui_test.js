"use strict";

const fs = require("fs");
const { runInApp } = require("./parent_app_ui_test");
const transcript = JSON.parse(fs.readFileSync(0, "utf8"));

runInApp(String.raw`
  const ble = await connectWithFakeBle();
  const requests = [];
  ble.chars.configCommand.write = (value) => {
    const request = JSON.parse(textFromValue(value));
    assert.strictEqual(request.op, transcript.op);
    assert.strictEqual(request.page, requests.length);
    if (request.op === "scanSongs") assert.strictEqual(request.theme, transcript.theme);
    const page = transcript.pages[request.page];
    assert(page, "App requested a page past the terminal response");
    requests.push(request);
    // Replay real C++ serializer output; only replace the request correlation
    // ID, which this app session allocated independently of the host fixture.
    ble.chars.configResponse.emit(JSON.stringify({ ...page, id: request.id }));
  };
  const actual = transcript.op === "scanThemes"
    ? await fetchThemeScan()
    : await fetchSongScan(transcript.theme);
  assert.strictEqual(actual.length, transcript.expected.length,
    "App scan returned " + actual.length + " of " + transcript.expected.length + " entries");
  assert.strictEqual(requests.length, transcript.pages.length,
    "App must follow hasMore through the final firmware page");
  const key = transcript.op === "scanThemes" ? "id" : "file";
  const byId = new Map(actual.map((row) => [row[key], row]));
  assert.strictEqual(byId.size, actual.length, "App scan duplicated entries");
  for (const expected of transcript.expected) {
    const row = byId.get(expected[key]);
    assert(row, "Missing entry " + expected[key]);
    for (const [field, value] of Object.entries(expected)) {
      assert.strictEqual(row[field], value, expected[key] + ": " + field);
    }
  }
`, { transcript }).then(() => {
  console.log("Firmware-to-app scan transcript passed");
}).catch((error) => {
  console.error(error);
  process.exitCode = 1;
});

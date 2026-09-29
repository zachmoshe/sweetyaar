# SweetYaar Test Suite Map

All automated regression tests are collected by pytest from this directory.
Run the full suite from the repo root or any worktree with:

```bash
uv run python -m pytest
```

If the venv is active, `pytest` is equivalent.

## Layout

- `conftest.py`: shared `repo_root` fixture.
- `helpers.py`: subprocess helpers and PlatformIO discovery.
- `test_firmware_config.py`: static checks for checked-in SD-card templates and app-owned config defaults.
- `test_firmware_build.py`: no-device firmware build checks through PlatformIO.
- `test_audio_handoff.py`: runs the production state-entry handler with the
  installed WAV decoder and volume stream. Checks repeated 48/44.1 kHz Bluetooth
  sessions restore the local format while muted, including return via Quiet time
  and immediate song/animal playback.
- `test_ble_transport.py`: executes production BLE response methods and the
  playback callback on the host; config replies must preserve the theme list,
  and playback commands must not accept JSON settings requests.
- `test_json_file.py`: runs the real JSON save/load code against a fake SD card
  with injected open, short-write, flush-truncation, removal, and rename failures.
  Checks read/save/reload with a WAV handle held open under the two-file limit.
  Uses the pinned ArduinoJson headers installed by `make build`.
- `test_config_reply_memory.py`: denies ArduinoJson pool allocations while
  executing the production acknowledgment and config-state serializers; checks
  complete values and correct escaping for all five state groups.
- `test_state_machine.py`: pytest wrapper that compiles and runs native C++ state-machine tests.
- `test_charger_status.py`: tests the pure charger status interpretation and the real charger driver against scripted I2C/GPIO inputs, including completion versus host disable, stale samples after enable changes, separate event logs, polling/interrupts, read failure/recovery, simultaneous app conditions, latest-read timeout and overcurrent indications, and binary snapshot encoding.
- `state_machine_native_test.cpp`: host-side C++ behavior tests for the real `firmware/esp32/src/StateMachine.cpp`.
- `native_stubs/`: tiny Arduino/FreeRTOS headers used only by native host tests.
- `test_parent_app.py`: pytest wrapper for the parent-app UI regression runner.
- `parent_app_ui_test.js`: fake DOM plus fake Web Bluetooth/GATT tests for `app/public/index.html`.
  Charger cases cover battery navigation, live activity/condition strings, warning/error border priority independent of battery level, all condition severities, malformed/failed reads and refresh recovery, unavailable diagnostics, and stale callbacks after disconnect. `test_ble_transport.py` also checks the complete six-byte notification and change-only publishing.
- `test_catalog_pagination.py`: compiles the production catalog serializers and
  checks page size, complete traversal, packing efficiency, and consumption by
  the real app's scan functions. `catalog_scan_native_test.cpp` supplies the RAM
  catalog; `catalog_scan_ui_test.js` replays the resulting firmware JSON through
  the app's Bluetooth test harness.

Pytest only discovers `test_*.py` files directly. The `.js`, `.cpp`, and
`native_stubs/` files are support programs used by those Python test wrappers.

## Current Tests

- `test_firmware_config.py`: checks the SD-card template, board-specific polarity overrides, and the default status-LED brightness setting.
- `test_firmware_build.py::test_sweetyaar_firmware_build`: builds the production and generic PlatformIO environments and expects each real-app firmware build to succeed; generic includes the current RGBW bench-LED override.
- `test_state_machine.py::test_state_machine_native_transitions`: compiles the real state machine on the host and runs the C++ scenarios in `state_machine_native_test.cpp`.
- `test_state_machine.py::test_sleep_entry_check_native_rules`: checks the 500 ms vibration observation window, quiet/moving/open inputs, cancellation, repeated attempts, and timer wraparound.
- `state_machine_native_test.cpp::testLocalPlaybackTransitions`: verifies idle/local playback transitions for song, animal, and stop events.
- `state_machine_native_test.cpp::testBtStreamingIgnoresLocalControls`: verifies that local play/stop controls do not change state while Classic BT streaming is active.
- `state_machine_native_test.cpp::testKillswitchTimerAndBtInterruption`: verifies killswitch state, timeout behavior, and BT interruption rules.
- `state_machine_native_test.cpp::testKillswitchCancel`: verifies that a second killswitch event cancels the active pause mode.
- `state_machine_native_test.cpp::testBlePayloadEventsDoNotForceTransitions`: verifies BLE volume/theme payloads are stored as pending values without forcing playback transitions.
- `state_machine_native_test.cpp::testSongLoopModeRules`: verifies loop-mode enable/disable and that animal playback, stop, and BT connect each clear loop mode.
- `test_parent_app.py::test_parent_app_save_flow`: runs the Node UI regression runner against the real script embedded in `app/public/index.html`.
- `parent_app_ui_test.js::initial opening screen is usable`: checks the first screen, connect button state, and visible copy.
- `parent_app_ui_test.js::connect success shows ready remote`: simulates a successful Web Bluetooth connection and checks the ready remote state.
- `parent_app_ui_test.js::connect opens remote before controls finish loading`: verifies that status alone opens the Ready screen while background BLE hydration keeps controls disabled.
- `parent_app_ui_test.js::connect cancel stays on opening screen`: simulates user cancellation from the browser device chooser.
- `parent_app_ui_test.js::missing BLE service asks for firmware upgrade`: simulates an incompatible firmware GATT shape and checks the upgrade message.
- `parent_app_ui_test.js::BT streaming status shows streaming screen and disables remote`: simulates a BT streaming status notification and verifies local controls are disabled.
- `parent_app_ui_test.js::remote playback buttons write command values`: checks play song, play animal, and stop BLE command writes.
- `parent_app_ui_test.js::remote theme picker writes selected theme`: checks theme picker rendering and BLE theme writes.
- `parent_app_ui_test.js::killswitch buttons write optimistic values`: checks pause-mode on/off BLE writes and local optimistic UI state.
- `parent_app_ui_test.js::settings screen loads config and content scans`: checks settings load, config fields, theme scan, and song scan handling.
- `parent_app_ui_test.js::settings save writes config, theme, and song payloads`: writes every config field plus theme/song edits and verifies the fake GATT payloads.

## Where To Add Tests

- Add app config template/default checks to `test_firmware_config.py`; avoid tests that only prove Python can mutate a dict.
- Add firmware compile checks to `test_firmware_build.py` and mark them with `@pytest.mark.firmware`.
- Add pure state-machine behavior to `state_machine_native_test.cpp`; update `test_state_machine.py` only when the host compile command changes.
- Add parent-app behavior to `parent_app_ui_test.js`; keep `test_parent_app.py` as the thin pytest wrapper.
- Put shared subprocess and PlatformIO helpers in `helpers.py`.

For deterministic scan API tests against `content/sd-card-template`, prefer a future
native scanner test with a fake filesystem/SD layer around the firmware scanner.
Do not rely on the inserted SD card for CI-like tests, and do not reimplement
the scanner in Python just to inspect the template.

## Useful Filters

Catalog pagination acceptance tests:

```bash
uv run python -m pytest tests/test_catalog_pagination.py
```

The legal-page/completeness tests exercise empty catalogs, page boundaries,
larger catalogs, different page sizes, UTF-8 names, JSON escaping, disabled or
invalid content, and wide numeric fields. Expected rows are checked field by
field, with no missing or duplicate entries. The app receives the actual C++
serializer output; only request IDs are rebound to its connection's requests.

The packing tests enforce pagination's byte budget:
adjacent pages must not fit together in one response envelope, and a nonfinal
page must not have room for the next entry. App traversal cases with 81 themes
and 601 songs check that scanning reaches the end without fixed page-count limits.
This host bridge does not exercise the BLE radio, negotiated MTU or OS cache.

```bash
# Fast local loop without a PlatformIO build.
uv run python -m pytest -m "not firmware"

# Complete suite, including all firmware build variants.
make test
```

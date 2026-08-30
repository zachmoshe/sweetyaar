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
- `test_state_machine.py`: pytest wrapper that compiles and runs native C++ state-machine tests.
- `state_machine_native_test.cpp`: host-side C++ behavior tests for the real `firmware/esp32/src/StateMachine.cpp`.
- `native_stubs/`: tiny Arduino/FreeRTOS headers used only by native host tests.
- `test_parent_app.py`: pytest wrapper for the parent-app UI regression runner.
- `parent_app_ui_test.js`: fake DOM plus fake Web Bluetooth/GATT tests for `app/public/index.html`.

Pytest only discovers `test_*.py` files directly. The `.js`, `.cpp`, and
`native_stubs/` files are support programs used by those Python test wrappers.

## Current Tests

- `test_firmware_config.py::test_sd_template_has_versioned_sleep_config`: checks that `content/sd-card-template/config.json` has schema version 2, the expected defaults, and all sleep config fields.
- `test_firmware_build.py::test_sweetyaar_firmware_build`: runs PlatformIO's default `sweetyaar` environment and expects a successful real-app firmware build.
- `test_state_machine.py::test_state_machine_native_transitions`: compiles the real state machine on the host and runs the C++ scenarios in `state_machine_native_test.cpp`.
- `state_machine_native_test.cpp::testLocalPlaybackTransitions`: verifies idle/local playback transitions for song, animal, and stop events.
- `state_machine_native_test.cpp::testBtStreamingIgnoresLocalControls`: verifies that local play/stop controls do not change state while Classic BT streaming is active.
- `state_machine_native_test.cpp::testKillswitchTimerAndBtInterruption`: verifies killswitch state, timeout behavior, and BT interruption rules.
- `state_machine_native_test.cpp::testKillswitchCancel`: verifies that a second killswitch event cancels the active pause mode.
- `state_machine_native_test.cpp::testBlePayloadEventsDoNotForceTransitions`: verifies BLE volume/theme payloads are stored as pending values without forcing playback transitions.
- `test_parent_app.py::test_parent_app_save_flow`: runs the Node UI regression runner against the real script embedded in `app/public/index.html`.
- `parent_app_ui_test.js::initial opening screen is usable`: checks the first screen, connect button state, and visible copy.
- `parent_app_ui_test.js::connect success shows ready remote`: simulates a successful Web Bluetooth connection and checks the ready remote state.
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

```bash
# Fast local loop without a PlatformIO build.
uv run python -m pytest -m "not firmware"

# Complete suite, including the production firmware build.
make test
```

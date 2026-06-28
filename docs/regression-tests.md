# SweetYaar Regression Tests

SweetYaar has two regression layers:

- Local non-hardware tests that run on a laptop and do not need an ESP32.
- Real-device smoke tests that upload or connect to the ESP32 and verify Bluetooth, BLE, SD config, and sleep behavior.

## Local Non-Hardware Regression Suite

Install the pytest dependency once:

```bash
/Users/zmoshe/proj/sweetyaar/.venv/bin/python -m pip install -r requirements-dev.txt
```

Then run this from the repo root or from a Git worktree:

```bash
/Users/zmoshe/proj/sweetyaar/.venv/bin/python -m pytest
```

If the venv is active, plain `pytest` is equivalent. The command runs:

- Python config-contract tests for the checked-in `SD:/config.json` template.
- A pytest-backed mocked Web Bluetooth parent-app UI test against `docs/index.html`.
- PWA manifest, icon, service-worker, and offline shell contract checks.
- A pytest-backed native C++ unit test that compiles the real `src/StateMachine.cpp` with Arduino/FreeRTOS stubs.
- A pytest firmware-build test that runs `pio run -e esp32dev`.
- Real-device smoke tests that are collected and reported as skipped when their hardware prerequisites are missing.

For a faster loop while editing tests:

```bash
/Users/zmoshe/proj/sweetyaar/.venv/bin/python -m pytest -m "not firmware and not hardware"
```

## Real-Device Smoke Tests

Use these after BT, BLE, I2S, state-machine, SD-card config, or sleep changes.

When the ESP32 is connected over USB, run the pytest-collected hardware tests
with the same command:

```bash
/Users/zmoshe/proj/sweetyaar/.venv/bin/python -m pytest --bt-address 40-22-D8-3D-8A-22 --device-name SweetYaar
```

If no ESP32 USB serial device is connected, each hardware test reports as
skipped instead of failing. When USB is present, the hardware tests first pulse
the ESP32 reset line through the serial adapter and wait briefly for the real
app firmware to boot, so a sleeping toy gets a chance to start advertising BLE
before the test decides to skip.

The hardware tests cover:

- Classic BT connect/audio route/audio start through `tools/mac_bt_smoke_test.py`.
- BLE connection, basic controls, config scan, and reversible config persistence through `tools/ble_gatt_probe.py`.

The standalone `vibsleep` firmware is intentionally **not** part of pytest,
because uploading it replaces the real app firmware and stops BLE advertising.
Run it only as a focused manual hardware check:

If macOS Bluetooth privacy blocks `blueutil`, run pytest from Terminal so
Terminal owns Bluetooth permission.

The BLE round-trip test writes temporary device name, default volume, default
theme, and sleep thresholds through the same config API used by the parent app,
verifies that `getConfig` sees them, then restores the original values.

The underlying commands remain available for focused manual runs:

```bash
/Users/zmoshe/proj/sweetyaar/.venv/bin/python tools/mac_bt_smoke_test.py --env esp32dev --bt-address 40-22-D8-3D-8A-22 --device-name SweetYaar
/Users/zmoshe/proj/sweetyaar/.venv/bin/python tools/ble_gatt_probe.py --name SweetYaar --control-smoke-test --config-api-test --config-round-trip-test
/Users/zmoshe/proj/sweetyaar/.venv/bin/pio run -e vibsleep -t upload
```

After a `vibsleep` manual run, re-upload `esp32dev` before running BLE or Classic
BT smoke tests. For vibration sleep, confirm in serial logs that the device
enters deep sleep, wakes from `EXT0`, and keeps the peripheral load switch
RTC-held off while asleep.

The standalone diagnostic firmware images drive GPIO13 HIGH while awake, so
`sdtest`, `audiotest`, `bttest`, and `vibsleep` can be used without bypassing
the active-HIGH load switch on the SD + amp rail.

The legacy wrapper also delegates to pytest:

```bash
/Users/zmoshe/proj/sweetyaar/.venv/bin/python tools/run_regression_tests.py
```

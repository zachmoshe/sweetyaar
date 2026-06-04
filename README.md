# SweetYaar

SweetYaar is an ESP32-WROOM-32 baby toy audio controller. The current codebase
is a PlatformIO/Arduino C++ firmware project with:

- Bluetooth Classic A2DP speaker support.
- BLE parent controls and settings over a single-page Web Bluetooth app.
- SD-card WAV playback for songs and animal sounds.
- Configurable content metadata, sleep-mode behavior, and planned Bedtime mode.
- Hardware notes and KiCad design files for the prototype PCB.

## Repository History

This repository has three useful history points:

- `main`: the current ESP32/PlatformIO firmware, Web Bluetooth parent remote,
  SD-card content template, sleep-mode work, and PCB prototype files.
- `v1.0`: the previous MicroPython-era implementation that used to be the
  remote `main` branch.
- `v0.0`: an older educational snapshot that used to be named `v1.0`.

To inspect the previous implementation:

```bash
git fetch origin
git switch v1.0
```

To inspect the older educational snapshot:

```bash
git switch v0.0
```

To return to the current codebase:

```bash
git switch main
```

## Development Setup

Use the project virtual environment for PlatformIO:

```bash
/Users/zmoshe/proj/sweetyaar/.venv/bin/pio run -e esp32dev
```

The main PlatformIO environments are:

- `esp32dev`: current application firmware.
- `btdebug`: application firmware with extra Classic BT/A2DP logging.
- `vibsleep`: standalone vibration wake and deep-sleep test firmware.

Useful commands:

```bash
/Users/zmoshe/proj/sweetyaar/.venv/bin/pio run -e esp32dev
/Users/zmoshe/proj/sweetyaar/.venv/bin/pio run -e btdebug
/Users/zmoshe/proj/sweetyaar/.venv/bin/pio run -e vibsleep
```

## Regression Tests

Install the test runner once:

```bash
/Users/zmoshe/proj/sweetyaar/.venv/bin/python -m pip install -r requirements-dev.txt
```

Run the standard regression suite:

```bash
/Users/zmoshe/proj/sweetyaar/.venv/bin/python -m pytest
```

If the venv is activated, plain `pytest` is equivalent. Real-device smoke tests
are collected by pytest; if the ESP32 USB serial device is missing, those
specific tests skip with a USB prerequisite message. If USB is present, pytest
resets the ESP32 before BLE smoke checks so a sleeping toy can wake and
advertise before the test decides whether to skip.

See `docs/regression-tests.md` for coverage details and hardware options.

## Project Layout

- `src/`: firmware source and diagnostic/test entry points.
- `tests/`: pytest regression suite, including host tests and real-device smoke tests.
- `docs/`: Web Bluetooth parent remote.
- `sd_card_template/`: expected SD-card folder structure, metadata, and config.
- `tools/`: local Bluetooth/BLE smoke and probe helpers.
- `esp32_prototype_board/`: PCB design files, manufacturing outputs, and notes.
- `project-plan.md`: detailed architecture and hardware planning notes.
- `docs/bedtime-mode.md`: product and UX spec for Bedtime mode.
- `breadboard-wiring.md`: breadboard wiring reference.

## Hardware Target

The firmware targets the original ESP32-WROOM-32. This matters because the toy
uses Bluetooth Classic A2DP, which is not available on ESP32-S3/C3/C6 variants.

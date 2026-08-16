# SweetYaar

SweetYaar is an ESP32-WROOM-32 baby toy audio controller. The current codebase
is a PlatformIO/Arduino C++ firmware project with:

- Bluetooth Classic A2DP speaker support.
- BLE parent controls and settings over a single-page Web Bluetooth app.
- SD-card WAV playback for songs and animal sounds.
- Configurable content metadata, sleep-mode behavior, and Bedtime mode.
- Hardware planning notes for the prototype and final PCB.

## Repository History

This repository has three useful history points:

- `main`: the current ESP32/PlatformIO firmware, Web Bluetooth parent remote,
  SD-card content template, sleep-mode work, and hardware planning artifacts.
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
/Users/zmoshe/proj/sweetyaar/.venv/bin/pio run -e sweetyaar
```

The only PlatformIO environment is `sweetyaar`, which builds the complete
application firmware:

```bash
/Users/zmoshe/proj/sweetyaar/.venv/bin/pio run -e sweetyaar
```

## Regression Tests

Create or update the project environment:

```bash
uv sync
```

Run the standard regression suite:

```bash
uv run python -m pytest
```

The `dev` dependency group is installed by default and locked in `uv.lock`. If
the venv is activated, plain `python -m pytest` is equivalent. Real-device smoke
tests are collected by pytest; if the ESP32 USB serial device is missing, those
specific tests skip with a USB prerequisite message. If USB is present, pytest
resets the ESP32 before BLE smoke checks so a sleeping toy can wake and
advertise before the test decides whether to skip.

See [`docs/firmware.md`](docs/firmware.md) for firmware behavior, architecture,
build instructions, and test coverage.

## Project Layout

- `src/`: production firmware source.
- `tests/`: pytest regression suite, including host tests and real-device smoke tests.
- `public/`: deployable Web Bluetooth parent remote PWA.
- `docs/`: one guide each for firmware, the mobile app, and hardware.
- `sd_card_template/`: expected SD-card folder structure, metadata, and config.
- `tools/`: local Bluetooth/BLE smoke and probe helpers.
- `project-plan.md`: detailed architecture and hardware planning notes.
- [`docs/firmware.md`](docs/firmware.md): device behavior, firmware components,
  build instructions, regression tests, and device smoke tests.
- [`docs/mobile-app.md`](docs/mobile-app.md): parent remote behavior, design
  assets, Bedtime mode, offline support, deployment, and app tests.
- [`docs/hardware.md`](docs/hardware.md): system architecture, DevKit wiring,
  production power design, safety requirements, and bring-up checks.

## Hardware Target

The firmware targets the original ESP32-WROOM-32. This matters because the toy
uses Bluetooth Classic A2DP, which is not available on ESP32-S3/C3/C6 variants.

The current hardware plan uses GPIO13/`PERIPH_PWR_EN` as the shared active-HIGH
enable for the 3.3 V peripheral load switch and the 5 V peripheral boost. The
real app enables both branches during boot, then drives and RTC-holds GPIO13 LOW
before deep sleep; see
[`docs/hardware.md`](docs/hardware.md) for the AP2281-3WG-7 SD switch, 5 V amp
boost, required common ground, and shared-enable pulldown.

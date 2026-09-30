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

Create or refresh the root development environment:

```bash
make setup
```

The root `Makefile` is the common entry point for project tasks. Run `make help`
to list every command. The most common ones are:

```bash
make app            # Serve the parent app at http://localhost:8000/
make build          # Build the complete ESP32 firmware
make flash          # Build and upload to a connected ESP32
make monitor        # Open the serial monitor
make flash-monitor  # Flash, then monitor
make test           # Run the regression suite
```

Targets are intentionally thin wrappers around the component tools and can be
extended in `Makefile`. Variables can be overridden per invocation, for example
`make app APP_PORT=8080` or
`make monitor SERIAL_PORT=/dev/cu.SLAB_USBtoUART`.

## Regression Tests

Run the standard regression suite:

```bash
make test
```

The `dev` dependency group is installed by default and locked in `uv.lock`. If
the venv is activated, plain `python -m pytest` is equivalent.

See [`docs/engineering/firmware.md`](docs/engineering/firmware.md) for firmware behavior, architecture,
build instructions, and test coverage.

## Project Layout

- `firmware/esp32/`: PlatformIO project and production firmware source.
- `hardware/mainboard/`: production KiCad mainboard project and revision releases.
- `hardware/libraries/`: repository-owned KiCad symbols, footprints, and 3D models.
- `hardware/mechanical/enclosure/`: enclosure CAD and mechanical drawings.
- `hardware/references/`: hardware datasheet and application-note index.
- `tests/`: host-side pytest, native C++, app, and firmware-build regression tests.
- `app/`: the deployable Web Bluetooth parent remote and editable design assets.
- `docs/engineering/`: firmware, app, and hardware engineering guides.
- `docs/assets/`: shared engineering-documentation images and diagrams.
- `content/sd-card-template/`: expected SD-card folder structure, metadata, and config.
- `tools/`: future standalone development and maintenance utilities.
- [`docs/overview.md`](docs/overview.md): high-level project overview and design history.
- [`docs/engineering/firmware.md`](docs/engineering/firmware.md): device behavior, firmware components,
  build instructions, and regression tests.
- [`docs/engineering/mobile-app.md`](docs/engineering/mobile-app.md): parent remote behavior, design
  assets, Bedtime mode, offline support, deployment, and app tests.
- [`docs/engineering/hardware.md`](docs/engineering/hardware.md): system architecture, DevKit wiring,
  production power design, safety requirements, and bring-up checks.

## Hardware Target

The firmware targets the original ESP32-WROOM-32. This matters because the toy
uses Bluetooth Classic A2DP, which is not available on ESP32-S3/C3/C6 variants.

The current hardware plan uses GPIO13/`PERIPH_PWR_EN` as the shared active-HIGH
enable for the 3.3 V peripheral load switch and the 5 V peripheral boost. The
real app enables both branches during boot, then drives and RTC-holds GPIO13 LOW
before deep sleep; see
[`docs/engineering/hardware.md`](docs/engineering/hardware.md) for the AP2281-3WG-7 SD switch, 5 V amp
boost, required common ground, and shared-enable pulldown.

The production status indicator is a single **WS2812B-V6 (LCSC C52917433)**,
a 5050 SMD addressable RGB LED on `5V_PERIPH_SW`. GPIO2 drives `DIN` directly
through the 330 Ω `R_LED_DIN1` series resistor (LCSC C23138); the LED interface
has no MMBT3904 stage or 5 V pull-up. The `sweetyaar` environment explicitly
selects non-inverted RMT output (`SWEETYAAR_STATUS_LED_DATA_INVERTED=0`) and
24-bit GRB data (`SWEETYAAR_STATUS_LED_RGBW=0`,
`SWEETYAAR_STATUS_LED_COLOR_ORDER_GRB=1`). The `sweetyaar-generic` environment
retains the directly wired 32-bit RGBW/SK6812-style bench LED with non-inverted
data and GRBW channel order. GPIO16 and GPIO17 carry BQ25186 charger I2C SDA
and SCL, respectively. A controller-wide brightness setting scales every
available color channel and currently defaults to 50% pending enclosure testing.

# SweetYaar Agent Notes

SweetYaar is a battery-powered ESP32-WROOM-32 audio toy for the inside of a
doll: two child buttons play songs and animal sounds from a microSD card, the
same device is a Classic Bluetooth A2DP speaker, and a BLE/Web Bluetooth parent
remote controls it. Read [docs/overview.md](docs/overview.md) first.

## Source of truth

Behavior and design are documented in `docs/`; keep those documents, not this
file, as the specification, and update them in the same change as the code or
design they describe.

- [Firmware](docs/engineering/firmware.md): behavior, Bluetooth policy, sleep,
  status LED, build/flash/test, BLE deployment checklist.
- [Hardware](docs/engineering/hardware.md): power tree, pin map, PCB, charger,
  enclosure interfaces, bring-up. The KiCad design under `hardware/` is the
  truth when it and the document disagree; `firmware/esp32/src/Config.h` is the
  truth for pins and timings.
- [Mobile app](docs/engineering/mobile-app.md): parent remote, PWA, deployment.
- `docs/engineering/*-validation.md` are records of real-device investigations
  and may describe superseded states; each says what has since changed.

## Implementation isolation

For every agent-initiated implementation in any chat, create a separate Git
worktree and a new `codex/...` branch before editing files, unless the user
explicitly says to reuse an existing branch or worktree (or to work on `main`).

## Environment and commands

- Repo root: `/Users/zmoshe/proj/sweetyaar`. Run commands from there.
- Use the project venv (`make setup` / `uv sync` creates it):
  `.venv/bin/pio` and `.venv/bin/python`. `pio` is not on `PATH`; the
  ESP32 toolchain is cached under `~/.platformio/packages`, and the first build
  of a fresh checkout clones the pinned `lib_deps` from GitHub (network needed).
- `make help` lists targets. Common ones: `make build`, `make flash`,
  `make monitor`, `make app`, `make test` (everything), `make test-unit`
  (host only, never touches hardware), `make animals` (build SD-card animal WAVs from `content/animal-sounds`),
  `make test-device` (approved real-device
  run; needs `DEVICE_TEST_APPROVED=1`, `PIO_ENV` and `SERIAL_PORT`).
- PlatformIO environments (in `firmware/esp32/platformio.ini`):
  - `sweetyaar`: production PCB (default).
  - `sweetyaar-generic`: the generic prototype board (active-HIGH amp mute via
    an inverting transistor, RGBW bench LED, no BQ25186).
  Confirm which board is connected before flashing, and pass `PIO_ENV=...`.
- Shell sandboxes may be unable to write `~/Library/Caches/uv` or open serial
  ports; that is an environment restriction, not a project fault.

## Editing and test discipline

- Use `apply_patch` for manual edits.
- Keep edits scoped; this project has a lot of hardware-state coupling.
- Two test layers: `make test-unit` (host pytest, native C++ and app tests) and
  `make test-device` (real hardware).
- Obtain explicit user approval before each hardware test session (including
  flashing). Approval for a session covers its necessary scenario attempts and
  fixes/retests; it does not authorize a later unrelated flash/test session.
- Capture flash, serial and host Bluetooth logs, and report passed, failed and
  untested flows separately. Never describe a build or mocked test as hardware
  validation.
- Real takeover and source-contention tests need two independent Bluetooth
  devices. Two clients on one Mac share the same Bluetooth identity.
- After firmware changes run at least `make build`. After BT, BLE, I2S, memory
  or state-machine changes, verify the relevant connection and audio behavior on
  the real device: connection, audio routing, `Audio state: STARTED`, and no
  crash/reboot. A successful compile proves none of that.
- Bluetooth memory is tight (see "Bluetooth memory budget" in firmware.md). Keep the A2DP queue at 8 KB and I2S at six
  512-frame DMA buffers, with the SD mount limited to two file slots; twelve DMA
  buffers caused a real Bluedroid allocation failure when encrypted BLE
  connected during Classic audio. Repeat coexistence and audio tests before
  increasing any reservation or BLE payload.

## Bluetooth traps (details in firmware.md)

- Classic Just Works lives in `ClassicBluetooth.cpp`, pinned to ESP-IDF 4.4.7.
  Keep `-Wl,--wrap=BTA_DmConfirm`; do not use `BTA_DM_CONN_PAIRED`, whose filter
  excludes Just Works keys. Revalidate its private ABI before any SDK upgrade.
- Pairing is bond-only. Do not reintroduce separate persistent approval lists,
  and do not replace the persisted `clearPending` bond reset with
  fire-and-forget asynchronous bond removal.
- On bonded Mac reconnects, BLE GAP AUTH can arrive before GATTS CONNECT.
  Preserve the result (metadata only, bounded lifetime, no keys) until the peer
  exists, apply the normal checks, and do not delete its bond.
- Android may need one encrypted status read to start bonding. While approval is
  pending but the encrypted read was admitted, reject application access with
  insufficient authorization (0x08), never insufficient authentication (0x05),
  or Android shows a duplicate pairing request. Never enable controls before
  approval completes.
- Never log keys or passcodes, and add no per-packet or per-loop logging during
  audio.

## Hardware lessons

- Bench setup: ESP32 on stable external 5 V with a data-capable USB cable for
  serial; common ground between supply, ESP32, SD module and amp. A power-only
  cable or hub causes confusing monitor/reset behavior, and a long USB power
  path sagged to about 4.2 V and caused brownouts.
- Some blue microSD breakouts were flaky (MISO stuck low or changing when the
  card moved, raw SPI returning `0xFF`). Replacing the board fixed it. Healthy
  diagnostics: idle MISO high, raw CMD0 response `0x01`, CMD8 response `0x01`
  with `00 00 01 AA`, and `SD.begin` listing the root directory.
- macOS writes `._*` and `.DS_Store` onto cards; firmware ignores them silently
  and must skip invalid or tiny WAVs without getting stuck.
- A bigger speaker exposes scratches and glitches more easily: suspect
  power, wiring, current or load before changing codec logic.
- Phone streaming sounded clean; Mac streaming had regular small gaps with high
  retransmits in macOS Bluetooth logs. Use a phone for subjective audio checks.
- The Classic BT address is printed at boot (`[BT] Classic BT address: ...`);
  never hard-code it. macOS may keep showing the cached name `SweetYaar Remote`.
- Pin assignments, the power tree, the switched-rail sequencing, current
  budgets and the status-LED electrical interface are in hardware.md; the
  user cannot rework SMD parts, so verify footprints and polarity before PCBA.
- The prototype draws about 200–250 mA at 5 V in playback; use 500 mA as a
  preliminary high bound until Bluetooth streaming with a 4 Ω speaker at full
  volume is measured, with extra transient margin for the power path. The
  current cell is 3400 mAh; about 2000 mAh is probably enough if runtime and
  packaging tests confirm it.
- On the generic prototype board GPIO13 only drives an indicator LED, so the SD
  card and amp stay powered in sleep and its sleep current is not representative.

## Content and app notes

- WAVs are 44.1 kHz, 16-bit PCM, mono or stereo. Keep the shared I2S output
  stereo (`WavPcmOutput` duplicates mono) and verify mono/stereo transitions and
  BT-to-local handoff after audio changes.
- Local volume applies to WAV playback only; never call A2DP volume APIs for it.
- Keep the BLE theme-list payload and every config JSON value within the 512-byte
  cap, and commands within 383 bytes.
- Changing the BLE contract needs matching firmware and app, a bump of
  `CACHE_VERSION` in `app/public/sw.js`, and the BLE deployment checklist in
  firmware.md.

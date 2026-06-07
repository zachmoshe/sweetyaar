# SweetYaar Agent Notes

These notes capture the current working setup and the debugging lessons from the
ESP32 bring-up. Future agents should read this before touching firmware,
Bluetooth, SD-card, or hardware-test workflows.

## Implementation Isolation

- For every agent-initiated implementation in any chat, create a separate Git
  worktree and a new `codex/...` branch before editing files, unless the user
  explicitly says to reuse an existing branch or worktree.

## Project Environment

- Repo root: `/Users/zmoshe/proj/sweetyaar`
- Use the project venv for PlatformIO and Python tools:
  - `/Users/zmoshe/proj/sweetyaar/.venv/bin/pio`
  - `/Users/zmoshe/proj/sweetyaar/.venv/bin/python`
- Main PlatformIO environments:
  - `esp32dev`: real application firmware.
  - `btdebug`: debug firmware with extra Classic BT/A2DP event logging.
  - `vibsleep`: standalone vibration wake/deep-sleep test firmware.
- Common commands:
  - Build real app: `/Users/zmoshe/proj/sweetyaar/.venv/bin/pio run -e esp32dev`
  - Upload real app: `/Users/zmoshe/proj/sweetyaar/.venv/bin/pio run -e esp32dev -t upload`
  - Build BT debug app: `/Users/zmoshe/proj/sweetyaar/.venv/bin/pio run -e btdebug`
  - Upload BT debug app: `/Users/zmoshe/proj/sweetyaar/.venv/bin/pio run -e btdebug -t upload`
  - Build vibration sleep test: `/Users/zmoshe/proj/sweetyaar/.venv/bin/pio run -e vibsleep`
  - Upload vibration sleep test: `/Users/zmoshe/proj/sweetyaar/.venv/bin/pio run -e vibsleep -t upload`
- The shell may not see this directory as a Git repository. Do not rely on
  `git diff` being available unless you verify it first.

## Hardware Known-Good Setup

- ESP32 is powered by stable external 5V, with USB connected for data/serial.
- USB cable must be a data cable. A power-only hub/cable caused earlier monitor
  and reset confusion.
- Common ground is required between external 5V supply, ESP32, SD module, and
  audio amp.
- MAX98357A amp wiring:
  - `BCLK -> GPIO26`
  - `LRC/WS -> GPIO25`
  - `DIN -> GPIO22`
  - `SD_MODE / enable -> GPIO21`
  - `VIN -> 5V`, `GND -> common GND`
- SD card SPI wiring:
  - `CS -> GPIO5`
  - `SCK/CLK -> GPIO18`
  - `MISO/DO -> GPIO19`
  - `MOSI/DI/CMD -> GPIO23`
  - `VIN -> 5V` for 5V-ready modules, or `3V3 -> 3.3V` for bare/3.3V modules.
- Buttons:
  - Button 1: `GPIO32`
  - Button 2: `GPIO33`
  - Wire each button between GPIO and GND; firmware uses pull-ups.
- Sleep-mode hardware:
  - Passive vibration switch: `GPIO27 -> switch -> GND`; firmware uses the ESP32 pull-up and EXT0 wake on LOW.
  - Peripheral load-switch enable: `GPIO13`, active HIGH in firmware.
  - The switched peripheral rail powers the SD card and MAX98357A amp together. GPIO13 HIGH wakes both; GPIO13 LOW turns both off before deep sleep.
  - If testing without a load switch, direct SD/amp power is acceptable for functional firmware testing, but sleep-current measurements will not represent the final design.

## Hardware Findings

- The original long USB/power path sagged to about 4.2V on the ESP32 5V rail and
  caused brownouts. Shorter USB or stable external 5V fixed this.
- Some blue microSD boards were mechanically/electrically flaky. Symptoms
  included MISO stuck low, changing when the module/card was moved, and raw SPI
  returning `0xFF` forever. Replacing the board fixed SD reads.
- The working SD diagnostic pattern is:
  - Idle MISO high.
  - Raw CMD0 response `0x01`.
  - CMD8 response `0x01` with `00 00 01 AA`.
  - `SD.begin` lists root directory contents.
- Mac-created SD noise files are expected, especially `._*` and `.DS_Store`.
  Firmware should ignore known metadata files silently and skip invalid/tiny WAVs
  without getting stuck.
- A larger speaker can produce scratches/glitches more easily than a small
  speaker. Treat that first as a power/wiring/current/load issue before changing
  codec logic.

## Bluetooth Findings

- ESP32 base MAC seen during upload: `40:22:d8:3d:8a:20`.
- Classic BT address printed by firmware: `40:22:D8:3D:8A:22`.
- The firmware prints this line on boot:
  - `[BT] Classic BT address: 40:22:D8:3D:8A:22`
- Do not hard-code the address forever; use the boot log if the board changes.
- Phone streaming sounded clean. Mac streaming previously had regular small gaps
  and macOS Bluetooth logs showed high retransmits/flushes. Use phone playback
  for subjective audio-quality sanity checks, and use the Mac smoke test mainly
  for connection/routing/regression automation.
- The real app currently starts A2DP and BLE together. Memory is tight but
  working with a 16KB A2DP queue:
  - `[BT] A2DP queue ready: 16384B (...)`
- Do not increase the A2DP ringbuffer or BLE payloads without rerunning both
  real-app and BT-debug smoke tests.
- `SweetYaar Remote` may appear as the macOS audio output even after the firmware
  advertises `SweetYaar`; this is likely a cached macOS device name. The smoke
  script fuzzy-matches output devices containing `SweetYaar`.

## Mac Bluetooth Automation

macOS Bluetooth privacy is the main trap.

- Running `blueutil` directly from Codex's backend process can fail with:
  - `absence of access to Bluetooth API`
  - `check that current terminal application has access in System Settings > Privacy & Security > Bluetooth`
- That process may not appear in System Settings, so the user cannot approve it
  directly.
- The working approach is to run the smoke test inside the real macOS Terminal
  app. Once Terminal is added/allowed under:
  - `System Settings -> Privacy & Security -> Bluetooth`
  automation can connect Classic BT successfully.
- Required macOS tools:
  - `/opt/homebrew/bin/blueutil`
  - `/opt/homebrew/bin/SwitchAudioSource`
- The smoke script searches `/opt/homebrew/bin`, `/usr/local/bin`, `/usr/bin`,
  and `/bin`.

## Bluetooth Smoke Tests

Use the script, not ad hoc commands:

```bash
/Users/zmoshe/proj/sweetyaar/.venv/bin/python /Users/zmoshe/proj/sweetyaar/tools/mac_bt_smoke_test.py --env esp32dev --bt-address 40-22-D8-3D-8A-22 --device-name SweetYaar
```

For a no-flash rerun against the current firmware:

```bash
/Users/zmoshe/proj/sweetyaar/.venv/bin/python /Users/zmoshe/proj/sweetyaar/tools/mac_bt_smoke_test.py --skip-upload --bt-address 40-22-D8-3D-8A-22 --device-name SweetYaar
```

For debug firmware:

```bash
/Users/zmoshe/proj/sweetyaar/.venv/bin/python /Users/zmoshe/proj/sweetyaar/tools/mac_bt_smoke_test.py --env btdebug --bt-address 40-22-D8-3D-8A-22 --device-name SweetYaar
```

When launching from Codex, prefer Terminal via AppleScript so Terminal owns the
Bluetooth permission:

```bash
osascript -e 'tell application "Terminal" to activate' \
  -e 'tell application "Terminal" to do script "/Users/zmoshe/proj/sweetyaar/.venv/bin/python /Users/zmoshe/proj/sweetyaar/tools/mac_bt_smoke_test.py --env esp32dev --bt-address 40-22-D8-3D-8A-22 --device-name SweetYaar 2>&1 | tee /Users/zmoshe/proj/sweetyaar/tools/bt_smoke_logs/terminal-realapp-smoke-latest.log; echo; echo Real app smoke finished; read -n 1 -s -r -p \"Press any key to close...\"; exit"'
```

Expected successful real-app smoke markers:

- PlatformIO upload succeeds for `esp32dev`.
- Boot prints `=== SweetYaar Boot ===`.
- SD mounts: `[WavPlayer] SD OK`.
- A2DP starts: `[BT] A2DP sink started as "SweetYaar"`.
- BT connects:
  - `[BT] A2DP sample rate: 44100 Hz`
  - `[BT] Connected`
  - `[SM] idle -> bt_streaming`
- macOS audio routes to an output containing `SweetYaar`.
- Sine playback starts:
  - `[BT] Audio state: STARTED`
- Playback ends cleanly:
  - `[BT] Audio state: REMOTE_SUSPEND`

Recent successful real-app smoke logs:

- `/Users/zmoshe/proj/sweetyaar/tools/bt_smoke_logs/bt-smoke-20260520-215100.log`
- `/Users/zmoshe/proj/sweetyaar/tools/bt_smoke_logs/terminal-realapp-smoke-latest.log`

## Firmware Behavior Notes

- BLE parent controls are for local toy mode only, not Classic BT streaming.
- While A2DP/BT is connected:
  - Status should show BT connected.
  - Web controls for volume, theme, killswitch, play song, and play animal should
    be disabled or ignored.
  - BLE writes during BT mode should be ignored and current values re-notified.
- Local volume controls WAV playback only; do not call A2DP volume APIs for it.
- Physical/app button events during BT streaming should be ignored, not queued
  for later playback.
- Idle sleep:
  - Firmware reads `sleep.enabled`, `normalIdleSec`, `vibrationWakeIdleSec`, and
    `bleIdleSec` from `SD:/config.json`.
  - Sleep is considered only in `IDLE`, or while Classic BT is connected with
    A2DP audio stopped/remote-suspended, with no WAV playback, no Bluetooth
    reopen cooldown, and no active killswitch.
  - Normal idle defaults to 10 minutes; vibration-only wake defaults to 2 minutes;
    idle connected BLE defaults to 2 minutes.
  - Deep sleep is a full reboot on wake. BT/BLE connections, current song, and
    playback position are intentionally not preserved.
  - Before sleep, firmware stops WAV playback, mutes the amp, ends SD/SPI/I2S,
    sets SD/I2S pins to input/high-Z, disables the GPIO13 load switch, waits for
    the wake switch to release if needed, and enables EXT0 wake on GPIO27 LOW.
- Killswitch:
  - Writing/triggering `1` activates it outside BT mode.
  - Repeated `1` restarts the timer.
  - Writing/triggering `0` cancels it.
  - It has no effect during BT streaming.
- Theme scanning is from `/songs/<theme>/metadata.json`; include only themes
  with at least one playable WAV.
- Keep the BLE theme-list payload under the conservative 512-byte cap.

## Editing and Test Discipline

- Use `apply_patch` for manual edits.
- Keep edits scoped; this project has a lot of hardware-state coupling.
- After firmware changes, run at least:
  - `/Users/zmoshe/proj/sweetyaar/.venv/bin/pio run -e esp32dev`
- After BT, BLE, I2S, memory, or state-machine changes, run:
  - Real-app smoke (`esp32dev`)
  - Debug smoke (`btdebug`) when event-level detail is needed.
- Do not trust a successful compile alone for BT/A2DP work. The important proof
  is connection, audio routing, `Audio state: STARTED`, and no crash/reboot.

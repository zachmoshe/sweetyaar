# SweetYaar Agent Notes

These notes capture the current working setup and the debugging lessons from the
ESP32 bring-up. Future agents should read this before touching firmware,
Bluetooth, SD-card, or hardware workflows.

## Implementation Isolation

- For every agent-initiated implementation in any chat, create a separate Git
  worktree and a new `codex/...` branch before editing files, unless the user
  explicitly says to reuse an existing branch or worktree.

## Project Environment

- Repo root: `/Users/zmoshe/proj/sweetyaar`
- Use the project venv for PlatformIO and Python tools:
  - `/Users/zmoshe/proj/sweetyaar/.venv/bin/pio`
  - `/Users/zmoshe/proj/sweetyaar/.venv/bin/python`
- PlatformIO environment:
  - `sweetyaar`: complete application firmware.
- Run common commands from the repository root:
  - List commands: `make help`
  - Build real app: `make build`
  - Upload real app: `make flash`
  - Open serial monitor: `make monitor`
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
  - Normally-closed passive vibration switch: externally biased `GPIO27 -> switch -> GND`; the final PCB uses a 470 kΩ pull-up to 3.3V and firmware uses EXT0 wake on HIGH with internal pulls disabled.
  - Final-PCB power-gating intent: use one AP2281-3WG-7 to switch 3.3V to the bare SD card and every SD pull-up, and use the 5V boost converter's EN to power-gate the MAX98357A. The boost must guarantee true load disconnect when disabled; otherwise it does not replace a dedicated amp load switch.
  - `PERIPH_PWR_EN` on GPIO13 enables the SD switch and 5V boost when HIGH and turns both off when LOW; firmware RTC-holds it LOW during deep sleep.
  - Keep a physical pulldown on the shared GPIO13/`PERIPH_PWR_EN` net as a reset/bootloader/failure-state default even though firmware holds GPIO13 LOW in normal deep sleep.
  - GPIO21 is not required for amp sleep-current isolation once the 5V boost is truly disconnected, but retain it by default because it cheaply provides runtime mute and click/pop sequencing. It can be reclaimed later if another function needs the GPIO; in that case configure MAX98357A `SD_MODE` passively from `5V_PERIPH_SW`.
  - The prototype currently draws roughly 200–250mA from a 5V PSU during playback. Use 500mA as the preliminary high bound for expected low-battery current until BT streaming with a 4Ω speaker at 100% volume is measured; select the battery and power path with additional transient margin. This is separate from the charger module's tested 1A default setting. The current battery is 3400mAh; roughly 2000mAh will probably be sufficient if runtime and packaging tests confirm it.
  - The final 3.3V rail uses a low-quiescent-current buck-boost regulator so the ESP32 sees regulated 3.3V across charger/SYS changes and low-battery sag. Exact part selection remains open.
  - On the current `esp32_prototype_devboard`, GPIO13 only drives an indication LED rather than a real SD switch or boost EN, so the SD and amp remain powered during sleep-current tests.
  - Production status LED: WS2812B-V6 (LCSC C52917433), 5050 SMD, powered by `5V_PERIPH_SW`; GPIO2 drives `DIN` through the 330 Ω R_LED_DIN1 series resistor (LCSC C23138), without the former MMBT3904/10 kΩ base resistor/1 kΩ 5 V pull-up. Keep 100 nF local decoupling; no external DIN pulldown is fitted. The schematic is migrated to direct drive; new firmware must not be used with an older inverting NPN board. The `sweetyaar` environment explicitly selects non-inverted 24-bit GRB and 300/950 ns zero, 650/600 ns one, 300 µs reset timing. Frame width, order, inversion and timing remain independently configurable. Firmware establishes inactive LOW before rail enable, sends black before rail disable, and releases GPIO2 after the 5 V regulator is disabled. Maximum brightness remains 50% pending enclosure testing. The `sweetyaar-generic` environment preserves active-HIGH amp mute, non-inverted RGBW/GRBW and its 400/850 ns zero, 800/450 ns one, 80 µs reset timing. Both environments share common compiler flags without inheriting each other's LED settings. Validate direct-drive voltage margin: V6 VIH is 0.55×VDD (2.75 V at 5 V), while ESP32 VOH minimum is 2.64 V at 3.3 V, so nominal compatibility is not a worst-case system guarantee. GPIO16 and GPIO17 carry BQ25186 I2C SDA and SCL, respectively. Verify footprint, frame, color order, timing and enclosure visibility before PCBA; the user cannot rework SMD components.
  - If testing without the final power gating, direct SD/amp power is acceptable for functional firmware testing, but sleep-current measurements will not represent the final design.

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
  and macOS Bluetooth logs showed high retransmits/flushes. Prefer phone playback
  for subjective audio-quality sanity checks.
- The real app currently starts A2DP and BLE together. Memory is tight but
  working with a 16KB A2DP queue:
  - `[BT] A2DP queue ready: 16384B (...)`
- Do not increase the A2DP ringbuffer or BLE payloads without repeating the
  relevant device audio and connection checks.
- `SweetYaar Remote` may appear as the macOS audio output even after the firmware
  advertises `SweetYaar`; this is likely a cached macOS device name.

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
  - Before sleep, firmware sends a black addressable-LED frame while 5 V remains
    powered, stops WAV playback, mutes the amp if GPIO21 is retained, ends
    SD/SPI/I2S, sets SD/I2S pins to input/high-Z, disables and RTC-holds the
    GPIO13 peripheral-enable control LOW, detaches the RMT output and releases
    GPIO2 after the rail is off, and enables EXT0 wake on GPIO27 HIGH.
  - Before any sleep shutdown, sample the normally-closed wake switch every
    20 ms for 500 ms while continuing the normal loop. All LOW permits sleep;
    any HIGH restarts the normal idle timer. All HIGH also sends a one-time
    app warning for that attempt. Never wait for closure after shutdown.
- Killswitch:
  - Writing/triggering `1` activates it outside BT mode.
  - Repeated `1` restarts the timer.
  - Writing/triggering `0` cancels it.
  - It has no effect during BT streaming.
- Status LED:
  - Components set semantic `StatusSignal` flags; only `StatusLed::service(millis())` owns blink timing and addressable-LED writes.
  - Initialization is solid yellow; ready is green 1 s on/1 s off; local playback is green 0.5 s on/0.5 s off; BT connected but idle is blue 1 s on/1 s off; A2DP `STARTED` is blue 0.5 s on/0.5 s off; a persistent post-init error is red 0.25 s on/0.25 s off; Quiet time is purple 1 s on/0.25 s off; deep sleep is off.
  - Firmware prints the complete canonical status-LED mode legend to serial at boot.
- Theme scanning is from `/songs/<theme>/metadata.json`; include only themes
  with at least one playable WAV.
- Keep the BLE theme-list payload under the conservative 512-byte cap.

## Editing and Test Discipline

- Use `apply_patch` for manual edits.
- Keep edits scoped; this project has a lot of hardware-state coupling.
- After firmware changes, run at least:
  - `make build`
- After BT, BLE, I2S, memory, or state-machine changes, verify the relevant
  connection and audio behavior manually on the real device.
- Do not trust a successful compile alone for BT/A2DP work. The important proof
  is connection, audio routing, `Audio state: STARTED`, and no crash/reboot.

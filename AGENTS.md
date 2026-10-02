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

- Bond-only pairing: Classic and BLE use the stack's bonds, with no separate
  persistent approval lists. New pairing requires the physical window; normal
  reconnects must authenticate with saved keys. Existing approval lists are
  read only for one-time migration, then removed.
- Classic Just Works uses `ClassicBluetooth.cpp`, pinned to ESP-IDF 4.4.7.
  Keep `--wrap=BTA_DmConfirm`: the SDK auto-confirms Just Works without a public
  confirmation event. The adapter gates this call and uses BTA's queued
  pairability API. Do not use `BTA_DM_CONN_PAIRED`: this SDK's filter excludes
  Just Works keys by requiring the MITM-authenticated key flag.
- A bond reset persists `clearPending` before disconnect/removal. Access stays
  closed until both transports have disconnected and deletion is confirmed by
  empty bond stores. A reboot resumes it. Do not replace this with fire-and-forget
  asynchronous bond-removal calls.

- ESP32 base MAC seen during upload: `40:22:d8:3d:8a:20`.
- Classic BT address printed by firmware: `40:22:D8:3D:8A:22`.
- The firmware prints this line on boot:
  - `[BT] Classic BT address: 40:22:D8:3D:8A:22`
- Do not hard-code the address forever; use the boot log if the board changes.
- Phone streaming sounded clean. Mac streaming previously had regular small gaps
  and macOS Bluetooth logs showed high retransmits/flushes. Prefer phone playback
  for subjective audio-quality sanity checks.
- The real app currently starts A2DP and BLE together with an 8 KB A2DP queue
  and six I2S DMA buffers. Keep these reservations within the coexistence budget
  described under Editing and Test Discipline.
- Do not increase the A2DP ringbuffer or BLE payloads without repeating the
  relevant device audio and connection checks.
- `SweetYaar Remote` may appear as the macOS audio output even after the firmware
  advertises `SweetYaar`; this is likely a cached macOS device name.

## Firmware Behavior Notes

- Ready/error/pairing cues are embedded in application flash, independent of SD.
  `SystemSoundOutput` serializes cue writes, regular audio writes and sample-rate
  changes. Feed it from the main loop; pause SD feeding while a cue is active.
  A2DP continues consuming packets during the cue, so music returns without a
  stale backlog. Keep its DMA drain count in sync with the shared I2S constants.
  Cues use effective local volume, including mute and bedtime caps. Persistent
  startup errors replace Ready; runtime error notification is latched once per
  boot. Pairing plays at window opening and every 15 seconds while open; closing
  or resetting stops repeats. Revalidate cue playback during Classic audio and
  without SD after changes.

- BLE parent controls are for local toy mode only, not Classic BT streaming.
- While A2DP/BT is connected:
  - Status should show BT connected.
  - Web controls for volume, theme, killswitch, play song, and play animal should
    be disabled or ignored.
  - BLE writes during BT mode should be ignored and current values re-notified.
- Local volume controls WAV playback only; do not call A2DP volume APIs for it.
- Local WAVs accept 44.1 kHz, 16-bit PCM with one or two channels. Keep the
  shared I2S output stereo; WavPcmOutput duplicates mono samples and preserves
  stereo frames before volume control. WavPlayer streams only the validated
  PCM data range, without allocating a WAV decoder. Keep its 512-byte conversion
  buffer fixed and verify mono/stereo transitions and BT-to-local handoff.
- Playback button events during BT streaming should be ignored, not queued
  for later playback. The three-second pairing and ten-second approval-reset
  gestures remain available.
- Physical buttons use 50 ms debounce and a 250 ms grace period before a held
  single press triggers playback. Both down cancels pending singles and emits
  Stop once until both are released; a released short tap resolves sooner.
  Pairing/reset hold time starts when the second button is debounced down.
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
  - An open pairing window overrides playback/connection/error patterns with blue 200 ms on / 200 ms off for the full 60 seconds. Closing it restores the normal pattern. Clearing approvals at a ten-second hold overrides all patterns with one red 250 ms flash, then restores the current state's pattern (normally green idle), even while both buttons remain held.
  - Request reset feedback once from the Forget action. The LED scheduler consumes the request after the flash; do not latch a post-reset LED state in the pairing policy.
  - A BLE remote connection alone does not change the LED pattern. Local idle/playback remain green and Quiet time remains purple; the normal blue connection/playback patterns indicate Classic audio only.
  - BT/BLE connection and authentication diagnostics print to serial, including admission decisions and raw failure codes. Never log keys or passcodes, or add per-packet/per-loop logging during audio.
- Theme scanning is from `/songs/<theme>/metadata.json`; include only themes
  with at least one playable WAV.
- Keep the BLE theme-list payload under the conservative 512-byte cap.

## Editing and Test Discipline

- Use `apply_patch` for manual edits.
- Keep edits scoped; this project has a lot of hardware-state coupling.
- Keep two test layers: `make test-unit` runs host tests without flashing or
  device interaction; `make test-device` exercises the real connected hardware.
- Obtain explicit user approval before each hardware test session (including
  flashing). Approval for a session covers its necessary scenario attempts and
  fixes/retests; do not ask again for each individual connection. It does not
  authorize a later unrelated flash/test session.
- Confirm the connected board's PlatformIO environment before flashing. Capture
  flash, serial and host Bluetooth logs, and report passed, failed and untested
  flows separately. Never describe builds or mocked tests as hardware validation.
- Real takeover and source-contention tests need two independent Bluetooth
  devices. Two clients on one Mac share the same Bluetooth identity.
- On bonded Mac reconnects, BLE GAP AUTH can arrive before GATTS CONNECT.
  Preserve the result until the peer exists, apply the normal approval checks,
  and do not delete its bond or expect another AUTH event from an already
  encrypted link. Cache outcome metadata only, with bounded lifetime; no keys.
- Android Chrome may need one encrypted status read to trigger bonding while
  the public access diagnostic is pending. Recheck approval afterward. Once
  Bluedroid admits that encrypted read but AUTH_CMPL has not arrived, reject
  application access with insufficient authorization (0x08), not insufficient
  authentication (0x05): Android retries bonding on the latter and can show a
  duplicate pairing request. Never enable controls before approval completes.
- I2S uses six 512-frame stereo DMA buffers (12 KB at 16-bit stereo), plus
  the separate 8 KB A2DP queue. Twelve DMA buffers caused a real Bluedroid
  allocation failure (`fixed_queue_new` / `vQueueDelete`) when encrypted BLE
  connected during Classic audio. Repeat coexistence/audio tests before
  increasing either reservation.
- After firmware changes, run at least:
  - `make build`
- After BT, BLE, I2S, memory, or state-machine changes, verify the relevant
  connection and audio behavior manually on the real device.
- Do not trust a successful compile alone for BT/A2DP work. The important proof
  is connection, audio routing, `Audio state: STARTED`, and no crash/reboot.

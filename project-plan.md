# SweetYaar — Baby Doll BT Speaker Controller

## Context

This project is a v2 redesign of a custom ESP32-based baby toy controller originally written in MicroPython. The key new requirement is that the device must appear as a **Bluetooth A2DP speaker** to phones and computers. MicroPython has no Bluetooth Classic / A2DP support, so the firmware is rewritten in **C++ using the Arduino framework on PlatformIO**. The project also includes a custom PCB, a Web BLE parent control/configuration interface, SD-card content curation, and a 3D-printed enclosure.

---

## Architecture Decisions

| Decision | Choice | Reason |
|---|---|---|
| Firmware language | C++ (Arduino framework) | MicroPython cannot do BT Classic A2DP |
| Toolchain | PlatformIO (VS Code extension) | Better dependency management than Arduino IDE |
| MCU | **ESP32-WROOM-32 (original ESP32 only)** | Only original ESP32 supports BT Classic; S3/C3/C6 do not |
| BT A2DP library | `pschatzmann/ESP32-A2DP` v1.8.x | Most mature maintained library; works on Arduino ESP32 core v3 |
| Audio pipeline | `pschatzmann/arduino-audio-tools` | Same author; integrates A2DP + WAV playback on same I2S bus |
| Audio DAC + amp | MAX98357A | I2S DAC + 3W mono amp in one chip; 2.5–5.5V (runs direct from LiPo) |
| SD card interface | SPI | WAV files for songs and animal sounds |
| BLE parent control | ESP32 built-in BLEDevice | Dual-mode: Classic BT (A2DP) + BLE simultaneously on same chip |
| Parent live-control app | Web BLE (single HTML page) | No install; controls normal play mode from Android Chrome + desktop Chrome |
| Parent config app | Same Web BLE app, settings screen | Device name, default volume/theme, and enabled content are edited over BLE |
| Asset management | Manual SD-card preparation | Parents/developer curate WAV files and metadata on the SD card; the app does not upload assets |
| OTA firmware | Not in product plan | Firmware is flashed through PlatformIO/serial during development |
| Idle sleep / wake | ESP32 deep sleep with passive vibration wake | Saves battery after inactivity; wake is a full reboot, which is acceptable for the toy |
| Peripheral power gating | GPIO-controlled load switch for SD + audio amp | SD card and amp are powered only while the ESP32 is awake |
| Battery | Single-cell LiPo, 3.7V, ~1500–2000 mAh | Compact, rechargeable |
| Charging / battery safety | Modern single-cell LiPo charger module/IC with battery protection | Safety over fast charging; exact part TBD; use low charge current, fuse protection, and battery temperature protection |
| Power regulation | Modern 3.3V LDO, not AMS1117 | Simple, lower-dropout 3.3V rail for ESP32 + SD + logic; buck-boost deferred unless testing shows brownouts or poor runtime |
| PCB tool | EasyEDA / LCEDA | Integrated with JLCPCB for small-batch manufacturing |
| Enclosure | 3D-printed (design TBD) | Holds PCB + LiPo + speaker; fits inside/attaches to doll body |

---

## Hardware Design

### PCB Components

| Component | Part | Notes |
|---|---|---|
| MCU module | ESP32-WROOM-32 | 4 MB flash, Wi-Fi + BT dual-mode |
| DAC + Amp | MAX98357A | SOP-8, I2S input, mono 3W out |
| SD card | Micro SD push-push slot | SPI, 3.3V logic level; slot on PCB edge (accessible externally) |
| Vibration wake sensor | Passive vibration/tilt switch | Wakes ESP32 from deep sleep; wired between GPIO27 and GND with ESP32 pull-up |
| Peripheral load switch | High-side load switch, EN from GPIO13 | Switched rail for SD card and MAX98357A amp; exact final rail topology TBD |
| USB-C | USB-C 16-pin charging port | Charging only, no data |
| Charging | Modern 1-cell LiPo charger module/IC, exact part TBD | MCP73831-class if simple/off-while-charging; BQ2407x/BQ2518x/MCP73871-class only if power-path charging is desired |
| Battery protection | Protected LiPo pack + board-level protection | Prefer pack PCM for overcharge, overdischarge, overcurrent, and short-circuit; add fuse/polyfuse and battery temperature protection |
| LDO | Modern 3.3V LDO, exact part TBD | AP2112K/MIC5504/MCP1700-class part; avoid AMS1117 for final battery design |
| Battery connector | JST-PH 2-pin | LiPo connection |
| Speaker connector | JST-PH 2-pin | Connects to doll's speaker |
| Button connectors | 2× JST-PH 2-pin | One per button; buttons wired to GND |
| Power switch | Slide switch (SPDT) | On/off between battery and rest of circuit |
| Status LED | 0805 + resistor | Power-on and BT/BLE status indicator |

### Sleep-Mode Hardware Notes

- The ESP32 remains powered by the 3.3V rail during deep sleep. The SD card and audio amp are behind the switched peripheral rail so their leakage and undefined pin states do not dominate sleep current.
- `GPIO27` is the wake input. The passive vibration switch connects `GPIO27` to GND when it moves; firmware enables the pull-up and uses ESP32 EXT0 deep-sleep wake on LOW.
- `GPIO13` drives the peripheral load-switch enable. The current firmware assumes active HIGH: HIGH powers SD + amp, LOW turns them off.
- One load-switch IC is acceptable if SD and amp are intentionally fed from the same switched rail in the final design. If the final PCB uses different rails for native 3.3V SD and higher-voltage amp power, keep one firmware enable signal but review whether it should drive one load switch, two load switches, or an enabled regulator plus a load switch.
- Before entering sleep, firmware stops WAV playback, mutes the amp, ends I2S/SPI/SD, sets SD/I2S pins to input/high-Z, turns off the load switch, waits for the vibration switch to release if it is still closed, and then enters deep sleep.
- Wake from vibration is a normal reboot. BT/BLE clients disconnect, the current song is not remembered, and state returns to normal boot defaults.

### Power and Charging Safety Baseline

This is a child toy, so the power design prioritises safety, low heat, and predictable behaviour over fast charging, maximum battery capacity, or operating while plugged in.

- **Use a reputable protected single-cell LiPo pack**. Prefer a pack with a built-in protection circuit module (PCM) covering overcharge, overdischarge, overcurrent, and short-circuit protection.
- **Add simple board-level protection**. Include an appropriately rated fuse or resettable polyfuse in the battery/USB power path. Add strain relief and keyed connectors so battery and speaker leads cannot be pulled loose or reversed easily.
- **Add battery temperature protection**. Prefer a battery pack with an NTC temperature lead routed to a charger temperature-sense input. If the selected charger/module does not support NTC sensing, use a conservative module with thermal protection and consider a physical thermal fuse placed against the cell/pack.
- **Charge slowly by default**. Target roughly 250-500 mA unless the selected cell datasheet, enclosure thermals, and bench testing justify more. The project does not need 1A fast charging.
- **Use a modern charger/module**. The charger should provide at least thermal regulation, charge termination, charge-status indication, and sane input/battery protection. Power-path support is optional; it is acceptable for the toy to be switched off or electrically disconnected from the load while charging.
- **Use a modern 3.3V LDO**. The ESP32/SD/logic rail should be powered from a low-dropout regulator rather than AMS1117. A buck-boost regulator is not required initially; revisit only if testing shows low-battery resets or unacceptable runtime.
- **Physically protect the battery**. The enclosure must prevent crushing, puncture, sharp edges, or wire strain on the LiPo. First prototypes should be charged only while supervised, and the charging/power section should get an electronics review before PCB manufacture.

### Key GPIO Assignments (ESP32-WROOM-32)

| Signal | GPIO |
|---|---|
| I2S BCLK (MAX98357A) | GPIO26 |
| I2S LRC/WS (MAX98357A) | GPIO25 |
| I2S DOUT (MAX98357A) | GPIO22 |
| MAX98357A SD_MODE (mute) | GPIO21 |
| SD MOSI | GPIO23 |
| SD MISO | GPIO19 |
| SD SCK | GPIO18 |
| SD CS | GPIO5 |
| Button 1 (Songs) | GPIO32 |
| Button 2 (Animals) | GPIO33 |
| Vibration wake switch | GPIO27 |
| SD + amp load-switch enable | GPIO13 |
| Status LED | GPIO2 |

### Target PCB Specs
- Size: ~60 × 40 mm
- 2-layer board
- Manufactured at JLCPCB (5–10 units)
- LCSC part numbers in BOM for JLCPCB SMT assembly
- **SD card slot on PCB edge** — physically accessible from enclosure for manual card swap

---

## Firmware Architecture

### Runtime Mode

SweetYaar boots directly into normal toy operation. A2DP, BLE live controls, BLE settings/content curation, WAV playback, buttons, and the state machine are active together. Wi-Fi is not part of the product runtime and there is no separate captive-portal/config-mode boot path.

### Idle Deep Sleep

The toy automatically enters real ESP32 deep sleep after inactivity, controlled by `SD:/config.json`.

- Default normal idle timeout: 10 minutes (`normalIdleSec: 600`).
- Default vibration-only wake timeout: 2 minutes (`vibrationWakeIdleSec: 120`). This shorter timeout is used when the only thing that happened was a vibration wake and nobody pressed a button, connected meaningfully, or started playback.
- Default BLE idle timeout: 2 minutes (`bleIdleSec: 120`). A connected parent app can delay sleep while it is active, but an idle BLE connection is allowed to be dropped by sleep after this timeout.
- Sleep is considered only in `IDLE`, or while Classic BT is connected with A2DP audio stopped/remote-suspended, with WAV playback stopped, no Bluetooth reopen cooldown, and no active killswitch.
- Button presses, BLE writes/config commands, BLE connect/disconnect, BT state changes, and state-machine transitions reset the activity timer.
- Killswitch does not trigger sleep and sleep does not replace killswitch. While the state machine is in `KILLSWITCH`, the device stays awake until the killswitch exits.
- Wake source is only the vibration switch on `GPIO27`. Buttons are not wake sources because touching the toy should move it enough to trip the vibration switch.
- Waking is a full reboot. This is deliberate: no BT client, BLE client, current song, or playback position is preserved.

### Bedtime Mode

Bedtime mode is a planned parent-controlled local playback mode. See
`docs/bedtime-mode.md` for the full product and UX spec.

- The feature has one master setting, one daily bedtime window, one bedtime
  theme, and one volume cap. It is not a general scheduler.
- Defaults: bedtime hours `18:30` to `06:30`; bedtime theme `lullabies` in the
  SD-card template.
- If the master setting is disabled, the toy behaves as it does today.
- If reliable local clock time is unavailable, the toy treats Bedtime mode as
  inactive even when the saved setting is enabled.
- When reliable local time is available and the current time is inside the
  bedtime window, the runtime Bedtime state turns on automatically.
- While Bedtime mode is active, local song playback uses the configured bedtime
  theme. If the configured bedtime theme is missing, disabled, or has no
  playable WAV files, firmware logs a serial warning and falls back to the
  normal active theme for song playback.
- While Bedtime mode is active, local song and animal WAV playback is capped by
  `volumeCapPct`. The cap still applies when the bedtime theme falls back to the
  normal theme. Animal sound selection is otherwise unchanged.
- Classic BT/A2DP streaming is unaffected by Bedtime mode; neither the bedtime
  theme nor the volume cap apply during BT streaming.
- Parents can toggle the runtime Bedtime state from a Bedtime/Daytime mode card
  in the app. A small glowing moon icon is used as a compact Bedtime indicator.
- If reliable local time is unavailable, the app shows a `Time unknown` mode
  card rather than pretending the toy is in Daytime mode.
- Parent theme changes override Bedtime mode for the current awake session.
- Runtime Bedtime overrides are cleared by deep sleep/reboot. After wake, the
  toy returns to automatic Bedtime decisions from saved settings and reliable
  local time.
- On BLE connection, the parent app syncs time with a simple config message such
  as `{ "op": "syncTime", "epochSec": 1780595400, "tzOffsetMin": 180 }`.

### Play-Mode State Machine

```
States: IDLE | PLAYING_SONG | PLAYING_ANIMAL | BT_STREAMING | KILLSWITCH

IDLE:
  - Button 1 pressed → PLAYING_SONG (next song in current effective theme)
  - Button 2 pressed → PLAYING_ANIMAL (random animal sound)
  - Both buttons pressed → (no-op, already idle)
  - BT device connects → BT_STREAMING
  - BLE killswitch → KILLSWITCH (10-min timer)

PLAYING_SONG:
  - Song finishes → IDLE
  - Button 1 pressed → next song (stays PLAYING_SONG)
  - Both buttons pressed → stop → IDLE
  - BLE killswitch → stop → KILLSWITCH  ← parents override
  - BT connects → stop WAV → BT_STREAMING  ← BT takes precedence

PLAYING_ANIMAL:
  - Sound finishes → IDLE
  - Both buttons pressed → stop → IDLE
  - BLE killswitch → stop → KILLSWITCH  ← parents override
  - BT connects → stop WAV → BT_STREAMING  ← BT takes precedence

BT_STREAMING:
  - Buttons DISABLED
  - BLE parent app shows `BT connected`
  - BLE local controls are read-only/ignored while BT is connected
  - BT disconnects → IDLE

KILLSWITCH (10-minute timer):
  - All buttons DISABLED
  - BT streaming still allowed (BT connects → BT_STREAMING)
  - BLE killswitch can cancel early → IDLE
  - BLE killswitch activation while already active restarts the timer
  - Timer expires → IDLE
```

### Firmware Modules

0. **ContentCatalog** (namespace, `src/ContentCatalog.h/.cpp`)
   - `buildCatalog()`: called once at boot after `SD.begin()`. Single pass over the SD card — reads `config.json`, every theme `metadata.json`, and every WAV header into an in-RAM structure: `CachedTheme` + `CachedSong` vectors.
   - All subsequent consumers (WAV playback file lists, BLE theme list, settings scans) are served from RAM with zero SD access.
   - Edits (`setThemeDisabled`, `setThemeShuffle`, `setSongDisabled`) write to the SD and flip the cached flag in place; no rescan is needed until reboot.
   - Also owns JSON I/O helpers, WAV header inspection, and paged JSON response builders for the BLE settings API.

1. **A2DP Sink** (`pschatzmann/ESP32-A2DP`)
   - Device name: configurable, stored in the NVS-backed device-config JSON blob (default: "SweetYaar")
   - Audio: SBC codec → 44.1 kHz 16-bit PCM → I2S → MAX98357A
   - Connect/disconnect callbacks drive state machine

2. **WAV Player** (`pschatzmann/arduino-audio-tools`)
   - Plays through same I2S bus (exclusive with A2DP)
   - Song and animal file lists are served from the in-RAM ContentCatalog; no SD access during playback
   - WAVDecoder + EncodedAudioOutput pipeline is allocated once at boot (`ensureDecoder()`), not per-file, to avoid heap fragmentation
   - Songs: sequential (filename order) or shuffle within the effective theme; non-shuffle order follows filename sort, not FAT directory order
   - Animals: random pick from `/animals/`
   - `refreshSongList(theme)`: rebuilds the live rotation from the catalog cache without interrupting the current song (called when a song is disabled mid-session)

3. **BLE Parent Service** (ESP32 BLEDevice)
   - Enabled in play mode alongside Classic BT A2DP.
   - Custom GATT service, characteristics:
     - `volume` (uint8, 0–100, read/write/notify) — live local WAV volume for the current session
     - `killswitch` (uint8, 0/1, read/write/notify) — stops local playback and disables buttons for 10 min
     - `theme` (string, read/write/notify) — sets active song folder for the current session
     - `status` (string, read/notify) — `Idle`, `Playing song - <theme> / <file>`, `Playing animal - <file>`, `BT connected`, or `Killswitch active (<mm:ss> left)`
     - `themes` (JSON string, read) — available song themes (served from in-RAM ContentCatalog)
     - `notice` (JSON string, read/notify) — device-to-app one-shot notice: `{"severity":"error"|"warn","message":"..."}`. Error notices are persistent; warnings auto-dismiss after a few seconds. App subscribes optionally; older firmware without it still connects.
   - `command` (uint8 or JSON string, write) — app equivalents for song, animal, stop, and config/content commands
   - `configResponse` (JSON string, read/notify) — paginated config/content responses; app subscribes to notifies for near-instant response instead of polling
   - BLE writes are live controls for local SD/WAV operation and persistent settings/content curation. While A2DP is connected, playback controls are read-only/ignored as needed, and current values are re-notified.

4. **BLE Settings + Content Curation**
   - Uses the same Web BLE parent app; no separate Wi-Fi AP or captive portal.
   - App can read/update:
     - Device name in NVS-backed device config
     - Default volume and default theme in `SD:/config.json`
     - Bedtime mode settings in `SD:/config.json`
     - Idle deep-sleep settings in `SD:/config.json`
     - Enabled/disabled themes in `SD:/config.json`
     - Enabled/disabled songs in each theme or animals `metadata.json`
   - App can scan available themes/songs through paged BLE config commands.
   - App does not upload WAV assets or firmware. SD-card content files are prepared manually outside the toy.
   - Parent-facing settings and media metadata are stored on the SD card.
   - Device-local settings that must survive SD-card replacement are stored in NVS as a compact device-config JSON blob.

5. **Button Handler**
   - Debounced (50 ms software debounce)
   - Active LOW (internal pull-up enabled)
   - Simultaneous press detection (both pressed within 50 ms window → IDLE)
   - Only processed outside BT_STREAMING and KILLSWITCH states

6. **Volume Control**
   - AudioTools software gain stage
   - Static firmware default: 75%
   - `SD:/config.json` may override the default volume
   - BLE volume writes change live volume only; they do not persist to NVS
   - Planned Bedtime mode applies an effective local WAV cap of
     `min(currentVolumePct, bedtime.volumeCapPct)` while active. The cap applies
     to songs and animals, but never to Classic BT/A2DP streaming.

7. **Idle Sleep Manager**
   - Reads `sleep.enabled`, `normalIdleSec`, `vibrationWakeIdleSec`, and `bleIdleSec` from `SD:/config.json`
   - Uses ESP32 EXT0 wake on `GPIO27` LOW
   - Drives the SD + amp load-switch enable on `GPIO13`
   - Powers peripherals back on during boot before SD, I2S, BT, and BLE init
   - Exposes sleep settings in BLE `getConfig`; persists edits through BLE `setConfig`

8. **Bedtime Mode Manager** (planned)
   - Reads `bedtime.enabled`, `startTime`, `endTime`, `theme`, and
     `volumeCapPct` from `SD:/config.json`
   - Tracks whether local clock time is reliable
   - Accepts BLE time sync from connected controllers
   - Computes automatic Bedtime state from local time and saved settings
   - Tracks parent runtime overrides until the next automatic boundary or deep
     sleep/reboot
   - Resolves the effective local song theme before starting song playback

### Config Storage

Most parent-editable configuration lives on the SD card so it can be changed, backed up, or replaced by the BLE app:

```json
{
  "schemaVersion": 2,
  "defaultVolumePct": 75,
  "defaultTheme": "lullabies",
  "disabledThemes": [],
  "bedtime": {
    "enabled": true,
    "startTime": "18:30",
    "endTime": "06:30",
    "theme": "lullabies",
    "volumeCapPct": 45
  },
  "sleep": {
    "enabled": true,
    "normalIdleSec": 600,
    "vibrationWakeIdleSec": 120,
    "bleIdleSec": 120
  }
}
```

Only device-local settings that should survive SD-card replacement live in NVS. NVS stores a compact JSON blob equivalent to:

```json
{
  "schemaVersion": 1,
  "btName": "SweetYaar"
}
```

### SD Card File Structure

```
/config.json
/songs/
  lullabies/
    metadata.json
    01.wav
    02.wav
    ...
  nature/
    metadata.json
    01.wav
    ...
  kids/
    metadata.json
    01.wav
    ...
/animals/
  cat.wav
  dog.wav
  cow.wav
  ...
```

**`metadata.json` schema** (UTF-8, emoji-friendly):
```json
{
  "name": "Lullabies 🌙",
  "shuffle": false
}
```

- `name`: display name shown in the Web BLE parent app (UTF-8, any emoji allowed)
- `shuffle`: if true, randomise song order once when the theme is selected; the shuffled order is then maintained (and wraps) on every subsequent button press until the theme changes
- Bedtime theme selection is global in `SD:/config.json`; individual theme
  metadata does not need a bedtime flag.

---

## Web BLE Parent App (Phase 2)

- Single `docs/index.html` (vanilla JS + CSS, no framework)
- Hosted on GitHub Pages from `/docs`
- Uses Web Bluetooth API (Android Chrome + desktop Chrome)
- Normal local play-mode live controls and BLE settings/content curation; not used for WAV upload or BT audio control
- Controls:
  - Connect / Disconnect
  - Play song / Play animal / Stop buttons
  - Volume slider for SD/WAV playback
  - Song theme selector backed by the firmware `themes` JSON characteristic
  - Bedtime/Daytime mode card for Bedtime mode runtime toggle and time-unknown state
  - Killswitch activate/restart and cancel controls
  - Device status indicator
  - Notice card (above the status card on the ready screen): error notices are red/persistent with a dismiss button; warnings are amber/auto-dismiss
  - Settings screen for device name, default volume, default theme, enabled themes, and enabled songs
  - Bedtime mode settings for the master toggle, bedtime theme, start/end
    times, and volume cap
  - Sleep settings for automatic sleep and idle timeouts
- When A2DP is connected, the app shows `BT connected` and disables volume, theme, and killswitch controls.
- During A2DP, Bedtime mode does not affect theme selection or volume.

---

## BLE Settings + Content Curation

- Runs through the same Web BLE app used for live controls.
- No Wi-Fi AP, captive portal, OTA page, or in-toy asset upload flow.
- Supported app flows:
  - **Device settings** — edit the NVS-backed device name.
  - **Toy defaults** — edit `SD:/config.json` values like default volume and default theme.
  - **Bedtime mode** — edit the master toggle, bedtime theme, bedtime start/end
    times, and volume cap; sync controller time on connection.
  - **Sleep** — edit automatic sleep, normal idle, vibration-wake idle, and BLE idle timeouts.
  - **Song themes** — scan themes, enable/disable theme folders, and choose default theme.
  - **Theme songs** — scan a selected theme and enable/disable individual WAV files.
  - **Animal sounds** — scan `/animals` and enable/disable individual WAV files.
- New WAV files and metadata are still prepared on the SD card outside the toy.

---

## Project Phases

### Phase 1 — Core Firmware
1. Set up PlatformIO project targeting ESP32-WROOM-32
2. A2DP sink → MAX98357A via I2S (phone streams music through doll)
3. SD WAV playback (songs + animals) via same I2S bus
4. State machine (IDLE / PLAYING / BT_STREAMING / KILLSWITCH)
5. Button debounce, simultaneous-press detection
6. Volume control via AudioTools gain
7. Device name from NVS-backed device-config JSON
8. Parent defaults from `SD:/config.json`

### Phase 2 — Web BLE Parent App
1. Enable and validate firmware BLE GATT service (volume, killswitch, theme, status, themes)
2. Design + build `docs/index.html` (Web Bluetooth)
3. BLE characteristic integration with BT-mode read-only behavior
4. Deploy `/docs` to GitHub Pages

### Phase 3 — PCB Design (EasyEDA)
1. Schematic: all components, power tree, GPIO mapping
2. Select final charger/protection/LDO parts and fuse/temperature-protection ratings
3. Electronics review of LiPo charging, battery protection, power switch, and regulator design
4. PCB layout: 60×40 mm, 2-layer
5. BOM with LCSC part numbers
6. Gerber export → JLCPCB order (5–10 units)

### Phase 4 — Assembly & Testing
1. Assemble first unit (manual or JLCPCB SMT)
2. Flash firmware via USB (boot/enable pins accessible on PCB)
3. End-to-end test: BT speaker, buttons, BLE app, battery
4. Sleep test: normal 10-minute idle, vibration-only 2-minute idle, BLE idle timeout, vibration wake reboot, SD/amp load-switch power-off

### Phase 5 — BLE Settings + Content Curation
1. Add BLE config command/response contract
2. Add settings screen to the Web BLE app
3. Read/update device name, default volume, and default theme
4. Scan themes/songs with paged responses
5. Enable/disable themes and individual songs
6. Test full parent setup flow through BLE

### Phase 5b — Bedtime Mode
1. Add BLE time-sync command and local clock reliability tracking
2. Add `bedtime` config parsing/persistence in `SD:/config.json`
3. Add effective theme resolution for local song playback
4. Add Bedtime volume cap for local song and animal WAV playback
5. Add parent app Bedtime/Daytime mode card on the Ready screen
6. Add Settings controls for master toggle, bedtime theme, start/end times, and volume cap
7. Test automatic bedtime entry/exit, parent overrides, deep-sleep reset, unreliable-time fallback, and BT streaming exclusion

### Phase 6 — 3D Enclosure
1. Choose CAD tool (FreeCAD or Fusion 360 — TBD)
2. Design shell: fits PCB + LiPo + speaker
3. Features: USB-C cutout, power switch, SD card slot access, button holes
4. 3D print prototype, iterate fit
5. Finalize for gifting

### Phase 7 — Final Toy PCB Power/Sleep Integration
1. Select orderable vibration switch footprint and placement strategy inside the doll
2. Select high-side load switch for the switched SD + amp rail
3. Decide final rail topology for native SD socket and MAX98357A power
4. Validate deep-sleep current with LiPo, charger/protection, ESP32, vibration switch, and load switch installed
5. Verify no backfeeding into the powered-off SD card or amp through SPI/I2S/control pins

---

## Key Libraries

| Library | Source | Use |
|---|---|---|
| ESP32-A2DP | `pschatzmann/ESP32-A2DP` | BT Classic A2DP sink |
| arduino-audio-tools | `pschatzmann/arduino-audio-tools` | I2S output, WAV decode, volume gain |
| ESP32 BLEDevice | Arduino-ESP32 core (built-in) | BLE GATT server |
| SD | Arduino-ESP32 core (built-in) | SD card file access |

---

## Open Items / To Discuss Later
- Speaker impedance (4Ω or 8Ω) — affects MAX98357A output power
- LiPo capacity (1000 vs 1500 vs 2000 mAh) — depends on doll body space
- Exact charger module/IC and whether it has NTC temperature-sense input
- Exact fuse/polyfuse and optional thermal-fuse ratings/placement
- Exact 3.3V LDO part and thermal/current validation under ESP32 radio peaks
- Exact vibration switch part/footprint and mechanical placement in the toy body
- Exact load-switch part, enabled polarity, current rating, and off-state leakage
- Final switched-rail topology for SD card and MAX98357A power
- CAD tool for enclosure (FreeCAD vs Fusion 360)
- BT name per-unit strategy (same name "SweetYaar" for all, or personalised per gift?)
- User's existing MicroPython code — review for any missing features

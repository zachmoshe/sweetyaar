# SweetYaar Firmware

SweetYaar is an ESP32-based audio toy designed to be installed inside a doll.
The doll has two physical buttons and works as a simple music player: one button
plays songs and the other plays animal sounds. Audio files and the toy's
configuration live on a microSD card, so the content can be changed without
rebuilding the firmware.

The same device can also work as a Bluetooth speaker. A separate parent mobile
app connects over Bluetooth Low Energy (BLE) to control local playback and
change settings. The buttons on the doll are limited to playing and stopping
audio. Volume, theme selection, looping, content settings, Bedtime mode, and
sleep settings are adjusted through the parent app.

This document explains what the firmware does and how its main pieces fit
together. See [Mobile App](mobile-app.md) for the parent interface and
[Hardware](hardware.md) for the board, wiring, and electrical design.

## Playing songs and animal sounds

The two buttons deliberately have a small, predictable set of actions:


| Interaction                            | Result                                                                                               |
| -------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| Press the song button                  | Start a song from the active theme. Press it again while a song is playing to move to the next song. |
| Press the animal button                | Play one animal sound. Press it again while an animal sound is playing to move to the next sound.    |
| Press the other button during playback | Switch immediately between song and animal playback.                                                 |
| Press both buttons together            | Stop local playback.                                                                                 |


Songs are grouped into themes, such as lullabies or holiday songs, so the toy
can play from one type of content at a time. Only the parent app can select the
active theme.

A song normally stops when that track ends. The parent app can enable continuous
song playback, which automatically starts the next song in the theme and wraps
around at the end. It follows the theme's normal or shuffled order. This is a
temporary setting: it starts off after every boot and is cleared by Stop,
animal playback, Bluetooth speaker mode, or the app's ten-minute Quiet time
lock.

Animal sounds are always single-shot. Their metadata controls whether the list
is shuffled; the example card enables shuffling by default. Either way,
pressing the animal button repeatedly rotates through the available sounds.

The app can also turn shuffling on or off and disable specific themes, songs,
or animal sounds. Disabled or empty themes are not offered for playback.

## Content on the microSD card

The card stores audio, content metadata, and configuration:


| Path                           | Purpose                                                             |
| ------------------------------ | ------------------------------------------------------------------- |
| `/songs/<theme>/*.wav`         | Song WAV files grouped into themes such as `lullabies` or `nature`. |
| `/songs/<theme>/metadata.json` | The theme's display name, shuffle setting, and disabled tracks.     |
| `/animals/*.wav`               | Animal-sound WAV files.                                             |
| `/animals/metadata.json`       | Shuffle and disabled-track settings for animal sounds.              |
| `/config.json`                 | Default volume and theme, Bedtime settings, and sleep settings.     |


Audio must be uncompressed PCM WAV at 44.1 kHz, 16-bit, stereo. The firmware
streams files from the card rather than loading a whole recording into memory.
At boot it scans the content once, validates the WAV files, and builds an
in-memory catalog used by playback and the parent app. Files added or removed
manually are therefore picked up after a restart; changes made through the app
also update the live catalog.

The checked-in [SD-card template](../../content/sd-card-template/README.txt) contains a
complete example card with the supported layout and configuration schema. If
the card or configuration is missing, Bluetooth speaker mode still starts and
the firmware uses safe defaults where possible, but local audio cannot play
without readable content.

## Parent controls

The mobile app uses BLE, which is separate from the Classic Bluetooth connection
used for streaming music. Through BLE, a parent can see the current state,
mirror the song, animal, and stop actions, select a theme, adjust local volume,
and turn song looping on or off. The settings screen can rename the toy, choose
defaults, configure sleep and Bedtime mode, and enable or disable themes and
individual audio files.

Most content settings are saved in `/config.json` or the relevant theme's
`metadata.json` on the SD card. The Bluetooth device name is different: it is
stored in the ESP32's non-volatile storage so replacing the card does not rename
the toy.

The app's **Quiet time** switch gives a parent a temporary way to disable the doll's buttons.
Activating it stops local audio and ignores physical-button and app playback commands for
ten minutes, unless the parent cancels it early. Quiet time applies only to local playback;
it does not prevent a Classic Bluetooth source from connecting and streaming.

The app is a control surface, not a content uploader. Songs and animal sounds
are placed on the microSD card directly. Its complete behavior, connection
flow, and offline support are described in [Mobile App](mobile-app.md).

## Battery and charging state

The production PCB measures the protected 18650 directly from `BAT` through the
switched 634 kΩ / 200 kΩ divider on GPIO36/ADC1_CH0. The 200 kΩ lower leg is
implemented as two 100 kΩ resistors in series. The firmware uses calibrated ADC
millivolt readings with 2.5 dB attenuation, but never exposes the measured voltage
or a percentage. It publishes only one coarse state:

| Encoded value | State | Meaning |
|---:|---|---|
| 0 | `UNKNOWN` | The divider is absent, invalid, or has not produced its initial sample yet. |
| 1 | `GOOD` | Averaged battery voltage is above the charge-soon band. |
| 2 | `MEDIUM` | Charge soon. |
| 3 | `LOW` | Charge now; playback may soon stop as the protected battery or charger power path reaches cutoff. |
| 4 | `CHARGING` | BQ25186 `STAT0.CHG_STAT` reports constant-current or constant-voltage charging; this temporarily overrides the voltage band. |

Battery initialization runs after the higher-current boot work. Five samples
100 ms apart are averaged into one seed observation, so the initial state is
available after about half a second rather than after a full rolling window.
One new sample is then added every 30 seconds; the window grows to ten samples,
or about five minutes, and stays at that size. The seed counts once rather than
five times.

The state uses 100 mV hysteresis: `GOOD` falls to `MEDIUM` at 3.40 V and returns
at 3.50 V; `MEDIUM` falls to `LOW` at 3.10 V and returns at 3.20 V. Voltage
sampling continues while charging so the most recent band is ready when charge
status ends. Charger faults are logged, while only normal charging uses the
`CHARGING` battery state.

The BLE battery characteristic is a one-byte read/notify value rather than
JSON. This keeps the public contract deliberately small and prevents the app
from presenting noisy voltage as precision that the circuit cannot provide.

## Charger supervision

The production board uses an I2C-controlled BQ25186 at 7-bit address `0x6A` on
GPIO16/GPIO17. It was selected because firmware can set and verify the battery's
required charging-temperature window. The fixed production policy is 4.20 V,
1.00 A charge current, 1.05 A input limit, a six-hour safety timer, and hard
0°C/45°C TS cutoffs with the intermediate COOL/WARM zones disabled.

Charging is fail closed. GPIO4 drives an external NPN that can pull `/CE` LOW.
Its default internal pulldown and the external base pulldown keep the NPN off
through reset and boot, and firmware explicitly drives GPIO4 LOW at the start
of `setup()`. It probes the device ID,
writes each configuration register, immediately reads that physical register
back, and enables charging only after the complete sequence succeeds. The
verification path deliberately has no cached register values. Every ten seconds
and after `/INT`, it rereads every configured register and the status/flag
registers. A mismatch or I2C error releases `/CE`; one complete rewrite and
read-back must succeed before charging can resume.

`/PG` on GPIO34 reports valid input power and wakes the ESP32 when USB/AUX is
attached during deep sleep. `/INT` on GPIO35 prompts a status read while awake.
They are useful but not required for detailed reporting: charge phase, input
state, temperature zone/open sensor, input/DPPM/thermal limiting, overvoltage,
battery protection, safety-timer status, flags, and device ID are available over
I2C. Firmware remains awake while valid charger input is present. For
battery-only deep sleep it disables charging and the BQ25186 host watchdog;
wake performs a fresh full configuration and verification.

Two independent hang detectors protect this flow. The ESP32 task watchdog
registers Arduino `loop()` on CPU1 alongside the already watched CPU0 idle task;
the current ESP-IDF configuration uses a five-second timeout. While awake, the
BQ25186 40-second host watchdog requires continuing I2C traffic and power-cycles
`SYS` if traffic stops. The charger watchdog is disabled only immediately before
intentional deep sleep, after a final direct read-back.

## Bluetooth speaker mode

SweetYaar advertises as a Classic Bluetooth A2DP speaker, so a phone, tablet,
or computer can send it ordinary system audio. Connecting an A2DP source stops
any local WAV playback and gives the stream exclusive use of the speaker.

While the A2DP connection is active, physical-button playback and parent-app
playback controls are ignored rather than saved for later. The streaming device
owns the stream volume; the toy's local volume setting only affects WAV files
from the SD card. When the source disconnects, the firmware returns to idle and
opens the speaker for a new connection after a short cleanup period.

BLE and Classic Bluetooth share the ESP32 radio and can run at the same time.
The app can still report that Bluetooth streaming is active, but local playback
controls remain unavailable until the A2DP session ends.

## Status indicator

The production status indicator is one **WS2812B-V6 (LCSC C52917433)**,
a 5050 SMD, 24-bit RGB LED with GRB serial channel order. GPIO2 drives `DIN`
without an inverting transistor. NeoPixelBus uses ESP32 RMT channel 0 with
`SWEETYAAR_STATUS_LED_DATA_INVERTED=0`. The `sweetyaar-generic` environment
also uses non-inverted direct drive, but retains its existing RGBW/GRBW bench LED
and timings. Inversion remains configurable for other hardware.

These production settings require the revised direct-DIN schematic, not the old
WS2812D/MMBT3904 circuit. The schematic now connects GPIO2 through 301 Ω to DIN. Verify
logic-HIGH margin and the waveform on the assembled board: configuring polarity
and timing does not validate the electrical connection. Only the onboard pixel
receives status colors; an additional LED on `J_LED_EXT1` requires code changes,
because increasing the pixel count alone leaves additional pixels black.

`SWEETYAAR_STATUS_LED_RGBW` selects the pixel width, independently of timing. Leave it
at `0` for a 24-bit WS2812-style RGB device, or set it to `1` for a 32-bit
SK6812-style RGBW device. `SWEETYAAR_STATUS_LED_COLOR_ORDER_GRB` independently
selects the channel order:

| `RGBW` flag | `GRB` flag | Frame and channel order |
|---:|---:|---|
| `0` | `0` | 24-bit RGB |
| `0` | `1` | 24-bit GRB |
| `1` | `0` | 32-bit RGBW |
| `1` | `1` | 32-bit GRBW |

The existing yellow, green, blue, and red patterns leave the dedicated white
channel at zero, so choosing RGBW does not change their appearance. A future
pattern can set white independently; on an RGB-only build, a requested logical
white is reproduced by mixing it into red, green, and blue. Verify both frame
type and channel order against the actual LED batch.

LED pulse timing is independently configurable with PlatformIO build flags:

| Build flag | Production default | `sweetyaar-generic` |
|---|---:|---:|
| `SWEETYAAR_STATUS_LED_T0H_NS` | 300 ns | 400 ns |
| `SWEETYAAR_STATUS_LED_T1H_NS` | 650 ns | 800 ns |
| `SWEETYAAR_STATUS_LED_BIT_NS` | 1250 ns | 1250 ns |
| `SWEETYAAR_STATUS_LED_RESET_US` | 300 µs | 80 µs |

T0L and T1L are the bit period minus their respective HIGH durations. Production
therefore uses 300/950 ns for zero and 650/600 ns for one, targeting the
[WS2812B-V6 datasheet](https://datasheet.lcsc.com/datasheet/pdf/0689d8fd6dabfc7959e82552d4ffad8b.pdf?productCode=C52917433)
(V1.1, page 4): T0H = 220–380 ns; T1H, T0L and T1L = 580–1000 ns;
bit period ≥1250 ns; reset >280 µs. The former 900/350 ns one-bit pulse does
not meet the V6 minimum LOW duration. The generic environment explicitly retains
the previous SK6812 waveform. For example, change the relevant environment's
existing T0H flag to `-DSWEETYAAR_STATUS_LED_T0H_NS=350` in `build_flags`
to change that HIGH pulse (and its complementary LOW pulse). These are
compile-time settings; frame width, channel order, and inversion remain separate.
Pulse durations must be positive multiples of the RMT's 25 ns tick, with HIGH
shorter than the bit period; the bit period is limited to 65535 ns by the backend
encoding helper, and reset to 1–819 µs by its 15-bit RMT counter. These are
encoding limits, not a claim that every allowed value matches an LED protocol.
Verify actual pulse widths and voltage levels at LED `DIN` on hardware before
accepting the production LED and its wiring.

`StatusLed` applies one maximum-brightness percentage uniformly to every
available color channel, preserving each pattern's color. It defaults to 50% through
`SWEETYAAR_STATUS_LED_MAX_BRIGHTNESS_PCT`; `setMaxBrightnessPct()` can change it
at runtime and immediately redraw the current phase. Tune the default after
enclosure and diffuser testing.

Firmware components report semantic `StatusSignal` values and never write the
pixel or call `Show()` themselves. `StatusLed` resolves simultaneous signals,
owns the frame buffer and RMT transmission, and is serviced once per main-loop
pass with `statusLed.service(millis())`. Once a signal is set, its blinking
continues without further calls from the producer. This remains valid if a
Bluetooth callback later moves threads because setting a signal is atomic and
the main loop remains the only LED hardware owner.

| Condition | Pattern |
|---|---|
| Boot initialization | Solid yellow. |
| Ready/idle | Green, 1 s on / 1 s off. |
| Local song or animal playback | Green, 0.5 s on / 0.5 s off. |
| Classic Bluetooth connected but not playing | Blue, 1 s on / 1 s off. |
| Classic Bluetooth audio started | Blue, 0.5 s on / 0.5 s off. |
| Quiet time | Purple, 1 s on / 0.25 s off. |
| Persistent error after initialization | Red, 0.25 s on / 0.25 s off; currently set for SD initialization/removal failures and other persistent `error` notices. |
| Deep sleep | Off and unpowered. |

The same canonical definitions are printed at every boot, before the remaining
subsystems initialize:

```text
[LED] Mode legend:
[LED]   initialization: yellow solid
[LED]   ready/idle: green 1000ms on / 1000ms off
[LED]   local playback: green 500ms on / 500ms off
[LED]   BT connected, idle: blue 1000ms on / 1000ms off
[LED]   BT audio playing: blue 500ms on / 500ms off
[LED]   Quiet time: purple 1000ms on / 250ms off
[LED]   persistent error: red 250ms on / 250ms off
[LED]   deep sleep/off: off
```

Initialization intentionally outranks errors so boot stays yellow. Once boot
clears `Initializing`, a latched error outranks every operational state;
active Bluetooth audio outranks an idle Bluetooth connection, which in turn
outranks Quiet time, local playback, and ready. Adding a second
indicator later means setting `SWEETYAAR_STATUS_LED_PIXEL_COUNT`, wiring LED1
`DOUT` to LED2 `DIN`, and extending the controller's mapping. Producers do not
change because they still report the same semantic signals.

## Bedtime mode

Bedtime mode changes local playback during a parent-defined daily window. It
selects a bedtime song theme and caps the effective volume of both songs and
animal sounds. It does not modify the parent's normal volume setting, and it
does not affect Classic Bluetooth audio.

The ESP32 does not know the local wall-clock time after a cold boot, so the
parent app sends the current time and timezone when it connects. Once the clock
is known, the firmware enters and leaves Bedtime mode at the configured
boundaries. A parent may also override the current Daytime or Bedtime state
until the next automatic boundary or until the device reboots.

If the configured bedtime theme is missing, disabled, or empty, local songs use
the normal active theme while the volume cap remains in force. Changing the
theme while Bedtime mode is active changes the theme for that awake session.
The full settings, fallback behavior, and app presentation are documented in
the [Bedtime mode section of the mobile-app guide](mobile-app.md#bedtime-mode).

## Sleep and wake

When the toy has been inactive long enough, the firmware stops its peripherals
and puts the ESP32 into deep sleep. The normal default timeout is ten minutes.
If vibration wakes the doll but nobody presses a button or otherwise interacts
with it, the shorter default timeout of two minutes avoids leaving it awake by
accident. A connected but idle parent app is also allowed two minutes before it
stops preventing sleep. All three values can be changed in the app.

The toy does not sleep while a local file or Bluetooth stream is playing, or
while the app's ten-minute Quiet time lock is active. A connected Bluetooth
source that has stopped or suspended its audio does not keep the toy awake
forever.

Each sleep attempt first samples the normally-closed vibration switch every
20 ms for 500 ms, while the normal loop continues servicing controls and the
charger. LOW means the switch is closed at rest; HIGH means it is open. All
LOW samples permit sleep. Any HIGH sample postpones sleep and restarts the
normal idle timeout (ten minutes by default), including after a vibration-only
wake. New user activity or loss of sleep eligibility cancels the check.

If every sample is HIGH, that attempt also sends a one-time app warning that
the movement sensor may be stuck or disconnected and battery life may be
shorter. The warning uses the existing notice channel: only a connected app
receives it, with no persistent fault state or replay on reconnect. A later
sleep attempt checks again and can warn again. A stuck-closed switch cannot be
distinguished from a resting toy by this check.

Before sleeping, the firmware sends a black status-LED frame while switched 5 V
is still present, stops playback, mutes the amplifier, closes the SD, SPI, and
I2S interfaces, disables charging and the charger host watchdog, and turns off
the switched peripheral power. It then releases GPIO2 to high-impedance so it
cannot drive HIGH into the unpowered LED. The normally-closed vibration switch
and charger `/PG` are wake sources. Waking from deep sleep is a full reboot:
Bluetooth connections, the current track, loop mode, and manual Bedtime
overrides are not restored.

There is no wait for switch closure after peripheral shutdown. Movement that
begins after the check can cause an immediate wake instead of trapping the toy
awake with its peripherals off.

## How the firmware is organized

The firmware runs as one application. A small state machine makes ownership of
the speaker explicit: the device is idle, playing a song, playing an animal
sound, serving a Bluetooth stream, or locked by Quiet time. Events from the
buttons, BLE, the audio player, and Bluetooth callbacks all pass through that
state model so two audio sources cannot take control at the same time.

At startup, `main.cpp` initializes the wake state and peripheral power, loads
the device name, prepares the buttons and audio output, starts Bluetooth,
mounts and scans the SD card, and finally starts the BLE parent service. Its
main loop then polls controls, advances WAV playback, processes state changes,
publishes app status, and decides when the device may sleep.

The high-level components are:


| Component                | Responsibility                                                                           |
| ------------------------ | ---------------------------------------------------------------------------------------- |
| `firmware/esp32/src/main.cpp`           | Boot sequence and coordination between every subsystem.                                  |
| `firmware/esp32/src/StateMachine.*`     | Playback ownership, mode changes, looping, and the Quiet time timer.                     |
| `firmware/esp32/src/ButtonHandler.*`    | Debouncing the two buttons and recognizing a simultaneous press.                         |
| `firmware/esp32/src/WavPlayer.*`        | Streaming and decoding SD-card WAV files to the I2S audio output.                        |
| `firmware/esp32/src/ContentCatalog.*`   | Scanning themes and tracks, validating content, and applying content-management changes. |
| `firmware/esp32/src/BLEParentService.*` | BLE characteristics used by the parent app for controls, status, and configuration.      |
| `firmware/esp32/src/ParentConfig.*`     | Parent-editable settings loaded from `/config.json`.                                     |
| `firmware/esp32/src/NVSConfig.*`        | Device-local settings that should survive SD-card replacement.                           |
| `firmware/esp32/src/BedtimeMode.*`      | Pure rules for daily windows and manual overrides.                                       |
| `firmware/esp32/src/PeripheralPower.*`  | Power-gating behavior during boot and deep sleep.                                        |
| `firmware/esp32/src/BQ25186Charger.*`   | Fail-closed charger setup, direct I2C read-back, periodic verification, status, and watchdog handling. |
| `firmware/esp32/src/BatteryMonitor.*`   | Coarse ADC battery bands plus the charger-reported `CHARGING` override.                   |
| `firmware/esp32/src/StatusLed.*` and `StatusLedPolicy.*` | Semantic status priority, blink timing, brightness limiting, and the single addressable-LED/RMT owner. |
| `firmware/esp32/src/Config.h`           | Pin assignments, BLE identifiers, and firmware fallback values.                          |


There is no Wi-Fi setup flow or over-the-air firmware updater. The only runtime
wireless interfaces are Classic Bluetooth audio and BLE parent control.

## Building and flashing

There are two PlatformIO build environments, one per supported board design:

- `sweetyaar` is the default and targets the production SweetYaar PCB.
- `sweetyaar-generic` targets the current generic prototype board setup. It
  includes every required override, including its directly wired 32-bit
  RGBW/SK6812-style LED. Its tested channel order is GRBW, with the preserved
  400 ns T0H / 800 ns T1H / 1250 ns bit / 80 µs reset timing.

The production environment explicitly selects non-inverted, 24-bit GRB and
300 ns T0H / 650 ns T1H / 1250 ns bit / 300 µs reset timing for WS2812B-V6.
`Config.h` has matching fallback values. Both environments share only common
compiler flags through `[common]`; the generic build does not inherit production
LED flags and redefine them. If the LED selection changes, update the frame,
channel-order, inversion, and timing flags in the appropriate environment rather
than adding another target. The controller-wide brightness cap remains 50%
pending enclosure testing.

The PlatformIO board identifier is `esp32dev` for both because both use the
original ESP32-WROOM-32; that identifier is a build-system detail, not a third
hardware target or firmware application.

Set up the checked-in development environment from the repository root:

```bash
uv sync
```

Build or flash the firmware from the repository root:

```bash
# Production board (default)
make build
make flash

# Generic prototype board
make build PIO_ENV=sweetyaar-generic
make flash PIO_ENV=sweetyaar-generic
```

## Testing changes

The regression suite is intentionally broader than a firmware compile. It
checks the SD-card configuration contract, runs the state-machine and Bedtime
rules as native C++ tests, builds the production firmware, checks the parent
app, and validates its offline shell.

Run the complete suite from the repository root:

```bash
uv run python -m pytest
```

For a quicker host-only loop that omits the PlatformIO build:

```bash
uv run python -m pytest -m "not firmware"
```

Bluetooth, BLE, I2S, sleep, and physical-device behavior still require manual
testing on the intended hardware; a successful compile does not exercise the
radio, audio path, or power circuitry.

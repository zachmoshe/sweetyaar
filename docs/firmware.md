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

The checked-in `[sd_card_template](../sd_card_template/README.txt)` contains a
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

Before sleeping, the firmware stops playback, mutes the amplifier, closes the
SD, SPI, and I2S interfaces, and turns off the switched peripheral power. The
normally-closed vibration switch is the wake source. Waking from deep sleep is
a full reboot: Bluetooth connections, the current track, loop mode, and manual
Bedtime overrides are not restored.

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
| `src/main.cpp`           | Boot sequence and coordination between every subsystem.                                  |
| `src/StateMachine.*`     | Playback ownership, mode changes, looping, and the Quiet time timer.                     |
| `src/ButtonHandler.*`    | Debouncing the two buttons and recognizing a simultaneous press.                         |
| `src/WavPlayer.*`        | Streaming and decoding SD-card WAV files to the I2S audio output.                        |
| `src/ContentCatalog.*`   | Scanning themes and tracks, validating content, and applying content-management changes. |
| `src/BLEParentService.*` | BLE characteristics used by the parent app for controls, status, and configuration.      |
| `src/ParentConfig.*`     | Parent-editable settings loaded from `/config.json`.                                     |
| `src/NVSConfig.*`        | Device-local settings that should survive SD-card replacement.                           |
| `src/BedtimeMode.*`      | Pure rules for daily windows and manual overrides.                                       |
| `src/PeripheralPower.*`  | Power-gating behavior during boot and deep sleep.                                        |
| `src/Config.h`           | Pin assignments, BLE identifiers, and firmware fallback values.                          |


There is no Wi-Fi setup flow or over-the-air firmware updater. The only runtime
wireless interfaces are Classic Bluetooth audio and BLE parent control.

## Building and flashing

The production firmware is the PlatformIO `sweetyaar` environment. The board
identifier inside PlatformIO is `esp32dev` because the current target is an
original ESP32-WROOM-32 development module; that identifier is a build-system
detail, not a second firmware application.

Set up the checked-in development environment from the repository root:

```bash
uv sync
```

Build the firmware with the project's virtual environment:

```bash
/Users/zmoshe/proj/sweetyaar/.venv/bin/pio run -e sweetyaar
```

Add `-t upload` to flash a connected ESP32.

## Testing changes

The regression suite is intentionally broader than a firmware compile. It
checks the SD-card configuration contract, runs the state-machine and Bedtime
rules as native C++ tests, builds the production firmware, checks the parent
app and its offline shell, and runs real-device Bluetooth tests when their
prerequisites are available.

Run the complete suite from the repository root:

```bash
uv run python -m pytest
```

For quicker or more focused work, use the pytest markers:

```bash
# Host-side tests only: no PlatformIO build and no connected hardware.
uv run python -m pytest -m "not firmware and not hardware"

# Include the production firmware build but skip connected hardware.
uv run python -m pytest -m "not hardware"

# Run only tests that require a connected device.
uv run python -m pytest -m hardware --device-name SweetYaar --bt-address 40-22-D8-3D-8A-22
```

Hardware tests skip cleanly when USB, BLE advertising, or the required local
Bluetooth tools are unavailable. When USB is available, pytest resets the
ESP32 before BLE checks so a sleeping device can boot and advertise.

Changes to Bluetooth, BLE, I2S, SD configuration, playback state, or sleep
behavior should also be checked on the real device:

```bash
/Users/zmoshe/proj/sweetyaar/.venv/bin/python tools/mac_bt_smoke_test.py --bt-address 40-22-D8-3D-8A-22 --device-name SweetYaar
/Users/zmoshe/proj/sweetyaar/.venv/bin/python tools/ble_gatt_probe.py --name SweetYaar --control-smoke-test --config-api-test --config-round-trip-test
```

On macOS, run the Classic Bluetooth smoke test from Terminal when Bluetooth
privacy blocks `blueutil`. A successful A2DP check requires an actual
connection, correct audio routing, an `Audio state: STARTED` serial message,
and no crash or reboot; a successful compile alone does not exercise the radio
or audio path.

The BLE round-trip check temporarily changes the device name, default volume,
default theme, and sleep thresholds, verifies the values through the BLE API,
and restores the originals.
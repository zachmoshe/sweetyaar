# SweetYaar Firmware

SweetYaar is an ESP32-based audio toy designed to be installed inside a doll.
The doll has two physical buttons and works as a simple music player: one button
plays songs and the other plays animal sounds. Audio files and the toy's
configuration live on a microSD card, so the content can be changed without
rebuilding the firmware.

The same device can also work as a Bluetooth speaker. A separate parent mobile
app connects over Bluetooth Low Energy (BLE) to control local playback and
change settings. The buttons on the doll control playback and Bluetooth pairing.
Volume, theme selection, looping, content settings, Bedtime mode, and
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
| Hold both buttons for 3 seconds        | Open Bluetooth pairing for 60 seconds. |
| Continue the same hold to 10 seconds   | Forget all Bluetooth approvals, disconnect both transports, flash red once, then restore the current state's indicator. |

Physical presses are debounced for 50 ms. A single held button waits another
250 ms for the second button before starting playback; releasing a short tap
resolves it sooner. When both buttons are down, pending individual actions are
canceled and Stop fires once. If the second press comes after the grace period,
the first action may already have started, but both buttons still stop it.
Both buttons must be released before another two-button action can fire.
The 3-second pairing and 10-second reset timers start when the second button
becomes stably pressed, not when the first button is pressed.


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

Startup-ready, persistent-error and pairing cues are stored separately in the
firmware's read-only flash. Ready plays once after initialization; a startup
fault plays Error instead. A first persistent runtime fault also plays Error
once. Pairing plays when the physical gesture opens the window, then every
15 seconds until the window closes or bonds are reset. The error cue
can therefore play with no SD card. These cues use the effective local volume
(including mute and the bedtime cap), briefly take over the speaker, and then
return it to SD or Bluetooth audio. They do not disconnect Bluetooth or change
its negotiated sample rate. See [system sound assets](../../firmware/esp32/assets/sounds/README.md).

The card stores audio, content metadata, and configuration:


| Path                           | Purpose                                                             |
| ------------------------------ | ------------------------------------------------------------------- |
| `/songs/<theme>/*.wav`         | Song WAV files grouped into themes such as `lullabies` or `nature`. |
| `/songs/<theme>/metadata.json` | The theme's display name, shuffle setting, and disabled tracks.     |
| `/animals/*.wav`               | Animal-sound WAV files.                                             |
| `/animals/metadata.json`       | Shuffle and disabled-track settings for animal sounds.              |
| `/config.json`                 | Default volume and theme, Bedtime settings, and sleep settings.     |


Audio must be uncompressed PCM WAV at 44.1 kHz, 16-bit, with one (mono) or two
(stereo) channels. Mono is recommended for the single-speaker toy and halves
PCM storage. The firmware duplicates each mono sample into both I2S channels;
stereo samples pass through unchanged. The shared I2S output remains stereo for
Bluetooth compatibility. Files are streamed from the card rather than loading
a whole recording into memory. Playback reads the validated WAV data section
directly, so RIFF headers and metadata are not sent to the speaker. The channel
adapter uses a fixed 512-byte buffer without per-file decoder allocations.
At boot it scans the content once, validates the WAV files, and builds an
in-memory catalog used by playback and the parent app. Files added or removed
manually are therefore picked up after a restart; changes made through the app
also update the live catalog.

The SD mount permits two simultaneous regular files: one for WAV playback and
one for settings operations, which open their read, write, and verification files
sequentially. This saves about 12 KB of reserved FatFs cache compared with the
library's five-file default, leaving more heap for Bluetooth connection setup
without reducing audio buffering. See the
[Bluetooth heap investigation](bt-heap-investigation.md) for measurements.

The checked-in [SD-card template](../../content/sd-card-template/README.txt) contains a
complete example card with the supported layout and configuration schema. If
the card or configuration is missing, Bluetooth speaker mode still starts and
the firmware uses safe defaults where possible, but local audio cannot play
without readable content.
If `/config.json` cannot be read or is not a valid JSON object, the error LED is
set and the app's settings requests return an error asking the parent to
restore the file and restart. Firmware defaults keep the toy operational;
they are not reported as successfully loaded settings.

## Parent controls

The mobile app uses BLE, which is separate from the Classic Bluetooth connection
used for streaming music. Through BLE, a parent can see the current state,
mirror the song, animal, and stop actions, select a theme, adjust local volume,
and turn song looping on or off. The settings screen can rename the toy, choose
defaults, configure sleep and Bedtime mode, and enable or disable themes and
individual audio files.

Saved default volume and theme are applied only at boot, including a wake from
deep sleep. Settings saves preserve the current-session volume and theme.
Bedtime cap changes still take effect immediately using the current requested
volume; unrelated saves preserve manual Bedtime choices.

### Configuration transport

Update commands (`setConfig`, `setTheme`, `setSong`, `syncTime`, and
`setBedtimeMode`) return only `{id, ok: true, op}` after processing, or
`{id, ok: false, error}`. There is no full-config reply or `getConfig` command.
Config state is exposed through five required read/notify characteristics:

| UUID suffix | App name | Read value (JSON) |
| --- | --- | --- |
| `789B` | `configGeneral` | Device name, startup volume/theme, SD availability, settings-file error if present. |
| `789C` | `configSleep` | Enabled flag and the three idle timeouts. |
| `789D` | `configBedtime` | Enabled flag, start/end times, theme, volume cap. |
| `789E` | `configRuntime` | Loop, active theme, clock sample, Bedtime active/automatic/override state, effective volume/theme. |
| `789F` | `catalogNotice` | Boot catalog warning, or an empty message. Stored only in RAM. |

Replies and config-state values are serialized directly, without a temporary
ArduinoJson document. Allocation failure in such a document can otherwise yield
`{}` or partial JSON while Bluetooth and audio compete for heap. Fault-injection
tests cover both successful/error replies and all five state groups. Settings
commands release their parsed document before persistence; an unchanged device
name does not rewrite NVS or restart advertising. The browser rejects replies
without an integer request ID and boolean result immediately instead of polling
the invalid value until timeout.

All UUIDs share `a1b2c3d4-e5f6-7890-abcd-ef123456` before that suffix.
Each JSON value is at most 512 UTF-8 bytes. Config attributes and
`configResponse` notify with a **one-byte change signal**, leaving their full
readable values intact. Clients must read the characteristic after a signal;
the signal is not JSON. This works with the minimum ATT MTU as well as larger
negotiated MTUs. The app ignores value-change events caused by its own reads
([Chrome's read-event example](https://googlechrome.github.io/samples/web-bluetooth/read-characteristic-value-changed.html)),
preventing repeated reads from triggering each other. Firmware publishes changed runtime state at schedule boundaries
and manual-override expiry, even when the resulting active flag stays the same.

Catalog requests use `scanThemes` or `scanSongs`, starting with `cursor: 0`.
Responses contain `cursor`, `nextCursor`, `hasMore`, and the corresponding rows.
Follow `nextCursor` until `hasMore` is false; there is no fixed number of rows or
pages. Firmware greedily fills each response up to 512 bytes, including JSON
syntax and escaped strings. Commands must fit the 383-byte receive buffer.

At boot, catalog validation rejects entries that cannot fit a single scan row
or their update command, reserving space for the largest numeric fields and
flags. A theme ID must also fit the 63-byte live-theme buffer and at most 126
JSON string bytes. Device names permit 32 UTF-8 bytes and at most 64 escaped
bytes. Display-name and song-filename limits depend on their actual encoded
response envelope, rather than a fixed character count. Rejected entries are
excluded from playback and scans. Serial logs identify every rejected entry;
the app receives a bounded warning with the first shortened name and a count.
Oversized theme references in `config.json` fall back to firmware defaults.

Most content settings are saved in `/config.json` or the relevant theme's
`metadata.json` on the SD card. The Bluetooth device name is different: it is
stored in the ESP32's non-volatile storage so replacing the card does not rename
the toy.

SD JSON saves write a sibling `.tmp` file first, flush and close it, and compare
the serializer's byte count and the resulting file size with the expected
length. They do not reread or reparse the saved contents for verification.
Only after those checks does firmware remove the previous file and rename the
temporary file into place. Write, size-check, removal, and rename failures are
reported to the app. No backup or automatic recovery is kept: power loss
between removal and rename can leave the configuration missing, which is an
accepted failure case. A later save truncates any leftover temporary file.
Settings updates also fail if the existing JSON cannot be loaded, rather than
silently replacing it with a partial set of defaults.

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

Battery sensing is configured after the higher-current boot work. `begin()`
returns without waiting or reading the ADC; `poll()` takes the first reading
on the first loop iteration and four more at least 100 ms apart. Each call takes
at most one reading, so buttons, BLE, and playback continue between samples.
BLE initially reports `UNKNOWN`. If all five readings are valid, their mean
seeds the rolling window and the new state is published through the normal
change notification. Otherwise the state remains `UNKNOWN` until a valid
periodic reading. One new sample is added every 30 seconds after the final
startup reading; the window grows to ten samples, or about five minutes, and
stays at that size. The startup mean counts once rather than five times.

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

`ChargerStatus` is a separate interpretation layer above register decoding. It
combines the reported charge phase with verified communication, valid input
power, and the firmware's `/CE` command. `BQ25186Charger::status()` exposes the
result; `[Charger status] time=<local date and time> STATUS=<value>` is
printed initially and when the interpreted value changes.

| Interpreted status | Meaning |
|---|---|
| `UNKNOWN` | No valid observation, or waiting for a read after enabling charging. |
| `NO_INPUT` | The latest valid observation reports no usable external power. |
| `DISABLED` | External power is valid, but firmware has commanded charging off. |
| `NOT_CHARGING` | Charging is enabled and the chip reports that it is not charging. |
| `CHARGING` | Charging is enabled and the chip reports either CC or CV charging. |
| `FINISHED` | Charging is enabled and a subsequent read reports charge completion. |

Every `/CE` transition invalidates the sampled charge phase for interpretation
until another successful read. This prevents the `DONE_OR_HOST_DISABLED` value
read during startup or configuration recovery from becoming `FINISHED` merely
because firmware enables charging afterwards. Confirmation comes through the
normal interrupt/periodic read path. Failed reads produce `UNKNOWN`; removing
input produces `NO_INPUT`, including when the chip still reports the combined
done/disabled value. `FINISHED` describes the completed charge cycle, not a
measured state-of-charge percentage, and is not latched across recharge.
Charging activity is separate from simultaneous faults and limiting conditions.
`BQ25186Charger::snapshot()` combines them for the app; the detailed field logs
below retain the raw decoded observations.

The read/notify charger characteristic
`a1b2c3d4-e5f6-7890-abcd-ef12345678a0` carries a complete six-byte snapshot:

| Byte | Meaning |
|---|---|
| 0 | Format version, currently `1`. |
| 1 | Activity: `0` unknown, `1` no input, `2` disabled, `3` not charging, `4` charging, `5` finished. |
| 2 | Bit 0: charger hardware available; bit 1: observations valid. |
| 3–4 | Little-endian condition mask, using `ChargerStatus::Condition`. |
| 5 | Reported-event mask: bit 0 reflects `BAT_OCP_FAULT` in the latest successful register read. |

Condition bits 0–10 are temperature out of range, temperature-reduced charging,
open temperature sensor, input-current limiting, system-voltage limiting,
input-voltage limiting, thermal regulation, input overvoltage, battery
undervoltage, safety-timer expiration, and supervision failure, respectively.
Activity and conditions are independent, so several limits may be shown together.
Failed supervision invalidates the observations and sets only supervision failure.
The battery-overcurrent message and safety-timer warning follow the latest sampled
bits: a reported 1 shows the condition and a reported 0 removes it. Firmware does
not latch either indication across reads or infer whether the hardware recovered.
The snapshot stays unchanged between successful reads; sampling is periodic and
interrupt-driven. Earlier events remain available in the serial log.

Firmware updates the readable snapshot even while disconnected and notifies only
when its bytes change, respecting the existing Classic-Bluetooth settle interval.
The whole value fits the minimum ATT notification payload. The app subscribes,
then reads once, and applies subsequent notifications directly. Manual Refresh
reads the latest firmware snapshot; it does not trigger an extra I2C transaction.
The generic board reports `[1, 0, 0, 0, 0, 0]` (unavailable).

Charger status, register, decoded-state, and event logs use local timestamps in
`YYYY-MM-DD HH:MM:SS` format, using the clock and timezone offset synchronized
by the parent app (also retained through deep sleep). Before synchronization
on a cold boot, they print `time=UNKNOWN`.

Serial prints `[Charger registers] time=<local date and time> STAT0=0x.. STAT1=0x.. FLAG0=0x.. PG=...`
on the first complete successful read, when any of the three full register bytes
or the physical `/PG` input changes, and after recovery from a failed read.
The hexadecimal bytes preserve every bit, including reserved/wake bits and
`FLAG0` transitions back to zero. Incomplete reads do not print a register snapshot.

Serial also prints a complete `[Charger state] time=<local date and time> ...`
snapshot on the first successful read, whenever a reported field changes, and
on recovery after a failed read. Identical periodic or interrupt-triggered
reads do not repeat these snapshots. Each decoded snapshot contains `CHARGE_STATUS`, `TEMP_STATUS`,
`TS_OPEN_STAT`, `VIN_OVP_STAT`, `BUVLO_STAT`, `SAFETY_TMR_FAULT_FLAG`,
`VIN_PGOOD_STAT`, `ILIM_ACTIVE_STAT`, `VDPPM_ACTIVE_STAT`,
`VINDPM_ACTIVE_STAT`, `THERMREG_ACTIVE_STAT`, and the physical `/PG` input.
The charging values are `NOT_CHARGING`, `CHARGING_CONSTANT_CURRENT`,
`CHARGING_CONSTANT_VOLTAGE`, and `DONE_OR_HOST_DISABLED`. Temperature values
are `NORMAL`, `HOT_OR_COLD_CHARGING_SUSPENDED`, `COOL_REDUCED_CURRENT`, and
`WARM_REDUCED_VOLTAGE`. The combined values preserve what the chip can actually
distinguish. Limiting/fault status uses `ACTIVE`/`INACTIVE`; input power uses
`VALID_INPUT`/`NO_VALID_INPUT`. These names describe the sampled register values,
not a measured battery temperature.

`FLAG0` changes appear in the raw register log without triggering the decoded
state log. Nonzero flags also produce a separate `[Charger events]` line listing
`TS_FAULT`, `ILIM_ACTIVE_FLAG`, `VDPPM_ACTIVE_FLAG`, `VINDPM_ACTIVE_FLAG`,
`THERMREG_ACTIVE_FLAG`, `VIN_OVP_FAULT_FLAG`, `BUVLO_FAULT_FLAG`, and/or
`BAT_OCP_FAULT`. This preserves evidence of short events that may have ended
before the live status read, including battery overcurrent, which has no
separate live status bit. Reasserted flags do not necessarily mean a new event.
Reserved and unused TS/MR wake flags do not trigger state logs. The safety-timer
indication in `STAT1` remains visible as `DETECTED`/`NOT_REPORTED`: TI marks it
read-to-clear, but clearing the charging fault requires a `/CE`, charge-enable,
or input-power toggle. Reading zero is not proof that charging recovered.
See the [BQ25186 datasheet, sections 6.3.8.7 and 6.5.1.1–6.5.1.3](https://www.ti.com/lit/ds/symlink/bq25186.pdf).
Timestamps represent successful sampling time, not the exact instant of a
hardware transition; interrupt handling and periodic reads cannot reconstruct
every rapid fluctuation. The app shows the interpreted activity and conditions
alongside the separate coarse battery-level characteristic.

Two independent hang detectors protect this flow. The ESP32 task watchdog
registers Arduino `loop()` on CPU1 alongside the already watched CPU0 idle task;
the current ESP-IDF configuration uses a five-second timeout. While awake, the
BQ25186 40-second host watchdog requires continuing I2C traffic and power-cycles
`SYS` if traffic stops. The charger watchdog is disabled only immediately before
intentional deep sleep, after a final direct read-back.

## Bluetooth pairing and remote ownership

Boot and wake start with pairing closed. Previously approved phones can reconnect
while the toy is awake; a new phone needs the physical three-second gesture.
Fresh Classic and BLE pairing requests require an open window even from a
previously bonded address; saved-key authentication on an ordinary reconnect
does not require that grant. This
admission policy does not guarantee bond preservation against unsolicited
re-pairing: the bundled Bluetooth stack can clear keys before or during rejection.
The window lasts a full 60 seconds from opening, even if audio and BLE both
connect. A connection neither closes nor extends it. The LED blinks blue at
200 ms on / 200 ms off throughout the window, even while Classic audio plays or
BLE is connected. This is faster than playback's 500 ms on / 500 ms off. When
the window closes, the indicator returns to the current operating state. BLE
remote connections alone do not change the light: local idle/playback remain
green, and Quiet time remains purple. Normal blue indicates Classic audio.

The ten-second gesture is measured from the start of the same hold. It cancels
the window, deletes the stack bonds, and disconnects both
transports. The indicator flashes red for 250 ms and then resumes the current
state's pattern, normally green idle. Quiet time, playback, and errors remain
visible afterward, even if both buttons are still held. Both buttons must be
released before another hold can begin: holding continuously for 13 seconds
only performs the reset once.
These gestures also work during Classic audio and Quiet time. The toy stays
awake while pairing is open or both buttons are held.

Classic audio and BLE use their respective Bluetooth bond stores as the sole
persistent source of trust; there are no separate application approval lists.
This ESP32 stack does not automatically enroll one transport by pairing the other: enroll the
phone once through its Bluetooth audio settings and once through the parent
app, during the same window or separate windows. Bonds survive reboot and
SD-card changes; their capacity and replacement are managed by the stack.
After a reset, the phone may also need to forget the old pairing before enrolling
again. On upgrade from the approval-list firmware, only bonds with matching
legacy approvals are retained; an older firmware with no approval metadata
requires enrollment again. The legacy lists are deleted after migration.

Both transports use Just Works (no displayed/typed number). The phone may still
ask the parent to tap Pair. Classic's private ESP-IDF 4.4.7 adapter sets
pairability on the Bluetooth task and intercepts `BTA_DmConfirm`, including
Bluedroid's automatic Just Works confirmation. It refuses fresh pairing outside
the window. A2DP requires successful stack authentication; bond-address membership
alone never proves possession of a key. Pairing finishing after the deadline is
rejected and its new bond removed. The adapter is guarded against SDK upgrades;
revalidate its private ABI and linker wrapping before changing the SDK.

Reset persists a pending-deletion marker before disconnecting. Access remains
disabled until both transports have disconnected and bond-store snapshots confirm
deletion. Removal is retried, and a reboot resumes an unfinished reset. This
marker stores no device identities or keys. Migration uses the same closed-access
period. A storage failure leaves access disabled and is logged.

BLE keeps advertising while a controller is connected. The most recently
connected phone that successfully authenticates becomes the controller. An
unapproved phone can enroll only during the window; afterward only approved,
bonded phones can take over. The previous controller immediately loses command
access, receives the notice `{"type":"takeover"}`, and is disconnected after
indication confirmation and a short delivery grace, or a bounded fallback delay.
The app displays **Someone else took control.** and does not automatically
reconnect. BLE private addresses are resolved through saved bond identities so
an approved phone remains recognizable when its address rotates. Enrollment and
handoff briefly use multiple BLE links, then release the displaced connection.

The authorization checks run before GATT reads, writes, and subscriptions reach
Arduino BLE. Notifications target the current controller, and pending commands
and prepared writes are discarded when ownership changes. Bluetooth bonding
supplies remembered keys; the button-controlled window authorizes new enrollment.

The public read-only `access` characteristic (`...78A1`) returns one byte for
the requesting connection: `0` pairing required, `1` authentication pending,
`2` authenticated controller, `3` authentication failed, or `4` taken over.
It exposes no settings or control data. Rejected peers have up to ten seconds
to read the reason before firmware disconnects them; the app reads it before
accessing controls and disconnects immediately after displaying a refusal.
All other application characteristics remain protected throughout that grace.
While authentication is pending, the app makes one encrypted status read to
initiate client-side bonding/encryption. Firmware does not also send a
peripheral Security Request on connection; competing initiators can cause
duplicate Android pairing dialogs. Approval still requires AUTH_CMPL and the
normal enrollment policy. An encrypted request that reaches the application
before approval receives insufficient authorization (0x08), not a request
to repeat authentication (0x05).
The app waits for pending authentication, supports older firmware without this
diagnostic, and never translates a generic discovery failure into proof that
the firmware needs upgrading.

Connection diagnostics are always printed to serial. `t=` is milliseconds since
boot, `peer=` is the Bluetooth address, and BLE `conn=` identifies that link.
`65535` in an owner/connection field means none or unmatched. The principal events
are:

| Log event | What it establishes |
|---|---|
| `[BLE] CONNECT` | A BLE link reached the device; includes bond presence, window state, and initial decision. |
| `[BLE] SECURITY_REQUEST` | A peer security request arrived; `result=0x0` means the response API accepted the operation, not that authentication finished. |
| `[BLE] AUTH` | Authentication completed; includes stack success, raw failure code, negotiated mode, and the admission decision. |
| `[Access] Bonds ready` | Bond migration or reset completed; lists Classic/BLE bond counts. |
| `[BT] JUST_WORKS_REQUEST` | The SDK requested fresh pairing; records the pairing-window decision without keys or codes. |
| `[BLE] CONTROL` | The authenticated connection and selected controller. |
| `[BLE] AUTH_TIMEOUT` / `DISCONNECT` | Authentication exceeded its deadline/window, or a link ended; includes timing or the disconnect reason. |
| `[BT] ACL_CONNECT` / `PAIRING_REQUEST` / `AUTH_COMPLETE` | Classic link arrival, pairing decision, and authentication result. |
| `[BT] A2DP_CONNECTION` / `A2DP_REJECT` | Audio-profile connection progress or approval rejection. |
| `[BT] SCAN_MODE` | Whether Classic accepts connections and permits discovery/pairing. |
| `[BLE] ADVERTISING ... failed` | BLE advertising could not start/stop; includes the stack status. |

No keys or passcodes are printed. Attribute reads/writes, key-exchange steps,
and successful advertising callbacks are not logged. Requests rejected by the
phone or controller before a link/security callback reaches the application
cannot produce an application connection log; absence of `CONNECT`/`ACL_CONNECT`
alone does not identify the cause on the phone.

## Bluetooth speaker mode

During pairing, SweetYaar is discoverable as a Classic Bluetooth A2DP speaker, so a phone, tablet,
or computer can send it ordinary system audio. Connecting an A2DP source stops
any local WAV playback and gives the stream exclusive use of the speaker.

While the A2DP connection is active, physical-button playback and parent-app
playback controls are ignored rather than saved for later. The streaming device
owns the stream volume; the toy's local volume setting only affects WAV files
from the SD card. When the source disconnects, the firmware returns to idle and
accepts another approved source after a short cleanup period (or a new source
if pairing is still open). There is one Classic audio connection at a time.
Opening pairing does not interrupt it: disconnect the current audio source on
its phone before connecting another.

Leaving Bluetooth mode mutes the amplifier and restores the shared audio output
to 44.1 kHz, stereo, 16-bit PCM before local playback resumes, including a return
through Quiet time. This prevents a 48 kHz Bluetooth session from speeding up
the SD card's 44.1 kHz WAV files. The sample-rate update retains the audio buffers.

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
WS2812D/MMBT3904 circuit. GPIO2 connects to DIN through the 330 Ω `R_LED_DIN1`
series resistor (LCSC C23138). Verify logic-HIGH margin and the waveform on the
assembled board: configuring polarity and timing does not validate the electrical
connection. Only the onboard pixel receives status colors; an additional LED on
`J_LED_EXT1` requires code changes, because increasing the pixel count alone
leaves additional pixels black.

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
| BLE controller connected without Classic audio | Keep the normal local idle/playback or Quiet time pattern. |
| Classic Bluetooth audio started | Blue, 0.5 s on / 0.5 s off. |
| Pairing window open, including during BT playback or BLE control | Blue, 0.2 s on / 0.2 s off throughout the window. |
| Bluetooth approvals cleared | Red once for 250 ms, then restore the current state's pattern. |
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
[LED]   pairing window open: blue 200ms on / 200ms off
[LED]   Bluetooth approvals cleared: red once for 250ms, then current state
[LED]   deep sleep/off: off
```

Initialization intentionally outranks errors so boot stays yellow. Once boot
clears `Initializing`, pairing feedback outranks playback, connections, and errors, and a latched error
outranks other operational states. Reset feedback has highest priority for its
single 250 ms flash, then normal state indication resumes;
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
boundaries. The synchronized clock and timezone are retained through deep sleep
after either vibration (EXT0) or charger-power (EXT1) wake, provided the retained
clock-valid marker is present. A cold boot still requires time synchronization.
A parent may also override the current Daytime or Bedtime state
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
| `firmware/esp32/src/PairingPolicy.h` | Three/ten-second gestures, release rearming, and the 60-second window. |
| `firmware/esp32/src/BluetoothAccess.*` and `BleIdentity.h` | Bond lookup, private-address resolution, one-time legacy migration, and durable reset. |
| `firmware/esp32/src/ClassicBluetooth.*` | Classic Just Works pairing gate and transient authenticated-link state. |
| `firmware/esp32/src/ApprovedA2DPSink.h` | Classic pairing admission, discoverability, and approved audio sessions. |
| `firmware/esp32/src/WavPlayer.*`        | Streaming validated SD-card WAV PCM to the I2S audio output.                            |
| `firmware/esp32/src/WavPcmOutput.h`     | Fixed-buffer mono duplication and stereo passthrough before volume control.             |
| `firmware/esp32/src/SystemSoundOutput.*` and `SystemSoundAssets.cpp` | Embedded ready/error/pairing cues and synchronized speaker ownership. |
| `firmware/esp32/src/ContentCatalog.*`   | Scanning themes and tracks, validating content, and applying content-management changes. |
| `firmware/esp32/src/BLEParentService.*` | BLE characteristics used by the parent app for controls, status, and configuration.      |
| `firmware/esp32/src/ParentConfig.*`     | Parent-editable settings loaded from `/config.json`.                                     |
| `firmware/esp32/src/JsonFile.cpp`       | Shared JSON loading and length-checked temporary-file saves for settings and metadata. |
| `firmware/esp32/src/NVSConfig.*`        | Device-local settings that should survive SD-card replacement.                           |
| `firmware/esp32/src/BedtimeMode.*`      | Pure rules for daily windows and manual overrides.                                       |
| `firmware/esp32/src/PeripheralPower.*`  | Power-gating behavior during boot and deep sleep.                                        |
| `firmware/esp32/src/BQ25186Charger.*`   | Fail-closed charger setup, direct I2C read-back, periodic verification, status, and watchdog handling. |
| `firmware/esp32/src/ChargerStatus.*`   | Interprets charge phase, host enable, input power, and observation validity into a usable charging status. |
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

### BLE deployment checklist

Run this after deploying firmware or a parent-app change involving Bluetooth.
`make flash` prints a reminder after a successful upload.

1. Disconnect the parent app before flashing. Deploy the matching app when the
   BLE contract changes, incrementing `CACHE_VERSION` in `app/public/sw.js`.
   Reload the app online so it loads the deployed version.
2. Hold both buttons for three seconds to enroll a new phone, then connect from
   Chrome or Edge. Verify the theme selector, clock/Bedtime state,
   Settings load and content scans. Commands use `configCommand`
   (`a1b2c3d4-e5f6-7890-abcd-ef1234567897`) and `configResponse`
   (`a1b2c3d4-e5f6-7890-abcd-ef1234567898`). Both and the five config state
   attributes (`789B`–`789F`) are required. Confirm subscriptions before saving,
   clock sync, and Bedtime toggles. `themes` contains the theme array; `command` accepts only
   one-byte playback commands. There is no older-GATT transport fallback.
3. Disconnect and reconnect **without rebooting the toy**. Verify that the theme
   selector still contains the same choices after clock synchronization and a
   Settings visit. Confirm a song plays, stop works, and no reboot occurs.
   Also leave the app connected across a Bedtime boundary: the mode and volume
   cap should update without a settings command. Confirm that changes still
   arrive after Classic Bluetooth streaming ends.
4. Check Classic Bluetooth audio on the intended hardware: confirm audio routing,
   `Audio state: STARTED` in the serial log, and playback without a crash/reboot.
5. Verify a new phone cannot enroll after boot or after the 60-second deadline.
   The matching app should show **Device not approved** and the three-second
   pairing instruction, without loading controls or asking for a firmware upgrade.
   Enroll audio and BLE during one window; neither success should close it.
   Confirm approved devices reconnect after the deadline and after reboot,
   including a BLE phone using a changed private address.
6. With BLE phone A controlling, connect B and then C. Each authenticated arrival
   takes over; the old app shows **Someone else took control.**, disables controls,
   and does not reconnect itself. A failed or unapproved attempt must leave the
   existing controller working. Repeat during Classic audio; playback should
   remain stable and app playback controls should stay disabled.
7. Keep Classic source A connected while opening pairing: B must wait until A
   disconnects manually. The blue blink must immediately speed up to 200 ms
   on / 200 ms off and remain fast for the full window. Then check B can connect
   in the remaining window. At timeout it must return to the normal playback or
   connected cadence. For each attempted connection inspect `CONNECT`/`ACL_CONNECT`,
   authentication results, and the approval decision before diagnosing an app failure.
8. Hold both buttons continuously for 13 seconds. Expect pairing at three seconds,
   a single red flash at ten, both links disconnected and approvals erased, then
   the current state indication (normally green idle) after 250 ms, and no
   reopening at thirteen. Verify Quiet time and errors also remain visible after
   the flash. Releasing only one button must not rearm; release
   both before trying another three-second hold. Confirm old phones require
   enrollment again, including after a reboot.

#### macOS recovery when characteristics are missing

Use this during deployment when the GATT table has changed or the app reports
missing characteristics despite the correct firmware being installed. Routine
flashes with an unchanged GATT table do not require forgetting the device.

1. Disconnect the app and close its tabs or installed-app window. Power the toy
   off while removing its remembered connection.
2. Open **System Settings → Bluetooth**, Control-click the toy's saved entry and
   choose **Forget** (or **Forget This Device**, depending on macOS). Use the name
   under which it was paired, which may still be `SweetYaar Remote` after a rename.
   If it has no saved entry, skip this step. Apple documents device removal in
   [Connect a Bluetooth device with your Mac](https://support.apple.com/guide/mac-help/connect-a-bluetooth-device-blth1004/mac).
3. Power the toy on, hold both buttons for three seconds, reopen the current app and select it again in the Bluetooth
   chooser. Pair it again in macOS when testing Classic Bluetooth audio.
4. If the same characteristics are still missing, try turning the Mac's Bluetooth
   off and on, then reconnect; restart the Mac if that does not help. Toggling
   Bluetooth temporarily disconnects other Bluetooth peripherals.
5. Repeat the deployment checks above. Treat successful discovery of both config
   characteristics and a successful Settings request as the verification, not
   completion of the reset steps alone.

These are recovery steps, not a guaranteed per-device GATT-cache flush: Apple's
Forget documentation does not promise one. Removing a browser's Bluetooth
permission or updating the app's service-worker cache also does not establish
that CoreBluetooth rediscovered the device's services. For future GATT schema
changes, validate the standard **Service Changed** indication on macOS; Apple
recommends it for accessories that support GATT caching
([Core Bluetooth, WWDC 2017, slide 88](https://devstreaming-cdn.apple.com/videos/wwdc/2017/712jqzhsxoww3zn/712/712_whats_new_in_core_bluetooth.pdf)).
This checklist does not claim that the current firmware sends that indication.

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

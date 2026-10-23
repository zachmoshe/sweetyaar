# Charger connection cue auditions — 2026-10-23

Three short felt-piano alternatives from the first charging-cue audition round.
Option 3, Upward nudge, was initially selected and tested, then replaced by
**Sunrise from the [second audition round](charger-happy-sound-options.md)**.
The files below and the initial validation record are retained for reference.
They reuse the isolated C5 strike from the existing Bluetooth pairing sound,
with the same resampling and smooth note endings used for the battery auditions.

| Option | Character | Notes | Duration |
| --- | --- | --- | --- |
| 1. Soft lift | Quick, light confirmation | C5–E5 | 0.538 s |
| 2. Warm chord | Softly rolled major chord | G4–B4–D5, overlapping | 0.454 s |
| 3. Upward nudge | Two taps, then a higher note | E4–E4–G4 | 0.628 s |

Option 3 shares the repeated-note rhythm of the
selected battery warning (G4–G4–E4) but rises at the end. The short duration
keeps the interruption brief and limits the additional flash asset size.

The WAVs and reproducible generator are in
[`content/system-sounds/charger-options`](../../content/system-sounds/charger-options/).
All are 44.1 kHz, 16-bit mono PCM. The target RMS is 0.085 and the peak ceiling
is 0.35 full scale, close to the existing cue levels. `manifest.json` records
the measured duration, RMS, peak and byte size. No external recordings or
third-party instrument samples were used.

Regenerate with the project Python environment:

```sh
.venv/bin/python content/system-sounds/charger-options/generate.py
```

## Selected trigger

Play once per cable connection after valid input (`STAT0.VIN_PGOOD_STAT`) and
active charging (`ChargerStatus::State::Charging`) are confirmed, including
power-on or wake while plugged in. A full battery that never begins charging
does not trigger it. A connection initially prevented from charging can sound
once when charging first starts. Once consumed, temperature/current pauses and
resumption cannot replay it. Only a healthy observation of absent input re-arms
the cue; failed I2C reads do not count as unplugging.

Valid input suppresses the battery cue even while charging is paused or finished.
It discards pending battery warnings and stops any warning in progress before
the charger cue plays. Charger takes precedence over Battery; Ready, Pairing
and Error finish first. Both power cues respect volume zero, consuming muted
events rather than replaying them when volume rises. See the
[firmware specification](firmware.md) for the complete behavior.

Use the same speaker ownership as existing cues: pause/resume local WAV audio;
consume Bluetooth PCM during the cue, then resume the live stream without
disconnecting. The generic prototype has no BQ25186 charger-presence detection.

Host audio checks cover PCM format, duration, peak headroom, finite samples,
silent endpoints and deterministic regeneration. Native tests exercise the
production trigger with battery filtering, charger observations and recorded
audio/BLE boundaries, and render both power cues during concurrent Bluetooth
writes. The production-board charger-trigger check is recorded below; broader
audio/Bluetooth coexistence still requires device validation.

## Integration checks — 2026-10-23

- `make test-unit`: 155 passed; the two firmware build tests were excluded.
- `make build` and `make build PIO_ENV=sweetyaar-generic`: passed.
- Selected battery and charger WAVs match their auditions byte-for-byte.
- Host scenarios cover startup/wake priority, MEDIUM/LOW transitions with input
  present, waiting for charging confirmation after `/CE`, charge pauses and
  resumption, unplug/replug, I2C failure/recovery, mute, generic-board behavior,
  and queued/active battery-warning suppression.
- Production `firmware.bin` is 1,957,376 bytes in the 1,966,080-byte OTA slot,
  leaving 8,704 bytes (8.5 KiB). Future firmware/assets have little room to grow.
- Initial integration checks were host-only. The subsequent approved device
  investigation is recorded below.

## Production-board investigation — 2026-10-23

The user reported no cue after uploading firmware and connecting the charger.
The board identified the BQ25186 and correctly reported valid input followed by
`STATUS=CHARGING`, but no charger sound request appeared. `esptool verify_flash`
confirmed that the installed application exactly matched the older main-checkout
binary (1,827,600 bytes), which did not contain the selected charger WAV.
The cue implementation was in the separate `codex/charger-sound-options`
worktree. No trigger-code change was needed.

With the user's approval, flashed the production `sweetyaar` build from that
worktree to `/dev/cu.usbserial-14320`; upload hash verification passed. Opening
the serial monitor restarted this board, so the captured boot is a real boot
with the cable already attached, not a deep-sleep wake.

Observed in the serial trace (timestamps UTC on 2026-10-22):

- 21:35:45.869: interpreted `CHARGING`; 21:35:46.800: `Playing charger`, after
  `Playing ready`. Exactly one charger cue was requested for this boot.
- 21:36:08.833: `NO_INPUT` after unplugging.
- 21:36:12.350: `CHARGING` after reconnecting; 21:36:12.356: `Playing charger`.
  Exactly one new request followed the new connection.
- 21:36:38.215: another `NO_INPUT`; 21:36:40.473: `CHARGING`, followed by one
  `Playing charger` at 21:36:40.479. Across boot and both reconnections there
  were three cue requests, with no extra requests while input stayed present,
  audio-output failures, crash reports, or unexpected reboots through 21:36:46.
- The battery was GOOD without input (about 3.9 V), so this session did not
  exercise real MEDIUM/LOW suppression.

The user confirmed hearing the cue, but reported crackling/gaps/distortion on
the toy compared with the embedded WAV preview. Audible playback quality is
therefore **not validated**. At 21:37:47 input was removed; at 21:37:51 the serial
stream ended with a partial `Brow` message. A later reset produced no boot log.
This may be a power interruption; whether the toy was switched off has not yet
been confirmed. Do not infer that the successful trigger fixed the audio issue.

A separate `codex/power-cue-playback` worktree contains a diagnostic build that
records cue duration, feed count, maximum feed gap, and output sample rate once
after each cue completes. It adds no per-buffer serial logging and changes no
audio buffers, cue samples, charger settings, or playback policy. The production
build passed; the diagnostic image has not yet been flashed.

Logs are retained under `tools/bt_smoke_logs/charger-cue-20261023/` in the
charger worktree: `serial-before.log`, `verify-before.log`, `flash.log`, and
`serial-after.log`. No host Bluetooth session was run. Thermal/current pause
and resume, deep-sleep wake, MEDIUM/LOW precedence, and local/Classic audio
resumption with BLE connected remain untested on hardware.

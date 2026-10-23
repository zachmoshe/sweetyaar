# Battery cue auditions — 2026-10-22

Three alternatives for a cue when the battery drops from `GOOD` to `MEDIUM`
or from `MEDIUM` to `LOW`. **Selected: option 3's first (medium) sound,
for all battery cues.** It is embedded once as `firmware/esp32/assets/sounds/battery.wav`,
with only all-zero edge silence trimmed and every audible sample preserved.
The other auditions remain available for reference.

The final trigger is every public status change into `MEDIUM` or `LOW`, including
the first medium/low reading after power-on or wake, while charger input is absent.
Valid input suppresses warnings even when charging is paused or finished, clears
pending warnings, and stops a warning in progress. The Sunrise charger cue takes precedence.
An invalid charger observation also suppresses warnings until input is known.
Stable readings do not
repeat the cue; `GOOD`, `CHARGING` and `UNKNOWN` stay silent and cancel pending
warnings. Local playback and Bluetooth streaming do not suppress
it; an active startup/pairing/error cue finishes first. Bluetooth music is
briefly replaced, with the connection maintained; overlay mixing is not enabled.

The current ready, pairing and error assets are short felt-piano cues. Their
approximate note patterns are G4–B4–D5, G4–C5, and D4–D4 respectively. These
candidates reuse the isolated C5 strike from the existing pairing asset,
repitched and arranged with smooth note endings. There are no new external
samples, services, or recordings.

The original audition pairs each have a gentler medium cue and a lower-register
low cue. Only the first sound in option 3 is used in firmware.

| Option | Character | GOOD → MEDIUM | MEDIUM → LOW |
| --- | --- | --- | --- |
| 1. Falling pair | Simple, brief reminder | B4–G4, 0.678 s | G4–E4, 0.738 s |
| 2. Little staircase | More melodic descent | D5–B4–G4, 0.778 s | B4–G4–E4, 0.868 s |
| 3. Gentle nudge | Repeated taps, then a lower note | G4–G4–E4, 0.838 s | E4–E4–C4, 0.908 s |

The selected G4–G4–E4 pattern uses two short taps followed by a lower note.
It has the same pitches, timing, and gain for every battery event. Subjective
playback on the toy has not been validated.

## Files and listening order

Assets and the reproducible generator live in
[`content/system-sounds/battery-options`](../../content/system-sounds/battery-options/).
Each option has separate `*-medium.wav` and `*-low.wav` assets, plus a
`*-preview.wav` containing **medium, a 1.10-second gap, then low**.
`manifest.json` records each file's measured duration, peak, RMS and byte size.

The files use the existing 44.1 kHz, 16-bit mono PCM WAV format. Existing system
cues measure about 0.09 RMS; candidates target 0.082 RMS for medium and 0.09 for
low, with a 0.35 peak ceiling. Urgency comes mainly from pitch and rhythm.
Preview files include extra silence for comparison and are not intended for
firmware embedding.

Regenerate from the checkout root with its project environment:

```sh
.venv/bin/python content/system-sounds/battery-options/generate.py
```

Host verification checks WAV format, finite/unclipped PCM, silent endpoints,
durations, and preview ordering. No flashing or hardware test was performed.
The selected cue's event handling is documented in [firmware](firmware.md).
Hardware validation of the battery transitions and audio coexistence is pending.

## Integration checks — 2026-10-23

These checks predate the silence trim. The current embedded asset preserves
the same audible PCM; see [the cue feed investigation](cue-feed-validation.md)
for subsequent playback changes and validation.

- Before charger integration, `make test-unit`: 153 passed, with the two firmware builds excluded.
- `make build`: passed for both `sweetyaar` and `sweetyaar-generic`.
- The embedded WAV matches `03-gentle-nudge-medium.wav` byte-for-byte. Native
  tests render every sample at 44.1/48 kHz and verify volume, mute, priorities,
  Bluetooth write suppression, and audio resumption.
- Real battery-filter/handler tests cover first readings after power-on/wake,
  medium/low transitions in both directions, silent charging, leaving charging, no
  repeat within a status, waiting behind the startup cue, cancellation when
  returning to GOOD or starting charging, and BLE independence.
- Not hardware-validated: audible battery transitions, local/Classic audio
  resumption with BLE connected, `Audio state: STARTED`, and no crash/reboot.

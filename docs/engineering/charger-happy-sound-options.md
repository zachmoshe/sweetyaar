# Happier charging cues — 2026-10-23

This is a second audition round after the user asked for a happier charging
sound. **Selected: option 1, Sunrise.** It was embedded unchanged for the selected-pair
flash below. After diagnosing playback starvation with a temporary Ready copy,
production now uses Sunrise again, with only all-zero edge silence trimmed.
See [the comparison record](charger-ready-validation.md) and
[cue feed investigation](cue-feed-validation.md) for the subsequent fix.
The previous E4–E4–G4 audition remains available for reference.
These previews use the existing felt-piano voice with major-chord melodies,
overlapping tails and gentler attacks. The selected battery cue remains
**Gentle nudge**, G4–G4–E4, shared by MEDIUM and LOW warnings.

| Option | Character | Notes | Duration |
| --- | --- | --- | --- |
| 1. Sunrise | Simple, bright upward confirmation | C5–E5–G5 | 0.638 s |
| 2. Little celebration | More playful, four rising notes | G4–B4–D5–G5 | 0.698 s |
| 3. Smiling finish | Upward leap, then a warm landing | C5–G5–E5, soft C5 harmony | 0.668 s |

Option 1 is the recommended starting point: its rising major triad makes the
charging confirmation clear, while keeping the interruption short. Option 2
is more exuberant; option 3 is gentler and more melodic.

Files and the reproducible generator are in
[`content/system-sounds/charger-happy-options`](../../content/system-sounds/charger-happy-options/).
All use 44.1 kHz, 16-bit mono PCM WAV. Target RMS is 0.080 and peak ceiling is
0.30 full scale. Note releases fade the actual pitched sample before zero
padding, and overlapping note tails avoid repeated isolated taps.
The piano source is the isolated C5 strike from the existing pairing cue;
no external recordings or third-party instrument samples were added.

Regenerate with the project Python environment:

```sh
.venv/bin/python content/system-sounds/charger-happy-options/generate.py
```

Each original alternative is below 0.7 seconds. The untrimmed Sunrise WAV is
56,316 bytes. Current firmware embeds its trimmed 43,658-byte version and the
trimmed 67,394-byte battery asset.

The existing valid-input/charging trigger and battery-warning precedence remain
the intended behavior. The user confirmed that the normal ready cue sounds
clean on the device, but reported extra distortion in the previous charger cue
compared with its preview. These alternatives do not establish that the device
playback issue is fixed. Hardware audition and audio routing checks remain
necessary. An approved flashing session follows the selection; its result is
recorded below when complete.

Host checks cover PCM format, sample counts, peak headroom, silent endpoints,
smooth sample transitions, deterministic regeneration and exact identity with
the selected audition samples.

Both embedded power cues have the same technical WAV format as the working
Ready/Error/Pairing cues: RIFF/WAVE, format code 1 (uncompressed PCM), 44,100 Hz,
one channel, 16-bit signed little-endian samples, block alignment 2 and byte
rate 88,200. The shared output duplicates mono into stereo. The exact audition
samples are preserved; peak levels leave more digital headroom than Ready,
and both begin and end at silence. Format checks do not establish subjective
device playback quality.

## Selected-pair integration — 2026-10-23

- `make test-unit`: 155 passed; two firmware build tests excluded.
- `make build PIO_ENV=sweetyaar`: passed. Final image size is 1,958,272 bytes,
  leaving 7,808 bytes in the 1,966,080-byte OTA slot.
- Both selected WAV byte sequences occur exactly once in the firmware image.
- All five embedded WAVs have byte-identical `fmt ` chunks. Battery peaks at
  −11.19 dBFS and Sunrise at −10.46 dBFS, compared with Ready at −8.98 dBFS.
  Their RMS levels are −21.72, −23.70 and −20.92 dBFS respectively. Selection
  did not change the audition samples or normalize them again.
- Native output tests render both cues at 44.1/48 kHz, check exact mono-to-stereo
  duplication, volume/mute handling, priorities, and concurrent Bluetooth write
  suppression/resumption. These host checks do not substitute for listening on
  the device.

The user approved flashing both selected cues. The connected device identified
the production board and BQ25186, and `make flash PIO_ENV=sweetyaar
SERIAL_PORT=/dev/cu.usbserial-14320` succeeded with upload hash verification.
The flashed image SHA-256 is
`1f0d9b419005e18570f5ae3fba73a5e017f7c470288df650999e7a8a48d767af`.
Post-flash serial capture reached `[Boot] Ready.`, played Ready, and reported
GOOD battery (about 3.9 V) with no charger input. The installed image contains
Sunrise and Gentle nudge, not the separate experimental timing instrumentation.

Session logs and the format comparison are retained in this worktree under
`tools/bt_smoke_logs/sunrise-20261023/`. The real LOW/MEDIUM transition and
Bluetooth coexistence were not exercised in this flashing session; host tests
cover their logic and PCM ownership. The user confirmed Sunrise played, but
reported continued distortion. Normal Ready playback was reported clean.

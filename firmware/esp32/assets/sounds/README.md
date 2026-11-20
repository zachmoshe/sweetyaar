# System sounds

The charger cue is the selected Sunrise recording. All five embedded cues have their all-zero
leading/trailing PCM trimmed, retaining one zero frame at each endpoint and
every audible sample. Charger plays once per confirmed input connection.
The main loop yields for 1 ms during cue playback, matching SD playback and
avoiding starvation under frequent charger interrupts.
Each file is an uncompressed **44.1 kHz, 16-bit mono PCM WAV**.

| File | Intended event | Duration | File size |
| --- | --- | --- | --- |
| `ready.wav` | Initialization completed | 0.723 s | 63,842 bytes |
| `error.wav` | An error prevents normal operation | 0.631 s | 55,706 bytes |
| `pairing.wav` | Bluetooth pairing window opened | 0.630 s | 55,568 bytes |
| `battery.wav` | Battery status changes into MEDIUM or LOW without charger input | 0.764 s | 67,394 bytes |
| `charger.wav` | Valid charger input with charging confirmed (Sunrise) | 0.494 s | 43,658 bytes |

Total: **286,168 bytes (279.5 KiB)**. The original recordings had identical
stereo channels. Storing one channel and duplicating it for output reproduces
the selected sound samples exactly.

These files are embedded directly in the application's read-only flash through
`board_build.embed_files`. They need no SD card or separate filesystem upload:

```ini
board_build.embed_files =
    assets/sounds/ready.wav
    assets/sounds/error.wav
    assets/sounds/pairing.wav
    assets/sounds/battery.wav
    assets/sounds/charger.wav
```

`SystemSoundOutput` reads the embedded PCM directly with a small output buffer:

- Ready plays once after initialization, including a reboot from deep sleep.
- A persistent startup fault plays Error instead of Ready. A first persistent
  runtime fault also plays Error once; a latched fault does not repeat the cue.
- Pairing plays once when the physical gesture opens a pairing window.
- Battery uses one shared G4–G4–E4 cue for each change into `MEDIUM` or `LOW`,
  including the first medium/low reading after power-on or wake.
  Stable readings and `GOOD`/`CHARGING`/`UNKNOWN` are silent. It waits for active
  system cues to finish; changing to one of those silent states clears a pending
  warning.
  Local playback and Bluetooth streaming do not suppress it.
- Charger uses Sunrise once per valid-input connection, after
  active charging is confirmed, including boot/wake with a cable attached.
  A healthy observation of absent input re-arms it. Charging pauses/resumptions
  and charger read failures do not. It waits for other system cues to finish.
  Valid input suppresses Battery even when charging is paused or finished;
  it clears a pending warning and stops any remaining warning samples.
  Unknown charger input also suppresses warnings. Charger has precedence,
  so these power cues cannot be queued together.

Cues use the effective local volume, including the bedtime cap and volume zero.
When SD initialization fails, the firmware's default volume still works. A cue
temporarily owns the speaker: SD playback pauses at its current sample, while
Bluetooth packets continue to be consumed without playing or building a backlog.
Both return to normal after the cue. Bluetooth's negotiated sample rate is
preserved; the cue is resampled when needed. No full sound is copied to RAM, and
the existing I2S/A2DP buffer reservations are unchanged.

These cues are original to SweetYaar; no third-party samples or recordings
are used. To change a cue, replace its WAV here (same format) and update the
table above.

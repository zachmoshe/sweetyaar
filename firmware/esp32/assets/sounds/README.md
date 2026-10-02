# System sounds

These are the selected felt-piano cues, at 1.25x tempo with unchanged pitches.
Each file is an uncompressed **44.1 kHz, 16-bit mono PCM WAV**.

| File | Intended event | Duration | File size |
| --- | --- | --- | --- |
| `ready.wav` | Initialization completed | 0.768 s | 67,782 bytes |
| `error.wav` | An error prevents normal operation | 0.672 s | 59,314 bytes |
| `pairing.wav` | Bluetooth pairing window opened | 0.672 s | 59,314 bytes |

Total: **186,410 bytes (182.0 KiB)**. The original recordings had identical
stereo channels. Storing one channel and duplicating it for output reproduces
the selected sound samples exactly.

These files are embedded directly in the application's read-only flash through
`board_build.embed_files`. They need no SD card or separate filesystem upload:

```ini
board_build.embed_files =
    assets/sounds/ready.wav
    assets/sounds/error.wav
    assets/sounds/pairing.wav
```

`SystemSoundOutput` reads the embedded PCM directly with a small output buffer:

- Ready plays once after initialization, including a reboot from deep sleep.
- A persistent startup fault plays Error instead of Ready. A first persistent
  runtime fault also plays Error once; a latched fault does not repeat the cue.
- Pairing plays when the physical gesture opens a pairing window, then every
  15 seconds while it remains open (normally at 0, 15, 30 and 45 seconds).

Cues use the effective local volume, including the bedtime cap and volume zero.
When SD initialization fails, the firmware's default volume still works. A cue
temporarily owns the speaker: SD playback pauses at its current sample, while
Bluetooth packets continue to be consumed without playing or building a backlog.
Both return to normal after the cue. Bluetooth's negotiated sample rate is
preserved; the cue is resampled when needed. No full sound is copied to RAM, and
the existing I2S/A2DP buffer reservations are unchanged.

These original cues were synthesized for SweetYaar; no third-party instrument
samples or recordings were used. The sound-design alternatives are retained in
the separate `codex/status-sound-options` worktree.

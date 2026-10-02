# Embedded system sounds — 2026-10-02

Implementation branch: `codex/wav-mono-stereo`. The embedded ready/error/pairing
cues build on this branch's mono/stereo playback implementation.

## Host validation

The initial cue implementation passed all 130 host tests and both firmware
builds. After adding the 15-second pairing repeat, all seven focused sound,
Bluetooth access and audio handoff tests passed, as did `make build` for both
`sweetyaar` and `sweetyaar-generic`. The cue tests execute the real startup/error
handlers and pairing polling function.

New coverage includes:

- Every PCM sample of all three actual assets, mono duplication, volume scaling
  and silence through the existing DMA queue before amplifier shutdown.
- 44.1/48 kHz output, preserved cue duration, and format changes during a cue.
- Concurrent Bluetooth writes being consumed without entering the cue output,
  then normal audio passing through after completion.
- Startup error replacing Ready, repeated errors not restarting/repeating the
  cue, pairing/error priorities, mute, malformed assets and short output writes.
- Pairing cues at opening and 15/30/45 seconds, no repeat at the 60-second
  deadline or after reset, reopening, blocked pairing and timer wraparound.
- Existing Bluetooth-to-local mono/stereo handoff and settings regressions.
- Actual flash symbols for all three WAV assets linked into the production ELF.

Final application images (include all three WAVs):

| Environment | Image bytes | Available per OTA slot |
| --- | ---: | ---: |
| `sweetyaar` | 1,824,496 | 1,966,080 |
| `sweetyaar-generic` | 1,804,048 | 1,966,080 |

Generic SHA-256:
`3923294939516d345ba915042dd1518f9389d5fa024188026e2531136bf36da1`

Production SHA-256:
`257e2b1d7bcf677adbf632d3ba2de38834b4f73505ef2da958873fb4c979c592`

## Hardware validation

Not yet flashed or tested on hardware in this session. Awaiting explicit
approval to flash the generic ESP32 prototype and check:

1. Ready once after normal boot; songs/animals still play afterward.
2. Pairing when the three-second gesture opens the window, then every 15
   seconds while open; no repeat at timeout or after the reset gesture.
3. Pairing during Classic audio, followed by uninterrupted connection and
   resumption of audio; BLE remains usable.
4. Error instead of Ready when booting without an SD card; only once per boot.
5. Restoring the SD card and rebooting returns to normal startup/playback.

The previous mono/stereo hardware validation predates these cues and does not
validate this new image. Existing A2DP/I2S buffer reservations are unchanged.

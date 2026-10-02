# Mono/stereo WAV validation — 2026-10-02

User-approved session on the generic ESP32 prototype (`sweetyaar-generic`),
USB `/dev/cu.usbserial-14320`, named Yaaruli. Its boot log reports Classic
address `1C:C3:AB:F5:C0:E6`. The Mac provided BLE controls and Classic audio.

The normal application firmware was restored after a temporary fixture writer
added an SD test theme. All playback checks below ran on the normal build,
without test hooks or debug-only firmware code. Flashed binary SHA-256:

`356507ead552642adc131ae884c341b76c5eddffe06c43b033a23513498f0319`

## Host checks

All **130 tests passed**, including the production and generic firmware builds.
After the final adapter-constructor cleanup, the affected PCM/handoff tests and
both builds passed again (four pytest cases).

Native tests check exact mono duplication, distinct stereo samples, volume
scaling, arbitrary byte boundaries, metadata chunks, complete first/last PCM
samples, truncated input and short output writes. Audio handoff tests cover
both 44.1 and 48 kHz A2DP configurations returning to local playback.

All 15 SD-template recordings were converted to 44.1 kHz, 16-bit mono, with
frame counts and every output PCM sample verified against the originals. The
original stereo files remain in the main checkout; the mono copies are in this
worktree's SD template. WAV template assets remain Git-ignored.

## Device checks

The added theme is `SD:/songs/audio-format-test-20261002`, displayed as
**Audio format test**. It contains two 2-second, 44.1 kHz, 16-bit PCM files:

| File | Format | Size | Contents |
| --- | --- | --- | --- |
| `01 Mono.wav` | Mono | 176,444 bytes | Three rising notes, duplicated by the firmware for stereo I2S. |
| `02 Stereo.wav` | Stereo | 352,844 bytes | Three rising notes: left only, right only, then both channels. |

The existing songs, SD configuration and Bluetooth bonds were preserved. The
new theme remains on the card for repeat testing. The final audible run used
100% local volume with fixture samples capped at 12% full scale, then restored
the original 40% volume and `nature` theme. Looping was turned off afterward.

| Check | Result |
| --- | --- |
| Boot and saved BLE pairing | Passed; pairing closed, protected reads authenticated with saved keys. |
| Catalog validation | Both fixtures accepted with correct file sizes and 2,000 ms durations. |
| Mono followed by stereo | Passed; natural mono EOF advanced to stereo, stereo EOF returned to idle. |
| Classic reconnect with BLE still connected | Passed with saved bond, pairing closed; BLE status reported BT connected. |
| Targeted Classic audio | Five-second tone completed on Yaaruli; firmware reported `STARTED`, then `REMOTE_SUSPEND`. |
| Local playback after Classic disconnect | Both mono and stereo completed again and returned to idle. |
| Stability and cleanup | No crash, reboot, PCM read failure or audio-output write failure. Original theme, volume and Mac output restored; Mac connections closed. |
| Listening observation | User confirmed both three-note clips, the Bluetooth tone, and both clips after disconnect all played clearly. |

The Mac negotiated **44.1 kHz** for this hardware run. The 48 kHz handoff has
native-test coverage, but was not exercised over the radio in this session.
This records the listed audio flows, not a new full Bluetooth pairing/reset
or power-management certification. System-cue embedding and automatic cue
playback remain unimplemented and were not tested.

## Local evidence and test-runner corrections

Raw logs, the one-session probe and reports are retained in the ignored
`tools/bt_smoke_logs/` directory:

- `20261002-mono-boot/`: saved BLE reconnect on the new firmware.
- `20261002-fixture-upload.log`: temporary SD fixture writer upload.
- `20261002-mono-final-upload.log`: normal firmware restored successfully.
- `20261002-mono-playback-final/`: successful seven-check report, serial log
  and targeted Bluetooth tone.
- `mono_playback_probe.py`: the session's Mac control/playback probe.
- `mono-fixture-writer/`: temporary writer source and PlatformIO configuration.

Two earlier runs stopped on host-test assumptions, without firmware failures.
macOS automatically selected the toy as its default output and started A2DP
before the test tone, so a check waiting for a new `STARTED` event timed out.
Restoring the Mac's previous output paused A2DP with `REMOTE_SUSPEND`, rather
than the runner's initially expected `STOPPED`. The final probe accepts either
inactive state, then requires a fresh `STARTED` for the targeted tone. The user
also found the original test level too faint, so the final run raised only
the test levels and restored the user's settings afterward.

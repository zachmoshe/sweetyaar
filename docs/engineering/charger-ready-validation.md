# Charger cue using the Ready WAV — 2026-10-23

Historical record: production now uses trimmed Sunrise once per connection.
The eventual fix and restoration are recorded in
[the cue feed investigation](cue-feed-validation.md).

This is a temporary diagnostic branch (`codex/charger-ready-control`). Sunrise
remains the selected charger sound; the user reported that it still sounded
distorted on the toy and requested the known-good Ready recording through the
existing charger playback path.

`firmware/esp32/assets/sounds/charger.wav` is a byte-for-byte copy of
`ready.wav`: 67,782 bytes, 33,869 frames, mono 44.1 kHz signed 16-bit PCM.
Both files have SHA-256
`a1e3b3f88ce15701adafa38c009951023be49d0ad1f2b50e75dac5de26552616`.
The charger event still selects `SystemSound::Charger` and its own embedded
asset. All 43 source files and `platformio.ini` are unchanged from the flashed
Sunrise integration. There is no timing instrumentation in this comparison.

## Initial build and checks

- Production build completed, but its final binary was **1,969,728 bytes**,
  exceeding the **1,966,080-byte** application slot by **3,648 bytes**. This
  oversized image was not flashed. PlatformIO's reported linked-code usage
  excludes some image overhead, so its build success was not sufficient.
- The image contained two complete copies of the exact Ready WAV.
- `tests/test_system_sounds.py`: **2 passed**, covering the native PCM output
  and asset/trigger wiring. This is a host check, not an audio-quality result.
- The battery recording has 4,504 bytes of trailing all-zero PCM, enough to
  make room by removing 46 ms of silence. This would retain all audible
  battery samples, both complete Ready copies and unchanged firmware code.
  The user approved that additional asset adjustment and flashing.

## Approved comparison image

Only 2,029 trailing all-zero battery frames (46.009 ms, 4,058 bytes) were
removed. The remaining PCM is an exact prefix of the selected battery recording;
all nonzero samples are preserved. The RIFF/data lengths were updated. The
complete Ready and charger files remain byte-identical, and source code and
build configuration remain unchanged.

The rebuilt production image is **1,965,680 bytes**, leaving **400 bytes** in
the existing application slot. No partition changes were made. Its SHA-256 is
`4f2418f6efba5d6ce4ca1a383cdaf5d919203f3f8185fbd992b29c6b03ab18e0`.
The image contains both complete Ready WAV copies and the trimmed battery WAV.
The same two native output/wiring checks passed again after the silent trim.

## Hardware status

The initial upload at 460,800 baud stopped responding near 94%. Retrying the
same application image at 115,200 baud succeeded with flash hash verification.
No firmware code, partition layout, or persistent settings were changed for
the retry.

The production board rebooted normally, identified BQ25186, reached
`[Boot] Ready.`, and logged `[Sound] Playing ready`. At boot it reported no
charger input and GOOD battery (about 3.893 V), with no crash in the observed
startup. Serial capture remains active for the requested cable-insertion test.
The user reported that this exact Ready copy **still sounded distorted** when
triggered by charging. Serial recorded charger plays after confirmed charging
at 15:17:03 and 15:17:11 UTC. This points away from Sunrise's unique waveform
as the sole cause; the power-transient hypothesis remains unmeasured. Bluetooth
streaming/coexistence and real LOW/MEDIUM transitions were not exercised in this
comparison session.

The user previously reported Sunrise distortion and a clean normal Ready cue.
This comparison does not by itself identify the root cause. It is superseded
by [the requested five-play diagnostic](charger-repeat-validation.md), which
also trims silent PCM at the edges of all cue files.

Build, upload, image-verification and serial logs are retained under
`tools/bt_smoke_logs/charger-ready-control-20261023/` in this worktree.

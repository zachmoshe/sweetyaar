# Five-play charger diagnostic — 2026-10-23

Historical record: the five-play sequence and Ready copy have been removed.
Production uses trimmed Sunrise once per connection; see
[the cue feed investigation](cue-feed-validation.md) for the scheduling fix.

After the exact Ready WAV also distorted when triggered by charging, the user
requested five plays after cable insertion to compare the initial charging
transition with later playback. The user also requested silence trims and
inline previews for all cue files. This branch is a temporary diagnostic;
the intended production charging policy remains once per connection.

The first play uses the existing valid-input plus confirmed-charging trigger.
Four more plays follow, separated by at least one second after the previous
system cue (including its DMA drain) has finished. The timer does not block the
main loop, charger polls, Bluetooth or audio service. Confirmed unplug cancels
the remaining repetitions and re-arms a new sequence. Uncertain charger input
pauses repeats; recovery and thermal/current pauses do not restart a sequence.
Other active system cues finish before the gap is counted again. Valid input
continues to suppress all low-battery warnings. No charger electrical settings,
amplifier settings, PCM mixer, or audio buffer reservations are changed.

`charger.wav` remains an exact copy of Ready after both are trimmed. All five
embedded assets remove only leading/trailing all-zero PCM, retaining one zero
frame at each endpoint and all intervening samples. They remain 44.1 kHz,
16-bit mono PCM. The five assets total 306,352 bytes, saving 17,738 bytes against
the previous diagnostic image's assets. A separate trimmed Sunrise preview is
0.49449 seconds and is not embedded in this comparison image.

Original audition WAVs remain available. Their generators now use the preserved
untrimmed pairing reference so existing note extraction offsets remain valid.
Trimmed previews and exact sample counts/hashes are in
`content/system-sounds/trimmed/manifest.json`.

## Validation

- Production build passed: 1,948,176 bytes, with 17,904 bytes free in the
  existing application slot. SHA-256:
  `d4e44ae88d161e5d5396029e9360ec4e486fbd23a1816be52c8d9d51ed499f4f`.
- Host regression suite: 156 passed, two firmware build tests excluded.
- All retained PCM and WAV formats were verified against the original files;
  the image contains two complete copies of the trimmed Ready recording.
- Regenerated all 15 original audition WAVs using the preserved pairing
  reference; all were byte-identical to their existing files.

The timing checks cover exactly five requests, full gaps, timer rollover,
unplug cancellation, read failure/recovery and other active system cues.
This diagnostic cannot establish a rail voltage dip without a measurement.

The first upload at 115,200 baud stopped responding near 33%. Retrying the same
application image at the same speed succeeded with flash hash verification.
This repeated upload interruption also occurred in the preceding comparison
session; its cause is not established.

The production board rebooted with valid input, detected BQ25186, confirmed
charging, and logged exactly five charger playback starts after Ready at
15:29:32.587, 15:29:34.452, 15:29:36.359, 15:29:38.285 and 15:29:40.140 UTC.
No crash or audio-output failure appeared during this observed sequence.
The user reported **later plays are distorted too**. The symptom is therefore
not confined to the first second after input connection; a brief plug-in
transient alone does not explain it. Sustained power-path conditions and
playback scheduling remain unmeasured possibilities, not diagnoses.

After the five cues, serial also recorded an A2DP connection at 44.1 kHz,
`Audio state: STARTED` at 15:30:07, and a clean stop/disconnect with subsequent
connection availability. No crash appeared in that interval. This establishes
an observed connection/stream lifecycle, not subjective audio quality or cue
interruption during streaming. BLE coexistence and physical LOW/MEDIUM
transitions were not exercised. Logs, build/test output and image verification
are retained under `tools/bt_smoke_logs/charger-repeat-20261023/`.

# Cue feed timing investigation — 2026-10-23

The diagnostic configurations below are historical. Production retains the
1 ms cue yield and restores trimmed Sunrise once per connection, with timing
counters and the five-play sequence removed.

The user reports clean Bluetooth streaming and SD songs while charging, but
distortion through the charger-cue mechanism, including an exact copy of the
normally clean Ready sound and later plays in a five-play sequence. This
narrows the investigation to differences in cue handling; it does not prove an
electrical fault is impossible.

## Code-path comparison

- Bluetooth PCM has a separate queue-draining task writing to the shared
  `SystemSoundOutput`/I2S endpoint.
- SD playback and cues both feed from the main loop. SD reads 2,048 source
  bytes per call (512 stereo frames or 1,024 mono frames) and gets a 1 ms loop
  yield. A cue renders 512 stereo frames per call, but while SD is idle the
  loop still yields for 5 ms. At 44.1 kHz each cue block covers 11.61 ms.
- Before audio feeding, charger polling may verify ten configuration registers
  and read three status/event registers over 100 kHz I2C. Charger limit events
  can trigger this work between the ten-second periodic checks.
- The existing six 512-frame DMA buffers and 8 KB Bluetooth queue are unchanged.
  The native PCM tests cover correctness but do not model real I2C/loop timing.

The first diagnostic keeps the five-play Ready-as-Charger sequence and all
audio/charger behavior unchanged. It accumulates feed intervals, time spent
servicing audio, and charger polling time, then prints one summary after each
cue. No per-loop or per-packet serial output is added.

## Initial checks

- Production build passed; image is 1,948,576 bytes.
- Focused native PCM and battery/charger event tests: 10 passed.
- Image SHA-256:
  `383b93cc268641e962a249752078b06679414fea56a9d7139737e8bf1c422b80`.

## Measured baseline and scheduling change

The timing-only image flashed successfully at 460,800 baud after a 921,600-baud
connection attempt failed before writing flash. Boot while charging produced
one Ready and five charger timing summaries. Charger cues used 69 feeds each:

| Measurement | Observed range |
| --- | --- |
| Cue service completion after request | 820.147–837.147 ms |
| Largest interval between feed starts | 12.987–13.589 ms |
| Time spent in charger polling per cue | 415.380–427.998 ms |
| Long charger polls per cue | 66–68 |
| Largest charger poll | 6.401–6.421 ms |
| Total time in render/I2S service per cue | 25.465–25.820 ms |

The WAV plus its 3,072-frame DMA drain supplies 34,971 frames, or 792.993 ms at
44.1 kHz. The accumulated polling cost plus 5 ms sleep per loop exceeds the
available feed budget; the I2S queue does not build the nominal 70 ms reserve.
The measurements strongly support cue starvation. This remains distinct from
a direct DMA-underflow trace or subjective confirmation of the fix.

The scheduling fix changes the loop yield to 1 ms whenever either a cue or SD
playback is active, retaining 5 ms only while both are idle. The sound data,
charger settings, amplifier logic, six DMA buffers and 8 KB Bluetooth queue
are unchanged. Timing summaries remain enabled for comparison. Ready, battery,
charger, pairing and error share this servicing path; there is no evidence
that the other cue types are inherently immune under the same charging load.

The fixed image builds successfully (1,948,592 bytes; 17,488 bytes free) and
the ten focused native tests pass. Image SHA-256:
`c7d3832e2284200fa8ae3b11e9c3e5c7cd57e89c5430746221e0313a36325762`.

## Hardware result with 1 ms cue yield

The fixed image flashed successfully at 460,800 baud, with flash hash
verification. The production board booted with valid charger input and played
Ready followed by all five charger repetitions without a crash or audio-output
failure. The user confirmed: "now all of them sound good".

| Measurement | Observed range across five charger plays |
| --- | --- |
| Cue service completion after request | 730.178–749.949 ms |
| Largest interval between feed starts | 12.694–18.956 ms |
| Time spent in charger polling per cue | 405.854–438.370 ms |
| Long charger polls per cue | 63–68 |
| Largest charger poll | 6.546–6.652 ms |
| Total time in render/I2S service per cue | 180.767–206.628 ms |

The occasional largest feed gaps did not shrink. Instead, reducing the routine
yield creates time to fill the I2S queue between those gaps. Increased time in
I2S service is consistent with writes waiting for space in a filled queue.
Service-completion timing measures enqueueing, not the final sample leaving
the speaker, so it can be shorter than the total submitted audio duration.

Passed: production build, ten focused native tests, successful flash/boot,
five charger-triggered Ready repetitions, and user listening confirmation.
Failed baseline: distorted charger-triggered playback with the 5 ms idle yield.
Not retested after the scheduling change: actual Sunrise and battery WAVs,
Bluetooth-to-cue handoff, SD-to-cue handoff, and Bluetooth/BLE coexistence.
The user's clean Bluetooth/SD observations preceded this fix. That diagnostic firmware
still uses the temporary Ready copy and five-play diagnostic configuration.

Logs, images and parsed timing data are retained locally under the ignored
`tools/bt_smoke_logs/cue-feed-20261023/` directory.

## Frequent charger interrupts

During the measured cues the main loop serviced approximately 80–92 full
charger polls per second. This is not a count of raw interrupt pulses: the ISR
sets a boolean, so multiple pulses can coalesce. Each poll verifies ten
configuration registers and reads three status/event registers. The driver
already suppresses routine current/voltage/thermal limit events from serial
logging, but still enables their interrupts and performs the I2C work.

TI documents ILIM interrupts and masks them by default; this firmware's
`CHARGECTRL1=0xD0` explicitly enables them. The configured 1 A charge target
and 1.05 A total input limit leave only 50 mA for the system if full charging
current were sustained, making frequent limiting plausible under toy load.
This is an inference from settings and status, not a measured current trace
or proof that every interrupt came from ILIM. TI does not specify the observed
interrupt rate in the cited sections.

TI explicitly states that masking the ILIM interrupt leaves current limiting
operational. A potential follow-up is to mask routine regulation notifications
while retaining periodic status reads and important input/charge/fault events.
No charger configuration or polling changes were made in this investigation.
References: [ILIM control, section 6.3.7](https://www.ti.com/lit/ds/symlink/bq25186.pdf#page=18),
[interrupts, section 6.3.13](https://www.ti.com/lit/ds/symlink/bq25186.pdf#page=24),
and [CHARGECTRL1, table 6-16](https://www.ti.com/lit/ds/symlink/bq25186.pdf#page=35).

## Production restoration on main — 2026-10-23

At the user's request, restored the selected Sunrise asset, removed the
five-play sequence and timing instrumentation, and retained the 1 ms cue yield.
All five embedded WAVs remain 44.1 kHz, 16-bit mono PCM with only all-zero edge
silence removed. Sunrise is byte-identical to the trimmed audition preview;
every asset appears exactly once in the application image. Charger limits,
interrupt masks, buffer reservations and amplifier control are unchanged.

- `make test-unit`: 156 passed, two firmware builds excluded.
- `make build PIO_ENV=sweetyaar`: passed. The initial sandboxed invocation
  could not open PlatformIO's global lock file; the permitted retry succeeded.
- Final image: 1,927,760 bytes, leaving 38,320 bytes in the existing OTA slot.
  SHA-256: `0ac0dfd16042ae3b84e31f4c58e2e8fae086009a527e3a4d365108030601aa00`.
- `make flash PIO_ENV=sweetyaar SERIAL_PORT=/dev/cu.usbserial-14320`: passed
  at 460,800 baud with flash hash verification.
- Production-board startup reached Ready with valid charger input, then
  requested Charger once after confirmed charging. During the 22-second serial
  capture, input became absent and then valid again; one further Charger
  request followed the new charging confirmation. No extra repetitions,
  audio-output failures, crashes or subsequent boots appeared in that window.
- Subjective listening to restored Sunrise, real MEDIUM/LOW transitions,
  SD/Bluetooth cue interruption and BLE coexistence were not freshly confirmed.
  The successful listening result above applies to the Ready-copy timing test.

Restoration build, test, flash and serial logs and the application image are
retained locally under `tools/bt_smoke_logs/power-cues-main-20261023/`.

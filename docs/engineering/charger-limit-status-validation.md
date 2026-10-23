# Charger regulation notifications — 2026-10-23–24

The user requested that expected current limiting remain visible as current
status without producing dozens of transient events per second. The preceding
[cue investigation](cue-feed-validation.md) measured approximately 80–92 full
charger polls per second while limiting; its 1 ms audio-service fix remains.

## Notification policy and status sampling

- `CHARGECTRL1` changes from `0xD0` to `0xD7`: mask charging-phase, ILIM and
  VINDPM/VDPPM interrupts; retain the same OCP/UVLO settings. The initial `0xD3`
  version left charging-phase interrupts enabled and failed the device-rate
  check below.
- `MASK_ID` changes from `0x01` to `0x41`: mask thermal-regulation interrupts;
  retain TS, battery-protection and input-good/overvoltage interrupts.
- Charge-current, input-current, voltage, thermal and battery-temperature
  limits, safety timer, charger watchdog and ESP32 watchdog remain unchanged.
- Read the three status/event registers once per second, keeping the existing
  BLE condition bits current. These are latest sampled conditions, not latched
  regulation events or a measure of time spent limiting. Important unmasked
  events can refresh the snapshot sooner. The app already presents current
  limiting as an informational detail, so its format and code are unchanged.
- Charging activity and completion also update on this cadence. Confirming
  charging after enabling `/CE`, and playing the plug-in cue, can take about
  one second. Input-good and fault interrupts remain enabled.
- Preserve full configuration read-back every ten seconds and on unmasked
  interrupts. Status-only sampling cannot postpone it. A failed read disables
  charging; recovery verifies the full policy before re-enabling `/CE`.
- Routine limit flags remain excluded from serial event/change logging. Real
  fault flags retain their separate event records. No periodic audit logging
  remains in the production source.

TI explicitly distinguishes ILIM interrupt masking from the limiter itself:
[section 6.3.7](https://www.ti.com/lit/ds/symlink/bq25186.pdf#page=18).
The notification controls are documented in
[section 6.3.13](https://www.ti.com/lit/ds/symlink/bq25186.pdf#page=24),
[CHARGECTRL1](https://www.ti.com/lit/ds/symlink/bq25186.pdf#page=35) and
[MASK_ID](https://www.ti.com/lit/ds/symlink/bq25186.pdf#page=41).

## Host validation

- Production build passed: 1,927,840 bytes, leaving 38,240 bytes in the existing
  application partition. SHA-256:
  `de340f50f7f4874c72acaa719fe8aa17af012a03de227961a01c4273967b21e1`.
- `make test-unit`: 156 passed, two firmware build tests excluded.
- Native driver tests cover mask values with unchanged protection thresholds,
  one-second live sampling through rapid limit-bit changes, absence of limit
  event logs, live-limit clearing, immediate real-fault handling, independent
  ten-second verification, periodic fail-closed recovery and timer rollover.
  The final run also covers charging, completion and recharge updates without
  phase interrupts. The production rebuild after removing audit counters is
  byte-identical to the tested build and has no audit log string.
- The initial full host run started before this fresh worktree's first build
  had finished installing its pinned libraries. Dependency lookup failures
  cleared after the build completed; the full rerun passed.

## Device validation

The first upload attempt on October 23 failed before writing flash because the
ESP32 did not respond. The user deferred hardware tests, then authorized a new
session on October 24 (local date; logs use October 23 UTC).

The serial boot confirmed the production PCB and BQ25186. All uploads in this
session use `/dev/cu.usbserial-14320`, 460800 baud, application offset `0x10000`;
the existing partition table and settings are preserved. Temporary diagnostic
images add only aggregate IRQ/poll/timing counts once per ten seconds.

### Initial mask failed the rate check

With `CHARGECTRL1=0xD3`, the charger alternated between constant-current and
constant-voltage phases. Nineteen charging windows recorded 162–560 IRQs/sec
and up to 43 full polls/sec. Most complete windows spent about 2.8–3.1 seconds
of each ten seconds servicing the driver, including synchronous status logs.
No-input operation had zero IRQs. This showed that masking regulation-only
notifications was insufficient. The user corrected their initial listening
reply: Sunrise (the charger cue, distinct from Ready) was disrupted.

The correction masks charging-phase interrupts too (`0xD7`), as described by
TI's `CHG_STATUS_INT_MASK`; it does not change the charging algorithm or any
protection threshold. The second audit image is 1,928,224 bytes, SHA-256
`80a571ddb4b99a2d544ce83033b42684f1e1acf28da0a223ec5cf5c91d564435`.

### Corrected mask measurements

Twenty windows covering 207.888 seconds of charging record zero IRQs, 208
status polls and 20 full configuration checks. Ordinary ten-second windows consume
about 22 ms of driver service time in total. Health remains valid. The boot
sequence confirms charging after enabling `/CE` and queues one Sunrise cue
after Ready. The user confirmed the corrected charger cue sounds clean.

An authenticated BLE connection using the existing bond completed 67 valid
charger reads over 70.55 seconds and a notification subscription, with activity
`CHARGING`. This initial interval did not observe an active limit or a cable
transition; it establishes readability, not those transition cases.

Classic reconnect and a five-second targeted audio file passed the transport
check, including `Audio state: STARTED`, a 44.1 kHz route and return to idle
after disconnect. A preliminary connection closed before an output appeared;
the subsequent attempt played successfully. The temporary Python harness also
needed its missing constructor arguments corrected before that successful run.
macOS automatically selected the toy on connection; after disconnect the
original `BuiltInSpeakerDevice` output was restored and verified.

An SD song then ran for 25 seconds under BLE control, with 24 valid charger
reads and successful stop/return to idle. Audit windows covering BT and SD
playback still reported zero IRQs. No additional boot, panic, watchdog reset,
supervision failure or configuration recovery appeared in this capture.
These are playback/transport observations; subjective BT/SD audio quality was
not independently confirmed during this session.

Session evidence is under
`tools/bt_smoke_logs/charger-limit-status-20261024/` in this worktree, including
`audit-summary.json`, flash/build logs, serial captures and BLE/audio probes.

### Final production image

The final image with no diagnostic counters was uploaded successfully; esptool
verified the written hash. Its size and SHA-256 are recorded under host
validation above. Boot confirmed the production board, verified charger
configuration, played Ready and then one Sunrise after charging was confirmed.
No audit lines occur in the production capture.

The final cable cycle is independently visible in serial and BLE:

- `21:32:30.571 UTC`: `NO_INPUT`; BLE notified the same state at `30.585`.
- `21:32:36.779 UTC`: valid input and `UNKNOWN` while `/CE` has just been
  enabled; BLE notified that transitional state at `36.795`.
- `21:32:37.775 UTC`: confirmed `CHARGING`; one `[Sound] Playing charger` at
  `37.780`; BLE notified charging at `37.785`.
- The user confirmed one clean charger cue after this reconnection.

The final BLE probe completed 96 valid reads over 100.94 seconds, including
notifications for all three cable-transition states above. Later sampled
CC/CV phase changes did not replay the cue. The capture contains exactly two
charger plays: one for the boot with input attached and one for reconnection.
The BLE connection and serial monitor were closed after capture.

The battery remained GOOD off input and CHARGING on input. No battery cue was
played. No panic, brownout, uncommanded reboot, charger supervision failure or
configuration-recovery message appeared during these checks.

### Not exercised

No active regulation condition was sampled after the final mask correction,
so setting/clearing the app's live limit indicator is covered by host tests,
not a positive device observation in this session. The first diagnostic image
did observe live ILIM/DPPM bits. Physical temperature/overvoltage/overcurrent
fault injection, charge completion, low-battery transitions, deep-sleep wake,
phone audio quality and charger-cue interruption of ongoing BT/SD playback
were not rerun. Existing protection settings are unchanged; these results do
not constitute physical protection validation.

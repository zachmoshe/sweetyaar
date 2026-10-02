# Pairing hardware validation — 2026-10-02

User-approved session on the generic ESP32 DevKit, USB
`/dev/cu.usbserial-14320`, named Yaaruli. Classic address from this board's
boot log: `1C:C3:AB:F5:C0:E6`. Mac is the test central/audio source.

Run from the pairing worktree using `tools/device_test.py`. Raw serial, host
output, upload logs and scenario reports are retained locally in the ignored
`tools/bt_smoke_logs/` directory. These observations do not establish that
every flow passes.

## Merge review

Reviewed the complete pairing worktree against local `main` on 2026-10-02.
Removed temporary BLE handshake/access traces, their two logging-only peer
fields, and the app's expected pairing-read exception print. Connection,
authentication, takeover and error logs remain intentional runtime diagnostics.
No generated logs, recordings, binaries, hard-coded test-device names or
firmware test bypasses are included in the changes. The reusable device runner
now executes commands from the repository root regardless of its caller's
working directory.

Pinned the PlatformIO platform to the validated 6.12.0 release because Classic
pairing depends on ESP-IDF 4.4.7's private API. Production and generic builds
pass after cleanup; `git diff --check` and Python compilation pass. The host
suite has 111 passes and two failures (song-title formatting and theme-icon
centering); both failures were reproduced independently on unchanged `main`.
Builds were run separately from the host suite's two deselected build cases.

This cleanup was not flashed or tested again on hardware. The device evidence
below identifies the previously flashed binary; it does not certify every flow
or the new build byte-for-byte. All pairing work remains uncommitted in this
worktree at review time; no merge was performed.

## Bond-only pairing and Just Works

The current implementation uses stack bonds as its only persistent device list.
Legacy approved bonds migrate once; unmatched old bonds are removed before
access opens. Classic declares no input/output capability and gates Bluedroid's
Just Works auto-confirmation through `BTA_DmConfirm`. A durable deletion marker
keeps access closed across asynchronous reset/removal and reboot.

The first hardware run preserved the bonds and passed BLE, but Classic audio
was rejected: the adapter compared ACL completion with `ESP_BT_STATUS_SUCCESS`
instead of `ESP_BT_STATUS_HCI_SUCCESS` (`0x100`). The correction was added to the
real-callback native test and reflashed. Subsequent device checks:

| Check | Result / evidence |
| --- | --- |
| Existing bonds survive migration; boot stays closed | Classic=2, BLE=2; Mac protected BLE reads passed. `20261002-bonds-boot`, `20261002-bonds-boot-retry`. |
| Classic saved-key reconnect after reboot, pairing closed | Passed after the ACL status correction. `20261002-bonds-classic-retry`. |
| Classic/BLE coexistence and blocked local volume changes | Passed. Same Classic retry record. |
| Targeted audio playback | Firmware STARTED, player completed, Mac default output unchanged; no crash. Same Classic retry record. |
| Repeated BLE saved-key reconnect | Three passed, pairing closed, no reboot between attempts. `20261002-bonds-repeat`. |
| Fresh phone Classic Just Works enrollment | Gate allowed the request, authentication succeeded, A2DP connected and audio STARTED. User confirmed no comparison code. `20261002-bonds-enroll`. |
| Pairing deadline despite Classic connection | Closed at 60.00 seconds. Same enrollment record. |
| Newly created Just Works bond reconnect outside window | User confirmed no pairing prompt; serial shows the same phone reconnecting after reboot, pairing closed, followed by audio STARTED. `20261002-bonds-phone-reconnect`. |
| New-key rejection outside the window; reset deletion/reboot failure cases | Native tests pass; not rerun as destructive hardware scenarios in this revision. |

The phone reconnect observer initially waited for an explicit disconnect event.
Opening the serial adapter rebooted the toy, so the successful reconnect followed
boot instead. The observer reported success late, after a later disconnect
released that unnecessary wait. It now accepts either boot or disconnect as a
session boundary and requires that boundary to precede the connection. Its
corrected checks pass against the captured real-device trace:
`20261002-bonds-phone-reconnect-trace-check.log` (offline trace validation, not a
second device run). The user also confirmed the reconnect independently.

A BLE enrollment began only about three seconds before the enrollment window
expired; the firmware rejected the pending handshake at closure. That attempt
is not counted as successful BLE enrollment.

Latest flashed generic SHA-256:
`3843b8baba3d5efdbb2a7779465c0cf5c0a4993885432bd10312251701c446fa`.
Upload and runner: `20261002-bonds-device-retry-runner.log`.
Both firmware builds pass. All 12 targeted host regressions passed; the four
Bluetooth regressions were rerun after the ACL correction and passed again.
The full host suite has 111 passes and the same two existing failures: song-title
formatting and theme-icon centering (two firmware-build cases deselected).
The sections below retain evidence from earlier revisions.

## Subsequent pairing-policy correction

Fresh BLE pairing now requires an open window even for a known address.
The new known-peer/closed-window regression failed before the change; all
12 targeted Bluetooth, BLE transport and state-machine tests pass afterward.
Both production and generic firmware builds pass. Coverage includes pairing
requests before/after CONNECT, known/unknown peers, open/closed windows,
already-rejected links, and saved-key reconnects with the window closed.

This revision has not been flashed or tested on hardware: the serial port is
currently occupied by an existing PlatformIO monitor. The hardware evidence
below applies to earlier revisions. Built generic binary SHA-256:
`5d5a83f2bfc3b740093b1213284102c55bfe0a32be7b990dc62c96b1ad904f21`.
Build logs: `20261002-pairing-policy-production-build.log` and
`20261002-pairing-policy-generic-build.log`. This only corrects the application's
pairing admission policy; it does not address Bluedroid's bond cleanup during
pairing rejection. Takeover confirmation and disconnect behavior are unchanged.

## Subsequent reset-indicator correction

The ten-second approval reset now flashes red for 250 ms and then restores the
current state indication, normally green idle, even while the buttons remain
held. Quiet time, playback, and error indications also resume. The gesture's
release requirement and approval-clearing behavior are unchanged.

A regression executing the production LED scheduler failed on the previous
dark-until-rearmed behavior and passes with the correction. All 12 targeted
Bluetooth, BLE transport and state-machine tests pass; both firmware variants
build successfully. Tests cover the 249/250 ms boundary, continuing the hold,
normal blink timing afterward, state changes during the flash, timer wraparound,
and a later separate reset. The correction has not been flashed or visually
verified on the device. Built generic binary SHA-256:
`c32b201dd11c5c22634dd20a66e9ed60fc624ebc5db58a3153669fee1b532b1b`.
Build logs: `20261002-reset-led-production-build.log` and
`20261002-reset-led-generic-build.log`.

The subsequent cleanup removes both persistent reset-feedback flags. Forget
requests a single flash, and the LED scheduler consumes that request after
250 ms. No completed-reset LED state remains. All 12 targeted tests and both
firmware builds pass, including assertions that the request clears without
discarding the current state. This cleanup is also not flashed or hardware
verified. Built generic SHA-256:
`e47c121b0bdbbc26d6ba4c918d88cc25843b1ea3cce10367885ca54b2d9929e7`.
Build logs: `20261002-reset-cleanup-production-build.log` and
`20261002-reset-cleanup-generic-build.log`.

## Subsequent leftover cleanup

Removed the unused BLE-remote LED signal, duplicate button-hold tracking,
cached BLE connection flag, unused volume-change peek, and unreachable
null-peer authentication branches. Connection state now comes from the
authenticated controller ID; pairing timing remains owned by PairingPolicy.

App v39 removes the persistent disconnect-suppression flag. Failed connections
and takeover notices clean up the current session immediately; delayed events
from an old device are ignored by identity. Two new regressions failed before
the fix and pass afterward, covering the next connection's real disconnect
and stale subscriptions after partial initialization. Picker cancellation and
service-discovery rejection still produce distinct messages.

All 12 targeted Bluetooth, BLE transport and state-machine tests pass. The app
runner passes 82 of 83 cases; its existing song-title formatting failure remains
(`Little Pigs` versus `3 Little Pigs`). Both firmware variants build. This
revision has not been flashed or tested on hardware; Classic pairing capability
and confirmation behavior are unchanged. Built generic binary SHA-256:
`3056e838d3864ef5ab101b054aa44dcba64ba350296ed781ac33cf7bf4bfa964`.
Build logs: `20261002-leftovers-production-build.log` and
`20261002-leftovers-generic-build.log`.

## Hardware findings and fixes

- macOS initially refused BLE before a firmware connection event with
  `Peer removed pairing information`. Forgetting this toy in Settings cleared
  the stale bond; command-line unpair alone did not.
- Bonded BLE reconnect delivered GAP authentication before GATTS CONNECT.
  The original handler lost the successful outcome and timed out. The fix
  retains bounded security-result metadata until CONNECT and applies normal
  authorization. Three actual reconnects passed, including this event order.
- Classic enrollment succeeded but its immediate audio connection failed.
  A later approved connection after reboot succeeded. Fresh Classic enrollment
  needs another test before this can be considered resolved.
- Classic followed by encrypted BLE crashed inside Bluedroid allocation
  (`gatt_allocate_tcb_by_bdaddr` → `fixed_queue_new` → `vQueueDelete`).
  Reducing I2S DMA from twelve to six buffers preserves the separate 8 KB
  Bluetooth audio queue and frees 12 KB. The same coexistence test then passed.
- A BLE-only remote incorrectly selected the blue Classic-connected LED mode.
  This was an LED policy error, not an audio state-machine transition. The
  corrected policy preserves local idle/playback and Quiet time while a remote
  is connected. A new regression failed before the fix and passed afterward.
- In the first actual Android takeover attempt, the Mac's BLE link timed out
  before the tablet connected. The tablet reached firmware while pairing was
  open but did not display a system pairing dialog; authentication failed after
  30 seconds with raw stack reason `0x63`, without exchanging keys or saving
  approval. The 60-second window was open throughout authentication. Neither
  takeover nor tablet enrollment passed in that attempt.
- App v38 now makes one encrypted status read while authentication is pending
  to trigger Android's bonding path, then still requires the access diagnostic
  to report approved. It avoids this probe for rejected devices. Nine targeted
  UI scenarios pass, including the Android handshake simulation and denial
  cases. The tablet-only retry then enrolled successfully and the user also
  enrolled a phone during the same window. The phone took control and the
  tablet displayed the takeover message. The earlier Mac timeout was not
  reproduced by these two Android devices.
- Both Android devices displayed two pairing requests. Each trace includes an
  encrypted GATT read reaching the application before final AUTH_CMPL. The
  application incorrectly returned insufficient authentication (`0x05`) while
  its approval was pending. It now returns insufficient authorization (`0x08`)
  to avoid asking Android to repeat authentication; encryption permissions and
  approval gates stay enforced. The user retried both Android devices after
  flashing and still observed two dialogs, so this correction did not resolve
  the reported issue.
- The first single-prompt retry runner incorrectly matched a rejected
  authentication attempt from before the user opened pairing. It stopped
  recording at the open event, so that run does not establish the enrollment
  outcome. The runner now starts enrollment assertions at the actual window
  opening; a replay of that event sequence passes.
- Further inspection found concurrent pairing triggers: the peripheral called
  `esp_ble_set_encryption` on connect, while the app also initiated security
  through its encrypted read. The next correction removes the peripheral
  request and leaves the encrypted client read as the trigger. A native
  regression fails on the previous implementation; all 12 targeted tests pass
  after the change. Both hardware builds pass, the generic binary is flashed,
  and the saved Mac BLE approval reconnects after reboot with pairing closed.
  The user then verified successful fresh pairing with exactly one system
  pairing message on both the phone and tablet. That observation occurred
  after the serial observer's 180-second gesture wait had expired, so it is
  recorded as human verification, not a successful automated enrollment run.

## Evidence so far

| Flow | Result | Evidence directory under tools/bt_smoke_logs |
| --- | --- | --- |
| Boot pairing closed, unknown BLE receives access=0; encrypted read rejected | Passed | `20261002-boot-clean` |
| Unknown Classic cannot connect with pairing closed and no saved approvals | Passed | `20261002-classic-denied` |
| Physical 3-second gesture, fast blue, no accidental song | Passed; LED/audio observed by user | `20261002-ble-pair` |
| New BLE approval saved; window stays open for 60.00 seconds | Passed | `20261002-ble-pair` |
| Approved BLE after reboot, pairing closed | Passed after callback-order fix | `20261002-early-auth-boot` |
| Approved Mac BLE after removing peripheral security initiation | Passed after reboot with pairing closed; authenticated status/volume reads | `20261002-client-pairing-mac` |
| Three approved BLE reconnects without reboot/window | Passed after callback-order fix | `20261002-early-auth-repeat` |
| BLE-only remote preserves green idle LED with pairing closed | Passed; protected status reads Idle, no Classic connection, user confirmed blinking green | `20261002-remote-led` |
| Classic approval saved, immediate audio connection | Enrollment passed; audio failed | `20261002-classic` |
| Classic and BLE together | Failed before memory fix; passed afterward | `20261002-classic-reconnect`, `20261002-coexist-memory` |
| BLE volume changes ignored during Classic connection | Passed | `20261002-coexist-memory` |
| Routed audio; firmware Audio STARTED | Passed; user heard Mac audio, did not identify test tone | `20261002-coexist-memory` |
| Tone routed only to toy; Mac default output unchanged | Transport passed; audible tone quality not separately confirmed | `20261002-targeted-tone` |
| Approved Classic reconnect outside pairing, including after reboot | Passed | `20261002-coexist-memory` |
| Two independent BLE devices and takeover notice during pairing | Passed with Android tablet and phone; user confirmed message | `20261002-tablet-enroll` |
| Both devices enroll while one 60-second window remains open | Passed, closure after 60.00 seconds | `20261002-tablet-enroll` |
| Mac/tablet takeover | Not passed: Mac link timed out before tablet's initial failed enrollment | `20261002-takeover-enroll-retry` |
| Android first-time enrollment uses a single system pairing request | Passed after client-initiated pairing correction; user verified phone and tablet | User observation after `20261002-client-pairing-flash.log`; observer `20261002-client-pairing-android` expired before the gesture |
| Approved Android takeover outside pairing | Pending | Requires reconnect from tablet/phone |
| Classic second-source contention/manual switching | Pending | Requires second audio source |
| Unknown Classic rejected while another Classic device is already approved | Pending | Requires second audio source |
| Continuous 13-second hold, one red flash then current state, persisted revocation | Pending | Requires physical hold with the reset-indicator correction flashed |

Uploaded generic binary SHA-256 during the earlier client-pairing correction:
`3263f276e074814fc90aabd7907e4919f497dc5683ab8051f604426db10fa9df`.
Upload: `20261002-client-pairing-flash.log` (upload hash verified).
The preceding coexistence/audio runs
used `68cc018843291f82e4e299fb79ca365cffaf114f22fa06ec862a4efb9e45a0f8`;
subsequent firmware changes are the BLE-only LED mapping, the application
authorization error code, and client-initiated BLE security. The Android enrollment/takeover run used the LED
fix binary `a86a2e144b60ce66079d33de2c7d8d7019e221751109b35f56917d0bfca25679`.
Both production and generic builds pass with client-initiated security;
12 targeted native regressions pass. The preceding authorization-only revision
(`1c944ce5c82cff7b77cfcfe6790eddcaef678dade6879bec6b919505ee8a37f4`)
still showed duplicate dialogs on both Android devices, per user observation.

The first audio runner temporarily changed the default Mac output, and the user
heard other Mac audio. It restored the original output. The runner now selects
the device only for its own AVAudioPlayer. The revised real-device test passed:
firmware reported STARTED, the player completed, and MacBook Pro Speakers
remained the default output before/after. Classic/BLE coexistence and a second
Classic reconnect also passed in that run, without a crash.

Host suite: 111 passed, two pre-existing failures (song-title formatting and
theme-icon centering), two firmware-build cases deselected. Latest targeted
Bluetooth, BLE transport and state-machine regressions: 12 passed; audio
handoff/configuration checks: 29 passed. These are host tests, separate from
the hardware evidence above.

After the LED correction, state-machine/pairing/LED checks: 9 passed. The
LED regression covers a remote combined with idle, playback, Quiet time,
Classic connection/playback, and the open pairing window.

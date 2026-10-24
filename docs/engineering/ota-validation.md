# BLE Firmware-Update Validation (2026-10-24)

This records two real-device sessions on the production PCB: transfer
measurements with a temporary probe firmware (not part of the repository) that
shaped the [Firmware updates](firmware.md#firmware-updates) design, then
end-to-end tests of the updater itself from a Mac and an Android phone.

## Part 1: transfer measurements (probe firmware)

### Setup

- Production PCB (BQ25186 detected), running on battery, with the 8 MB partition
  table.
- MacBook as the BLE central about 30 cm away, already bonded, so every
  transfer used the encrypted link. Script: `bleak` over CoreBluetooth, waiting
  for `canSendWriteWithoutResponse` before each write.
- Payload: the real 1.94 MB firmware image. "Flash" cases wrote it to the
  inactive app slot and passed `esp_ota_end()` (SHA-256 and structure check)
  without changing the boot partition.
- The probe requested a 15 ms connection interval (`6–12` units) and a
  251-byte data length, unless stated otherwise. Local MTU 517.

### Results

| Case | Sent | Throughput | Time to validated image |
| --- | --- | --- | --- |
| Normal firmware, macOS default 30 ms interval, 512 B writes, discard | 1.94 MB | 12.8 KiB/s | 148 s |
| Normal firmware, 15 ms, 512 B writes, discard | 1.94 MB | 25.7 KiB/s | 73 s |
| Normal firmware, 15 ms, 182 B writes, discard | 1.94 MB | 19.0 KiB/s | 100 s |
| Normal firmware, 15 ms, 20 B writes, discard | 256 KB sample | 7.5 KiB/s | **data lost** |
| Normal firmware, 15 ms, 512 B writes with response | 256 KB sample | 12.0 KiB/s | — |
| Normal firmware, flash raw (direct write in the GATT callback) | 1.94 MB | 25.3 KiB/s | 75 s |
| BLE-only controller, flash raw | 1.91 MB | 23.6 KiB/s | 79 s |
| BLE-only controller, zlib (8 KB window), inflated on the device | 1.23 MB | 24.2 KiB/s | 50 s |
| BLE-only controller, zlib, 7.5 ms requested (macOS chose 30 ms) | 1.23 MB | 13.4 KiB/s | 90 s |

### Findings

- Throughput follows the connection interval: about one 512-byte write per
  connection event. macOS accepted 15 ms and refused 7.5 ms (falling back to
  30 ms). Phones were not measured; Android commonly accepts shorter intervals.
- Releasing Classic Bluetooth did not change throughput, but it raised free
  heap after BLE start from 18.7 KB to 65.7 KB.
- With Classic running, a BLE connection left about 12 KB free and a transfer
  drained it to 1.3–3 KB. A 14 KB buffered writer failed with
  `ESP_ERR_NO_MEM`; only writing directly in the GATT callback worked.
- With 20-byte writes in normal mode, 42% of the data never arrived while the
  heap fell to 1.3 KB: Bluedroid dropped packets. The update protocol therefore
  acknowledges offsets and resends from the device's position.
- Flash writing was not the bottleneck (8–16 s in total, overlapping the
  transfer). zlib inflation with the ROM `tinfl` used about 36 KB of RAM (with
  a queue and task the shipped updater does not use) and cut the transfer by
  35%; a 32 KB window compresses the image to 62%.
- One serial flash attempt failed with `Invalid head of packet` mid-image; the
  retry verified. Wired flashing over the debugger is unaffected by OTA.

## Part 2: updater end to end

Production PCB on battery, firmware 1.0.0 with the updater flashed by cable,
then updated over BLE to test builds that differ only in `FIRMWARE_VERSION`
(1.2 MB compressed). Mac: `tools/ota_update.py` from Terminal. Android: the
parent app in Chrome, served from the worktree through an HTTPS tunnel.

| Scenario | Client | Result |
| --- | --- | --- |
| Full update 1.0.0 → 1.0.1 | Mac | Pass: 66 s total, 44.5 s transfer at 26 KiB/s; new image confirmed itself after restart; bond kept. |
| Cancel at 30% | Mac | Pass: partial image discarded, normal restart on the current version. |
| Disconnect at 40% for 15 s, then resume | Mac | Pass: resumed at byte 483,108 and installed. |
| Idle in update mode (nothing sent, and after a dropped link) | Mac | Pass: normal restart exactly 2 minutes after the last update traffic. |
| Full update 1.0.0 → 1.0.2 from the app | Android | Pass after the fixes below: 37 s transfer (~32 KiB/s, MTU 517), about 48 s from entering update mode to the new firmware; Settings then showed the new version as both current and latest. |
| Switch the doll off at 25–35% | Android | Pass: on power-up the doll ran the old 1.0.0 in normal mode (green); the app showed **Update didn't finish**; **Try again** installed the update completely. |

### Problems found and fixed

- **Stale GATT cache on a bonded Mac.** The Mac had bonded before the update
  characteristics existed and kept its cached table, so `…78A2` was "not
  found". Neither Bluedroid's automatic Service Changed nor an explicit
  indication after authentication made macOS rediscover it. Forgetting the toy
  in macOS and pairing again fixed it. This affects only layout changes, which
  is why the GATT table must stay frozen across releases (a layout version is
  planned).
- **Idle timeout fired after 35 s mid-transfer.** The Bluetooth task recorded
  activity after the loop sampled `millis()`, so the unsigned difference
  wrapped. Fixed with a signed comparison.
- **12 KiB/s at macOS's default 30 ms interval.** Update mode now requests
  7.5–15 ms when an image begins (26 KiB/s on the Mac). One later transfer lost
  its link (supervision timeout) 8 s after such a request; three others did not.
- **Android: generic "GATT operation failed" right after reconnecting** to
  update mode. The app now waits 0.5 s after reconnecting and retries generic
  errors by reconnecting and resuming.
- **Android: no response to enter update mode, and a 7 s delay before the
  phone noticed the restart.** The app treated the missing response as a
  failure and cancelled. The toy now closes the link before every restart, and
  the app waits up to 12 s for it and treats silence as the restart.

The negotiated MTU was 185 in normal mode and 517 in update mode on both
clients. Switching the board off with the debugger attached first logged a
brownout and the restart reported `SW_CPU_RESET`; the result was the same.

## Not tested

iPhone (no Web Bluetooth), automatic rollback of a bad image, low-battery
refusal on real hardware, transfers while A2DP was connected, and the
lock-screen pause on Android.

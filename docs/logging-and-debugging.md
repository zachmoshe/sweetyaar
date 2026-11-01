# Logging and Debugging

The toy is sewn into a doll, so the six-pin debugger is usually out of reach.
The firmware therefore keeps its own rolling record on flash: diagnostic
events, crash information and periodic telemetry. This document is the
specification for that record.

The work is split into steps. Step 1 stores the record on the device without
disturbing audio, Bluetooth or sleep. Later steps read it back and show it:

| Step | What | Status |
| --- | --- | --- |
| 1 | Rolling log, crash copy, telemetry and usage stored on flash | Implemented |
| 2 | Bench tool: read the partition with the debugger and print decoded text | Implemented |
| 3 | Fetch the log over BLE (script and parent app) | Mac script implemented; parent app planned |
| 4 | Log viewer: timeline, charts and stats from fetched files | First version |
| 5 | Parents upload logs to the cloud; the viewer reads them | Planned |

With the debugger connected, `make fetch-logs` and `make parse-logs` save and
print the log (see [Reading the log on the bench](#reading-the-log-on-the-bench)).
Without it, `make fetch-logs-ble` saves the same file over BLE from a paired Mac
(see [Fetching the log over BLE](#fetching-the-log-over-ble)), and
`make logs-ui` shows every fetched log in a browser (see
[Log viewer](#log-viewer)).

## Principles

- **Serial output does not change.** A stored line prints exactly the same
  text as before (BLE and Classic connection lines lost only their `t=`
  prefix, which every record now carries). Bench tooling that waits for
  `[Boot] Ready.` or `AUTH conn=` keeps working.
- **A stored line is an ID plus its arguments**, not text. The format string
  lives once, in `firmware/esp32/src/DevLogEvents.h`, and the decoder rebuilds
  the text from it.
- **Logging never waits for the radio or the speaker.** A record is written
  immediately (about 1 ms); the only slow flash operation, erasing a sector,
  is done ahead of time while no audio plays.
- **Bounded.** The log never grows beyond its partition; the oldest data is
  overwritten. A boot loop or an event flood cannot wipe the history.
- **No secrets.** As on serial, keys and passcodes are never logged.

## Partition

| Item | Value |
| --- | --- |
| Label | `logs` (`data`, subtype `0x40`); firmware falls back to `spiffs` |
| Offset, size | `0x670000`, `0x180000` (1.5 MiB) |
| Sectors | 384 × 4 KiB |

The partition table is written only by wired flashing, so toys updated over
BLE keep the old `spiffs` label at the same offset and size. The firmware looks
for `logs` first and then `spiffs`, and treats the area as a raw ring (no file
system). A partition holding anything other than valid log sectors is reused
from its first sector. Without either partition the toy still runs and prints
to serial; it only stores nothing.

`make flash` does not erase the log. A full chip erase does.

## Ring layout

The partition is a ring of 4 KiB sectors. Each sector starts with a header and
then holds records back to back. Writing fills one sector; when the next
record does not fit, the following sector (already erased) gets a new header
and writing continues there. When the last sector fills, writing wraps to the
first, overwriting the oldest data one sector at a time.

### Sector header (24 bytes)

| Offset | Size | Field |
| --- | --- | --- |
| 0 | 4 | Magic `SYLG` |
| 4 | 1 | Format version (1). It governs the header, record and argument encoding below. |
| 5 | 1 | Header size (24) |
| 6 | 2 | Reserved (`0xFFFF`) |
| 8 | 4 | Sector sequence number, increasing by one per opened sector |
| 12 | 4 | Boot number that opened the sector |
| 16 | 6 | Device ID (the chip's factory MAC) |
| 22 | 1 | Reserved (`0xFF`) |
| 23 | 1 | CRC-8 of bytes 0–22 |

All multi-byte fields are little-endian. CRC-8 uses polynomial `0x07`, initial
value `0x00`. A sector whose header is missing or fails its CRC holds no
records. The newest sector is the valid header with the highest sequence
number; the decoder reads sectors in sequence order.

### Record

| Offset | Size | Field |
| --- | --- | --- |
| 0 | 1 | Payload length (0–240) |
| 1 | 2 | Event ID |
| 3 | 4 | Milliseconds since boot (`millis()`) |
| 7 | n | Payload |
| 7 + n | 1 | CRC-8 of bytes 0 to 6 + n |

A record costs 8 bytes plus its payload. A length byte of `0xFF` is erased
flash and marks the end of the sector's records.

The device ID and wall-clock time are deliberately not in every record. The
device ID is in every sector header. A record's boot is the most recent `BOOT`
record before it (or the sector header's boot number, if that `BOOT` has been
overwritten). Wall time is derived per boot; see [Time](#time).

### Payload: self-describing arguments

| Part | Encoding |
| --- | --- |
| Argument count | 1 byte; bit 7 set means the payload was truncated |
| Argument types | One 4-bit type per argument, two per byte, low nibble first |
| Values | In argument order |

| Type | Value encoding |
| --- | --- |
| 1 unsigned | LEB128 varint |
| 2 signed | Zigzag, then LEB128 varint |
| 3 string | Length byte, then up to 63 bytes (longer strings are truncated) |
| 4 float | 4-byte IEEE 754 |
| 5 bytes | Length byte, then raw bytes |

Because each value carries its type, the decoder never needs to know the
firmware version's argument types, only the format text. If the arguments do
not fit in 240 bytes, packing stops and the truncated flag is set.

### Writes, power loss and resuming after a reboot

Each record is written with a single flash write. NOR flash can only turn bits
from 1 to 0 without an erase, so the space after the last record stays
writable across reboots: **at boot the firmware continues in the same sector,
right after the last valid record, without erasing it.**

Boot-time scan (about 10 ms):

1. Read the 384 sector headers and pick the newest valid one.
2. Walk its records, checking each CRC, to find where the next record goes.
3. Check that the rest of the sector is still erased (`0xFF`).
4. Check whether the following sector is already erased.

A reset during a flash write can leave a torn record: its CRC fails, or bytes
after the last valid record are no longer `0xFF`. That sector is then closed,
and writing continues in the next sector. Nothing already written is lost.

Records are written as they happen; nothing waits in RAM. What is lost on a
reset is only a record being written at that instant, plus anything the code
had not logged yet. The cause of the reset comes from the next boot's `BOOT`
record and, after a crash, the core dump.

## Erasing ahead of time

Erasing a sector is the only slow operation. Typical datasheet times for this
class of flash:

| Operation | Time | Effect |
| --- | --- | --- |
| Write one record (≤ 248 bytes) | ~0.5–2 ms | Code running from flash pauses on both cores |
| Erase one 4 KiB sector | ~45 ms typical, up to ~400 ms | Same pause, for longer |

The I2S output keeps playing from its DMA buffers during a pause, but they
hold only about 70 ms (six 512-frame buffers), and local WAV playback refills
them from the main loop. A record write is far below that; an erase is not.

So the firmware keeps **one erased sector ready ahead of the current one**. As
soon as writing moves into a new sector, the sector after it is marked for
erasure, and the main loop erases it at the next quiet moment:

- No WAV is playing. This includes the gap between two songs, because the
  loop checks before starting the next track; the erase delays that start by
  about 45 ms.
- No system sound (cue) is playing.
- No Classic Bluetooth audio is streaming. A connected but paused phone is
  quiet.

Boot is quiet too (nothing plays during `setup()`), so a pending erase left by
the previous session is done before the first sound. A sector lasts hours (see
[Capacity](#capacity)), so quiet moments come long before it fills.

If a sector does fill while no erased sector is ready (for example, many hours
of uninterrupted Bluetooth streaming), new records are **dropped and counted**
until the next quiet moment. The counts are then stored as a `LOG_DROPPED`
record. The firmware never erases during audio.

The partition is never erased as a whole: a fresh or unknown partition is
erased one sector at a time as it is reached.

## Boot

On the ESP32, a wake from deep sleep is a full restart: every wake runs
`setup()` and writes a boot's worth of records. A toy woken by the movement
sensor many times a day therefore pays the boot cost many times, so that cost
is kept small:

- **Detail records** (configuration summary, charger identification and
  configuration check, catalog summary, Bluetooth queue and sink start, GATT
  layout, BLE address, bond counts, theme list, SD mount, boot heap
  milestones) repeat the same values on every boot. During `setup()` after a
  deep-sleep wake they print to serial only; after a cold boot (power-on,
  reset button, firmware restart, crash, watchdog or brownout) and once
  `setup()` has finished (for example after a settings change), they are
  stored.
- Everything else (reset reason, wake cause, clock, charger state, battery,
  volume, readiness) is stored on every boot.

### Records written at boot

`BOOT` is the first record of every boot:

| Argument | Meaning |
| --- | --- |
| Boot number | One more than the previous boot found in the log |
| Abnormal-reset streak | See [Boot loops](#boot-loops) |
| Reset reason | `esp_reset_reason()`, name and code |
| Wake cause | `esp_sleep_get_wakeup_cause()` |
| Firmware version, board | `FIRMWARE_VERSION`, `FIRMWARE_BOARD_ID` |
| Running slot | `app0` or `app1` |
| Epoch | UTC seconds if the RTC clock survived (deep-sleep wake after a time sync), else 0 |

It is followed by `LOG_OPENED` (where writing resumed), any crash records, the
existing boot lines, `[Boot] Ready.` (now with the boot duration in
milliseconds), and `BOOT_STABLE` once the boot has run for 60 seconds.

### Crashes and the core dump

A crash (panic or watchdog) writes a core dump into the 64 KB `coredump`
partition, as before. At the next boot the firmware:

1. Checks the core dump's checksum (`esp_core_dump_image_check()`).
2. Stores a `CRASH` record with the crashing task, exception cause, program
   counter, faulting address and the first eight backtrace addresses
   (`esp_core_dump_get_summary()`).
3. Copies the whole core dump into the log as `COREDUMP_BEGIN`, a series of
   `COREDUMP_CHUNK` records (offset plus up to 224 raw bytes each) and
   `COREDUMP_END`. A typical dump is 10–30 KB. The copy happens before audio
   starts and erases the log sectors it needs; this adds up to about 0.7 s to
   that one boot.
4. Erases the first sector of the `coredump` partition so the same dump is not
   copied twice. The next crash rewrites the whole dump as usual.

The bench tool reassembles the chunks into an ELF core file for
`espcoredump.py`, which also needs the matching `firmware.elf`; keep the ELF of
every released or field-flashed build.

During a boot loop (below) only the `CRASH` summary is stored, and the dump
stays in its partition until a boot is stable, which then copies the latest
dump.

### Boot loops

A boot is abnormal when its reset reason is a panic, a watchdog
(interrupt, task or other) or a brownout. The **streak** counts abnormal boots
in a row, each following a boot that did not reach `BOOT_STABLE` (60 s
uptime). A normal reset, or an abnormal one after a stable boot, starts over.

From a streak of 3, the boot is **suppressed**: it stores only `BOOT`, `CRASH`,
`LOG_SUPPRESSED` and `BOOT_STABLE`, and counts everything else as dropped. A
device rebooting every few seconds therefore writes about 100 bytes per boot
instead of a full boot (about 0.8 KB). At that rate the 1.5 MiB history lasts
about 15,000 looping boots instead of under 2,000. When a suppressed boot
reaches 60 s, it stores the drop count and logging returns to normal.

## Event catalog

`firmware/esp32/src/DevLogEvents.h` defines every stored event with two
macros:

```cpp
#define DEVLOG_ID_BLE_DISCONNECT  0x020B
#define DEVLOG_FMT_BLE_DISCONNECT "[BLE] DISCONNECT conn=%u reason=0x%02X was_controller=%d"
```

Code logs with `DLOG(BLE_DISCONNECT, connection, reason, wasOwner)`, which
prints the formatted line to serial and stores the ID and arguments. The
arguments are evaluated once. `DLOG_DETAIL(...)` is the same for
[detail records](#boot), and `DLOG_STORE(...)` stores without printing. Lines
that do not help after the fact (per-theme catalog scans, the status-LED
legend, the 30-second battery sample, the long decoded charger-state line,
static UUIDs and addresses) stay plain `Serial.printf` and are not stored.

IDs are grouped by area:

| Range | Area |
| --- | --- |
| `0x00xx` | Log itself, boot, crash, time, telemetry, usage |
| `0x01xx` | Main loop: sleep, sound, notices, bedtime, theme, volume |
| `0x02xx` | BLE parent service and its commands |
| `0x03xx` | Classic Bluetooth, access and pairing |
| `0x04xx` | Charger and battery |
| `0x05xx` | State machine, playback, content catalog, configuration files |
| `0x06xx` | Firmware updates |

**Rules for changing the catalog**, because logs outlive firmware versions:

- **Add** new events with new IDs. Never reuse or renumber an ID.
- You may change an event's wording, or **append** arguments at the end.
  Changing the meaning, order or type of existing arguments needs a new ID.
  Retire the old one by leaving its definition in place.
- Format version 1 covers the byte layout above. Changing the layout needs a
  new version, and the decoder keeps reading old ones.

### Numeric names

The hottest events store numbers instead of names: `SM_EVENT` and
`SM_TRANSITION` store the state and event values, while serial still prints
the names. Store-only formats may use `{LIST}` placeholders, which consume an
unsigned argument and print the matching entry of `DEVLOG_ENUM_<LIST>` (for
example, `DEVLOG_ENUM_SM_STATE`). A host test checks those lists against
`stateToString()` and `eventToString()`. A `{bytes}` placeholder consumes a
bytes argument.

## Telemetry and usage

`TELEMETRY` is stored about 2 s after boot, then every 5 minutes while awake,
and at deep-sleep entry:

| Argument | Meaning |
| --- | --- |
| Battery mV | Rolling mean (0 until the first valid sample) |
| Battery state | `BatteryState` value |
| Charger status | `ChargerStatus::State` value |
| Charger conditions | `ChargerStatus::Condition` bits, as on BLE |
| Activity | Bits: 0 local playback, 1 Classic connected, 2 Classic streaming, 3 BLE connected, 4 Quiet time, 5 Bedtime, 6 pairing open, 7 SD ready |
| Volume | Effective volume % |
| Heap | Free, largest block and lowest-ever free (bytes) |

`USAGE` counts activity since the previous `USAGE` record. It is stored every
60 minutes of awake time and at deep-sleep entry:

| Argument | Meaning |
| --- | --- |
| Interval | Seconds covered |
| Song button, animal button, both buttons | Physical presses |
| Songs started, animals started | Successful starts, any trigger |
| Local playback | Seconds of WAV playback |
| Bluetooth streaming | Seconds of Classic audio |
| App controls | BLE writes and config commands from the parent app |

Nothing is sampled during deep sleep; the battery drop across a sleep is the
difference between the readings before sleep and after the wake.

## Time

Every record carries milliseconds since boot. Wall time comes from:

- `BOOT`'s epoch, when the RTC clock survived a deep-sleep wake.
- `CLOCK_RETAINED` (time zone offset after a wake) and `TIME_SYNC` (epoch and
  time zone offset whenever the parent app sets the clock).

The decoder maps each boot's milliseconds to local time from the first such
anchor in that boot, and shows boots without one in boot order without wall
time. The clock is lost on a cold boot until an app connects.

## Protection

- **One writer at a time.** Bluetooth callbacks (core 0) and the main loop
  (core 1) log concurrently; a mutex serializes them, and a writer waits at
  most 50 ms before dropping its record. Packing uses one static buffer, so
  logging from a Bluetooth task adds almost nothing to its stack.
- **Rate limit.** At most 64 records in a burst, refilled at 8 per second.
  Excess records are dropped and counted. Boot and crash records are exempt.
- **Drops are recorded.** `LOG_DROPPED` stores the counts by reason (rate
  limit, waiting for an erased sector, boot loop, writer busy, flash error) at
  the next opportunity.
- **Repeating conditions are stored once.** See below.
- Logging never happens from an interrupt.

### Repeating conditions

Some events report a condition that a periodic check or a retry finds again
for as long as it lasts: an invalid battery reading every 30 seconds, a
charger that stops answering I2C every second, a sleep attempt postponed by a
stuck movement sensor. Without a limit they fill the log; the bench board
without a battery wrote 53 % of its records this way.

The events in `DEVLOG_REPEATING_EVENTS` (end of `DevLogEvents.h`) are stored
as "first, then changes":

- The first record of a line is stored in full and at once. A line is the
  event with its exact arguments: 78 mV and 79 mV are different lines.
- Identical repeats are only counted, with the time of the newest.
- `REPEATED` stores a pending count: "`<event>` from `<ms>` repeated N more
  times, last at `<ms>`", where the first time identifies the stored line.
  It is written when another line of the same event is stored, every 10
  minutes while counts are pending (so an ongoing condition shows up), and
  before deep sleep or a planned restart. The last one gives the end time.
- The last 16 distinct lines are remembered (356 bytes of RAM), so two
  alternating lines are each stored once and counted separately. When the
  table is full, the line seen least recently is reported and forgotten.
- Counts still pending when power is cut, the toy crashes or the debugger
  resets it for a fetch are lost: the stored line shows that the condition
  started, but not how long it lasted.
- The table is in RAM, so each boot stores the first line again.

The list holds only such conditions: battery ADC, charger I2C and
configuration checks, refused or postponed sleep, and app notices. Events
that record something happening (a button, a song, a connection) stay one
record per occurrence even when identical, and so do boot, crash, log,
telemetry, usage and time records and, for now, every Bluetooth and update
event. A host test enforces those exclusions.

## Capacity

A sector holds 4,072 bytes of records; 383 of the 384 sectors hold data at any
time (one is kept erased), about 1.56 MB.

Approximate record sizes:

| Record | Bytes |
| --- | --- |
| `SM_EVENT`, `SM_TRANSITION` | 12 each |
| Start a song by button (event, transition, volume, file path) | ~110 |
| Next song in loop mode (file path only) | ~55 |
| Track end (event, transition) | ~25 |
| `TELEMETRY` | ~30 |
| `USAGE` | ~25 |
| BLE app session (connect, auth, control, config commands, heap, disconnect) | ~0.8–1.5 KB |
| Classic connection (ACL, pairing checks, connect, audio states, disconnect, heap) | ~0.6 KB |
| Deep-sleep wake and sleep again (boot and sleep entry) | ~0.35 KB |
| Cold boot | ~0.8 KB |

### Awake time per sector

| Activity | Rate | One sector lasts |
| --- | --- | --- |
| Continuous looped playback | ~1.4 KB/h | ~3 h |
| Button-driven playback (a press per song) | ~2.5 KB/h | ~1.6 h |
| Bluetooth streaming | ~0.45 KB/h | ~9 h |
| Awake and idle, or charging | ~0.45 KB/h | ~9 h |
| Wake/sleep cycles | ~0.35 KB each | ~11 cycles |

### Whole partition

| Usage | Rate | History kept |
| --- | --- | --- |
| Continuous playback only | ~1.4 KB/h | ~1,100 h of playback |
| Bluetooth streaming only | ~0.45 KB/h | ~3,500 h of streaming |
| Typical day: 10 wakes, 30 songs started by button, 1 h looped playback, 1 h Bluetooth, 1 app session, 3 h awake | ~10 KB/day | ~5 months |
| Heavy day: 40 wakes, 150 presses, 3 h Bluetooth, 5 app sessions, 6 h awake | ~40 KB/day | ~6 weeks |

These are estimates from the formats, not measurements; the boot and sector
sequence numbers in a real dump give the real rate.

### Flash wear

The flash is rated for at least 100,000 erase cycles **per sector**; there is
no separate whole-device limit. The ring erases each log sector once per
wrap, so wear is spread evenly. Even the heavy day wraps the partition about
every 6 weeks, about 9 erases per sector per year. The log's own wear is
therefore negligible. Other partitions are unaffected; NVS has its own wear
levelling.

## Reading the log on the bench

Connect the six-pin debugger (powered, see the programming-interface rules in
[hardware.md](engineering/hardware.md)) and run:

```bash
make fetch-logs
```

```bash
make parse-logs
```

`tools/devlog.py` does both:

- **`fetch`** connects with esptool to the first ESP it finds, as the
  esptool command line does (`SERIAL_PORT=` picks one when several are
  connected). It reads the partition table, then reads the
  `logs` partition (or `spiffs` on a toy that was only updated over BLE) and
  the `coredump` partition. It writes nothing to the toy. The toy resets into
  download mode for the read and boots normally afterward, which shows as
  one more boot in the log. The read runs at 230,400 baud (under 2 minutes
  in all). A read sends the whole partition uncompressed from the toy, and
  at 460,800, the speed `make flash` uses, the CH340C debugger drops bytes
  ("Corrupt data"); `LOG_ARGS="--baud 115200"` is the slowest option. A
  read that fails within 30 seconds of connecting loses bytes rather than
  power, so fetch keeps what it has and continues one speed lower (460,800,
  230,400, then 115,200). The sectors are added to the device's saved
  file (see [Saved files](#saved-files)) in `devlogs/` (ignored by Git;
  `LOG_DIR=` changes the folder). A core dump that is still in its
  partition, not yet copied into the log (for example during a boot loop),
  is saved next to it as `...-coredump-partition.bin`.
- **The toy drops out about every 40 seconds during a fetch, by design.**
  While awake, the firmware enables the BQ25186 charger's 40-second host
  watchdog, which power-cycles `SYS` when I2C traffic stops (see the hang
  detectors in [firmware.md](engineering/firmware.md)). In download mode no
  firmware runs, so nothing talks to the charger and it cuts the toy's power
  40 seconds into the read (about 40 % of the log at 230,400 baud). Fetch
  reads in 64 KiB pieces, prints a note when this happens, reconnects and
  continues from the last complete piece. Each dropout adds a short boot to
  the toy's log, because the firmware starts for about a second before the
  reconnect resets it into download mode again.
- **`parse`** prints a saved file: `make parse-logs devlogs/<file>.bin`, or
  the newest in `devlogs/` when no file is given. Options go in `LOG_ARGS`:
  `--boots N` prints only the last N boots, `--ids` prefixes each line with
  its event name and `--chunks` prints the core dump chunk records too.

The output starts with the device ID, the number of sectors and their
sequence range, whether older sectors were overwritten on the toy before
they were fetched, and any torn or unreadable records. Then each boot
follows, one line per record:

```text
--- Boot 41 ---
2026-10-30 07:12:03.000   +0:00:00.112  [Log] Boot 41 streak=0 reset=DEEPSLEEP(8) wake=2 fw=1.2.0 board=sweetyaar slot=app0 epoch=1793337123
2026-10-30 07:12:03.000   +0:00:00.112  [Bedtime] Clock retained from deep sleep (tzOffsetMin=120)
2026-10-30 07:12:05.485   +0:00:02.597  [Boot] Ready. (2485ms)
```

The first column is local time, shown only for a boot that has a time anchor
(see [Time](#time)); a boot without one shows `-`. The second is the time since
boot. The text is rebuilt from the format in the current
`DevLogEvents.h`. The catalog rules keep that valid for older logs: an event
missing from the catalog prints as `[Unknown event 0x....]` with its
arguments, missing arguments print as `?`, and extra arguments are appended.
A boot whose start was overwritten by the ring is labeled as such.

A copied core dump prints as one line per `COREDUMP_*` record, and `parse`
reassembles it into `<log>-boot<N>-core.bin` beside the log. Decode it with
the `firmware.elf` of the firmware version in that boot's `BOOT` line
(`pip install esp-coredump`):

```bash
esp-coredump --chip esp32 info_corefile --core-format raw --core <core.bin> <firmware.elf>
```

## Fetching the log over BLE

From a Mac that is an approved remote for the toy, in Terminal (it needs
Bluetooth permission), with no debugger or USB:

```bash
make fetch-logs-ble
```

It adds to the same saved file as `make fetch-logs` (see
[Saved files](#saved-files)) in `devlogs/` (`LOG_DIR=` changes the folder).
`LOG_ARGS=--full` reads every sector the toy holds, even those already saved.

**What happens on the toy.** The script connects like `make ota-update` and
sends *enter update mode* with the log-read flag. The toy saves pending repeat
counts, restarts into update mode (yellow blinking: no audio, no Classic
Bluetooth, about 65 KB free heap, a 517-byte ATT MTU) and asks for a 7.5–15 ms
connection interval at the first read. The battery is not checked, since
nothing is written, and that boot refuses a firmware image. When the script
is done it sends *cancel* and the toy restarts its normal firmware; if the Mac
goes away, the 2-minute idle timeout does the same. Both restarts are software
restarts, so they show as two boots in the log and the clock is unknown until
an app connects again.

**Only what is not saved yet.** The script reads the toy's sector headers
first and reads only the sectors that are not in any saved file of that
device with the same header, plus the newest saved sector, which may have
grown since. A sector without a valid header holds no records and is not
read. Sectors are read oldest first, so the one still being written comes
last. If the toy holds a new history (see [Saved files](#saved-files)), every
sector is read.

After reading, the script reads the headers again and also reads any sector
opened in the meantime (the toy keeps logging in update mode). A core dump
still waiting in its partition (only during a boot loop) is saved next to
the log as `...-coredump-partition.bin`; unlike the debugger's copy it holds
the dump itself, not the whole partition.

**Speed.** Each packet carries up to 507 bytes. On the bench toy (macOS)
reads ran at about 26 KiB/s: 26 sectors took 5 s, and a whole 1.5 MiB
partition would take about a minute. A fetch that adds three sectors took
about 1 s, plus the two restarts (about 10 s in all).

### Saved files

Both fetches keep **one file per device history**,
`devlog-<MAC>-<date>-<time>.bin`, where the time is that of the latest fetch.
It holds only the sectors with records, in sequence order, not the erased
rest of the partition; `make parse-logs` and the viewer read it like a
partition image. Each fetch adds the new sectors, replaces the sector that
was still being written, writes the file under the new time and then deletes
every other file of that device whose sectors are all in the new one (for
example the previous fetch, or whole-partition images saved before this
format). A file that holds anything the new one lacks is kept.

- **The toy's ring goes around.** A file holds at most one partition's worth
  of sectors (384). When adding would go past that, the oldest 384 sectors
  stay in the earlier file under its name, and the rest start a new file
  that later fetches add to. Sectors the toy overwrote stay in the earlier
  file.
- **The partition was erased** (a full chip erase): the boot and sector
  numbers start again, so the toy's newest sequence is older than the file's
  or a saved sequence has a different header. That is a new history: it gets
  a new file and the old one is kept.

### Protocol

The read uses the firmware-update characteristics (see "Update protocol" in
[firmware.md](engineering/firmware.md)) plus `logData` (`…78A6`, notify).
Little endian throughout.

| Command on `otaControl` | Bytes |
| --- | --- |
| Enter update mode to read the log (normal mode) | `01 01` |
| Read: region, offset (u32), length (u32) | `05`, then 9 bytes |
| Cancel: restart normal firmware | `04` |

| Region | Contents |
| --- | --- |
| 0 info (20 bytes) | Format `1`, device ID (6), sector header size, sector size (u32), log partition size (u32), core dump size (u32, 0 when none waits) |
| 1 headers | Each sector's 24-byte header, back to back (384 × 24 bytes) |
| 2 log | The log partition |
| 3 core dump | A core dump not yet copied into the log |

The toy answers a read with notifications on `logData`: region, offset (u32),
then up to `min(MTU − 3, 512) − 5` bytes from that offset, in order. A range is
clipped to the region. A read that starts at or past the region's end, or a
flash read that fails, gets one packet with no bytes and ends the read. A new
read replaces the one in progress, so after a lost packet (the next offset is
not the expected one) or 2 seconds without the expected packet, the script
asks again from the first missing byte. The toy sends only while the
controller has free buffers for the link, at most four packets per loop pass,
and reads each piece of the log under the log's lock, so a record being
written is read whole or not at all.

The same read works in normal mode, for the parent app: there it keeps the
phone's connection interval and runs only while the toy is idle. Otherwise
the toy ends the read with one **busy packet**, region `FE` and the offset of
the next byte it would have sent, and logs `OTA_LOG_BUSY` when that stopped a
read in progress.

The toy logs `OTA_RESTART_TO_LOG_READ` before the restart, `OTA_UPDATE_MODE`
with `log read`, and `OTA_LOG_SENT` (bytes, packets, requests) before
restarting normal firmware. In normal mode `OTA_LOG_SENT` follows 10 seconds
without a read request.

## Log viewer

```bash
make logs-ui
```

opens a local viewer at `http://localhost:8010/` (`LOGS_PORT=` changes the
port) for every fetched file in `devlogs/` (`LOG_DIR=` changes the folder).
Files are read again when they change, so a new fetch shows up on Reload. The
viewer is `tools/logviewer/`: `history.py` merges the files, `server.py`
serves JSON and the page, and `static/` holds the page (no build step, no
external libraries).

### One history per device

A device usually has one saved file (see [Saved files](#saved-files)); it
may have more after its ring went around, after an erase, or when older
files were kept, and those can overlap. The viewer groups files by
the device ID in their sector headers and merges them into one history. A
record is identified by its content: boot number, milliseconds since boot,
event ID and arguments, plus a count for identical records in the same
millisecond. The boot number is stored in the log, so it survives power loss,
resets and flashing; it restarts only if the partition is erased, which would
mix two histories (not handled yet).

### Timeline

The time axis has two modes:

- **Real time** places each boot at its local wall time (see [Time](#time)).
  A boot without a clock is placed one minute after the previous boot (or
  before the next) and drawn faded, and the time axis is striped from it to
  the next dated boot, since its times there are a guess. Deep sleep
  between two boots is a dotted line. When no boot has a clock, the whole
  axis is estimated.
- **Awake time** puts boots back to back and hides sleep and off time; this
  is usually the easier view for a bench toy.

From top to bottom (sections alternate background, charts have a legend and
their scale in the left margin):

| Lane | Shows |
| --- | --- |
| Boots | One bar per boot: green cold boot, blue deep-sleep wake, red abnormal reset. A ✖ at the end of a boot means the next boot reported a panic, watchdog or brownout. |
| Firmware | One band per firmware version, from each boot's `BOOT` record. A dashed line across every lane marks a version change, so behavior before and after an update can be compared; hovering shows the version's boots and abnormal resets per awake hour. |
| Playing | Song, animal, Bluetooth audio and Quiet time, from `SM_TRANSITION` |
| App session, Phone (A2DP) | BLE connections (`BLE_CONNECT` to `BLE_DISCONNECT`) and Classic connections |
| Events by area | A mark per record, by ID range: grey info, amber warning, red error (a word heuristic on the text). A repeating condition also gets a bar from its stored record to its last counted repeat, in the stored record's area and color. |
| Battery | `TELEMETRY` battery voltage (mV); the background is shaded green between two samples whose charger state was charging |
| Volume | `TELEMETRY` effective volume, 0–100 % |
| Heap | `TELEMETRY` free heap now (blue), the largest free block (yellow; a large allocation such as a Bluetooth buffer fails when no single block is big enough, even with enough total free memory) and the lowest free heap since boot (grey, dashed). The low-water mark includes the temporary allocations of `setup()`, so it is already below the first sample's free heap. |

Scroll to zoom, drag to pan, shift-drag to zoom to a range and double-click
to fit. Hovering shows details; clicking jumps the log list to that moment,
and clicking a ✖ zooms to the last minutes before the crash. The log list
below shows the records in view, filtered by area, level and text.

Records that store codes or bit fields get short badges under the line that
translate them: `TELEMETRY` battery and charger states, charger conditions
and activity bits; `CHARGER_REGISTERS` STAT0, STAT1 and FLAG0 of the BQ25186;
the reset reason, wake cause and abnormal-reset streak of `BOOT` and
`SLEEP_WAKE` ("cold start", "woken by movement", "woken by charger"; a cold
start also covers the EN pin that the debugger, flashing and fetching pulse); BLE
disconnect reasons and pairing results; crash exception causes; lost
record counts; and the repeat count of a `REPEATED` record, which is shown in
the area and level of the line it repeats. Badges are amber for warnings and red for faults, and the text
filter matches them too. The tables are in `tools/logviewer/decoders.py` and
mirror the firmware; when a bit's meaning changes in firmware, update them
in the same change.

The summary cards include battery drain: the voltage drop per hour between
two 5-minute `TELEMETRY` samples of one boot while not charging, counted as
playing when at least 80 % of that interval was playback or Bluetooth audio
and as idle when at most 20 % was. It is a rough number until the battery
readings are calibrated, and drain across deep sleep is not counted yet.

Playback and Bluetooth hours and the song and animal counts come from the
playback records themselves (`SM_TRANSITION` and `WAV_PLAYING`), not from
`USAGE`: a boot that ends without deep sleep (power cut, flashing, a fetch or
a restart) never stores its last `USAGE` record.

**All devices** lists every device in the folder with naive totals (boots,
abnormal resets, awake, playback and Bluetooth hours, drain, errors, and the
firmware versions its log covers, oldest to newest, since updates change it
over time). Clicking a row opens that device.

To try the viewer without a toy, generate demo fetches (two overlapping
fetches with an app session, songs, Bluetooth audio, a crash and charging):

```bash
.venv/bin/python tests/devlog_fixture.py /tmp/devlog-demo
```

```bash
make logs-ui LOG_DIR=/tmp/devlog-demo
```

### Cloud (step 5)

The parent app will upload the raw log file with a small metadata record
(device, upload time, firmware and app versions). The viewer stays the same:
`history.Library` reads snapshots from a folder today, and a cloud source
will provide the same snapshots from the upload store. Hosting the viewer
for anyone but the developer needs access control, since uploads describe a
child's use of the toy.

## Real-device validation for step 1

A build and the host tests prove only that the code compiles and that the ring
logic works against a simulated flash. Before relying on it, verify on the
toy:

- A cold boot, a deep-sleep wake and a reset during playback each resume in
  the same sector, with valid records.
- A forced crash produces `CRASH` and the copied core dump, and the next boot
  does not copy it again.
- Wrap-around: a test build with a small ring fills and wraps without losing
  valid records.
- No audible glitch from writes during local playback, Bluetooth streaming or
  a cue, or from an erase between songs.
- No change in Bluetooth heap headroom (`[BT] Post-session heap`) or in BLE
  plus Classic coexistence.

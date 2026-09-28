# Bluetooth connection heap investigation — 2026-09-28

The connection crash was reproduced on the generic ESP32 prototype from a fresh
boot, before any app settings commands. The original firmware had insufficient free heap
for the Bluetooth connection's transient allocations. The earlier config JSON
change avoids one allocation pool but does not fix this overall memory budget.

The permanent fix mounts the SD card with two file slots instead of five,
recovering about 12 KB while retaining all 12 I2S DMA buffers. Both normal build
environments use this limit. Temporary heap logging, host probes, and experiment
profiles were removed after diagnosis; the measurements below record those runs.

## Evidence

The user's original ELF SHA prefix `a7a19616b0209d8c` matches the local generic
build. Decoding its backtrace shows `l2cu_allocate_ccb -> fixed_queue_new ->
fixed_queue_free -> osi_sem_free -> vQueueDelete`. The SDK cleans up a partially
constructed queue without checking whether its semaphore was created.

On the diagnostic baseline (12 I2S DMA buffers, five SD file slots), a Mac
connection reproduced heap exhaustion and a subsequent `host_recv_pkt_cb`
assertion. The allocation-failure hook captured the earlier cause:

```text
[HeapFail] bytes=4112 caps=0x00001800 allocator=heap_caps_malloc task=BTU_TASK free=2372 largest=1972
```

That first allocation decodes to `AVRC_BldResponse / avrc_bld_init_rsp_buffer`.
Another 4,112-byte allocation fails in SDP service discovery, then even 12- and
16-byte allocations fail with 312 bytes free. This reproduced a different final
assertion from the user's trace, with direct evidence of heap exhaustion before
the panic. The baseline diagnostic ELF SHA prefix is `92f32414265db4bf`.

## Controlled experiments

Both experiments retain the complete BLE service and the 8 KB A2DP ring buffer.
No SDK crash guard was patched.

| Profile | I2S DMA buffers | SD file slots | Free internal byte-accessible heap at ready | Observed result |
| --- | ---: | ---: | ---: | --- |
| Baseline | 12 | 5 | 13,544 bytes | Allocation failures and reboot during connection. |
| Smaller DMA | 6 | 5 | 25,224 bytes | Two ten-second Mac streaming probes completed; serial observed both `STARTED` events and no allocation failures during capture. Capture ended before the second disconnect. |
| Smaller SD reservation | 12 | 2 | 25,024 bytes | 35-second Mac streaming probe completed, including BLE subscriptions and attribute reads during playback; clean disconnect and no allocation failures/reboot during the complete capture. |

For the SD experiment, the catalog still loaded all four scanned themes and 15
files, and the parent-facing theme list remained two playable song themes. The
lowest reported heap watermark in the captured run was 7,384 bytes. After the
stream and BLE client disconnected, the heap settled at 21,820 bytes; this run
does not establish whether repeated long sessions retain additional memory.

The last tested experiment was `sweetyaar-generic-heap-small-sd`, ELF SHA prefix
`1e494211ad427c5e`. Capture completed with one boot, one audio start, no failed
allocations, and no assertions. Both probes disconnected, the Mac output was
restored to its built-in speakers, and the serial port was released.

The host probe played silence, establishing transport setup and coexistence.
The user subsequently reported successful playback. These checks do not establish
long-duration reliability. Settings persistence closes each file before opening
the next, while WAV playback can hold one file open. A native regression exercises
the production JSON read/save/reload functions with a WAV handle held open and
the two-file limit enforced. Saving during local playback remains a useful
real-device follow-up.

## Where the RAM goes

The original I2S initialization consumes about 25 KB. Halving its DMA buffer
count recovers about 12 KB, at the cost of less audio buffering.

The stock `SD.begin()` default reserves five simultaneous file slots. In the
installed SDK, `CONFIG_FATFS_PER_FILE_CACHE=1` and `FF_MAX_SS=4096`. Each `FIL`
contains a 4 KB cache, and mount reserves `max_files * sizeof(FIL)` up front.
These caches consume memory even when no file is open. Mounting with two slots
recovers about 12 KB while retaining the original audio buffering. See the
[SDK mount allocation](https://github.com/espressif/esp-idf/blob/v4.4.7/components/fatfs/vfs/vfs_fat.c#L152).

The BLE service adds about 23 KB during startup; the catalog and WAV decoder
objects account for much smaller amounts. The measurements identify a combined
reservation problem, not proof of a 160 KB Bluetooth memory leak.

## Local evidence and follow-up checks

Use the normal `sweetyaar` or `sweetyaar-generic` environment for future builds.
For repeat testing, connect Classic audio before BLE on macOS: a BLE-only link
can appear connected in `blueutil` without providing an A2DP audio output.
Confirm `Audio state: STARTED`, audible playback, BLE coexistence, repeated
connect/disconnect cycles, and no reboot. Also save settings during local WAV
playback to verify SD concurrency on the device.

Local captures are in the ignored `tools/bt_smoke_logs/` directory:

- `heap-baseline-serial.log` and `heap-baseline-host.log`
- `heap-small-dma-serial.log`, `heap-small-dma-host.log`, and `heap-small-dma-repeat-host.log`
- `heap-small-sd-serial.log`, `heap-small-sd-stream-host.log`, and `heap-small-sd-coexist-ble.log`

These ignored captures are local investigation artifacts, not test fixtures.

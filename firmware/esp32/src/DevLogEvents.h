#pragma once

// Catalog of stored log events. Each event has a permanent ID and the printf
// format that both serial output and the host decoder use.
//
// Rules (logs outlive firmware versions; see docs/logging-and-debugging.md):
// - Add events with new IDs. Never reuse or renumber an ID.
// - Wording may change and arguments may be appended. Changing the meaning,
//   order or type of an existing argument needs a new ID; leave the retired
//   definition in place.
// - Store-only formats may use {LIST} placeholders (an unsigned value named
//   by DEVLOG_ENUM_<LIST>) and {bytes} (a bytes argument).

// --- 0x00xx: log, boot, crash, time, telemetry, usage ----------------------
#define DEVLOG_ID_BOOT 0x0001
#define DEVLOG_FMT_BOOT "[Log] Boot %lu streak=%u reset=%s(%u) wake=%u fw=%s board=%s slot=%s epoch=%lu"
#define DEVLOG_ID_BOOT_STABLE 0x0002
#define DEVLOG_FMT_BOOT_STABLE "[Log] Boot %lu stable after %lus"
#define DEVLOG_ID_LOG_OPENED 0x0003
#define DEVLOG_FMT_LOG_OPENED "[Log] Partition %s: %lu sectors, writing sector %lu (sequence %lu) at %lu"
#define DEVLOG_ID_LOG_DROPPED 0x0004
#define DEVLOG_FMT_LOG_DROPPED "[Log] Dropped records: rate=%lu space=%lu loop=%lu busy=%lu flash=%lu"
#define DEVLOG_ID_LOG_SUPPRESSED 0x0005
#define DEVLOG_FMT_LOG_SUPPRESSED "[Log] %u abnormal resets in a row; storing only boot and crash records until stable"
#define DEVLOG_ID_CRASH 0x0006
#define DEVLOG_FMT_CRASH "[Crash] task=%s cause=%lu pc=0x%08lX vaddr=0x%08lX depth=%lu corrupted=%u bt=0x%08lX 0x%08lX 0x%08lX 0x%08lX 0x%08lX 0x%08lX 0x%08lX 0x%08lX"
#define DEVLOG_ID_COREDUMP_BEGIN 0x0007
#define DEVLOG_FMT_COREDUMP_BEGIN "[Crash] Copying core dump to the log: %lu bytes"
#define DEVLOG_ID_COREDUMP_CHUNK 0x0008
#define DEVLOG_FMT_COREDUMP_CHUNK "[Crash] Core dump offset=%lu {bytes}"
#define DEVLOG_ID_COREDUMP_END 0x0009
#define DEVLOG_FMT_COREDUMP_END "[Crash] Core dump copied: %lu bytes in %u records"
#define DEVLOG_ID_COREDUMP_SKIPPED 0x000A
#define DEVLOG_FMT_COREDUMP_SKIPPED "[Crash] Core dump not copied: %s"
// Store-only: the stored {EVENT} record at that time repeated identically.
#define DEVLOG_ID_REPEATED 0x000B
#define DEVLOG_FMT_REPEATED "[Log] {EVENT} from %lums repeated %lu more times, last at %lums"
#define DEVLOG_ID_TELEMETRY 0x0010
#define DEVLOG_FMT_TELEMETRY "[Telemetry] battery=%umV state=%u charger=%u cond=0x%04X activity=0x%02X vol=%u%% free=%u largest=%u min=%u"
#define DEVLOG_ID_USAGE 0x0011
#define DEVLOG_FMT_USAGE "[Usage] %lus song=%u animal=%u both=%u songs=%u animals=%u local=%lus bt=%lus app=%u"
#define DEVLOG_ID_TIME_SYNC 0x0012
#define DEVLOG_FMT_TIME_SYNC "[Bedtime] Time synced epoch=%ld tzOffsetMin=%d"
#define DEVLOG_ID_CLOCK_RETAINED 0x0013
#define DEVLOG_FMT_CLOCK_RETAINED "[Bedtime] Clock retained from deep sleep (tzOffsetMin=%d)"
#define DEVLOG_ID_CLOCK_UNKNOWN 0x0014
#define DEVLOG_FMT_CLOCK_UNKNOWN "[Bedtime] Clock unknown until parent app syncs local time"

// --- 0x01xx: main loop ------------------------------------------------------
#define DEVLOG_ID_SLEEP_WAKE 0x0101
#define DEVLOG_FMT_SLEEP_WAKE "[Sleep] Wake cause=%d vibration=%d"
#define DEVLOG_ID_DEVICE_NAME 0x0102
#define DEVLOG_FMT_DEVICE_NAME "[Device] btName=%s"
#define DEVLOG_ID_DEVICE_NAME_OVERSIZED 0x0103
#define DEVLOG_FMT_DEVICE_NAME_OVERSIZED "[Config] Ignoring oversized device name: %s"
#define DEVLOG_ID_SD_INIT_FAILED 0x0104
#define DEVLOG_FMT_SD_INIT_FAILED "[WARN] SD init failed; WAV playback unavailable"
#define DEVLOG_ID_BOOT_READY 0x0105
#define DEVLOG_FMT_BOOT_READY "[Boot] Ready. (%lums)"
#define DEVLOG_ID_HEAP 0x0106
#define DEVLOG_FMT_HEAP "[Heap] %s free=%u largest=%u min=%u"
#define DEVLOG_ID_WATCHDOG_FAILED 0x0107
#define DEVLOG_FMT_WATCHDOG_FAILED "[Watchdog] CPU1 loop task registration failed: %d"
#define DEVLOG_ID_SOUND 0x0108
#define DEVLOG_FMT_SOUND "[Sound] Playing %s"
#define DEVLOG_ID_SOUND_FAILED 0x0109
#define DEVLOG_FMT_SOUND_FAILED "[Sound] Audio output failed"
#define DEVLOG_ID_BLE_IDENTITY_RESTART 0x010A
#define DEVLOG_FMT_BLE_IDENTITY_RESTART "[BLE] New BLE address after bond reset; restarting"
#define DEVLOG_ID_SLEEP_POSTPONED 0x010B
#define DEVLOG_FMT_SLEEP_POSTPONED "[Sleep] Postponed: wake input was HIGH during the 500ms check"
#define DEVLOG_ID_SLEEP_ABORTED 0x010C
#define DEVLOG_FMT_SLEEP_ABORTED "[Sleep] Aborted: charger could not be prepared safely"
#define DEVLOG_ID_SLEEP_ENTER 0x010D
#define DEVLOG_FMT_SLEEP_ENTER "[Sleep] Entering deep sleep after %lus idle (wake GPIO%d HIGH)"
#define DEVLOG_ID_NOTICE 0x010E
#define DEVLOG_FMT_NOTICE "[Notice] %s: %s"
#define DEVLOG_ID_SD_LOST 0x010F
#define DEVLOG_FMT_SD_LOST "[WARN] SD card no longer readable at play time"
#define DEVLOG_ID_BEDTIME_IGNORED_DISABLED 0x0110
#define DEVLOG_FMT_BEDTIME_IGNORED_DISABLED "[Bedtime] Ignoring runtime %s; mode disabled in settings (%s)"
#define DEVLOG_ID_BEDTIME_IGNORED_NO_TIME 0x0111
#define DEVLOG_FMT_BEDTIME_IGNORED_NO_TIME "[Bedtime] Ignoring runtime %s; local time unknown (%s)"
#define DEVLOG_ID_BEDTIME_OVERRIDE 0x0112
#define DEVLOG_FMT_BEDTIME_OVERRIDE "[Bedtime] Runtime override=%s until %s (%s)"
#define DEVLOG_ID_BEDTIME_OVERRIDE_CLEARED 0x0113
#define DEVLOG_FMT_BEDTIME_OVERRIDE_CLEARED "[Bedtime] Clearing runtime override=%s"
#define DEVLOG_ID_BEDTIME_THEME_CLEARED 0x0114
#define DEVLOG_FMT_BEDTIME_THEME_CLEARED "[Bedtime] Clearing theme override \"%s\""
#define DEVLOG_ID_BEDTIME_STATE 0x0115
#define DEVLOG_FMT_BEDTIME_STATE "[Bedtime] Runtime %s (auto=%d override=%s timeKnown=%d)"
#define DEVLOG_ID_BEDTIME_THEME_UNAVAILABLE 0x0116
#define DEVLOG_FMT_BEDTIME_THEME_UNAVAILABLE "[Bedtime] Theme \"%s\" is unavailable; using normal theme \"%s\" (volume cap still applies)"
#define DEVLOG_ID_BEDTIME_THEME_OVERRIDE 0x0117
#define DEVLOG_FMT_BEDTIME_THEME_OVERRIDE "[Bedtime] Theme override \"%s\" while bedtime remains active"
#define DEVLOG_ID_THEME_LIST 0x0118
#define DEVLOG_FMT_THEME_LIST "[Theme] %d playable theme(s), BLE payload=%u bytes"
#define DEVLOG_ID_THEME_FALLBACK 0x0119
#define DEVLOG_FMT_THEME_FALLBACK "[Theme] Theme \"%s\" is unavailable; using \"%s\""
#define DEVLOG_ID_VOLUME 0x011A
#define DEVLOG_FMT_VOLUME "[Vol] %u%% (%.2f, %s)"
#define DEVLOG_ID_VOLUME_CAPPED 0x011B
#define DEVLOG_FMT_VOLUME_CAPPED "[Vol] requested=%u%% effective=%u%% bedtimeCap=%u%% (%.2f, %s)"
#define DEVLOG_ID_KILLSWITCH_ACTIVE 0x011C
#define DEVLOG_FMT_KILLSWITCH_ACTIVE "[SM] Killswitch active for %lu ms"

// --- 0x02xx: BLE parent service ---------------------------------------------
#define DEVLOG_ID_BLE_SECURITY_CONFIG_FAILED 0x0201
#define DEVLOG_FMT_BLE_SECURITY_CONFIG_FAILED "[BLE] Security configuration failed param=%u result=0x%X; parent service disabled"
#define DEVLOG_ID_BLE_SERVICE_CHANGED_UNAVAILABLE 0x0202
#define DEVLOG_FMT_BLE_SERVICE_CHANGED_UNAVAILABLE "[BLE] Service Changed mode unavailable; cached GATT tables may go stale"
#define DEVLOG_ID_BLE_OUT_OF_MEMORY 0x0203
#define DEVLOG_FMT_BLE_OUT_OF_MEMORY "[BLE] Out of memory in GATT event %d (free=%u largest=%u)"
#define DEVLOG_ID_BLE_MTU_FAILED 0x0204
#define DEVLOG_FMT_BLE_MTU_FAILED "[BLE] MTU request failed: %d"
#define DEVLOG_ID_BLE_ADDRESS_RANDOM 0x0205
#define DEVLOG_FMT_BLE_ADDRESS_RANDOM "[BLE] Address %02X:%02X:%02X:%02X:%02X:%02X (random static, from the last bond reset)"
#define DEVLOG_ID_BLE_ADDRESS_PUBLIC 0x0206
#define DEVLOG_FMT_BLE_ADDRESS_PUBLIC "[BLE] Address: public (no bond reset yet)"
#define DEVLOG_ID_BLE_LOW_MEMORY 0x0207
#define DEVLOG_FMT_BLE_LOW_MEMORY "[BLE] Low memory: value not updated (len=%u free=%u largest=%u)"
#define DEVLOG_ID_BLE_CONFIG_TOO_LARGE 0x0208
#define DEVLOG_FMT_BLE_CONFIG_TOO_LARGE "[BLE] Config attribute %u exceeds 512 bytes"
#define DEVLOG_ID_BLE_NAME_SET 0x0209
#define DEVLOG_FMT_BLE_NAME_SET "[BLE] Device name set to \"%s\""
#define DEVLOG_ID_BLE_CONNECT 0x020A
#define DEVLOG_FMT_BLE_CONNECT "[BLE] CONNECT conn=%u peer=%02X:%02X:%02X:%02X:%02X:%02X bonded=%d pairing=%s decision=%s"
#define DEVLOG_ID_BLE_DISCONNECT 0x020B
#define DEVLOG_FMT_BLE_DISCONNECT "[BLE] DISCONNECT conn=%u reason=0x%02X was_controller=%d"
#define DEVLOG_ID_BLE_DISCONNECT_REQUEST 0x020C
#define DEVLOG_FMT_BLE_DISCONNECT_REQUEST "[BLE] DISCONNECT_REQUEST conn=%u"
#define DEVLOG_ID_BLE_ADVERTISING_FAILED 0x020D
#define DEVLOG_FMT_BLE_ADVERTISING_FAILED "[BLE] ADVERTISING %s failed status=0x%02X"
#define DEVLOG_ID_BLE_SECURITY_REQUEST 0x020E
#define DEVLOG_FMT_BLE_SECURITY_REQUEST "[BLE] SECURITY_REQUEST conn=%u decision=%s pairing=%s audio=%s result=0x%X"
#define DEVLOG_ID_BLE_AUTH_DROPPED 0x020F
#define DEVLOG_FMT_BLE_AUTH_DROPPED "[BLE] Authentication result dropped: no free connection slot"
#define DEVLOG_ID_BLE_AUTH 0x0210
#define DEVLOG_FMT_BLE_AUTH "[BLE] AUTH conn=%u peer=%02X:%02X:%02X:%02X:%02X:%02X success=%d fail_reason=0x%02X mode=0x%02X bonded_before=%d new_keys=%d pairing=%s decision=%s"
#define DEVLOG_ID_BLE_CONTROL 0x0211
#define DEVLOG_FMT_BLE_CONTROL "[BLE] CONTROL authenticated_conn=%u owner=%u previous=%u free=%u largest=%u"
#define DEVLOG_ID_BLE_AUTH_TIMEOUT 0x0212
#define DEVLOG_FMT_BLE_AUTH_TIMEOUT "[BLE] AUTH_TIMEOUT conn=%u elapsed=%lu pairing=%s"
#define DEVLOG_ID_BLE_GATT_LAYOUT 0x0213
#define DEVLOG_FMT_BLE_GATT_LAYOUT "[BLE] GATT layout=%08lX"
#define DEVLOG_ID_BLE_SERVICE_CHANGED 0x0214
#define DEVLOG_FMT_BLE_SERVICE_CHANGED "[BLE] SERVICE_CHANGED conn=%u status=0x%02X recorded=%d"
#define DEVLOG_ID_BLE_SERVICE_CHANGED_TIMEOUT 0x0215
#define DEVLOG_FMT_BLE_SERVICE_CHANGED_TIMEOUT "[BLE] SERVICE_CHANGED conn=%u status=timeout"
#define DEVLOG_ID_BLE_SERVICE_CHANGED_REQUEST 0x0216
#define DEVLOG_FMT_BLE_SERVICE_CHANGED_REQUEST "[BLE] SERVICE_CHANGED_REQUEST conn=%u recorded=%08lX layout=%08lX new_keys=%d result=0x%X"
#define DEVLOG_ID_BLE_IGNORED_VOLUME 0x0217
#define DEVLOG_FMT_BLE_IGNORED_VOLUME "[BLE] Ignoring volume write during BT streaming"
#define DEVLOG_ID_BLE_IGNORED_KILLSWITCH 0x0218
#define DEVLOG_FMT_BLE_IGNORED_KILLSWITCH "[BLE] Ignoring killswitch write during BT streaming"
#define DEVLOG_ID_BLE_IGNORED_THEME 0x0219
#define DEVLOG_FMT_BLE_IGNORED_THEME "[BLE] Ignoring theme write during BT streaming"
#define DEVLOG_ID_BLE_UNKNOWN_THEME 0x021A
#define DEVLOG_FMT_BLE_UNKNOWN_THEME "[BLE] Ignoring unknown theme: %s"
#define DEVLOG_ID_BLE_IGNORED_COMMAND 0x021B
#define DEVLOG_FMT_BLE_IGNORED_COMMAND "[BLE] Ignoring command %u while controls are disabled"
#define DEVLOG_ID_BLE_UNKNOWN_COMMAND 0x021C
#define DEVLOG_FMT_BLE_UNKNOWN_COMMAND "[BLE] Ignoring unknown command: %u"
#define DEVLOG_ID_BLE_CONFIG_COMMAND 0x021D
#define DEVLOG_FMT_BLE_CONFIG_COMMAND "[BLE] Config command %s id=%lu"
#define DEVLOG_ID_BLE_CONFIG_ERROR 0x021E
#define DEVLOG_FMT_BLE_CONFIG_ERROR "[BLE] Config command id=%lu failed: %s"

// --- 0x03xx: Classic Bluetooth, access and pairing --------------------------
#define DEVLOG_ID_BT_CONNECTED 0x0301
#define DEVLOG_FMT_BT_CONNECTED "[BT] Connected (free=%u largest=%u)"
#define DEVLOG_ID_BT_DISCONNECTED 0x0302
#define DEVLOG_FMT_BT_DISCONNECTED "[BT] Disconnected"
#define DEVLOG_ID_BT_AUDIO_STATE 0x0303
#define DEVLOG_FMT_BT_AUDIO_STATE "[BT] Audio state: %s"
#define DEVLOG_ID_BT_SAMPLE_RATE 0x0304
#define DEVLOG_FMT_BT_SAMPLE_RATE "[BT] A2DP sample rate: %u Hz"
#define DEVLOG_ID_BT_ADDRESS_UNAVAILABLE 0x0305
#define DEVLOG_FMT_BT_ADDRESS_UNAVAILABLE "[BT] %s address unavailable"
#define DEVLOG_ID_BT_SINK_STARTED 0x0306
#define DEVLOG_FMT_BT_SINK_STARTED "[BT] A2DP sink started as \"%s\""
#define DEVLOG_ID_BT_PAUSING 0x0307
#define DEVLOG_FMT_BT_PAUSING "[BT] Pausing new connections for %lu ms (%s, free=%u largest=%u)"
#define DEVLOG_ID_BT_ACCEPTING 0x0308
#define DEVLOG_FMT_BT_ACCEPTING "[BT] Accepting approved connections (%s, free=%u largest=%u)"
#define DEVLOG_ID_BT_POST_SESSION_HEAP 0x0309
#define DEVLOG_FMT_BT_POST_SESSION_HEAP "[BT] Post-session heap: free=%lu largest=%lu min=%lu"
#define DEVLOG_ID_BT_HEAP_RESTART 0x030A
#define DEVLOG_FMT_BT_HEAP_RESTART "[BT] Heap too low after BT session; restarting (%lu/%lu)"
#define DEVLOG_ID_BT_HEAP_RESTART_LOOP 0x030B
#define DEVLOG_FMT_BT_HEAP_RESTART_LOOP "[BT] Repeated low-heap restarts; entering deep sleep to break loop."
#define DEVLOG_ID_BT_NAME_SET 0x030C
#define DEVLOG_FMT_BT_NAME_SET "[BT] Classic BT name set to \"%s\""
#define DEVLOG_ID_BT_NAME_DEFERRED_ERROR 0x030D
#define DEVLOG_FMT_BT_NAME_DEFERRED_ERROR "[BT] Classic BT name update deferred: %d"
#define DEVLOG_ID_BT_NAME_DEFERRED 0x030E
#define DEVLOG_FMT_BT_NAME_DEFERRED "[BT] Classic BT name update deferred until audio disconnects"
#define DEVLOG_ID_BT_PEER 0x030F
#define DEVLOG_FMT_BT_PEER "[BT] %s peer=%02X:%02X:%02X:%02X:%02X:%02X code=0x%02X pairing=%s decision=%s"
#define DEVLOG_ID_BT_JUST_WORKS 0x0310
#define DEVLOG_FMT_BT_JUST_WORKS "[BT] JUST_WORKS_REQUEST decision=%s pairing=%s"
#define DEVLOG_ID_BT_SCAN_MODE 0x0311
#define DEVLOG_FMT_BT_SCAN_MODE "[BT] SCAN_MODE connectable=%d discoverable=%d pairable=%d"
#define DEVLOG_ID_BT_SEMAPHORE_FAILED 0x0312
#define DEVLOG_FMT_BT_SEMAPHORE_FAILED "[BT] A2DP semaphore allocation failed (free=%u largest=%u)"
#define DEVLOG_ID_BT_QUEUE_FALLBACK 0x0313
#define DEVLOG_FMT_BT_QUEUE_FALLBACK "[BT] A2DP queue fell back to %dB (requested %dB, free=%u largest=%u)"
#define DEVLOG_ID_BT_QUEUE_READY 0x0314
#define DEVLOG_FMT_BT_QUEUE_READY "[BT] A2DP queue ready: %dB (free=%u largest=%u)"
#define DEVLOG_ID_BT_RINGBUFFER_FAILED 0x0315
#define DEVLOG_FMT_BT_RINGBUFFER_FAILED "[BT] A2DP ringbuffer allocation failed (requested %dB, free=%u largest=%u)"
#define DEVLOG_ID_BT_TASK_FAILED 0x0316
#define DEVLOG_FMT_BT_TASK_FAILED "[BT] A2DP I2S task allocation failed (free=%u largest=%u)"
#define DEVLOG_ID_ACCESS_INIT_FAILED 0x0317
#define DEVLOG_FMT_ACCESS_INIT_FAILED "[Access] Initialization failed: NVS unavailable; Bluetooth access disabled"
#define DEVLOG_ID_ACCESS_BONDS 0x0318
#define DEVLOG_FMT_ACCESS_BONDS "[Access] Bonds ready classic=%d ble=%d pairing=closed"
#define DEVLOG_ID_PAIRING_BONDS_CLEARED 0x0319
#define DEVLOG_FMT_PAIRING_BONDS_CLEARED "[Pairing] All bonds cleared"
#define DEVLOG_ID_PAIRING_OPEN 0x031A
#define DEVLOG_FMT_PAIRING_OPEN "[Pairing] Open for 60 seconds (audio and BLE enroll separately)"
#define DEVLOG_ID_PAIRING_CLOSED 0x031B
#define DEVLOG_FMT_PAIRING_CLOSED "[Pairing] Closed; bonded phones may reconnect"
#define DEVLOG_ID_PAIRING_CLEARING 0x031C
#define DEVLOG_FMT_PAIRING_CLEARING "[Pairing] Clearing all bonds"
#define DEVLOG_ID_PAIRING_RESET_FAILED 0x031D
#define DEVLOG_FMT_PAIRING_RESET_FAILED "[Pairing] Bond reset storage error; access disabled"

// --- 0x04xx: charger and battery --------------------------------------------
#define DEVLOG_ID_CHARGER_EVENTS 0x0401
#define DEVLOG_FMT_CHARGER_EVENTS "[Charger events] time=%s%s%s%s%s"
#define DEVLOG_ID_CHARGER_DETECTED 0x0402
#define DEVLOG_FMT_CHARGER_DETECTED "[Charger] BQ25186 detected, MASK_ID=0x%02X"
#define DEVLOG_ID_CHARGER_VERIFIED 0x0403
#define DEVLOG_FMT_CHARGER_VERIFIED "[Charger] Configuration verified; charging %s"
#define DEVLOG_ID_CHARGER_MISMATCH 0x0404
#define DEVLOG_FMT_CHARGER_MISMATCH "[Charger] Configuration mismatch; attempting fail-closed recovery"
#define DEVLOG_ID_CHARGER_RESTORED 0x0405
#define DEVLOG_FMT_CHARGER_RESTORED "[Charger] Configuration restored and verified"
#define DEVLOG_ID_CHARGER_STATUS 0x0406
#define DEVLOG_FMT_CHARGER_STATUS "[Charger status] time=%s STATUS=%s"
#define DEVLOG_ID_CHARGER_SLEEP_REFUSED 0x0407
#define DEVLOG_FMT_CHARGER_SLEEP_REFUSED "[Charger] Refusing deep sleep while charger is unhealthy"
#define DEVLOG_ID_CHARGER_INPUT_APPEARED 0x0408
#define DEVLOG_FMT_CHARGER_INPUT_APPEARED "[Charger] External input appeared; keeping system awake"
#define DEVLOG_ID_CHARGER_SLEEP_READY 0x0409
#define DEVLOG_FMT_CHARGER_SLEEP_READY "[Charger] Configuration verified; charging and host watchdog disabled for deep sleep"
#define DEVLOG_ID_CHARGER_I2C_WRITE_FAILED 0x040A
#define DEVLOG_FMT_CHARGER_I2C_WRITE_FAILED "[Charger] I2C write reg 0x%02X failed (%u)"
#define DEVLOG_ID_CHARGER_I2C_SELECT_FAILED 0x040B
#define DEVLOG_FMT_CHARGER_I2C_SELECT_FAILED "[Charger] I2C select reg 0x%02X failed (%u)"
#define DEVLOG_ID_CHARGER_I2C_READ_FAILED 0x040C
#define DEVLOG_FMT_CHARGER_I2C_READ_FAILED "[Charger] I2C read reg 0x%02X failed"
#define DEVLOG_ID_CHARGER_VERIFY_FAILED 0x040D
#define DEVLOG_FMT_CHARGER_VERIFY_FAILED "[Charger] Verify reg 0x%02X expected=0x%02X actual=0x%02X"
#define DEVLOG_ID_CHARGER_CONFIG_CHANGED 0x040E
#define DEVLOG_FMT_CHARGER_CONFIG_CHANGED "[Charger] Config changed reg 0x%02X expected=0x%02X actual=0x%02X"
#define DEVLOG_ID_CHARGER_REGISTERS 0x040F
#define DEVLOG_FMT_CHARGER_REGISTERS "[Charger registers] time=%s STAT0=0x%02X STAT1=0x%02X FLAG0=0x%02X PG=%s"
#define DEVLOG_ID_CHARGER_DISABLED 0x0410
#define DEVLOG_FMT_CHARGER_DISABLED "[Charger] Disabled: %s"
#define DEVLOG_ID_BATTERY_BOOT_INVALID 0x0411
#define DEVLOG_FMT_BATTERY_BOOT_INVALID "[Battery] Initial ADC invalid (%u/%u valid)"
// No longer written: it repeated BATTERY_ADC_INVALID.
#define DEVLOG_ID_BATTERY_SAMPLE_IGNORED 0x0412
#define DEVLOG_FMT_BATTERY_SAMPLE_IGNORED "[Battery] Ignoring invalid ADC sample"
#define DEVLOG_ID_BATTERY_STATE 0x0413
#define DEVLOG_FMT_BATTERY_STATE "[Battery] State %s -> %s"
#define DEVLOG_ID_BATTERY_ADC_INVALID 0x0414
#define DEVLOG_FMT_BATTERY_ADC_INVALID "[Battery] Invalid raw ADC=%lumV (valid=%u-%umV)"

// --- 0x05xx: state machine, playback, content, configuration files ----------
#define DEVLOG_ENUM_SM_STATE "idle,playing_song,playing_animal,bt_streaming,killswitch"
#define DEVLOG_ENUM_SM_EVENT "NONE,BUTTON1,BUTTON2,BOTH_BUTTONS,BT_CONNECTED,BT_DISCONNECTED,WAV_FINISHED,KILLSWITCH_ON,KILLSWITCH_OFF,THEME_CHANGED,VOLUME_CHANGED,LOOP_ON,LOOP_OFF,KILLSWITCH_EXPIRED"
#define DEVLOG_ID_SM_TRANSITION 0x0501
#define DEVLOG_FMT_SM_TRANSITION "[SM] {SM_STATE} → {SM_STATE}"
#define DEVLOG_ID_SM_EVENT 0x0502
#define DEVLOG_FMT_SM_EVENT "[SM] State={SM_STATE} Event={SM_EVENT}"
#define DEVLOG_ID_SM_KILLSWITCH_RESTARTED 0x0503
#define DEVLOG_FMT_SM_KILLSWITCH_RESTARTED "[SM] Killswitch timer restarted"
#define DEVLOG_ID_WAV_SD_FAILED 0x0504
#define DEVLOG_FMT_WAV_SD_FAILED "[WavPlayer] SD init failed"
#define DEVLOG_ID_WAV_SD_OK 0x0505
#define DEVLOG_FMT_WAV_SD_OK "[WavPlayer] SD OK (SPI %lu MHz)"
#define DEVLOG_ID_WAV_NO_THEME_SONGS 0x0506
#define DEVLOG_FMT_WAV_NO_THEME_SONGS "[WavPlayer] No playable songs in theme %s"
#define DEVLOG_ID_WAV_NO_ANIMALS 0x0507
#define DEVLOG_FMT_WAV_NO_ANIMALS "[WavPlayer] No animal sounds"
#define DEVLOG_ID_WAV_READ_FAILED 0x0508
#define DEVLOG_FMT_WAV_READ_FAILED "[WavPlayer] Cannot read complete PCM block"
#define DEVLOG_ID_WAV_WRITE_FAILED 0x0509
#define DEVLOG_FMT_WAV_WRITE_FAILED "[WavPlayer] Audio output write failed"
#define DEVLOG_ID_WAV_NO_SONG_FILES 0x050A
#define DEVLOG_FMT_WAV_NO_SONG_FILES "[WavPlayer] No playable song files"
#define DEVLOG_ID_WAV_NO_ANIMAL_FILES 0x050B
#define DEVLOG_FMT_WAV_NO_ANIMAL_FILES "[WavPlayer] No playable animal files"
#define DEVLOG_ID_WAV_OPEN_FAILED 0x050C
#define DEVLOG_FMT_WAV_OPEN_FAILED "[WavPlayer] Cannot open: %s"
#define DEVLOG_ID_WAV_TOO_SMALL 0x050D
#define DEVLOG_FMT_WAV_TOO_SMALL "[WavPlayer] Skipping too-small WAV: %s (%u bytes)"
#define DEVLOG_ID_WAV_INVALID 0x050E
#define DEVLOG_FMT_WAV_INVALID "[WavPlayer] Skipping invalid WAV: %s (%u bytes)"
#define DEVLOG_ID_WAV_UNSUPPORTED 0x050F
#define DEVLOG_FMT_WAV_UNSUPPORTED "[WavPlayer] Skipping unsupported WAV: %s (format=%u rate=%lu channels=%u bits=%u)"
#define DEVLOG_ID_WAV_SEEK_FAILED 0x0510
#define DEVLOG_FMT_WAV_SEEK_FAILED "[WavPlayer] Cannot seek to WAV data: %s"
#define DEVLOG_ID_WAV_PLAYING 0x0511
#define DEVLOG_FMT_WAV_PLAYING "[WavPlayer] Playing: %s"
#define DEVLOG_ID_WAV_THEME_CAP 0x0512
#define DEVLOG_FMT_WAV_THEME_CAP "[WavPlayer] Theme list reached firmware cap (%d); extra themes ignored"
#define DEVLOG_ID_WAV_THEME_LIST_TRUNCATED 0x0513
#define DEVLOG_FMT_WAV_THEME_LIST_TRUNCATED "[WavPlayer] BLE theme list truncated to %u bytes"
#define DEVLOG_ID_CATALOG_ATTRIBUTION_IGNORED 0x0514
#define DEVLOG_FMT_CATALOG_ATTRIBUTION_IGNORED "[Catalog] Ignoring attribution for theme %s: must be one line of at most %u bytes"
#define DEVLOG_ID_CATALOG_REMOVE_FAILED 0x0515
#define DEVLOG_FMT_CATALOG_REMOVE_FAILED "[Catalog] Could not remove %s/%s"
#define DEVLOG_ID_CATALOG_METADATA_REMOVED 0x0516
#define DEVLOG_FMT_CATALOG_METADATA_REMOVED "[Catalog] Removed %u macOS metadata file(s) from %s"
#define DEVLOG_ID_CATALOG_CANNOT_PLAY 0x0517
#define DEVLOG_FMT_CATALOG_CANNOT_PLAY "[Catalog] Cannot play %s: %s"
#define DEVLOG_ID_CATALOG_BUILT 0x0518
#define DEVLOG_FMT_CATALOG_BUILT "[Catalog] Built in %lums: %u themes, %d files (free=%u largest=%u)"
#define DEVLOG_ID_CATALOG_CHANGED 0x0519
#define DEVLOG_FMT_CATALOG_CHANGED "[Catalog] %s changed since boot (%u files, %u expected); restart to rescan"
#define DEVLOG_ID_CATALOG_HEADER_CHECK 0x051A
#define DEVLOG_FMT_CATALOG_HEADER_CHECK "[Catalog] Header check: %u files, busy=%lums over %lums, %u unplayable"
#define DEVLOG_ID_CATALOG_OVERSIZED 0x051B
#define DEVLOG_FMT_CATALOG_OVERSIZED "[Catalog] Ignoring oversized %s: %s (%u UTF-8 bytes, %u JSON bytes). Must fit a 512-byte scan response and 383-byte update command; theme IDs also have a 63-byte limit. Shorten the name and reboot."
#define DEVLOG_ID_CATALOG_ATTRIBUTION_DROPPED 0x051C
#define DEVLOG_FMT_CATALOG_ATTRIBUTION_DROPPED "[Catalog] Dropping attribution for theme %s: entry exceeds the BLE response limit"
#define DEVLOG_ID_CONFIG_READ_FAILED 0x051D
#define DEVLOG_FMT_CONFIG_READ_FAILED "[Config] Cannot read %s"
#define DEVLOG_ID_CONFIG_INVALID 0x051E
#define DEVLOG_FMT_CONFIG_INVALID "[Config] Invalid %s: %s"
#define DEVLOG_ID_CONFIG_SAVE_NO_MEMORY 0x051F
#define DEVLOG_FMT_CONFIG_SAVE_NO_MEMORY "[Config] Not enough memory to save %s"
#define DEVLOG_ID_CONFIG_WRITE_FAILED 0x0520
#define DEVLOG_FMT_CONFIG_WRITE_FAILED "[Config] Cannot write %s"
#define DEVLOG_ID_CONFIG_SHORT_WRITE 0x0521
#define DEVLOG_FMT_CONFIG_SHORT_WRITE "[Config] Short write to %s (%u/%u bytes)"
#define DEVLOG_ID_CONFIG_SIZE_UNKNOWN 0x0522
#define DEVLOG_FMT_CONFIG_SIZE_UNKNOWN "[Config] Cannot check size of %s"
#define DEVLOG_ID_CONFIG_WRONG_SIZE 0x0523
#define DEVLOG_FMT_CONFIG_WRONG_SIZE "[Config] Wrong size for %s (%u/%u bytes)"
#define DEVLOG_ID_CONFIG_REPLACE_FAILED 0x0524
#define DEVLOG_FMT_CONFIG_REPLACE_FAILED "[Config] Cannot replace %s"
#define DEVLOG_ID_CONFIG_RENAME_FAILED 0x0525
#define DEVLOG_FMT_CONFIG_RENAME_FAILED "[Config] Cannot rename %s to %s"
#define DEVLOG_ID_CONFIG_DEFAULT_THEME_OVERSIZED 0x0526
#define DEVLOG_FMT_CONFIG_DEFAULT_THEME_OVERSIZED "[Config] Ignoring oversized defaultTheme: %s"
#define DEVLOG_ID_CONFIG_BEDTIME_THEME_OVERSIZED 0x0527
#define DEVLOG_FMT_CONFIG_BEDTIME_THEME_OVERSIZED "[Config] Ignoring oversized bedtime theme: %s"
#define DEVLOG_ID_CONFIG_SUMMARY 0x0528
#define DEVLOG_FMT_CONFIG_SUMMARY "[Config] defaultVolume=%u defaultTheme=%s disabledThemes=%d sleep=%d normal=%lus vibWake=%lus ble=%lus bedtime=%d start=%02u:%02u end=%02u:%02u theme=%s cap=%u"

// --- 0x06xx: firmware updates -----------------------------------------------
#define DEVLOG_ID_OTA_MTU 0x0601
#define DEVLOG_FMT_OTA_MTU "[OTA] ATT MTU %u"
#define DEVLOG_ID_OTA_INTERVAL 0x0602
#define DEVLOG_FMT_OTA_INTERVAL "[OTA] Requested 7.5-15 ms connection interval result=0x%X"
#define DEVLOG_ID_OTA_REFUSED_BATTERY 0x0603
#define DEVLOG_FMT_OTA_REFUSED_BATTERY "[OTA] Update mode refused: battery low"
#define DEVLOG_ID_OTA_RESTART_TO_UPDATE 0x0604
#define DEVLOG_FMT_OTA_RESTART_TO_UPDATE "[OTA] Restarting into update mode"
#define DEVLOG_ID_OTA_BEGIN 0x0605
#define DEVLOG_FMT_OTA_BEGIN "[OTA] Begin encoding=%u encoded=%lu image=%lu resume=%lu result=%u free=%u"
#define DEVLOG_ID_OTA_FINISH 0x0606
#define DEVLOG_FMT_OTA_FINISH "[OTA] Finish result=%u state=%u"
#define DEVLOG_ID_OTA_CANCELLED 0x0607
#define DEVLOG_FMT_OTA_CANCELLED "[OTA] Cancelled; restarting normal firmware"
#define DEVLOG_ID_OTA_CONTROLLER 0x0608
#define DEVLOG_FMT_OTA_CONTROLLER "[OTA] BLE-only controller init=0x%X enable=0x%X free=%u"
#define DEVLOG_ID_OTA_IDLE_TIMEOUT 0x0609
#define DEVLOG_FMT_OTA_IDLE_TIMEOUT "[OTA] No update traffic for 2 minutes; restarting normal firmware"
#define DEVLOG_ID_OTA_CONFIRMED 0x060A
#define DEVLOG_FMT_OTA_CONFIRMED "[OTA] Firmware %s confirmed after update"
#define DEVLOG_ID_OTA_ROLLBACK 0x060B
#define DEVLOG_FMT_OTA_ROLLBACK "[OTA] New firmware failed its startup check; rolling back"
#define DEVLOG_ID_OTA_UPDATE_MODE 0x060C
#define DEVLOG_FMT_OTA_UPDATE_MODE "[OTA] Update mode (%s)"
#define DEVLOG_ID_OTA_UPDATE_MODE_FAILED 0x060D
#define DEVLOG_FMT_OTA_UPDATE_MODE_FAILED "[OTA] Bluetooth failed in update mode; restarting normal firmware"
#define DEVLOG_ID_OTA_READY 0x060E
#define DEVLOG_FMT_OTA_READY "[OTA] Ready for an image (free=%u largest=%u)"
#define DEVLOG_ID_OTA_RESTART_TO_LOG_READ 0x060F
#define DEVLOG_FMT_OTA_RESTART_TO_LOG_READ "[OTA] Restarting into update mode to send the log"
#define DEVLOG_ID_OTA_LOG_SENT 0x0610
#define DEVLOG_FMT_OTA_LOG_SENT "[OTA] Sent %lu log bytes in %lu packets for %lu requests"

// --- Repeating conditions ---------------------------------------------------
// Conditions a periodic check or retry reports again for as long as they last.
// Each distinct line (same event, byte-identical arguments) is stored once;
// identical repeats are counted in REPEATED records (see DevLog.cpp). Never
// list boot, crash, log, telemetry, usage or time events, nor Bluetooth
// (BLE_*, BT_*, OTA_*) events, which stay one record per occurrence.
#define DEVLOG_REPEATING_EVENTS \
    DEVLOG_ID_BATTERY_ADC_INVALID, \
    DEVLOG_ID_CHARGER_I2C_READ_FAILED, \
    DEVLOG_ID_CHARGER_I2C_SELECT_FAILED, \
    DEVLOG_ID_CHARGER_I2C_WRITE_FAILED, \
    DEVLOG_ID_CHARGER_VERIFY_FAILED, \
    DEVLOG_ID_CHARGER_CONFIG_CHANGED, \
    DEVLOG_ID_CHARGER_MISMATCH, \
    DEVLOG_ID_CHARGER_RESTORED, \
    DEVLOG_ID_SLEEP_POSTPONED, \
    DEVLOG_ID_SLEEP_ABORTED, \
    DEVLOG_ID_CHARGER_SLEEP_REFUSED, \
    DEVLOG_ID_CHARGER_INPUT_APPEARED, \
    DEVLOG_ID_NOTICE

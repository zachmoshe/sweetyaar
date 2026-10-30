#include <Arduino.h>
#include <atomic>
#include <esp_core_dump.h>
#include <esp_ota_ops.h>
#include <esp_partition.h>
#include <esp_sleep.h>
#include <esp_system.h>
#include <freertos/FreeRTOS.h>
#include <freertos/semphr.h>
#include <time.h>

#include "Config.h"
#include "DevLog.h"
#include "DevLogRing.h"

namespace devlog {

namespace {

constexpr uint32_t LOCK_WAIT_MS = 50;
constexpr uint32_t STABLE_AFTER_MS = 60UL * 1000UL;
constexpr uint32_t BOOT_LOOP_STREAK = 3;
constexpr uint32_t RATE_BURST = 64;
constexpr uint32_t RATE_PER_SECOND = 8;
constexpr size_t COREDUMP_CHUNK_BYTES = 224;
constexpr uint32_t REPEAT_FLUSH_MS = 10UL * 60UL * 1000UL;
constexpr uint16_t REPEATING_IDS[] = {DEVLOG_REPEATING_EVENTS};
constexpr time_t VALID_EPOCH = 1577836800;  // 2020-01-01

class PartitionFlash : public Flash {
public:
    void attach(const esp_partition_t* partition) { _partition = partition; }
    uint32_t size() const override { return _partition ? _partition->size : 0; }
    bool read(uint32_t offset, void* data, size_t length) override {
        return esp_partition_read(_partition, offset, data, length) == ESP_OK;
    }
    bool write(uint32_t offset, const void* data, size_t length) override {
        return esp_partition_write(_partition, offset, data, length) == ESP_OK;
    }
    bool eraseSector(uint32_t offset) override {
        return esp_partition_erase_range(_partition, offset, SECTOR_SIZE) == ESP_OK;
    }

private:
    const esp_partition_t* _partition = nullptr;
};

struct Drops {
    std::atomic<uint32_t> rate{0};
    std::atomic<uint32_t> space{0};
    std::atomic<uint32_t> loop{0};
    std::atomic<uint32_t> busy{0};
    std::atomic<uint32_t> flash{0};
};

PartitionFlash g_flash;
Ring g_ring;
StaticSemaphore_t g_lockBuffer;
SemaphoreHandle_t g_lock = nullptr;
uint8_t g_record[MAX_RECORD];
uint8_t g_repeatRecord[RECORD_OVERHEAD + 24];  // a REPEATED record, built while g_record is in use
RepeatFilter g_repeats;
uint32_t g_repeatsFlushedMs = 0;
Drops g_drops;
bool g_ready = false;
bool g_storeDetail = true;
std::atomic<bool> g_suppressed{false};
std::atomic<bool> g_quiet{true};
bool g_lastWritten = false;
bool g_stableLogged = false;
uint32_t g_boot = 0;
uint32_t g_rateTokens = RATE_BURST * 1000UL;  // thousandths of a record
uint32_t g_rateUpdatedMs = 0;

bool essential(uint16_t id) {
    return id == DEVLOG_ID_BOOT || id == DEVLOG_ID_BOOT_STABLE || id == DEVLOG_ID_CRASH ||
           id == DEVLOG_ID_LOG_SUPPRESSED || id == DEVLOG_ID_LOG_DROPPED ||
           id == DEVLOG_ID_COREDUMP_BEGIN || id == DEVLOG_ID_COREDUMP_CHUNK ||
           id == DEVLOG_ID_COREDUMP_END || id == DEVLOG_ID_COREDUMP_SKIPPED;
}

bool repeating(uint16_t id) {
    for (uint16_t listed : REPEATING_IDS) {
        if (listed == id) return true;
    }
    return false;
}

// Called with the lock held.
bool takeRateToken(uint32_t now) {
    const uint32_t elapsed = now - g_rateUpdatedMs;
    g_rateUpdatedMs = now;
    const uint64_t refilled = static_cast<uint64_t>(g_rateTokens) +
                              static_cast<uint64_t>(elapsed) * RATE_PER_SECOND;
    g_rateTokens = refilled > RATE_BURST * 1000ULL ? RATE_BURST * 1000UL
                                                   : static_cast<uint32_t>(refilled);
    if (g_rateTokens < 1000) return false;
    g_rateTokens -= 1000;
    return true;
}

uint8_t* acquire(uint16_t id, bool detail, size_t* capacity) {
    if (!g_ready || (detail && !g_storeDetail)) return nullptr;
    if (g_suppressed && !essential(id)) {
        ++g_drops.loop;
        return nullptr;
    }
    if (xSemaphoreTake(g_lock, pdMS_TO_TICKS(LOCK_WAIT_MS)) != pdTRUE) {
        ++g_drops.busy;
        return nullptr;
    }
    if (!essential(id) && !takeRateToken(millis())) {
        ++g_drops.rate;
        xSemaphoreGive(g_lock);
        return nullptr;
    }
    *capacity = MAX_PAYLOAD;
    return g_record + RECORD_HEADER_SIZE;
}

// Called with the lock held.
bool append(uint8_t* record, uint16_t id, size_t payloadLength, uint32_t ms) {
    const Ring::Result result = g_ring.append(record, payloadLength, id, ms, g_quiet);
    if (result == Ring::Result::NoSpace) ++g_drops.space;
    if (result == Ring::Result::FlashError) ++g_drops.flash;
    return result == Ring::Result::Written;
}

// Called with the lock held.
void storeRepeat(const Repeat& repeat) {
    Packer packer(g_repeatRecord + RECORD_HEADER_SIZE, sizeof(g_repeatRecord) - RECORD_OVERHEAD, 4);
    packer.add(static_cast<unsigned>(repeat.id));
    packer.add(static_cast<unsigned long>(repeat.firstMs));
    packer.add(static_cast<unsigned long>(repeat.count));
    packer.add(static_cast<unsigned long>(repeat.lastMs));
    append(g_repeatRecord, DEVLOG_ID_REPEATED, packer.size(), millis());
    Serial.printf("[Log] Event 0x%04X from %lums repeated %lu more times, last at %lums\n",
                  static_cast<unsigned>(repeat.id), static_cast<unsigned long>(repeat.firstMs),
                  static_cast<unsigned long>(repeat.count), static_cast<unsigned long>(repeat.lastMs));
}

void commit(uint16_t id, size_t payloadLength) {
    const uint32_t now = millis();
    if (repeating(id) &&
        !g_repeats.admit(id, g_record + RECORD_HEADER_SIZE, payloadLength, now, storeRepeat)) {
        g_lastWritten = true;  // counted; a REPEATED record will carry it
    } else {
        g_lastWritten = append(g_record, id, payloadLength, now);
    }
    xSemaphoreGive(g_lock);
}

// esp_restart() runs this first, so the counts of a planned restart survive.
void flushRepeatsOnRestart() { flushRepeats(); }

const Backend g_backend = {acquire, commit};

// Called with the lock held; records the drop counts once they can be stored.
void storeDrops() {
    const uint32_t rate = g_drops.rate, space = g_drops.space, loop = g_drops.loop,
                   busy = g_drops.busy, flash = g_drops.flash;
    if (rate + space + loop + busy + flash == 0 || g_suppressed) return;
    Packer packer(g_record + RECORD_HEADER_SIZE, MAX_PAYLOAD, 5);
    packer.add(rate);
    packer.add(space);
    packer.add(loop);
    packer.add(busy);
    packer.add(flash);
    if (!append(g_record, DEVLOG_ID_LOG_DROPPED, packer.size(), millis())) return;
    g_drops.rate -= rate;
    g_drops.space -= space;
    g_drops.loop -= loop;
    g_drops.busy -= busy;
    g_drops.flash -= flash;
    Serial.printf(DEVLOG_FMT_LOG_DROPPED "\n", static_cast<unsigned long>(rate),
                  static_cast<unsigned long>(space), static_cast<unsigned long>(loop),
                  static_cast<unsigned long>(busy), static_cast<unsigned long>(flash));
}

const char* resetName(esp_reset_reason_t reason) {
    switch (reason) {
        case ESP_RST_POWERON: return "power-on";
        case ESP_RST_EXT: return "external";
        case ESP_RST_SW: return "software";
        case ESP_RST_PANIC: return "panic";
        case ESP_RST_INT_WDT: return "interrupt-watchdog";
        case ESP_RST_TASK_WDT: return "task-watchdog";
        case ESP_RST_WDT: return "watchdog";
        case ESP_RST_DEEPSLEEP: return "deep-sleep";
        case ESP_RST_BROWNOUT: return "brownout";
        case ESP_RST_SDIO: return "sdio";
        default: return "unknown";
    }
}

bool abnormalReset(esp_reset_reason_t reason) {
    return reason == ESP_RST_PANIC || reason == ESP_RST_INT_WDT ||
           reason == ESP_RST_TASK_WDT || reason == ESP_RST_WDT ||
           reason == ESP_RST_BROWNOUT;
}

void copyCoreDump() {
    if (esp_core_dump_image_check() != ESP_OK) return;

    // Runs once from setup() on the 8 KB loop task stack; no static RAM.
    esp_core_dump_summary_t summary;
    if (esp_core_dump_get_summary(&summary) == ESP_OK) {
        uint32_t bt[8] = {};
        for (uint32_t i = 0; i < 8 && i < summary.exc_bt_info.depth; ++i) {
            bt[i] = summary.exc_bt_info.bt[i];
        }
        DLOG(CRASH, summary.exc_task, static_cast<unsigned long>(summary.ex_info.exc_cause),
             static_cast<unsigned long>(summary.exc_pc),
             static_cast<unsigned long>(summary.ex_info.exc_vaddr),
             static_cast<unsigned long>(summary.exc_bt_info.depth),
             summary.exc_bt_info.corrupted ? 1U : 0U,
             static_cast<unsigned long>(bt[0]), static_cast<unsigned long>(bt[1]),
             static_cast<unsigned long>(bt[2]), static_cast<unsigned long>(bt[3]),
             static_cast<unsigned long>(bt[4]), static_cast<unsigned long>(bt[5]),
             static_cast<unsigned long>(bt[6]), static_cast<unsigned long>(bt[7]));
    } else {
        DLOG(COREDUMP_SKIPPED, "summary unavailable; copying the dump only");
    }
    // In a boot loop keep the dump; the first stable boot copies the latest.
    if (g_suppressed) return;

    size_t address = 0;
    size_t size = 0;
    const esp_partition_t* partition = esp_partition_find_first(
        ESP_PARTITION_TYPE_DATA, ESP_PARTITION_SUBTYPE_DATA_COREDUMP, nullptr);
    if (partition == nullptr || esp_core_dump_image_get(&address, &size) != ESP_OK ||
        address < partition->address || address + size > partition->address + partition->size) {
        DLOG(COREDUMP_SKIPPED, "image location unavailable");
        return;
    }

    DLOG(COREDUMP_BEGIN, static_cast<unsigned long>(size));
    uint8_t chunk[COREDUMP_CHUNK_BYTES];
    const uint32_t start = address - partition->address;
    unsigned records = 0;
    for (uint32_t offset = 0; offset < size; offset += COREDUMP_CHUNK_BYTES) {
        const size_t length = size - offset < COREDUMP_CHUNK_BYTES ? size - offset
                                                                    : COREDUMP_CHUNK_BYTES;
        if (esp_partition_read(partition, start + offset, chunk, length) != ESP_OK) {
            DLOG(COREDUMP_SKIPPED, "core dump read failed");
            return;
        }
        g_lastWritten = false;
        DLOG_STORE(COREDUMP_CHUNK, static_cast<unsigned long>(offset), Bytes{chunk, length});
        if (!g_lastWritten) {
            DLOG(COREDUMP_SKIPPED, "log write failed; dump kept for the next boot");
            return;
        }
        ++records;
    }
    DLOG(COREDUMP_END, static_cast<unsigned long>(size), records);
    // Invalidate the header only; the next crash rewrites the whole dump.
    esp_partition_erase_range(partition, 0, SECTOR_SIZE);
}

}  // namespace

void begin() {
    g_lock = xSemaphoreCreateMutexStatic(&g_lockBuffer);
    const esp_partition_t* partition = esp_partition_find_first(
        ESP_PARTITION_TYPE_DATA, ESP_PARTITION_SUBTYPE_ANY, "logs");
    if (partition == nullptr) {
        partition = esp_partition_find_first(
            ESP_PARTITION_TYPE_DATA, ESP_PARTITION_SUBTYPE_ANY, "spiffs");
    }
    if (partition == nullptr) {
        Serial.println("[Log] No log partition; logging to serial only");
        return;
    }
    g_flash.attach(partition);
    uint8_t deviceId[6] = {};
    esp_efuse_mac_get_default(deviceId);
    if (!g_ring.open(g_flash, deviceId, DEVLOG_ID_BOOT, DEVLOG_ID_BOOT_STABLE)) {
        Serial.printf("[Log] Partition %s is too small; logging to serial only\n",
                      partition->label);
        return;
    }

    const esp_reset_reason_t reset = esp_reset_reason();
    const BootHistory& history = g_ring.history();
    uint32_t streak = 0;
    if (abnormalReset(reset)) {
        streak = (history.found && !history.lastStable) ? history.lastStreak + 1 : 1;
    }
    g_boot = history.lastBoot + 1;
    g_ring.setBoot(g_boot);
    g_storeDetail = reset != ESP_RST_DEEPSLEEP;
    g_suppressed = streak >= BOOT_LOOP_STREAK;
    g_quiet = true;  // nothing plays during setup()
    g_ready = true;
    backend() = &g_backend;
    esp_register_shutdown_handler(flushRepeatsOnRestart);

    const esp_partition_t* running = esp_ota_get_running_partition();
    const time_t now = time(nullptr);
    DLOG(BOOT, static_cast<unsigned long>(g_boot), static_cast<unsigned>(streak),
         resetName(reset), static_cast<unsigned>(reset),
         static_cast<unsigned>(esp_sleep_get_wakeup_cause()), FIRMWARE_VERSION,
         FIRMWARE_BOARD_ID, running ? running->label : "?",
         static_cast<unsigned long>(now >= VALID_EPOCH ? now : 0));
    if (g_suppressed) DLOG(LOG_SUPPRESSED, static_cast<unsigned>(streak));
    DLOG_DETAIL(LOG_OPENED, partition->label, static_cast<unsigned long>(g_ring.sectorCount()),
                static_cast<unsigned long>(g_ring.currentSector()),
                static_cast<unsigned long>(g_ring.currentSequence()),
                static_cast<unsigned long>(g_ring.writeOffset()));
    copyCoreDump();

    // A pending erase from the previous session is cheapest now.
    xSemaphoreTake(g_lock, portMAX_DELAY);
    g_ring.prepareNext(true);
    xSemaphoreGive(g_lock);
}

void service(bool quiet) {
    g_quiet = quiet;
    if (!g_ready) return;
    g_storeDetail = true;  // setup() has finished; detail records are rare now
    const uint32_t now = millis();
    if (!g_stableLogged && now >= STABLE_AFTER_MS) {
        g_stableLogged = true;
        g_suppressed = false;
        DLOG(BOOT_STABLE, static_cast<unsigned long>(g_boot),
             static_cast<unsigned long>(now / 1000UL));
    }
    if (xSemaphoreTake(g_lock, 0) != pdTRUE) return;
    g_ring.prepareNext(quiet);
    storeDrops();
    if (now - g_repeatsFlushedMs >= REPEAT_FLUSH_MS) {
        g_repeatsFlushedMs = now;
        g_repeats.flush(storeRepeat);
    }
    xSemaphoreGive(g_lock);
}

void flushRepeats() {
    if (!g_ready || !g_repeats.pending()) return;
    if (xSemaphoreTake(g_lock, pdMS_TO_TICKS(LOCK_WAIT_MS)) != pdTRUE) return;
    g_repeats.flush(storeRepeat);
    xSemaphoreGive(g_lock);
}

}  // namespace devlog

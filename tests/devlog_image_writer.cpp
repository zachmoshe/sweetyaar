// Writes a small log partition image through the firmware's DLOG macros and
// ring, for the host decoder test (tests/test_devlog_tool.py).
//   devlog_image_writer <image.bin> <serial.txt> <core.bin>
// serial.txt holds what DLOG printed from boot 2 on; the decoder must print
// the same lines.

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <vector>

#include "recording_serial.h"
#include "DevLog.h"
#include "DevLogRing.h"

using namespace devlog;

namespace {

constexpr uint32_t SECTORS = 6;
const uint8_t DEVICE_ID[6] = {0x24, 0x0A, 0xC4, 0x01, 0x02, 0x03};

class MemoryFlash : public Flash {
public:
    std::vector<uint8_t> bytes = std::vector<uint8_t>(SECTORS * SECTOR_SIZE, ERASED_BYTE);
    uint32_t size() const override { return static_cast<uint32_t>(bytes.size()); }
    bool read(uint32_t offset, void* data, size_t length) override {
        memcpy(data, bytes.data() + offset, length);
        return true;
    }
    bool write(uint32_t offset, const void* data, size_t length) override {
        const auto* in = static_cast<const uint8_t*>(data);
        for (size_t i = 0; i < length; ++i) bytes[offset + i] &= in[i];
        return true;
    }
    bool eraseSector(uint32_t offset) override {
        memset(bytes.data() + offset, ERASED_BYTE, SECTOR_SIZE);
        return true;
    }
};

MemoryFlash g_flash;
Ring g_ring;
uint8_t g_record[MAX_RECORD];
uint32_t g_ms = 0;

uint8_t* acquire(uint16_t, bool, size_t* capacity) {
    *capacity = MAX_PAYLOAD;
    return g_record + RECORD_HEADER_SIZE;
}
void commit(uint16_t id, size_t length) {
    if (g_ring.append(g_record, length, id, g_ms, true) != Ring::Result::Written) {
        fprintf(stderr, "append failed\n");
        exit(1);
    }
}
const Backend g_backend = {acquire, commit};

void boot(uint32_t number) {
    g_ring.open(g_flash, DEVICE_ID, DEVLOG_ID_BOOT, DEVLOG_ID_BOOT_STABLE);
    g_ring.setBoot(number);
    g_ms = 100;
}

}  // namespace

int main(int argc, char** argv) {
    if (argc != 4) return 2;
    backend() = &g_backend;

    // Boot 1 fills more than the ring, so its start is overwritten. Its clock
    // is set near the end; earlier records get times from that anchor.
    boot(1);
    DLOG(BOOT, 1UL, 0U, "POWERON", 1U, 0U, "1.1.0", "sweetyaar", "app0", 0UL);
    DLOG(CLOCK_UNKNOWN);
    for (uint32_t i = 0; i < 1500; ++i) {
        g_ms = 10000 + i * 1000;
        DLOG(TELEMETRY, 3900U, 1U, 2U, 0x0003U, 0x81U, 50U, 61000U + i, 40000U, 30000U);
    }
    g_ms = 2000000;
    DLOG(TIME_SYNC, 1767225600L, 120);  // 2026-01-01 00:00:00 UTC, UTC+2

    // Boot 2 crashed before it: crash summary, core dump copy, numeric names.
    Serial.output.clear();
    boot(2);
    DLOG(BOOT, 2UL, 1U, "PANIC", 4U, 0U, "1.1.0", "sweetyaar", "app1", 0UL);
    DLOG(CRASH, "BTC_TASK", 28UL, 0x400D1234UL, 0UL, 3UL, 0U, 0x400D1234UL, 0x400D5678UL,
         0x400D9ABCUL, 0UL, 0UL, 0UL, 0UL, 0UL);
    uint8_t core[500];
    for (size_t i = 0; i < sizeof(core); ++i) core[i] = static_cast<uint8_t>(i * 7);
    DLOG(COREDUMP_BEGIN, static_cast<unsigned long>(sizeof(core)));
    unsigned chunks = 0;
    for (size_t offset = 0; offset < sizeof(core); offset += 224, ++chunks) {
        const size_t length = sizeof(core) - offset < 224 ? sizeof(core) - offset : 224;
        DLOG_STORE(COREDUMP_CHUNK, static_cast<unsigned long>(offset), Bytes{core + offset, length});
    }
    DLOG(COREDUMP_END, static_cast<unsigned long>(sizeof(core)), chunks);
    g_ms = 1500;
    DLOG(THEME_FALLBACK, "Lullabies \"night\"", "default");
    DLOG(BLE_DISCONNECT, 1, 0x13, -1);
    DLOG_STORE(SM_TRANSITION, 1U, 0U);
    DLOG_STORE(SM_EVENT, 1U, 99U);
    uint8_t unknown[3] = {1, ARG_UNSIGNED, 42};
    memcpy(g_record + RECORD_HEADER_SIZE, unknown, sizeof(unknown));
    commit(0x7FFF, sizeof(unknown));

    // Boot 3 woke from deep sleep with the RTC clock and ends in a torn write.
    boot(3);
    DLOG(BOOT, 3UL, 0U, "DEEPSLEEP", 8U, 2U, "1.1.0", "sweetyaar", "app1", 1767229200UL);
    DLOG(CLOCK_RETAINED, 120);
    g_ms = 2600;
    DLOG(BOOT_READY, 2500UL);
    const uint32_t torn = g_ring.currentSector() * SECTOR_SIZE + g_ring.writeOffset();
    const uint8_t partial[4] = {5, 0x05, 0x01, 0x00};
    g_flash.write(torn, partial, sizeof(partial));

    std::ofstream(argv[1], std::ios::binary)
        .write(reinterpret_cast<const char*>(g_flash.bytes.data()), g_flash.bytes.size());
    std::ofstream(argv[2]) << Serial.output;
    std::ofstream(argv[3], std::ios::binary).write(reinterpret_cast<const char*>(core), sizeof(core));
    return 0;
}

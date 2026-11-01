#include <algorithm>
#include <cassert>
#include <cstdint>
#include <cstring>
#include <initializer_list>
#include <iostream>
#include <string>
#include <vector>

#include "recording_serial.h"
#include "DevLog.h"
#include "DevLogRing.h"

using namespace devlog;

namespace {

constexpr uint16_t BOOT_ID = DEVLOG_ID_BOOT;
constexpr uint16_t STABLE_ID = DEVLOG_ID_BOOT_STABLE;
const uint8_t DEVICE_ID[6] = {0x24, 0x0A, 0xC4, 0x01, 0x02, 0x03};

// NOR flash: a write can only clear bits; only an erase sets them again.
class FakeFlash : public Flash {
public:
    explicit FakeFlash(uint32_t sectors) : bytes(sectors * SECTOR_SIZE, ERASED_BYTE) {}
    uint32_t size() const override { return static_cast<uint32_t>(bytes.size()); }
    bool read(uint32_t offset, void* data, size_t length) override {
        if (offset + length > bytes.size()) return false;
        memcpy(data, bytes.data() + offset, length);
        return true;
    }
    bool write(uint32_t offset, const void* data, size_t length) override {
        if (offset + length > bytes.size()) return false;
        const auto* in = static_cast<const uint8_t*>(data);
        const size_t written = std::min(length, tornWriteBytes);
        for (size_t i = 0; i < written; ++i) bytes[offset + i] &= in[i];
        ++writes;
        return written == length;
    }
    bool eraseSector(uint32_t offset) override {
        assert(offset % SECTOR_SIZE == 0);
        std::fill(bytes.begin() + offset, bytes.begin() + offset + SECTOR_SIZE, ERASED_BYTE);
        ++erases;
        return true;
    }

    std::vector<uint8_t> bytes;
    size_t tornWriteBytes = SIZE_MAX;
    int writes = 0;
    int erases = 0;
};

struct Record {
    uint32_t sequence;
    uint16_t id;
    uint32_t ms;
    std::vector<uint8_t> payload;
};

// Independent reader, as the host decoder will do it: sectors in sequence
// order, records until erased flash or a bad CRC.
std::vector<Record> readAll(const FakeFlash& flash) {
    struct Sector { uint32_t index, sequence; };
    std::vector<Sector> sectors;
    for (uint32_t s = 0; s < flash.size() / SECTOR_SIZE; ++s) {
        const uint8_t* h = flash.bytes.data() + s * SECTOR_SIZE;
        if (memcmp(h, "SYLG", 4) != 0 || h[4] != FORMAT_VERSION || crc8(h, 23) != h[23]) continue;
        assert(memcmp(h + 16, DEVICE_ID, 6) == 0);
        sectors.push_back({s, getLe32(h + 8)});
    }
    std::sort(sectors.begin(), sectors.end(),
              [](const Sector& a, const Sector& b) { return a.sequence < b.sequence; });
    std::vector<Record> records;
    for (const Sector& sector : sectors) {
        const uint8_t* base = flash.bytes.data() + sector.index * SECTOR_SIZE;
        uint32_t offset = SECTOR_HEADER_SIZE;
        while (offset + RECORD_OVERHEAD <= SECTOR_SIZE && base[offset] != ERASED_BYTE) {
            const size_t length = base[offset];
            const size_t total = RECORD_OVERHEAD + length;
            if (offset + total > SECTOR_SIZE || crc8(base + offset, total - 1) != base[offset + total - 1]) break;
            records.push_back({sector.sequence, getLe16(base + offset + 1), getLe32(base + offset + 3),
                               std::vector<uint8_t>(base + offset + 7, base + offset + 7 + length)});
            offset += static_cast<uint32_t>(total);
        }
    }
    return records;
}

Ring::Result appendArgs(Ring& ring, uint16_t id, uint32_t ms, std::initializer_list<uint32_t> args,
                        bool mayErase = true) {
    uint8_t record[MAX_RECORD];
    Packer packer(record + RECORD_HEADER_SIZE, MAX_PAYLOAD, args.size());
    for (uint32_t value : args) packer.add(value);
    return ring.append(record, packer.size(), id, ms, mayErase);
}

uint32_t arg(const Record& record, size_t index) {
    uint32_t value = 0;
    assert(readUnsignedArg(record.payload.data(), record.payload.size(), index, value));
    return value;
}

void testPackerEncoding() {
    uint8_t buffer[MAX_PAYLOAD];
    Packer packer(buffer, sizeof(buffer), 6);
    packer.add(uint8_t(5));
    packer.add(-3);
    packer.add("open");
    packer.add(1.5f);
    packer.add(300000UL);
    const uint8_t raw[3] = {1, 2, 3};
    packer.add(Bytes{raw, sizeof(raw)});
    const uint8_t expected[] = {
        6, 0x21, 0x43, 0x51,       // count, types (unsigned/signed, string/float, unsigned/bytes)
        5,                         // 5
        5,                         // -3 zigzag
        4, 'o', 'p', 'e', 'n',     // "open"
        0x00, 0x00, 0xC0, 0x3F,    // 1.5f
        0xE0, 0xA7, 0x12,          // 300000 varint
        3, 1, 2, 3,                // bytes
    };
    assert(packer.size() == sizeof(expected));
    assert(memcmp(buffer, expected, sizeof(expected)) == 0);
    uint32_t value = 0;
    assert(readUnsignedArg(buffer, packer.size(), 4, value) && value == 300000);
    assert(!readUnsignedArg(buffer, packer.size(), 1, value));  // signed, not unsigned
    assert(!readUnsignedArg(buffer, packer.size(), 2, value));  // string

    // Long strings are capped; arguments that do not fit set the truncated flag.
    std::string longText(100, 'x');
    uint8_t small[20];
    Packer tight(small, sizeof(small), 3);
    tight.add(7U);
    tight.add(longText.c_str());
    tight.add(9U);
    assert(tight.truncated() && (small[0] & TRUNCATED_FLAG) && (small[0] & 0x7F) == 3);
    assert(readUnsignedArg(small, tight.size(), 0, value) && value == 7);
    Packer capped(buffer, sizeof(buffer), 1);
    capped.add(longText.c_str());
    assert(buffer[2] == MAX_STRING && capped.size() == 3 + MAX_STRING);
}

void testFreshPartitionAndResume() {
    FakeFlash flash(8);
    Ring ring;
    assert(ring.open(flash, DEVICE_ID, BOOT_ID, STABLE_ID));
    assert(!ring.hasCurrent() && !ring.history().found && ring.history().lastBoot == 0);
    ring.setBoot(1);
    // A blank partition needs no erase, even when erasing is not allowed.
    assert(appendArgs(ring, BOOT_ID, 10, {1, 0}, false) == Ring::Result::Written);
    assert(appendArgs(ring, 0x0301, 20, {42}, false) == Ring::Result::Written);
    assert(flash.erases == 0);
    const uint32_t offset = ring.writeOffset();

    // Reboot: continue in the same sector, after the last record, no erase.
    Ring again;
    assert(again.open(flash, DEVICE_ID, BOOT_ID, STABLE_ID));
    assert(again.hasCurrent() && again.currentSector() == 0 && again.writeOffset() == offset);
    assert(again.history().found && again.history().lastBoot == 1 && !again.history().lastStable);
    again.setBoot(2);
    assert(appendArgs(again, BOOT_ID, 5, {2, 0}) == Ring::Result::Written);
    assert(appendArgs(again, STABLE_ID, 60000, {2, 60}) == Ring::Result::Written);
    assert(flash.erases == 0);

    const auto records = readAll(flash);
    assert(records.size() == 4);
    assert(records[0].id == BOOT_ID && arg(records[0], 0) == 1 && records[0].ms == 10);
    assert(records[1].id == 0x0301 && arg(records[1], 0) == 42);
    assert(records[2].id == BOOT_ID && arg(records[2], 0) == 2);

    Ring third;
    assert(third.open(flash, DEVICE_ID, BOOT_ID, STABLE_ID));
    assert(third.history().lastBoot == 2 && third.history().lastStable);
}

void testWrapKeepsNewestRecords() {
    FakeFlash flash(4);
    Ring ring;
    assert(ring.open(flash, DEVICE_ID, BOOT_ID, STABLE_ID));
    ring.setBoot(1);
    uint32_t written = 0;
    for (uint32_t i = 0; i < 2000; ++i) {
        assert(appendArgs(ring, 0x0500, i, {i, i * 7}) == Ring::Result::Written);
        ++written;
    }
    const auto records = readAll(flash);
    // Older sectors were erased and reused; the newest records remain.
    assert(!records.empty() && records.size() < written);
    for (size_t i = 0; i < records.size(); ++i) {
        assert(arg(records[i], 0) == written - records.size() + i);  // newest, in order
        assert(arg(records[i], 1) == arg(records[i], 0) * 7);
    }
    assert(records.back().ms == written - 1);
    assert(ring.currentSequence() > 4);  // wrapped more than once
}

void testEraseOnlyWhenAllowed() {
    FakeFlash flash(4);
    // Old data everywhere: every sector needs an erase before reuse.
    std::fill(flash.bytes.begin(), flash.bytes.end(), 0x00);
    Ring ring;
    assert(ring.open(flash, DEVICE_ID, BOOT_ID, STABLE_ID));
    ring.setBoot(1);
    assert(appendArgs(ring, 0x0100, 1, {1}, false) == Ring::Result::NoSpace);
    assert(flash.erases == 0);
    assert(appendArgs(ring, 0x0100, 2, {2}, true) == Ring::Result::Written);
    assert(flash.erases == 1);

    // Fill the sector while erasing is not allowed: the next sector is not
    // ready, so records are refused until a quiet moment erases it.
    Ring::Result result = Ring::Result::Written;
    uint32_t i = 0;
    while ((result = appendArgs(ring, 0x0100, 3 + i, {i}, false)) == Ring::Result::Written) ++i;
    assert(result == Ring::Result::NoSpace && flash.erases == 1);
    assert(!ring.prepareNext(false) && ring.prepareNext(true) && ring.nextReady());
    assert(flash.erases == 2);
    assert(appendArgs(ring, 0x0100, 9999, {i}, false) == Ring::Result::Written);
    assert(readAll(flash).back().ms == 9999);
}

void testTornWriteClosesSector() {
    FakeFlash flash(4);
    Ring ring;
    assert(ring.open(flash, DEVICE_ID, BOOT_ID, STABLE_ID));
    ring.setBoot(1);
    assert(appendArgs(ring, BOOT_ID, 1, {1, 0}) == Ring::Result::Written);
    assert(appendArgs(ring, 0x0200, 2, {7}) == Ring::Result::Written);
    // Power fails halfway through the next record.
    flash.tornWriteBytes = 5;
    assert(appendArgs(ring, 0x0200, 3, {8, 9, 10}) == Ring::Result::FlashError);
    flash.tornWriteBytes = SIZE_MAX;

    Ring rebooted;
    assert(rebooted.open(flash, DEVICE_ID, BOOT_ID, STABLE_ID));
    assert(rebooted.history().lastBoot == 1);
    rebooted.setBoot(2);
    assert(appendArgs(rebooted, BOOT_ID, 1, {2, 0}) == Ring::Result::Written);
    assert(rebooted.currentSector() == 1);  // the torn sector was closed

    const auto records = readAll(flash);
    assert(records.size() == 3);
    assert(arg(records[1], 0) == 7 && arg(records[2], 0) == 2 && records[2].sequence == 2);
}

void testBootHistoryAcrossSectors() {
    FakeFlash flash(6);
    Ring ring;
    assert(ring.open(flash, DEVICE_ID, BOOT_ID, STABLE_ID));
    ring.setBoot(7);
    assert(appendArgs(ring, BOOT_ID, 1, {7, 2}) == Ring::Result::Written);
    // Enough records to push the writer into the next sector.
    for (uint32_t i = 0; i < 600; ++i) assert(appendArgs(ring, 0x0500, i, {i}) == Ring::Result::Written);
    assert(ring.currentSector() == 1);
    Ring rebooted;
    assert(rebooted.open(flash, DEVICE_ID, BOOT_ID, STABLE_ID));
    const BootHistory& history = rebooted.history();
    assert(history.found && history.lastBoot == 7 && history.lastStreak == 2 && !history.lastStable);
}

// DLOG prints the catalog format to serial and stores the same arguments.
struct Stored {
    uint16_t id;
    bool detail;
    std::vector<uint8_t> payload;
};
std::vector<Stored> g_stored;
uint8_t g_buffer[MAX_PAYLOAD];
uint16_t g_pendingId;
bool g_pendingDetail;
bool g_refuseDetail = false;

uint8_t* testAcquire(uint16_t id, bool detail, size_t* capacity) {
    if (detail && g_refuseDetail) return nullptr;
    g_pendingId = id;
    g_pendingDetail = detail;
    *capacity = sizeof(g_buffer);
    return g_buffer;
}
void testCommit(uint16_t id, size_t length) {
    assert(id == g_pendingId);
    g_stored.push_back({id, g_pendingDetail, std::vector<uint8_t>(g_buffer, g_buffer + length)});
}
const Backend g_testBackend = {testAcquire, testCommit};

void testMacros() {
    DLOG(BLE_DISCONNECT, 1, 0x13, 0);  // printed only: no backend yet
    assert(Serial.output == "[BLE] DISCONNECT conn=1 reason=0x13 was_controller=0\n");
    assert(g_stored.empty());

    backend() = &g_testBackend;
    Serial.output.clear();
    int evaluations = 0;
    DLOG(BLE_DISCONNECT, ++evaluations, 0x08, 1);
    assert(evaluations == 1);
    assert(Serial.output == "[BLE] DISCONNECT conn=1 reason=0x08 was_controller=1\n");
    assert(g_stored.size() == 1 && g_stored[0].id == DEVLOG_ID_BLE_DISCONNECT && !g_stored[0].detail);
    uint32_t value = 0;
    assert(readUnsignedArg(g_stored[0].payload.data(), g_stored[0].payload.size(), 0, value) == false);  // signed int
    assert(g_stored[0].payload[0] == 3);

    DLOG(PAIRING_OPEN);
    assert(Serial.output.find("[Pairing] Open for 60 seconds") != std::string::npos);
    assert(g_stored.back().id == DEVLOG_ID_PAIRING_OPEN && g_stored.back().payload == std::vector<uint8_t>{0});

    g_refuseDetail = true;
    Serial.output.clear();
    DLOG_DETAIL(DEVICE_NAME, "SweetYaar");
    assert(Serial.output == "[Device] btName=SweetYaar\n");  // still printed
    assert(g_stored.back().id == DEVLOG_ID_PAIRING_OPEN);    // not stored

    Serial.output.clear();
    DLOG_STORE(SM_EVENT, 1U, 6U);
    assert(Serial.output.empty());
    assert(g_stored.back().id == DEVLOG_ID_SM_EVENT);
    assert(readUnsignedArg(g_stored.back().payload.data(), g_stored.back().payload.size(), 1, value) && value == 6);
    backend() = nullptr;
}

void testRepeatFilter() {
    RepeatFilter filter;
    std::vector<Repeat> emitted;
    auto emit = [&](const Repeat& repeat) { emitted.push_back(repeat); };
    const uint8_t a[] = {1, 0x01, 78};  // one argument
    const uint8_t b[] = {1, 0x01, 79};  // one millivolt apart: a different line
    const uint16_t ADC = DEVLOG_ID_BATTERY_ADC_INVALID;
    const uint16_t I2C = DEVLOG_ID_CHARGER_I2C_READ_FAILED;

    // First, then counted.
    assert(filter.admit(ADC, a, sizeof(a), 1000, emit));
    assert(!filter.admit(ADC, a, sizeof(a), 31000, emit));
    assert(!filter.admit(ADC, a, sizeof(a), 61000, emit));
    assert(emitted.empty() && filter.pending());

    // Another event never flushes this one; the same event changing does.
    assert(filter.admit(I2C, a, sizeof(a), 62000, emit));
    assert(emitted.empty());
    assert(filter.admit(ADC, b, sizeof(b), 91000, emit));
    assert(emitted.size() == 1);
    assert(emitted[0].id == ADC && emitted[0].firstMs == 1000 && emitted[0].count == 2 &&
           emitted[0].lastMs == 61000);

    // Alternating lines are each remembered and counted.
    assert(!filter.admit(ADC, a, sizeof(a), 121000, emit));
    assert(!filter.admit(ADC, b, sizeof(b), 151000, emit));
    assert(!filter.admit(ADC, a, sizeof(a), 181000, emit));
    assert(emitted.size() == 1);

    // flush() reports every pending count, then counting starts again.
    filter.flush(emit);
    assert(emitted.size() == 3 && !filter.pending());
    std::sort(emitted.begin() + 1, emitted.end(),
              [](const Repeat& x, const Repeat& y) { return x.firstMs < y.firstMs; });
    assert(emitted[1].firstMs == 1000 && emitted[1].count == 2 && emitted[1].lastMs == 181000);
    assert(emitted[2].firstMs == 91000 && emitted[2].count == 1 && emitted[2].lastMs == 151000);
    assert(!filter.admit(ADC, a, sizeof(a), 211000, emit));  // still remembered
    filter.flush(emit);
    assert(emitted.size() == 4 && emitted[3].count == 1);

    // A full table reuses the least recently seen line, reporting its count.
    RepeatFilter full;
    emitted.clear();
    for (uint8_t i = 0; i < RepeatFilter::SLOTS; ++i) {
        const uint8_t line[] = {1, 0x01, i};
        assert(full.admit(I2C, line, sizeof(line), 1000u + i, emit));
    }
    emitted.clear();  // each new line of the same event flushed nothing pending
    const uint8_t first[] = {1, 0x01, 0};
    assert(!full.admit(I2C, first, sizeof(first), 5000, emit));  // line 0 is now the newest
    const uint8_t extra[] = {1, 0x01, 200};
    assert(full.admit(I2C, extra, sizeof(extra), 6000, emit));
    assert(emitted.size() == 1 && emitted[0].firstMs == 1000 && emitted[0].count == 1);
    const uint8_t second[] = {1, 0x01, 1};
    assert(full.admit(I2C, second, sizeof(second), 7000, emit));  // line 1 was reused
}

}  // namespace

void testSharingStart() {
    assert(sharingStart(0, 1) == 0);
    assert(sharingStart(40, 56) == 40);
    assert(sharingStart(56, 56) == 56);
    // The log started over below the stored opt-in point.
    assert(sharingStart(57, 56) == 0);
    assert(sharingStart(300, 1) == 0);
}

int main() {
    testPackerEncoding();
    testSharingStart();
    testFreshPartitionAndResume();
    testWrapKeepsNewestRecords();
    testEraseOnlyWhenAllowed();
    testTornWriteClosesSector();
    testBootHistoryAcrossSectors();
    testMacros();
    testRepeatFilter();
    std::cout << "devlog tests passed\n";
    return 0;
}

#include <cassert>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <vector>

#include "DevLogFormat.h"
#include "DevLogTransfer.h"

using namespace devlog;

namespace {

const uint8_t DEVICE_ID[6] = {0x24, 0x0A, 0xC4, 0x01, 0x02, 0x03};

class FakeSource : public TransferSource {
public:
    FakeSource(uint32_t sectors, uint32_t coreSize) : log(sectors * SECTOR_SIZE), core(coreSize) {
        for (size_t i = 0; i < log.size(); ++i) log[i] = static_cast<uint8_t>(i * 7 + i / SECTOR_SIZE);
        for (size_t i = 0; i < core.size(); ++i) core[i] = static_cast<uint8_t>(255 - i);
    }
    void deviceId(uint8_t out[6]) override { memcpy(out, DEVICE_ID, 6); }
    uint32_t logSize() override { return static_cast<uint32_t>(log.size()); }
    bool readLog(uint32_t offset, void* data, size_t length) override {
        if (offset == failAt || offset + length > log.size()) return false;
        memcpy(data, log.data() + offset, length);
        return true;
    }
    uint32_t coreDumpSize() override { return static_cast<uint32_t>(core.size()); }
    bool readCoreDump(uint32_t offset, void* data, size_t length) override {
        if (offset + length > core.size()) return false;
        memcpy(data, core.data() + offset, length);
        return true;
    }

    std::vector<uint8_t> log;
    std::vector<uint8_t> core;
    uint32_t failAt = UINT32_MAX;
};

std::vector<uint8_t> request(Region region, uint32_t offset, uint32_t length) {
    std::vector<uint8_t> bytes = {5, static_cast<uint8_t>(region)};
    for (int i = 0; i < 4; ++i) bytes.push_back(static_cast<uint8_t>(offset >> (8 * i)));
    for (int i = 0; i < 4; ++i) bytes.push_back(static_cast<uint8_t>(length >> (8 * i)));
    return bytes;
}

uint32_t u32(const uint8_t* bytes) {
    return uint32_t(bytes[0]) | (uint32_t(bytes[1]) << 8) | (uint32_t(bytes[2]) << 16) |
           (uint32_t(bytes[3]) << 24);
}

struct Packet {
    uint8_t region;
    uint32_t offset;
    std::vector<uint8_t> bytes;
};

// Starts a read and collects every packet it produces.
std::vector<Packet> run(TransferSender& sender, Region region, uint32_t offset, uint32_t length,
                        size_t capacity) {
    const auto bytes = request(region, offset, length);
    assert(sender.request(bytes.data(), bytes.size()));
    std::vector<Packet> packets;
    uint8_t buffer[512];
    while (size_t size = sender.next(buffer, capacity)) {
        assert(size <= capacity && size >= TRANSFER_PACKET_HEADER);
        packets.push_back({buffer[0], u32(buffer + 1),
                           std::vector<uint8_t>(buffer + TRANSFER_PACKET_HEADER, buffer + size)});
        assert(packets.size() < 100000);
    }
    assert(!sender.active());
    return packets;
}

std::vector<uint8_t> joined(const std::vector<Packet>& packets, Region region, uint32_t offset) {
    std::vector<uint8_t> data;
    for (const auto& packet : packets) {
        assert(packet.region == static_cast<uint8_t>(region));
        assert(packet.offset == offset + data.size());  // in order, no gaps
        data.insert(data.end(), packet.bytes.begin(), packet.bytes.end());
    }
    return data;
}

void testInfo() {
    FakeSource source(8, 300);
    TransferSender sender(source);
    const auto data = joined(run(sender, Region::Info, 0, 100, 512), Region::Info, 0);
    assert(data.size() == TRANSFER_INFO_SIZE);  // clipped to the region
    assert(data[0] == TRANSFER_INFO_FORMAT);
    assert(memcmp(data.data() + 1, DEVICE_ID, 6) == 0);
    assert(data[7] == SECTOR_HEADER_SIZE);
    assert(u32(data.data() + 8) == SECTOR_SIZE);
    assert(u32(data.data() + 12) == 8 * SECTOR_SIZE);
    assert(u32(data.data() + 16) == 300);
    // Any slice of it, as at the minimum MTU.
    const auto tail = joined(run(sender, Region::Info, 3, 17, 20), Region::Info, 3);
    assert(std::vector<uint8_t>(data.begin() + 3, data.end()) == tail);
}

void testHeadersAreTheSectorStarts() {
    FakeSource source(8, 0);
    TransferSender sender(source);
    // A small packet size splits headers across packets.
    const auto data = joined(run(sender, Region::Headers, 0, UINT32_MAX, 5 + 17), Region::Headers, 0);
    assert(data.size() == 8 * SECTOR_HEADER_SIZE);
    for (uint32_t sector = 0; sector < 8; ++sector) {
        assert(memcmp(data.data() + sector * SECTOR_HEADER_SIZE,
                      source.log.data() + sector * SECTOR_SIZE, SECTOR_HEADER_SIZE) == 0);
    }
    const auto middle = joined(run(sender, Region::Headers, 30, 40, 512), Region::Headers, 30);
    assert(std::vector<uint8_t>(data.begin() + 30, data.begin() + 70) == middle);
}

void testLogRangeAndClipping() {
    FakeSource source(8, 0);
    TransferSender sender(source);
    const uint32_t start = 3 * SECTOR_SIZE + 100;
    const auto packets = run(sender, Region::Log, start, 2 * SECTOR_SIZE, 512);
    const auto data = joined(packets, Region::Log, start);
    assert(data == std::vector<uint8_t>(source.log.begin() + start, source.log.begin() + start + 2 * SECTOR_SIZE));
    assert(packets.front().bytes.size() == 512 - TRANSFER_PACKET_HEADER);
    // Past the end of the partition: clipped, and the offset never wraps.
    const auto tail = joined(run(sender, Region::Log, 7 * SECTOR_SIZE, UINT32_MAX, 512), Region::Log,
                             7 * SECTOR_SIZE);
    assert(tail.size() == SECTOR_SIZE);
}

void testCoreDump() {
    FakeSource source(8, 1000);
    TransferSender sender(source);
    assert(joined(run(sender, Region::CoreDump, 0, 1000, 512), Region::CoreDump, 0) == source.core);
    FakeSource none(8, 0);
    TransferSender empty(none);
    const auto packets = run(empty, Region::CoreDump, 0, 1000, 512);
    assert(packets.size() == 1 && packets[0].offset == 0 && packets[0].bytes.empty());
}

void testEndAndFailureAreHeaderOnly() {
    FakeSource source(8, 0);
    TransferSender sender(source);
    auto packets = run(sender, Region::Log, 8 * SECTOR_SIZE, 10, 512);
    assert(packets.size() == 1 && packets[0].offset == 8 * SECTOR_SIZE && packets[0].bytes.empty());
    source.failAt = SECTOR_SIZE + 2 * (512 - TRANSFER_PACKET_HEADER);
    packets = run(sender, Region::Log, SECTOR_SIZE, SECTOR_SIZE, 512);
    assert(packets.size() == 3);
    assert(packets[2].offset == source.failAt && packets[2].bytes.empty());
}

void testRequestsReplaceAndReject() {
    FakeSource source(8, 0);
    TransferSender sender(source);
    uint8_t buffer[512];
    assert(!sender.active() && sender.next(buffer, sizeof(buffer)) == 0);
    auto first = request(Region::Log, 0, 8 * SECTOR_SIZE);
    assert(sender.request(first.data(), first.size()));
    assert(sender.next(buffer, sizeof(buffer)) > TRANSFER_PACKET_HEADER);
    // A malformed request keeps the read in progress.
    auto shortRequest = request(Region::Log, 0, 1);
    shortRequest.pop_back();
    assert(!sender.request(shortRequest.data(), shortRequest.size()));
    auto badRegion = request(Region::Log, 0, 1);
    badRegion[1] = REGION_COUNT;
    assert(!sender.request(badRegion.data(), badRegion.size()));
    assert(sender.active());
    assert(u32(buffer + 1) == 0);
    sender.next(buffer, sizeof(buffer));
    assert(u32(buffer + 1) == 512 - TRANSFER_PACKET_HEADER);
    // A new request replaces it (the client asks again after a lost packet).
    auto again = request(Region::Log, 100, 50);
    assert(sender.request(again.data(), again.size()));
    assert(sender.next(buffer, sizeof(buffer)) == TRANSFER_PACKET_HEADER + 50);
    assert(u32(buffer + 1) == 100 && !sender.active());
    // No room for data: nothing is sent and the read waits.
    assert(sender.request(again.data(), again.size()));
    assert(sender.next(buffer, TRANSFER_PACKET_HEADER) == 0 && sender.active());
}

}  // namespace

int main() {
    testInfo();
    testHeadersAreTheSectorStarts();
    testLogRangeAndClipping();
    testCoreDump();
    testEndAndFailureAreHeaderOnly();
    testRequestsReplaceAndReject();
    std::cout << "devlog transfer tests passed\n";
    return 0;
}

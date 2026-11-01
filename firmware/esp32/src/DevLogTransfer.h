#pragma once

// Reading the log over BLE. The client asks for a byte range
// of one region and the toy streams it as notifications, each starting with
// the region and offset, so a lost packet is asked for again. Platform
// independent so host tests can run it against a fake source; DevLog.cpp
// supplies the flash and OtaUpdate.cpp the BLE transport. See "Fetching the
// log over BLE" in docs/logging-and-debugging.md.

#include <stddef.h>
#include <stdint.h>

namespace devlog {

enum class Region : uint8_t {
    Info = 0,      // TRANSFER_INFO_SIZE bytes, below
    Headers = 1,   // every sector's header, back to back
    Log = 2,       // the whole log partition
    CoreDump = 3,  // a core dump not yet copied into the log (empty if none)
};
constexpr uint8_t REGION_COUNT = 4;

// Request: command byte, region, offset (u32), length (u32), little endian.
constexpr size_t TRANSFER_REQUEST_SIZE = 10;
// Packet: region, offset (u32), then the bytes at that offset.
constexpr size_t TRANSFER_PACKET_HEADER = 5;
// Packet region of a read stopped because the toy is busy (normal mode:
// playing, or a Classic Bluetooth link); the offset is the next byte it
// would have sent.
constexpr uint8_t TRANSFER_BUSY = 0xFE;
// Info: format, device ID (6), sector header size, sector size (u32),
// log size (u32), core dump size (u32).
constexpr uint8_t TRANSFER_INFO_FORMAT = 1;
constexpr size_t TRANSFER_INFO_SIZE = 20;

class TransferSource {
public:
    virtual ~TransferSource() {}
    virtual void deviceId(uint8_t out[6]) = 0;
    virtual uint32_t logSize() = 0;
    virtual bool readLog(uint32_t offset, void* data, size_t length) = 0;
    // 0 when no core dump waits in its partition.
    virtual uint32_t coreDumpSize() = 0;
    virtual bool readCoreDump(uint32_t offset, void* data, size_t length) = 0;
};

// Runs on one task: request() replaces the read in progress, next() fills
// the packets.
class TransferSender {
public:
    explicit TransferSender(TransferSource& source) : _source(source) {}

    // False for a malformed request; the read in progress then continues.
    bool request(const uint8_t* data, size_t length);
    bool active() const { return _active; }

    // Fills the next packet, at most |capacity| bytes; returns its length, or
    // 0 when nothing is left to send. A request at or past the region's end,
    // or a failed flash read, gets one header-only packet and ends the read.
    size_t next(uint8_t* packet, size_t capacity);
    // Ends the read and fills the busy packet (TRANSFER_PACKET_HEADER bytes).
    size_t busy(uint8_t* packet);
    // Ends the read without a packet (the client went away).
    void cancel() { _active = false; }

private:
    bool read(uint32_t offset, uint8_t* data, size_t length);

    TransferSource& _source;
    bool _active = false;
    Region _region = Region::Info;
    uint32_t _offset = 0;
    uint32_t _end = 0;  // clipped to the region size at request time
};

}  // namespace devlog

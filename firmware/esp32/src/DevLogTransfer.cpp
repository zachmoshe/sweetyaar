#include "DevLogTransfer.h"

#include <string.h>

#include "DevLogFormat.h"

namespace devlog {
namespace {

uint32_t readU32(const uint8_t* bytes) {
    return uint32_t(bytes[0]) | (uint32_t(bytes[1]) << 8) |
           (uint32_t(bytes[2]) << 16) | (uint32_t(bytes[3]) << 24);
}

void writeU32(uint8_t* out, uint32_t value) {
    for (int i = 0; i < 4; ++i) out[i] = static_cast<uint8_t>(value >> (8 * i));
}

}  // namespace

bool TransferSender::request(const uint8_t* data, size_t length) {
    if (length != TRANSFER_REQUEST_SIZE || data[1] >= REGION_COUNT) return false;
    _region = static_cast<Region>(data[1]);
    _offset = readU32(data + 2);
    uint32_t size = 0;
    switch (_region) {
        case Region::Info: size = TRANSFER_INFO_SIZE; break;
        case Region::Headers:
            size = _source.logSize() / SECTOR_SIZE * SECTOR_HEADER_SIZE;
            break;
        case Region::Log: size = _source.logSize(); break;
        case Region::CoreDump: size = _source.coreDumpSize(); break;
    }
    const uint64_t end = uint64_t(_offset) + readU32(data + 6);
    _end = end < size ? static_cast<uint32_t>(end) : size;
    _active = true;
    return true;
}

size_t TransferSender::next(uint8_t* packet, size_t capacity) {
    if (!_active || capacity <= TRANSFER_PACKET_HEADER) return 0;
    size_t length = 0;
    if (_offset < _end) {
        length = capacity - TRANSFER_PACKET_HEADER;
        if (length > _end - _offset) length = _end - _offset;
        if (!read(_offset, packet + TRANSFER_PACKET_HEADER, length)) length = 0;
    }
    packet[0] = static_cast<uint8_t>(_region);
    writeU32(packet + 1, _offset);
    _offset += length;
    _active = length > 0 && _offset < _end;
    return TRANSFER_PACKET_HEADER + length;
}

bool TransferSender::read(uint32_t offset, uint8_t* data, size_t length) {
    switch (_region) {
        case Region::Info: {
            uint8_t info[TRANSFER_INFO_SIZE];
            info[0] = TRANSFER_INFO_FORMAT;
            _source.deviceId(info + 1);
            info[7] = SECTOR_HEADER_SIZE;
            writeU32(info + 8, SECTOR_SIZE);
            writeU32(info + 12, _source.logSize());
            writeU32(info + 16, _source.coreDumpSize());
            memcpy(data, info + offset, length);
            return true;
        }
        case Region::Headers:
            // Header n is at n * SECTOR_HEADER_SIZE here and at n * SECTOR_SIZE in flash.
            while (length > 0) {
                const uint32_t sector = offset / SECTOR_HEADER_SIZE;
                const uint32_t within = offset % SECTOR_HEADER_SIZE;
                size_t piece = SECTOR_HEADER_SIZE - within;
                if (piece > length) piece = length;
                if (!_source.readLog(sector * SECTOR_SIZE + within, data, piece)) return false;
                offset += piece;
                data += piece;
                length -= piece;
            }
            return true;
        case Region::Log: return _source.readLog(offset, data, length);
        case Region::CoreDump: return _source.readCoreDump(offset, data, length);
    }
    return false;
}

}  // namespace devlog

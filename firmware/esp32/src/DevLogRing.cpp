#include "DevLogRing.h"

#include <string.h>

namespace devlog {

namespace {
const uint8_t MAGIC[4] = {'S', 'Y', 'L', 'G'};
}

bool Ring::open(Flash& flash, const uint8_t deviceId[6], uint16_t bootId, uint16_t stableId) {
    _flash = &flash;
    memcpy(_deviceId, deviceId, sizeof(_deviceId));
    _bootId = bootId;
    _stableId = stableId;
    _sectors = flash.size() / SECTOR_SIZE;
    _history = BootHistory();
    _hasCurrent = false;
    _closed = false;
    _lastSequence = 0;
    _nextState = NextState::Unknown;
    if (_sectors < 3) return false;

    bool found = false;
    Header newest = {0, 0};
    uint32_t newestSector = 0;
    for (uint32_t sector = 0; sector < _sectors; ++sector) {
        Header header;
        if (readHeader(sector, header) && (!found || header.sequence > newest.sequence)) {
            found = true;
            newest = header;
            newestSector = sector;
        }
    }
    if (!found) {
        _next = 0;
        return true;
    }

    // The previous sector usually holds the latest BOOT when this one does not.
    const uint32_t previous = (newestSector + _sectors - 1) % _sectors;
    Header previousHeader;
    if (newest.sequence > 1 && readHeader(previous, previousHeader) &&
        previousHeader.sequence == newest.sequence - 1) {
        bool ignored = true;
        scanRecords(previous, ignored);
    }
    bool clean = true;
    _writeOffset = scanRecords(newestSector, clean);
    _closed = !clean || !blankFrom(newestSector, _writeOffset);

    if (newest.boot > _history.lastBoot) {
        // The BOOT of the boot that opened this sector has been overwritten.
        _history.lastBoot = newest.boot;
        _history.lastStreak = 0;
        _history.lastStable = true;
    }
    _hasCurrent = true;
    _current = newestSector;
    _lastSequence = newest.sequence;
    _next = (newestSector + 1) % _sectors;
    return true;
}

Ring::Result Ring::append(uint8_t* record, size_t payloadLength, uint16_t id, uint32_t ms,
                          bool mayErase) {
    if (_flash == nullptr || payloadLength > MAX_PAYLOAD) return Result::FlashError;
    const size_t total = RECORD_OVERHEAD + payloadLength;
    if (!_hasCurrent || _closed || _writeOffset + total > SECTOR_SIZE) {
        Result failure = Result::NoSpace;
        if (!openNextSector(mayErase, failure)) return failure;
    }
    record[0] = static_cast<uint8_t>(payloadLength);
    putLe16(record + 1, id);
    putLe32(record + 3, ms);
    record[RECORD_HEADER_SIZE + payloadLength] =
        crc8(record, RECORD_HEADER_SIZE + payloadLength);
    if (!_flash->write(_current * SECTOR_SIZE + _writeOffset, record, total)) {
        // The bytes may be partly written; continue in a fresh sector.
        _closed = true;
        return Result::FlashError;
    }
    _writeOffset += total;
    return Result::Written;
}

bool Ring::prepareNext(bool mayErase) {
    if (_flash == nullptr) return false;
    if (_nextState == NextState::Erased) return true;
    if (_nextState == NextState::Unknown) {
        _nextState = blankFrom(_next, 0) ? NextState::Erased : NextState::Dirty;
        if (_nextState == NextState::Erased) return true;
    }
    if (!mayErase) return false;
    if (!_flash->eraseSector(_next * SECTOR_SIZE)) return false;
    _nextState = NextState::Erased;
    return true;
}

bool Ring::openNextSector(bool mayErase, Result& failure) {
    if (!prepareNext(mayErase)) {
        failure = Result::NoSpace;
        return false;
    }
    const uint32_t sequence = _lastSequence + 1;
    if (!writeHeader(_next, sequence)) {
        // Leave it for a later erase rather than writing into a bad header.
        _nextState = NextState::Dirty;
        failure = Result::FlashError;
        return false;
    }
    _current = _next;
    _hasCurrent = true;
    _closed = false;
    _lastSequence = sequence;
    _writeOffset = SECTOR_HEADER_SIZE;
    _next = (_current + 1) % _sectors;
    _nextState = NextState::Unknown;
    return true;
}

bool Ring::readHeader(uint32_t sector, Header& header) {
    uint8_t bytes[SECTOR_HEADER_SIZE];
    if (!_flash->read(sector * SECTOR_SIZE, bytes, sizeof(bytes))) return false;
    if (memcmp(bytes, MAGIC, sizeof(MAGIC)) != 0 || bytes[4] != FORMAT_VERSION ||
        bytes[5] != SECTOR_HEADER_SIZE ||
        crc8(bytes, SECTOR_HEADER_SIZE - 1) != bytes[SECTOR_HEADER_SIZE - 1]) {
        return false;
    }
    header.sequence = getLe32(bytes + 8);
    header.boot = getLe32(bytes + 12);
    return true;
}

bool Ring::writeHeader(uint32_t sector, uint32_t sequence) {
    uint8_t bytes[SECTOR_HEADER_SIZE];
    memcpy(bytes, MAGIC, sizeof(MAGIC));
    bytes[4] = FORMAT_VERSION;
    bytes[5] = SECTOR_HEADER_SIZE;
    bytes[6] = ERASED_BYTE;
    bytes[7] = ERASED_BYTE;
    putLe32(bytes + 8, sequence);
    putLe32(bytes + 12, _boot);
    memcpy(bytes + 16, _deviceId, sizeof(_deviceId));
    bytes[22] = ERASED_BYTE;
    bytes[23] = crc8(bytes, SECTOR_HEADER_SIZE - 1);
    return _flash->write(sector * SECTOR_SIZE, bytes, sizeof(bytes));
}

bool Ring::blankFrom(uint32_t sector, uint32_t from) {
    uint8_t chunk[64];
    for (uint32_t offset = from; offset < SECTOR_SIZE; offset += sizeof(chunk)) {
        const size_t length = SECTOR_SIZE - offset < sizeof(chunk) ? SECTOR_SIZE - offset
                                                                   : sizeof(chunk);
        if (!_flash->read(sector * SECTOR_SIZE + offset, chunk, length)) return false;
        for (size_t i = 0; i < length; ++i) {
            if (chunk[i] != ERASED_BYTE) return false;
        }
    }
    return true;
}

uint32_t Ring::scanRecords(uint32_t sector, bool& clean) {
    uint8_t record[MAX_RECORD];
    uint32_t offset = SECTOR_HEADER_SIZE;
    clean = true;
    while (offset + RECORD_OVERHEAD <= SECTOR_SIZE) {
        const uint32_t base = sector * SECTOR_SIZE + offset;
        if (!_flash->read(base, record, 1)) {
            clean = false;
            break;
        }
        const size_t length = record[0];
        if (length == ERASED_BYTE) break;
        const size_t total = RECORD_OVERHEAD + length;
        if (length > MAX_PAYLOAD || offset + total > SECTOR_SIZE ||
            !_flash->read(base, record, total) ||
            crc8(record, total - 1) != record[total - 1]) {
            clean = false;  // torn or corrupted record: stop here
            break;
        }
        const uint16_t id = getLe16(record + 1);
        const uint8_t* payload = record + RECORD_HEADER_SIZE;
        uint32_t value = 0;
        if (id == _bootId && readUnsignedArg(payload, length, 0, value)) {
            _history.found = true;
            _history.lastBoot = value;
            _history.lastStreak = readUnsignedArg(payload, length, 1, value) ? value : 0;
            _history.lastStable = false;
        } else if (id == _stableId) {
            _history.lastStable = true;
        }
        offset += total;
    }
    return offset;
}

}  // namespace devlog

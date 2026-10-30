#pragma once

// Ring of 4 KiB flash sectors holding the diagnostic log. Platform independent
// so host tests can run it against a simulated flash; DevLog.cpp supplies the
// partition, the lock and the timestamps. See docs/logging-and-debugging.md.

#include <stddef.h>
#include <stdint.h>

#include "DevLogFormat.h"

namespace devlog {

class Flash {
public:
    virtual ~Flash() {}
    virtual uint32_t size() const = 0;
    virtual bool read(uint32_t offset, void* data, size_t length) = 0;
    virtual bool write(uint32_t offset, const void* data, size_t length) = 0;
    virtual bool eraseSector(uint32_t offset) = 0;
};

// What the boot scan found about the most recent boot in the log.
struct BootHistory {
    bool found = false;     // a BOOT record was read
    uint32_t lastBoot = 0;  // highest boot number seen (records or headers)
    uint32_t lastStreak = 0;
    bool lastStable = true;
};

class Ring {
public:
    enum class Result : uint8_t { Written, NoSpace, FlashError };

    // Scans the partition and positions the writer after the newest record.
    // bootId and stableId identify the records the boot history comes from.
    bool open(Flash& flash, const uint8_t deviceId[6], uint16_t bootId, uint16_t stableId);

    const BootHistory& history() const { return _history; }

    // Boot number written into the headers of sectors opened from now on.
    void setBoot(uint32_t boot) { _boot = boot; }

    // record holds MAX_RECORD bytes with the payload at RECORD_HEADER_SIZE.
    // The header and CRC are filled in here. mayErase allows an erase when the
    // next sector is not ready (only while no audio plays).
    Result append(uint8_t* record, size_t payloadLength, uint16_t id, uint32_t ms,
                  bool mayErase);

    // Makes sure the sector after the current one is erased. Without
    // mayErase it only checks whether that sector is already blank.
    bool prepareNext(bool mayErase);
    bool nextReady() const { return _nextState == NextState::Erased; }

    uint32_t sectorCount() const { return _sectors; }
    bool hasCurrent() const { return _hasCurrent; }
    uint32_t currentSector() const { return _current; }
    uint32_t currentSequence() const { return _lastSequence; }
    uint32_t writeOffset() const { return _writeOffset; }

private:
    enum class NextState : uint8_t { Unknown, Erased, Dirty };

    struct Header {
        uint32_t sequence;
        uint32_t boot;
    };

    bool readHeader(uint32_t sector, Header& header);
    bool writeHeader(uint32_t sector, uint32_t sequence);
    bool blankFrom(uint32_t sector, uint32_t from);
    // Walks a sector's records; returns the offset after the last valid one.
    uint32_t scanRecords(uint32_t sector, bool& clean);
    bool openNextSector(bool mayErase, Result& failure);

    Flash* _flash = nullptr;
    uint8_t _deviceId[6] = {};
    uint16_t _bootId = 0;
    uint16_t _stableId = 0;
    uint32_t _sectors = 0;
    bool _hasCurrent = false;
    bool _closed = false;
    uint32_t _current = 0;
    uint32_t _lastSequence = 0;
    uint32_t _writeOffset = 0;
    uint32_t _next = 0;
    NextState _nextState = NextState::Unknown;
    uint32_t _boot = 0;
    BootHistory _history;
};

// A pending REPEATED summary: `count` more records identical to the stored
// one at `firstMs`, the newest at `lastMs`.
struct Repeat {
    uint16_t id;
    uint32_t firstMs;
    uint32_t count;
    uint32_t lastMs;
};

// Stores each distinct line of a repeating condition once and counts its
// identical repeats ("the same" is the same event with byte-identical
// arguments). Remembers the last SLOTS distinct lines, so alternating lines
// are each stored once. Pending counts are handed to `emit`, which stores the
// REPEATED record: before a new line of the same event, when a slot is
// reused, and on flush().
class RepeatFilter {
public:
    static constexpr size_t SLOTS = 16;

    // Returns false when this record repeats a remembered line and was only
    // counted; true when it must be stored (after any summaries emitted).
    template <typename Emit>
    bool admit(uint16_t id, const uint8_t* payload, size_t length, uint32_t ms, Emit&& emit) {
        const uint32_t hash = hashOf(id, payload, length);
        Slot* reuse = &_slots[0];
        for (Slot& slot : _slots) {
            if (slot.repeat.id == id && slot.hash == hash) {
                ++slot.repeat.count;
                slot.repeat.lastMs = ms;
                return false;
            }
            // A free slot, else the one whose line was seen least recently.
            if (reuse->repeat.id != 0 &&
                (slot.repeat.id == 0 || ms - slot.repeat.lastMs > ms - reuse->repeat.lastMs)) {
                reuse = &slot;
            }
        }
        for (Slot& slot : _slots) {
            if (slot.repeat.id == id) flushSlot(slot, emit);  // this event changed
        }
        flushSlot(*reuse, emit);
        reuse->hash = hash;
        reuse->repeat = Repeat{id, ms, 0, ms};
        return true;
    }

    // Emits every pending count; the lines stay remembered.
    template <typename Emit>
    void flush(Emit&& emit) {
        for (Slot& slot : _slots) flushSlot(slot, emit);
    }

    bool pending() const {
        for (const Slot& slot : _slots) {
            if (slot.repeat.count > 0) return true;
        }
        return false;
    }

private:
    struct Slot {
        uint32_t hash = 0;
        Repeat repeat = {};  // id 0 marks a free slot (no event uses ID 0)
    };

    template <typename Emit>
    static void flushSlot(Slot& slot, Emit& emit) {
        if (slot.repeat.count == 0) return;
        emit(static_cast<const Repeat&>(slot.repeat));
        slot.repeat.count = 0;
    }

    // FNV-1a over the event ID and the encoded arguments.
    static uint32_t hashOf(uint16_t id, const uint8_t* payload, size_t length) {
        uint32_t hash = 2166136261u;
        hash = (hash ^ static_cast<uint8_t>(id)) * 16777619u;
        hash = (hash ^ static_cast<uint8_t>(id >> 8)) * 16777619u;
        for (size_t i = 0; i < length; ++i) hash = (hash ^ payload[i]) * 16777619u;
        return hash;
    }

    Slot _slots[SLOTS];
};

}  // namespace devlog

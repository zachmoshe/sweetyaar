#pragma once

// Diagnostic log: DLOG(NAME, args...) prints DEVLOG_FMT_NAME to serial, as
// Serial.printf did, and stores DEVLOG_ID_NAME with the arguments in the
// flash log. See DevLogEvents.h and docs/logging-and-debugging.md.
//
//   DLOG(name, ...)         print and store
//   DLOG_DETAIL(name, ...)  print; store except after a deep-sleep wake
//   DLOG_STORE(name, ...)   store only
//
// Arguments are evaluated once. Allowed types: integers, bool, float/double,
// C strings and devlog::Bytes (pass String.c_str(), cast enums).

#include <stddef.h>
#include <stdint.h>

#include "DevLogEvents.h"
#include "DevLogFormat.h"

namespace devlog {

// Firmware side, in DevLog.cpp. begin() opens the log partition, writes the
// boot records and copies a pending core dump; call it first in setup().
// service() runs from loop(): quiet means no WAV, cue or Bluetooth audio is
// playing, so a sector may be erased ahead of time.
void begin();
void service(bool quiet);
// Stores pending REPEATED counts now; call before deep sleep (a restart
// does it by itself).
void flushRepeats();

// The sector being written: its sequence and index in the ring. False until
// the log is open.
struct Position {
    uint32_t sequence;
    uint32_t sector;
    uint32_t sectors;
};
bool position(Position& out);

// Sequences only grow within one log, so a sharing start past the sector
// being written belongs to a log that is gone (erased or new partition):
// share the new log from its start.
inline uint32_t sharingStart(uint32_t from, uint32_t sequence) {
    return from > sequence ? 0 : from;
}

class TransferSource;
// The log partition and a core dump not yet copied into it, read-only, for
// the fetch over BLE (DevLogTransfer.h).
TransferSource& transferSource();

// Storage behind the macros; DevLog.cpp installs it once the log partition is
// open. Without it (host tests, before begin()) logging only prints.
struct Backend {
    // Returns the payload buffer, or nullptr when this record is not stored.
    uint8_t* (*acquire)(uint16_t id, bool detail, size_t* capacity);
    void (*commit)(uint16_t id, size_t payloadLength);
};

inline const Backend*& backend() {
    static const Backend* instance = nullptr;
    return instance;
}

inline void packAll(Packer&) {}

template <typename T, typename... Rest>
inline void packAll(Packer& packer, T value, Rest... rest) {
    packer.add(value);
    packAll(packer, rest...);
}

template <typename... Args>
inline void store(uint16_t id, bool detail, Args... args) {
    const Backend* storage = backend();
    if (storage == nullptr) return;
    size_t capacity = 0;
    uint8_t* payload = storage->acquire(id, detail, &capacity);
    if (payload == nullptr) return;
    Packer packer(payload, capacity, sizeof...(Args));
    packAll(packer, args...);
    storage->commit(id, packer.size());
}

// Never called at run time; lets the compiler check each format string.
inline void checkFormat(const char*, ...) __attribute__((format(printf, 1, 2)));
inline void checkFormat(const char*, ...) {}

template <typename Output>
inline void emit(Output& output, uint16_t id, bool detail, const char* line) {
    output.printf("%s", line);
    store(id, detail);
}

template <typename Output, typename First, typename... Rest>
inline void emit(Output& output, uint16_t id, bool detail, const char* format,
                 First first, Rest... rest) {
    output.printf(format, first, rest...);
    store(id, detail, first, rest...);
}

}  // namespace devlog

#define DEVLOG_EMIT_(name, detail, ...) do { \
    if (false) ::devlog::checkFormat(DEVLOG_FMT_##name "\n", ##__VA_ARGS__); \
    ::devlog::emit(Serial, DEVLOG_ID_##name, detail, DEVLOG_FMT_##name "\n", ##__VA_ARGS__); \
} while (0)

#define DLOG(name, ...) DEVLOG_EMIT_(name, false, ##__VA_ARGS__)
#define DLOG_DETAIL(name, ...) DEVLOG_EMIT_(name, true, ##__VA_ARGS__)
#define DLOG_STORE(name, ...) ::devlog::store(DEVLOG_ID_##name, false, ##__VA_ARGS__)

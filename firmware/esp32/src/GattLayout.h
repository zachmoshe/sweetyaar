#pragma once
#include <cstddef>
#include <cstdint>
#include <cstring>

// Bonded clients (macOS in particular) cache the GATT table by handle and do
// not rediscover it on reconnect. ESP-IDF 4.4's Bluedroid never persists
// which bonded clients still need a Service Changed indication, so the
// firmware keeps one fingerprint per bonded identity and sends the indication
// itself when the running table differs from what that client last saw.
static constexpr char GATT_LAYOUT_NAMESPACE[] = "sy-gatt";

// FNV-1a over everything a client caches: UUIDs, handles, descriptors and
// access. Arduino assigns handles at runtime, so hash the real values.
struct GattLayoutHash {
    uint32_t value = 2166136261u;
    void add(const uint8_t* data, size_t size) {
        for (size_t i = 0; i < size; ++i) value = (value ^ data[i]) * 16777619u;
    }
    void add(uint16_t number) {
        const uint8_t bytes[2] = {static_cast<uint8_t>(number), static_cast<uint8_t>(number >> 8)};
        add(bytes, sizeof(bytes));
    }
    void add(const char* text) {
        add(reinterpret_cast<const uint8_t*>(text), strlen(text) + 1);
    }
};

// New keys mean a fresh bond: its client may still hold a table cached under
// the old bond (macOS keeps it across Forget), so tell it once regardless.
inline bool gattServiceChangedNeeded(bool hasRecord, uint32_t recorded, uint32_t current, bool newKeys) {
    return newKeys || !hasRecord || recorded != current;
}

// NVS keys are limited to 15 characters: twelve hex digits of the identity.
inline void gattLayoutKey(const uint8_t* identity, char* key) {
    static const char digits[] = "0123456789abcdef";
    for (int i = 0; i < 6; ++i) {
        key[2 * i] = digits[identity[i] >> 4];
        key[2 * i + 1] = digits[identity[i] & 0xf];
    }
    key[12] = '\0';
}

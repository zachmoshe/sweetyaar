#pragma once
#include <stdint.h>
#include <string.h>

// IDF stores SMP keys little-endian; mbedTLS AES uses big-endian blocks.
// Address bytes use the printed Bluetooth order (prand followed by hash).
template<typename Encrypt>
bool bleResolvableAddressMatches(const uint8_t* address, const uint8_t* irk,
                                 Encrypt encrypt) {
    if ((address[0] & 0xc0) != 0x40) return false;
    uint8_t key[16], input[16] = {}, output[16] = {};
    for (int i = 0; i < 16; ++i) key[i] = irk[15 - i];
    memcpy(input + 13, address, 3);
    const bool ok = encrypt(key, input, output);
    const bool matches = ok && memcmp(output + 13, address + 3, 3) == 0;
    // Do not retain temporary key material on the stack.
    volatile uint8_t* wipe = key;
    for (int i = 0; i < 16; ++i) wipe[i] = 0;
    return matches;
}

// The parent service's BLE address after a full bond reset: a static random
// address (two most significant bits set, see Core Spec Vol 6 Part B 1.3.2.1).
// A new one makes every phone and computer see a new device, so none of them
// keeps using keys or a GATT cache the toy no longer has. Classic audio keeps
// its public address.
inline bool isStaticRandomAddress(const uint8_t* address) {
    if ((address[0] & 0xc0) != 0xc0) return false;
    bool zeros = (address[0] & 0x3f) == 0, ones = (address[0] & 0x3f) == 0x3f;
    for (int i = 1; i < 6; ++i) {
        zeros = zeros && address[i] == 0;
        ones = ones && address[i] == 0xff;
    }
    return !zeros && !ones;  // the 46 random bits may be neither
}

inline void makeStaticRandomAddress(const uint8_t* random, uint8_t* address) {
    memcpy(address, random, 6);
    address[0] |= 0xc0;
    if (!isStaticRandomAddress(address)) address[5] ^= 0x01;
}

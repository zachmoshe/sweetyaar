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

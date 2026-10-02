#pragma once
#include <stdint.h>

// Transient link state only. Persistent trust lives in the stack's bond store.
namespace ClassicBluetooth {
void setAccess(bool connectable);
void connected(const uint8_t* address, bool success);
void disconnected(const uint8_t* address);
bool authenticated(const uint8_t* address, bool success);
bool canUseAudio(const uint8_t* address);
bool hasLinks();
void disconnectAll();
}

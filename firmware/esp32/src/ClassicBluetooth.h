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
// Close a link and keep its bond, so the phone can simply connect again.
// Removing the bond is reserved for keys that must not exist.
void closeLink(const uint8_t* address);
// True when this link created fresh keys (as opposed to using saved ones).
bool pairedOnThisLink(const uint8_t* address);
// The link carries an approved A2DP connection.
void audioConnected(const uint8_t* address, bool connected);
// Close links that have had no A2DP connection for IDLE_LINK_MS: the phone
// otherwise shows the toy as connected while it is not usable as a speaker.
// Links still pairing inside the window are left alone. Returns how many closed.
int closeIdleLinks(uint32_t now);
constexpr uint32_t IDLE_LINK_MS = 30000;
// True once after a paired phone's link ended without ever getting its A2DP
// connection, although nothing here refused or closed it and no pairing was
// attempted on it. Seen
// when the connection's set-up ran out of heap: the stack then accepts no
// speaker at all until the firmware restarts.
bool takeIncompleteLink();
// True once after a phone the toy does not know linked, or asked to pair,
// while pairing mode was closed. The phone only says that connecting failed,
// so the toy signals the refusal.
bool takePairingRefused();
constexpr uint32_t INCOMPLETE_LINK_MS = 5000;
}

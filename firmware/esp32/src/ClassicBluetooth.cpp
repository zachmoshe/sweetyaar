#include "ClassicBluetooth.h"
#include "BluetoothAccess.h"
#include <esp_gap_bt_api.h>
#include <esp_idf_version.h>
#include <sdkconfig.h>
#include "DevLog.h"

// Arduino bundles Bluedroid as libbt.a. Its public GAP API does not expose
// pairability and auto-confirms Just Works before delivering an app callback.
// Keep this small adapter pinned to the verified private ABI. BTA queues mode
// changes onto the Bluetooth task; do not mutate BTM globals from loop().
// Source: ESP-IDF v4.4.7 bta_api.h, bta_dm_api.c and btc_dm.c.
#if ESP_IDF_VERSION != ESP_IDF_VERSION_VAL(4, 4, 7)
#error "Revalidate the Classic Bluetooth pairing adapter for this ESP-IDF version"
#endif
extern "C" void BTA_DmSetVisibility(uint16_t, uint16_t, uint8_t, uint8_t);
extern "C" void __real_BTA_DmConfirm(uint8_t*, uint8_t);
// bta_dm_api.c: closes the ACL; remove_dev=0 keeps the bond. transport 1 = BR/EDR.
extern "C" void BTA_DmCloseACL(uint8_t*, uint8_t remove_dev, uint8_t transport);

namespace {
struct Link {
    uint8_t address[6] = {};
    bool used = false;
    bool pairing = false;
    bool authenticated = false;
    bool rejected = false;
    bool audio = false;
    bool audioEver = false;
    bool closing = false;
    bool bonded = false;      // the toy held a saved pairing for this phone when it linked
    bool pairedEver = false;  // a pairing was attempted on this link
    uint32_t since = 0;
};
Link links[CONFIG_BTDM_CTRL_BR_EDR_MAX_ACL_CONN];
portMUX_TYPE mux = portMUX_INITIALIZER_UNLOCKED;
Link* findLink(const uint8_t* address, bool create = false) {
    for (auto& link : links)
        if (link.used && memcmp(link.address, address, 6) == 0) return &link;
    if (create) for (auto& link : links) {
        if (link.used) continue;
        link = Link{};
        memcpy(link.address, address, 6);
        link.used = true;
        link.since = millis();
        return &link;
    }
    return nullptr;
}
}

// --wrap replaces every call the A2DP library makes to start AVRCP (see
// platformio.ini). Each reports success and does nothing, so the library
// carries on with A2DP alone: no AVRCP record is published and phones open no
// AVRCP channel.
extern "C" int __wrap_esp_avrc_ct_init(void) { return 0; }
extern "C" int __wrap_esp_avrc_ct_register_callback(void*) { return 0; }
extern "C" int __wrap_esp_avrc_tg_init(void) { return 0; }
extern "C" int __wrap_esp_avrc_tg_register_callback(void*) { return 0; }
extern "C" int __wrap_esp_avrc_tg_set_rn_evt_cap(const void*) { return 0; }

// --wrap intercepts the SDK's Just Works auto-confirm, as well as the ordinary
// SSP reply. Saved-key reconnects do not call it. Never accept by address alone.
extern "C" void __wrap_BTA_DmConfirm(uint8_t* address, uint8_t accept) {
    bool allow = accept && bluetoothAccess.pairingOpen();
    portENTER_CRITICAL(&mux);
    auto* link = findLink(address, true);
    allow = allow && link && !link->rejected;
    if (link) {
        link->pairing = true;
        link->pairedEver = true;
        link->authenticated = false;
        link->rejected = !allow;
    }
    portEXIT_CRITICAL(&mux);
    DLOG(BT_JUST_WORKS,
        allow ? "allow" : "deny", bluetoothAccess.pairingOpen() ? "open" : "closed");
    __real_BTA_DmConfirm(address, allow);
}

void ClassicBluetooth::setAccess(bool connectable) {
    const bool pairing = bluetoothAccess.pairingOpen();
    const bool connection = connectable && bluetoothAccess.classicConnectionsAllowed();
    // 0xFF00 preserves BLE visibility/connectability. BTA_DM_CONN_PAIRED must
    // NOT be used: 4.4.7 requires a MITM-authenticated key and rejects Just Works.
    BTA_DmSetVisibility(0xff00 | (connectable && pairing ? 2 : 0),
                        0xff00 | (connection ? 1 : 0), pairing ? 1 : 0, 0);
    DLOG(BT_SCAN_MODE,
        connection, connectable && pairing, pairing);
}
void ClassicBluetooth::connected(const uint8_t* address, bool success) {
    if (!success) return;
    const bool bonded = bluetoothAccess.ready() && bluetoothAccess.classicBonded(address);
    portENTER_CRITICAL(&mux);
    auto* link = findLink(address, true);
    if (link && !bluetoothAccess.ready()) link->rejected = true;
    if (link) link->bonded = bonded;
    portEXIT_CRITICAL(&mux);
    if (!bluetoothAccess.ready()) {
        // This also closes a link racing a reset, including one without A2DP.
        esp_bt_gap_remove_bond_device(const_cast<uint8_t*>(address));
    } else if (!link) {
        // No room to track it. Close it, but never delete a valid bond for that.
        closeLink(address);
    }
}
void ClassicBluetooth::closeLink(const uint8_t* address) {
    DLOG(BT_PEER, "ACL_CLOSE",
        address[0], address[1], address[2], address[3], address[4], address[5], 0u,
        bluetoothAccess.pairingOpen() ? "open" : "closed", "bond-kept");
    BTA_DmCloseACL(const_cast<uint8_t*>(address), 0, 1);
}
bool ClassicBluetooth::pairedOnThisLink(const uint8_t* address) {
    portENTER_CRITICAL(&mux);
    const auto* link = findLink(address);
    const bool paired = link && link->pairing;
    portEXIT_CRITICAL(&mux);
    return paired;
}
void ClassicBluetooth::audioConnected(const uint8_t* address, bool connected) {
    portENTER_CRITICAL(&mux);
    if (auto* link = findLink(address)) {
        link->audio = connected;
        if (connected) link->audioEver = true;
        link->since = millis();
    }
    portEXIT_CRITICAL(&mux);
}
int ClassicBluetooth::closeIdleLinks(uint32_t now) {
    const bool pairingOpen = bluetoothAccess.pairingOpen();
    Link idle[CONFIG_BTDM_CTRL_BR_EDR_MAX_ACL_CONN];
    int count = 0;
    portENTER_CRITICAL(&mux);
    for (auto& link : links) {
        if (!link.used || link.audio || link.closing || now - link.since < IDLE_LINK_MS) continue;
        if (link.pairing && pairingOpen) continue;
        link.closing = true;
        idle[count++] = link;
    }
    portEXIT_CRITICAL(&mux);
    for (int i = 0; i < count; ++i) closeLink(idle[i].address);
    return count;
}
namespace { bool incompleteLink = false; }
void ClassicBluetooth::disconnected(const uint8_t* address) {
    const uint32_t now = millis();
    portENTER_CRITICAL(&mux);
    if (auto* link = findLink(address)) {
        // Only a phone the toy already knew, and that did not pair on this
        // link: a new phone pairing, or one the toy has forgotten, also
        // leaves without audio and is no sign of trouble.
        if (link->bonded && !link->pairedEver && !link->audioEver && !link->closing &&
            !link->rejected && now - link->since >= INCOMPLETE_LINK_MS) incompleteLink = true;
        *link = Link{};
    }
    portEXIT_CRITICAL(&mux);
}
bool ClassicBluetooth::takeIncompleteLink() {
    portENTER_CRITICAL(&mux);
    const bool taken = incompleteLink;
    incompleteLink = false;
    portEXIT_CRITICAL(&mux);
    return taken;
}
bool ClassicBluetooth::authenticated(const uint8_t* address, bool success) {
    bool allowed = success && bluetoothAccess.classicBonded(address);
    portENTER_CRITICAL(&mux);
    if (auto* link = findLink(address)) {
        allowed = allowed && !link->rejected && (!link->pairing || bluetoothAccess.pairingOpen());
        link->authenticated = allowed;
        link->rejected = !allowed;
        // A2DP re-authenticates with the new key after the window may have
        // closed; keeping the pairing mark would then delete the fresh bond.
        if (allowed) link->pairing = false;
    }
    portEXIT_CRITICAL(&mux);
    return allowed;
}
bool ClassicBluetooth::canUseAudio(const uint8_t* address) {
    bool allowed = bluetoothAccess.classicBonded(address);
    portENTER_CRITICAL(&mux);
    const auto* link = findLink(address);
    allowed = allowed && link && !link->rejected && (!link->pairing || link->authenticated);
    portEXIT_CRITICAL(&mux);
    // A2DP is registered with BTA_SEC_AUTHENTICATE by the pinned SDK. Getting
    // here requires proof of the saved key, not simply a matching bond entry.
    return allowed;
}
bool ClassicBluetooth::hasLinks() {
    portENTER_CRITICAL(&mux);
    bool active = false;
    for (const auto& link : links) active |= link.used;
    portEXIT_CRITICAL(&mux);
    return active;
}
void ClassicBluetooth::disconnectAll() {
    Link snapshot[CONFIG_BTDM_CTRL_BR_EDR_MAX_ACL_CONN];
    portENTER_CRITICAL(&mux);
    for (auto& link : links) link.rejected = true;
    memcpy(snapshot, links, sizeof(links));
    portEXIT_CRITICAL(&mux);
    for (auto& link : snapshot)
        if (link.used) esp_bt_gap_remove_bond_device(link.address);
}

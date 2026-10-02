#include "ClassicBluetooth.h"
#include "BluetoothAccess.h"
#include <esp_gap_bt_api.h>
#include <esp_idf_version.h>
#include <sdkconfig.h>

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

namespace {
struct Link {
    uint8_t address[6] = {};
    bool used = false;
    bool pairing = false;
    bool authenticated = false;
    bool rejected = false;
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
        return &link;
    }
    return nullptr;
}
}

// --wrap intercepts the SDK's Just Works auto-confirm, as well as the ordinary
// SSP reply. Saved-key reconnects do not call it. Never accept by address alone.
extern "C" void __wrap_BTA_DmConfirm(uint8_t* address, uint8_t accept) {
    bool allow = accept && bluetoothAccess.pairingOpen();
    portENTER_CRITICAL(&mux);
    auto* link = findLink(address, true);
    allow = allow && link && !link->rejected;
    if (link) {
        link->pairing = true;
        link->authenticated = false;
        link->rejected = !allow;
    }
    portEXIT_CRITICAL(&mux);
    Serial.printf("[BT] JUST_WORKS_REQUEST decision=%s pairing=%s\n",
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
    Serial.printf("[BT] SCAN_MODE connectable=%d discoverable=%d pairable=%d\n",
        connection, connectable && pairing, pairing);
}
void ClassicBluetooth::connected(const uint8_t* address, bool success) {
    if (!success) return;
    portENTER_CRITICAL(&mux);
    auto* link = findLink(address, true);
    if (link && !bluetoothAccess.ready()) link->rejected = true;
    portEXIT_CRITICAL(&mux);
    if (!link || !bluetoothAccess.ready()) {
        // This also closes a link racing a reset, including one without A2DP.
        esp_bt_gap_remove_bond_device(const_cast<uint8_t*>(address));
    }
}
void ClassicBluetooth::disconnected(const uint8_t* address) {
    portENTER_CRITICAL(&mux);
    if (auto* link = findLink(address)) *link = Link{};
    portEXIT_CRITICAL(&mux);
}
bool ClassicBluetooth::authenticated(const uint8_t* address, bool success) {
    bool allowed = success && bluetoothAccess.classicBonded(address);
    portENTER_CRITICAL(&mux);
    if (auto* link = findLink(address)) {
        allowed = allowed && !link->rejected && (!link->pairing || bluetoothAccess.pairingOpen());
        link->authenticated = allowed;
        link->rejected = !allowed;
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

#include "BluetoothAccess.h"
#include "BleIdentity.h"
#include "PairingPolicy.h"
#include <Preferences.h>
#include <esp_gap_ble_api.h>
#include <esp_gap_bt_api.h>
#include <mbedtls/aes.h>
#include <memory>
#include <new>

BluetoothAccess bluetoothAccess;

namespace {
// Read only during the one-time upgrade. Never written by this firmware.
struct LegacyApprovals {
    uint8_t count = 0;
    uint8_t addresses[8][6] = {};
    void load(Preferences& prefs, const char* key) {
        if (prefs.getBytesLength(key) != sizeof(*this) ||
            prefs.getBytes(key, this, sizeof(*this)) != sizeof(*this) || count > 8)
            count = 0;
    }
    bool contains(const uint8_t* address) const {
        for (uint8_t i = 0; i < count; ++i)
            if (memcmp(addresses[i], address, 6) == 0) return true;
        return false;
    }
};

// BLE bond records include key material. Wipe temporary copies on every exit.
struct BleBonds {
    int count = esp_ble_get_bond_device_num();
    const int capacity = count;
    std::unique_ptr<esp_ble_bond_dev_t[]> data;
    bool load() {
        if (count < 0 || count > 32) return false;
        if (!count) return true;
        data.reset(new (std::nothrow) esp_ble_bond_dev_t[count]{});
        return data && esp_ble_get_bond_device_list(&count, data.get()) == ESP_OK;
    }
    ~BleBonds() {
        if (!data) return;
        volatile uint8_t* bytes = reinterpret_cast<uint8_t*>(data.get());
        for (size_t i = 0; i < sizeof(esp_ble_bond_dev_t) * capacity; ++i) bytes[i] = 0;
    }
};
bool encryptIdentityBlock(const uint8_t* key, const uint8_t* input, uint8_t* output) {
    mbedtls_aes_context context;
    mbedtls_aes_init(&context);
    bool ok = mbedtls_aes_setkey_enc(&context, key, 128) == 0 &&
        mbedtls_aes_crypt_ecb(&context, MBEDTLS_AES_ENCRYPT, input, output) == 0;
    mbedtls_aes_free(&context);
    return ok;
}
}

void BluetoothAccess::begin() {
    Preferences prefs;
    if (!prefs.begin("sy-access", false)) {
        Serial.println("[Access] Initialization failed: NVS unavailable; Bluetooth access disabled");
        return;
    }
    _storageOk = true;
    _maintenance = prefs.getBool("clearPending", false) ? Maintenance::Reset
        : prefs.getBool("bondsOnly", false) ? Maintenance::None : Maintenance::Migrate;
    _lastPoll = millis() - 500;
}

void BluetoothAccess::openPairing(uint32_t now) {
    _openedAt.store(now);
    _pairing.store(ready());
}
void BluetoothAccess::closePairing() { _pairing.store(false); }
bool BluetoothAccess::pairingOpen() const {
    return ready() && _pairing.load() && millis() - _openedAt.load() < PairingPolicy::WINDOW_MS;
}
bool BluetoothAccess::classicBonded(const uint8_t* address) const {
    if (!ready()) return false;
    int count = esp_bt_gap_get_bond_device_num();
    if (count <= 0 || count > 32) return false;
    std::unique_ptr<esp_bd_addr_t[]> bonds(new (std::nothrow) esp_bd_addr_t[count]);
    if (!bonds || esp_bt_gap_get_bond_device_list(&count, bonds.get()) != ESP_OK) return false;
    for (int i = 0; i < count; ++i)
        if (memcmp(bonds[i], address, 6) == 0) return true;
    return false;
}
bool BluetoothAccess::classicConnectionsAllowed() {
    return ready() && (pairingOpen() || esp_bt_gap_get_bond_device_num() > 0);
}

bool BluetoothAccess::bleIdentity(const uint8_t* address, uint8_t* identity) {
    BleBonds bonds;
    if (!bonds.load()) return false;
    bool found = false;
    for (int i = 0; i < bonds.count && !found; ++i) {
        const auto& bond = bonds.data[i];
        const bool hasIdentity = (bond.bond_key.key_mask & ESP_BLE_ID_KEY_MASK) != 0;
        const auto& pid = bond.bond_key.pid_key;
        if (memcmp(address, bond.bd_addr, 6) == 0 ||
            (hasIdentity && (memcmp(address, pid.static_addr, 6) == 0 ||
                            bleResolvableAddressMatches(address, pid.irk, encryptIdentityBlock)))) {
            memcpy(identity, hasIdentity ? pid.static_addr : bond.bd_addr, 6);
            found = true;
        }
    }
    return found;
}
bool BluetoothAccess::bleBonded(const uint8_t* address) const {
    uint8_t identity[6];
    return ready() && bleIdentity(address, identity);
}
bool BluetoothAccess::forgetBonds() {
    closePairing();
    _ready = false;
    _maintenance = Maintenance::Reset;
    _lastPoll = millis() - 500;
    Preferences prefs;
    _storageOk = prefs.begin("sy-access", false) && prefs.putBool("clearPending", true) == 1;
    return _storageOk;
}
bool BluetoothAccess::poll(bool linksActive) {
    if (ready() || millis() - _lastPoll < 500) return false;
    if (!_storageOk && _maintenance != Maintenance::Reset) return false;
    _lastPoll = millis();
    Preferences prefs;
    if (!prefs.begin("sy-access", false)) return false;
    LegacyApprovals classic, ble;
    if (_maintenance == Maintenance::Migrate) {
        classic.load(prefs, "classic");
        ble.load(prefs, "ble");
    }
    bool pending = linksActive;
    int count = esp_bt_gap_get_bond_device_num();
    if (count < 0 || count > 32) return false;
    if (count > 0) {
        std::unique_ptr<esp_bd_addr_t[]> addresses(new (std::nothrow) esp_bd_addr_t[count]);
        if (!addresses || esp_bt_gap_get_bond_device_list(&count, addresses.get()) != ESP_OK) return false;
        for (int i = 0; i < count; ++i) {
            if (_maintenance == Maintenance::None ||
                (_maintenance == Maintenance::Migrate && classic.contains(addresses[i]))) continue;
            pending = true;
            esp_bt_gap_remove_bond_device(addresses[i]);
        }
    }
    BleBonds bonds;
    if (!bonds.load()) return false;
    for (int i = 0; i < bonds.count; ++i) {
        const auto& bond = bonds.data[i];
        const uint8_t* identity = (bond.bond_key.key_mask & ESP_BLE_ID_KEY_MASK)
            ? bond.bond_key.pid_key.static_addr : bond.bd_addr;
        if (_maintenance == Maintenance::None ||
            (_maintenance == Maintenance::Migrate && ble.contains(identity))) continue;
        pending = true;
        esp_ble_remove_bond_device(bonds.data[i].bd_addr);
    }
    if (pending || !_storageOk) return false;
    // Deletion is asynchronous. Only commit after a later snapshot proves it
    // finished and no old live link can recreate a bond after the commit.
    if (prefs.putBool("bondsOnly", true) != 1 || prefs.putBool("clearPending", false) != 1) return false;
    if (prefs.isKey("classic") && !prefs.remove("classic")) return false;
    if (prefs.isKey("ble") && !prefs.remove("ble")) return false;
    const bool reset = _maintenance == Maintenance::Reset;
    _maintenance = Maintenance::None;
    _ready = true;
    Serial.printf("[Access] Bonds ready classic=%d ble=%d pairing=closed\n",
        esp_bt_gap_get_bond_device_num(), esp_ble_get_bond_device_num());
    if (reset) Serial.println("[Pairing] All bonds cleared");
    return true;
}

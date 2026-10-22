#include <cassert>
#include <atomic>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <map>
#include <memory>
#include <set>
#include <string>
#include <vector>
#include "recording_serial.h"
uint32_t nowMs = 0;
uint32_t millis() { return nowMs; }
using esp_bd_addr_t = uint8_t[6];
constexpr int ESP_OK = 0, ESP_BLE_ID_KEY_MASK = 2;
struct esp_ble_bond_dev_t {
    uint8_t bd_addr[6] = {};
    struct {
        int key_mask = 0;
        struct { uint8_t static_addr[6] = {}, irk[16] = {}; } pid_key;
    } bond_key;
};
struct mbedtls_aes_context {};
void mbedtls_aes_init(mbedtls_aes_context*) {}
void mbedtls_aes_free(mbedtls_aes_context*) {}
int mbedtls_aes_setkey_enc(mbedtls_aes_context*, const uint8_t*, int) { return -1; }
int mbedtls_aes_crypt_ecb(mbedtls_aes_context*, int, const uint8_t*, uint8_t*) { return -1; }
constexpr int MBEDTLS_AES_ENCRYPT = 1; // AES boundary; identity matching is tested separately.

std::set<uint8_t> classic;
std::map<uint8_t, esp_ble_bond_dev_t> ble;
std::set<uint8_t> classicRemovals, bleRemovals;
bool failReads = false, failRemovals = false;
void address(uint8_t* out, uint8_t id) { memset(out, 0, 6); out[5] = id; }
int esp_bt_gap_get_bond_device_num() { return classic.size(); }
int esp_ble_get_bond_device_num() { return ble.size(); }
int esp_bt_gap_get_bond_device_list(int* count, esp_bd_addr_t* out) {
    if (failReads) return -1;
    int n = 0;
    for (auto id : classic) { if (n == *count) break; address(out[n++], id); }
    *count = n; return ESP_OK;
}
int esp_ble_get_bond_device_list(int* count, esp_ble_bond_dev_t* out) {
    if (failReads) return -1;
    int n = 0;
    for (const auto& item : ble) { if (n == *count) break; out[n++] = item.second; }
    *count = n; return ESP_OK;
}
int esp_bt_gap_remove_bond_device(uint8_t* peer) {
    if (failRemovals) return -1;
    classicRemovals.insert(peer[5]); return ESP_OK;
}
int esp_ble_remove_bond_device(uint8_t* peer) {
    if (failRemovals) return -1;
    bleRemovals.insert(peer[5]); return ESP_OK;
}
void finishRemovals() {
    for (auto id : classicRemovals) classic.erase(id);
    for (auto id : bleRemovals) ble.erase(id);
    classicRemovals.clear(); bleRemovals.clear();
}
void addBle(uint8_t id, uint8_t identity = 0) {
    auto& bond = ble[id];
    address(bond.bd_addr, id);
    if (identity) {
        bond.bond_key.key_mask = ESP_BLE_ID_KEY_MASK;
        address(bond.bond_key.pid_key.static_addr, identity);
    }
}
class Preferences {
public:
    static inline std::map<std::string, std::vector<uint8_t>> saved;
    static inline bool failWrites = false, failBegin = false;
    static inline int writes = 0;
    bool begin(const char*, bool) { return !failBegin; }
    bool isKey(const char* key) { return saved.count(key); }
    bool getBool(const char* key, bool fallback) { return isKey(key) ? saved[key][0] != 0 : fallback; }
    size_t putBool(const char* key, bool value) {
        if (failWrites) return 0;
        saved[key] = {uint8_t(value)}; ++writes; return 1;
    }
    size_t getBytesLength(const char* key) { return isKey(key) ? saved[key].size() : 0; }
    size_t getBytes(const char* key, void* value, size_t size) {
        if (getBytesLength(key) != size) return 0;
        memcpy(value, saved[key].data(), size); return size;
    }
    bool remove(const char* key) {
        if (failWrites) return false;
        return saved.erase(key);
    }
};
#include "approvals_under_test.inc"

bool poll(BluetoothAccess& access, bool links = false) { nowMs += 500; return access.poll(links); }
int main() {
    uint8_t phone[6] = {};
    // Startup keeps every stack bond, including BLE identity addresses, and
    // writes nothing.
    classic = {1}; addBle(2, 5);
    BluetoothAccess access;
    access.begin();
    assert(!access.ready() && !access.pairingOpen());
    assert(poll(access) && access.ready());
    assert(classicRemovals.empty() && bleRemovals.empty());
    assert(Preferences::writes == 0);
    address(phone, 1);
    assert(access.classicBonded(phone) && !access.bleBonded(phone));
    address(phone, 5);
    assert(access.bleBonded(phone) && !access.classicBonded(phone));
    assert(!access.pairingOpen() && access.classicConnectionsAllowed());

    // Enrollment changes the stack store alone, with no application approval
    // write. A reboot uses that same store.
    int writes = Preferences::writes;
    classic.insert(3); addBle(4);
    address(phone, 3); assert(access.classicBonded(phone));
    address(phone, 4); assert(access.bleBonded(phone));
    assert(Preferences::writes == writes);
    BluetoothAccess reboot;
    reboot.begin();
    assert(poll(reboot));
    assert(reboot.bleBonded(phone) && !reboot.pairingOpen());
    reboot.openPairing(nowMs);
    nowMs += 59999; assert(reboot.pairingOpen());
    ++nowMs; assert(!reboot.pairingOpen());
    failReads = true;
    assert(!reboot.bleBonded(phone));
    address(phone, 1); assert(!reboot.classicBonded(phone));
    failReads = false;

    // Reset is durable before asynchronous deletion begins. Failure and live
    // links cannot reopen access, even when the key list momentarily looks empty.
    assert(reboot.forgetBonds());
    assert(!reboot.ready() && !reboot.classicBonded(phone));
    reboot.openPairing(nowMs); assert(!reboot.pairingOpen());
    failRemovals = true; assert(!poll(reboot));
    assert(!classic.empty() && !ble.empty());
    failRemovals = false;
    assert(!poll(reboot, true));
    finishRemovals();
    assert(!poll(reboot, true));
    assert(Preferences::saved["clearPending"][0] == 1);
    // A reboot mid-reset must also finish deletion before accepting any bond.
    classic.insert(8); addBle(8);
    BluetoothAccess midReset;
    midReset.begin();
    assert(!poll(midReset));
    finishRemovals();
    Preferences::failWrites = true;
    assert(!poll(midReset) && !midReset.ready());
    Preferences::failWrites = false;
    assert(poll(midReset) && midReset.ready());
    assert(classic.empty() && ble.empty());
    assert(Preferences::saved["clearPending"][0] == 0);
    assert(Serial.output.find("[Pairing] All bonds cleared") != std::string::npos);

    // A failed reset-marker write still deletes keys but never reports ready.
    BluetoothAccess failedReset;
    failedReset.begin();
    assert(poll(failedReset));
    classic.insert(1);
    Preferences::failWrites = true;
    assert(!failedReset.forgetBonds());
    assert(!poll(failedReset));
    finishRemovals();
    Preferences::failWrites = false;
    assert(!poll(failedReset) && !failedReset.ready());

    // Failure to open the access store must not delete a valid user's bonds.
    classic.insert(1);
    Preferences::failBegin = true;
    BluetoothAccess unavailable;
    unavailable.begin();
    Preferences::failBegin = false;
    assert(!poll(unavailable) && classicRemovals.empty() && classic.count(1));
    std::cout << "Bluetooth bond startup and reset tests passed\n";
}

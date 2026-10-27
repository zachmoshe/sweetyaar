#include <cassert>
#include <array>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <map>
#include <new>
#include <set>
#include <string>
#include <vector>
#include "ChargerStatus.h"
#include "GattLayout.h"
#include "recording_serial.h"

using String = std::string;
using esp_err_t = int;
using esp_gatt_if_t = int;
using esp_gatt_status_t = int;
using esp_gatts_cb_event_t = int;
using esp_gap_ble_cb_event_t = int;
using esp_ble_sm_param_t = int;
using esp_gatt_perm_t = int;
using portMUX_TYPE = int;
#define portMUX_INITIALIZER_UNLOCKED 0
#define portENTER_CRITICAL(mux) ((void)(mux))
#define portEXIT_CRITICAL(mux) ((void)(mux))
enum { ESP_OK, ESP_BT_STATUS_SUCCESS = 0, ESP_GATT_OK = 0, ESP_GATT_IF_NONE = -1,
    ESP_GATTS_CONF_EVT = 1, ESP_GATTS_READ_EVT, ESP_GATTS_WRITE_EVT,
    ESP_GATTS_EXEC_WRITE_EVT, ESP_GATT_INSUF_AUTHORIZATION,
    ESP_GATT_INSUF_AUTHENTICATION, ESP_GATT_PREP_WRITE_EXEC,
    ESP_GATT_INVALID_OFFSET, ESP_GATT_REQ_NOT_SUPPORTED, ESP_GATT_INVALID_ATTR_LEN, ESP_GATT_WRITE_NOT_PERMIT,
    ESP_GAP_BLE_SEC_REQ_EVT, ESP_GAP_BLE_KEY_EVT, ESP_GAP_BLE_AUTH_CMPL_EVT,
    ESP_GAP_BLE_ADV_START_COMPLETE_EVT, ESP_GAP_BLE_ADV_STOP_COMPLETE_EVT, ESP_GAP_BLE_PASSKEY_NOTIF_EVT,
    ESP_GATTS_REG_EVT, ESP_BLE_SEC_ENCRYPT_NO_MITM, ESP_GATTS_MTU_EVT,
    ESP_GATT_NO_RESOURCES, MALLOC_CAP_8BIT, ESP_GATTS_SEND_SERVICE_CHANGE_EVT };
enum { ESP_LE_AUTH_BOND = 1, ESP_LE_AUTH_REQ_SC_BOND = 9, ESP_IO_CAP_NONE = 3,
    ESP_BLE_ONLY_ACCEPT_SPECIFIED_AUTH_ENABLE = 1,
    ESP_BLE_ENC_KEY_MASK = 1, ESP_BLE_ID_KEY_MASK = 2,
    ESP_GATT_PERM_READ = 1, ESP_GATT_PERM_READ_ENCRYPTED = 2,
    ESP_GATT_PERM_WRITE_ENCRYPTED = 32 };
enum { ESP_BLE_SM_AUTHEN_REQ_MODE, ESP_BLE_SM_ONLY_ACCEPT_SPECIFIED_SEC_AUTH,
    ESP_BLE_SM_IOCAP_MODE, ESP_BLE_SM_MAX_KEY_SIZE, ESP_BLE_SM_MIN_KEY_SIZE,
    ESP_BLE_SM_SET_INIT_KEY, ESP_BLE_SM_SET_RSP_KEY };
struct esp_ble_gatts_cb_param_t {
    struct { int status = ESP_OK; } reg;
    struct { uint16_t conn_id = 0, handle = 0; int status = ESP_OK; } conf;
    struct { uint16_t conn_id = 0, trans_id = 0, handle = 0, offset = 0; bool need_rsp = true; } read;
    struct { uint16_t conn_id = 0, trans_id = 0, handle = 0, len = 0, offset = 0;
        bool need_rsp = true, is_prep = false; uint8_t* value = nullptr; uint8_t bda[6] = {}; } write;
    struct { uint16_t conn_id = 0, trans_id = 0; int exec_write_flag = 0; uint8_t bda[6] = {}; } exec_write;
    struct { uint16_t conn_id = 0; uint8_t remote_bda[6] = {}; } connect;
    struct { uint16_t conn_id = 0, reason = 0; } disconnect;
    struct { uint16_t conn_id = 0, mtu = 23; } mtu;
    struct { int status = ESP_OK; } service_change;
};
struct esp_ble_gap_cb_param_t {
    struct {
        struct { uint8_t bd_addr[6] = {}; int key_type = 0; } ble_req, ble_key;
        struct { uint8_t bd_addr[6] = {}; bool success = true;
            int auth_mode = ESP_LE_AUTH_BOND, fail_reason = 0; } auth_cmpl;
    } ble_security;
    struct { int status = 0; } adv_start_cmpl, adv_stop_cmpl;
};
struct esp_gatt_rsp_t {
    struct { uint16_t handle = 0, offset = 0, len = 0; uint8_t value[600] = {}; } attr_value;
};
using esp_gap_ble_cb_t = void(*)(int, esp_ble_gap_cb_param_t*);
using esp_gatts_cb_t = void(*)(int, int, esp_ble_gatts_cb_param_t*);
int callbackRegistrations = 0;
esp_gap_ble_cb_t esp_ble_gap_get_callback() { return [](int, esp_ble_gap_cb_param_t*) {}; }
esp_gatts_cb_t esp_ble_gatts_get_callback() { return [](int, int, esp_ble_gatts_cb_param_t*) {}; }
int esp_ble_gap_register_callback(esp_gap_ble_cb_t) { ++callbackRegistrations; return ESP_OK; }
int esp_ble_gatts_register_callback(esp_gatts_cb_t) { ++callbackRegistrations; return ESP_OK; }
int securityFailureAt = -1;
std::map<esp_ble_sm_param_t, uint8_t> securityParameters;
int esp_ble_gap_set_security_param(esp_ble_sm_param_t param, void* value, uint8_t length) {
    assert(length == 1);
    const bool fail = int(securityParameters.size()) == securityFailureAt;
    securityParameters[param] = *static_cast<uint8_t*>(value);
    return fail ? -1 : ESP_OK;
}
uint32_t fakeMillis = 0;
size_t fakeLargestBlock = 100000;
size_t heap_caps_get_largest_free_block(int) { return fakeLargestBlock; }
size_t heap_caps_get_free_size(int) { return fakeLargestBlock + 1000; }
uint32_t millis() { return fakeMillis; }
struct BLE2902 {
    uint16_t handle = 0;
    uint16_t getHandle() { return handle; }
    void setAccessPermissions(int) {}
};
struct BLECharacteristicCallbacks;
struct BLECharacteristic {
    enum { PROPERTY_READ = 1, PROPERTY_WRITE = 2, PROPERTY_NOTIFY = 4, PROPERTY_INDICATE = 8,
        PROPERTY_WRITE_NR = 32 };
    uint16_t handle = 0;
    BLE2902 cccd;
    std::string value;
    std::string uuid;
    uint16_t getHandle() { return handle; }
    struct BLEUUID getUUID();
    BLE2902* getDescriptorByUUID(const char*) { return &cccd; }
    std::string getValue() { ++valueCopies; return value; }
    uint8_t* getData() { return reinterpret_cast<uint8_t*>(value.data()); }
    size_t getLength() { return value.size(); }
    static inline int valueCopies = 0;
    static inline bool throwOnSet = false;
    void setValue(const char* next) { value = next; }
    void setValue(uint8_t* next, size_t length) {
        if (throwOnSet) throw std::bad_alloc();
        value.assign(reinterpret_cast<char*>(next), length);
    }
    void addDescriptor(BLE2902* descriptor) { delete descriptor; }
    void setCallbacks(BLECharacteristicCallbacks*);
    void setAccessPermissions(int) {}
};
struct BLECharacteristicCallbacks {
    virtual ~BLECharacteristicCallbacks() = default;
    virtual void onWrite(BLECharacteristic*) {}
};
void BLECharacteristic::setCallbacks(BLECharacteristicCallbacks* callbacks) { delete callbacks; }
struct BLEUUID {
    std::string text;
    explicit BLEUUID(const char* value) : text(value) {}
    std::string toString() { return text; }
};
BLEUUID BLECharacteristic::getUUID() { return BLEUUID(uuid.c_str()); }
struct BLEService {
    std::array<BLECharacteristic, 21> characteristics;
    size_t count = 0;
    bool started = false;
    uint16_t getHandle() { return 40; }
    BLECharacteristic* createCharacteristic(const char* uuid, int) {
        auto& characteristic = characteristics.at(count++);
        characteristic.uuid = uuid;
        characteristic.handle = uint16_t(41 + 3 * count);
        return &characteristic;
    }
    void start() { started = true; }
};
struct BLEServerCallbacks;
struct BLEServer {
    std::vector<uint16_t> closed;
    BLEService service;
    void disconnect(uint16_t id) { closed.push_back(id); }
    void setCallbacks(BLEServerCallbacks*);
    BLEService* createService(BLEUUID, int) { return &service; }
};
struct BLEServerCallbacks {
    virtual ~BLEServerCallbacks() = default;
    virtual void onConnect(BLEServer*, esp_ble_gatts_cb_param_t*) {}
    virtual void onDisconnect(BLEServer*, esp_ble_gatts_cb_param_t*) {}
};
void BLEServer::setCallbacks(BLEServerCallbacks* callbacks) { delete callbacks; }
struct BLEAdvertising {
    void addServiceUUID(const char*) {}
    void setScanResponse(bool) {}
    void setMinPreferred(int) {}
    void setMaxPreferred(int) {}
    void setMinInterval(int) {}
    void setMaxInterval(int) {}
};
struct BLEDevice {
    static inline int starts = 0;
    static inline int servers = 0;
    static inline esp_gatts_cb_t customGatt = nullptr;
    static void init(const char*) {}
    static void setCustomGattsHandler(esp_gatts_cb_t callback) { customGatt = callback; }
    static int setMTU(int) { return ESP_OK; }
    static BLEServer* createServer() {
        ++servers;
        static BLEServer server;
        esp_ble_gatts_cb_param_t registration;
        customGatt(ESP_GATTS_REG_EVT, 7, &registration);
        return &server;
    }
    static BLEAdvertising* getAdvertising() { static BLEAdvertising advertising; return &advertising; }
    static void startAdvertising() { ++starts; }
    static void stopAdvertising() {}
};
int lastResponse = ESP_OK, encryptedRequests = 0;
int lastAccess = -1;
bool securityAccepted = false;
std::set<uint8_t> removedBonds;
void esp_ble_gap_set_device_name(const char*) {}
int esp_ble_set_encryption(uint8_t*, int) { ++encryptedRequests; return ESP_OK; }
int esp_ble_gap_security_rsp(uint8_t*, bool allow) { securityAccepted = allow; return ESP_OK; }
void esp_ble_remove_bond_device(uint8_t* address) { removedBonds.insert(address[5]); }
void esp_ble_gatts_send_response(int, uint16_t, uint16_t, int status, esp_gatt_rsp_t* reply) {
    lastResponse = status;
    lastAccess = reply && reply->attr_value.len == 1 ? reply->attr_value.value[0] : -1;
}
struct Packet { uint16_t connection, handle; std::string data; bool indication; };
std::vector<Packet> packets;
int esp_ble_gatts_send_indicate(int, uint16_t connection, uint16_t handle, size_t length,
                               uint8_t* data, bool indication) {
    packets.push_back({connection, handle, std::string(reinterpret_cast<char*>(data), length), indication});
    return ESP_OK;
}
int serviceChangeMode = -1;
extern "C" uint8_t BTA_GATTS_SetServiceChangeMode(uint8_t mode) { serviceChangeMode = mode; return 0; }
std::vector<uint8_t> serviceChanges; // last address byte of each indication request
int esp_ble_gatts_send_service_change_indication(int, uint8_t* address) {
    serviceChanges.push_back(address[5]);
    return ESP_OK;
}
std::map<std::string, uint32_t> storedLayouts;
struct Preferences {
    bool begin(const char* name, bool) { assert(std::string(name) == GATT_LAYOUT_NAMESPACE); return true; }
    void end() {}
    bool isKey(const char* key) { return storedLayouts.count(key); }
    uint32_t getULong(const char* key, uint32_t fallback) {
        auto found = storedLayouts.find(key);
        return found == storedLayouts.end() ? fallback : found->second;
    }
    size_t putULong(const char* key, uint32_t value) { storedLayouts[key] = value; return sizeof(value); }
};
struct BluetoothAccess {
    bool open = false;
    bool available = true;
    static inline std::set<uint8_t> bonds;
    bool ready() { return available; }
    bool pairingOpen() { return available && open; }
    bool bleBonded(const uint8_t* address) { return available && bonds.count(address[5]); }
    static bool bleIdentity(const uint8_t* address, uint8_t* identity) {
        memcpy(identity, address, 6); return bonds.count(address[5]);
    }
} bluetoothAccess;

#include "ble_service_under_test.inc"

int dispatches = 0;
std::string committed;
void dispatch(int event, int, esp_ble_gatts_cb_param_t* p) {
    ++dispatches;
    if (event == ESP_GATTS_WRITE_EVT)
        committed.assign(reinterpret_cast<char*>(p->write.value), p->write.len);
}

int main() {
    // A rejected security setting must leave the remote unavailable, including
    // after normal loop polling and a later device-name update.
    for (int failure = 0; failure < 7; ++failure) {
        securityParameters.clear();
        securityFailureAt = failure;
        BLEParentService failed;
        assert(!failed.begin("SweetYaar"));
        assert(securityParameters.size() == size_t(failure + 1));
        assert(!failed._server && !failed.isConnected() && !failed.hasLinks());
        failed.pollAdvertising();
        failed.updateDeviceName("SweetYaar");
        assert(BLEDevice::servers == 0 && BLEDevice::starts == 0);
        assert(callbackRegistrations == 0);
        assert(Serial.output.find("parent service disabled") != std::string::npos);
    }
    securityFailureAt = -1;
    securityParameters.clear();
    BLEParentService initialized;
    assert(initialized.begin("SweetYaar"));
    assert(securityParameters.at(ESP_BLE_SM_AUTHEN_REQ_MODE) == ESP_LE_AUTH_REQ_SC_BOND);
    assert(securityParameters.at(ESP_BLE_SM_ONLY_ACCEPT_SPECIFIED_SEC_AUTH) == ESP_BLE_ONLY_ACCEPT_SPECIFIED_AUTH_ENABLE);
    assert(securityParameters.at(ESP_BLE_SM_IOCAP_MODE) == ESP_IO_CAP_NONE);
    assert(securityParameters.at(ESP_BLE_SM_MIN_KEY_SIZE) == 16);
    assert(securityParameters.at(ESP_BLE_SM_MAX_KEY_SIZE) == 16);
    assert(securityParameters.at(ESP_BLE_SM_SET_INIT_KEY) == (ESP_BLE_ENC_KEY_MASK | ESP_BLE_ID_KEY_MASK));
    assert(securityParameters.at(ESP_BLE_SM_SET_RSP_KEY) == (ESP_BLE_ENC_KEY_MASK | ESP_BLE_ID_KEY_MASK));
    assert(initialized._server->service.started && BLEDevice::servers == 1 && BLEDevice::starts == 1);
    assert(callbackRegistrations == 2 && !initialized.isConnected());
    // Bonded clients learn about a changed table only through manual mode.
    assert(serviceChangeMode == 1 && initialized._gattLayout != 0);
    const uint32_t bootLayout = initialized._gattLayout;
    initialized.computeGattLayout(&initialized._server->service);
    assert(initialized._gattLayout == bootLayout);
    initialized._configCommandChar->handle += 2; // the table moved
    initialized.computeGattLayout(&initialized._server->service);
    assert(initialized._gattLayout != bootLayout);
    Serial.output.clear();

    BLEParentService ble;
    BLEServer server;
    BLECharacteristic chars[16];
    ble._server = &server;
    ble._originalGatt = dispatch;
    ble._originalGap = [](int, esp_ble_gap_cb_param_t*) {};
    for (int i = 0; i < 16; ++i) {
        chars[i].handle = 10 + i * 2;
        chars[i].cccd.handle = chars[i].handle + 1;
        ble._securedChars[i] = &chars[i];
    }
    ble._noticeChar = &chars[13];
    BLECharacteristic access;
    access.handle = 80;
    ble._accessChar = &access;
    auto readAccess = [&](uint16_t id) {
        esp_ble_gatts_cb_param_t p{};
        p.read.conn_id = id; p.read.handle = access.handle;
        assert(!ble.filterGatt(ESP_GATTS_READ_EVT, configGattsIf, &p));
        assert(lastResponse == ESP_GATT_OK);
        return lastAccess;
    };
    auto connect = [&](uint16_t id) {
        esp_ble_gatts_cb_param_t p{}; p.connect.conn_id = id; p.connect.remote_bda[5] = id;
        ble.connected(&p);
    };
    auto auth = [&](uint8_t id, bool success = true) {
        esp_ble_gap_cb_param_t p{}; p.ble_security.auth_cmpl.bd_addr[5] = id;
        p.ble_security.auth_cmpl.success = success;
        if (!success) p.ble_security.auth_cmpl.fail_reason = 5;
        // The stack saves successful new bonds before AUTH_CMPL reaches us.
        if (success && bluetoothAccess.pairingOpen()) bluetoothAccess.bonds.insert(id);
        ble.handleGap(ESP_GAP_BLE_AUTH_CMPL_EVT, &p);
    };
    auto canWrite = [&](uint16_t id) {
        esp_ble_gatts_cb_param_t p{}; p.write.conn_id = id;
        p.write.handle = chars[0].handle;
        return ble.filterGatt(ESP_GATTS_WRITE_EVT, configGattsIf, &p);
    };
    // Closed at boot; an unknown phone cannot acquire control.
    connect(1);
    assert(!ble.isConnected() && server.closed.empty());
    assert(readAccess(1) == 0); // rejection is readable without exposing controls
    assert(Serial.output.find("CONNECT conn=1 peer=00:00:00:00:00:01 bonded=0 pairing=closed decision=pairing-required") != std::string::npos);
    const auto diagnosticSize = Serial.output.size();
    readAccess(1);
    assert(Serial.output.size() == diagnosticSize); // access polling does not flood serial
    assert(encryptedRequests == 0 && !canWrite(1));
    esp_ble_gatts_cb_param_t blockedRead{};
    blockedRead.read.conn_id = 1; blockedRead.read.handle = chars[0].handle;
    assert(!ble.filterGatt(ESP_GATTS_READ_EVT, configGattsIf, &blockedRead));
    assert(lastResponse == ESP_GATT_INSUF_AUTHORIZATION);
    fakeMillis = 9999; ble.pollAdvertising();
    assert(server.closed.empty());
    fakeMillis = 10000; ble.pollAdvertising();
    assert(server.closed.back() == 1); // bounded grace for clients that do not leave
    ble.disconnected(1);
    fakeMillis = 0;
    bluetoothAccess.open = true;
    connect(1);
    // The encrypted client read starts bonding. A peripheral security request
    // in parallel can produce a second Android pairing dialog.
    assert(encryptedRequests == 0);
    assert(readAccess(1) == 1);
    assert(!canWrite(1)); // transport connected is NOT authenticated
    // Android's encrypted status read can reach the app after encryption but
    // before AUTH_CMPL/key distribution. Block it without requesting another
    // round of pairing (Android retries authentication on 0x05, not 0x08).
    blockedRead.read.handle = chars[3].handle;
    assert(!ble.filterGatt(ESP_GATTS_READ_EVT, configGattsIf, &blockedRead));
    assert(lastResponse == ESP_GATT_INSUF_AUTHORIZATION);
    assert(!ble.isConnected() && readAccess(1) == 1);
    auth(1);
    assert(readAccess(1) == 2);
    assert(ble.filterGatt(ESP_GATTS_READ_EVT, configGattsIf, &blockedRead));
    assert(ble.isConnected() && canWrite(1));
    ble.peer(1)->subscriptions = 1UL << 13;
    // An unbonded/failing candidate never displaces the working controller.
    connect(2); auth(2, false);
    assert(readAccess(2) == 3 && readAccess(1) == 2); // per-peer, never a shared cached value
    assert(Serial.output.find("fail_reason=0x05") != std::string::npos);
    assert(Serial.output.find("decision=stack-authentication-failed") != std::string::npos);
    assert(ble._ownerId == 1 && canWrite(1));
    ble.disconnected(2);
    // A new authenticated controller discards queued commands from the old one.
    ble._newCommand = true;
    connect(2); auth(2);
    assert(readAccess(1) == 4 && readAccess(2) == 2);
    assert(Serial.output.find("CONTROL authenticated_conn=2 owner=2 previous=1") != std::string::npos);
    assert(ble._ownerId == 2 && !ble._newCommand && !canWrite(1) && canWrite(2));
    ble.pollAdvertising();
    assert(packets.size() == 1 && packets[0].connection == 1);
    assert(packets[0].data == "{\"type\":\"takeover\"}" && packets[0].data.size() <= 20 && packets[0].indication);
    // Notifications target the new owner, never every connected phone.
    ble.peer(2)->subscriptions = 1;
    chars[0].value = "volume";
    ble.notifyOwner(&chars[0]);
    assert(packets.back().connection == 2 && packets.back().data == "volume");
    esp_ble_gatts_cb_param_t confirmation{};
    confirmation.conf.conn_id = 1; confirmation.conf.handle = chars[13].handle;
    ble.filterGatt(ESP_GATTS_CONF_EVT, configGattsIf, &confirmation);
    fakeMillis = 250;
    ble.pollAdvertising();
    assert(server.closed.back() == 1);
    ble.disconnected(1);
    assert(ble.isConnected() && ble._ownerId == 2); // old disconnect must not clear the new owner
    // Closing the window keeps the controller and permits bonded takeovers.
    bluetoothAccess.open = false;
    connect(1); auth(1);
    assert(encryptedRequests == 0); // saved-key reconnect also waits for the client
    assert(ble._ownerId == 1);
    connect(3); auth(3);
    assert(ble._ownerId == 1 && !canWrite(3));
    ble.disconnected(3);
    ble.disconnected(2);
    // A candidate that began enrollment before timeout but finished after it is rejected.
    bluetoothAccess.open = true; connect(3); bluetoothAccess.open = false; auth(3);
    assert(ble._ownerId == 1 && !bluetoothAccess.bonds.count(3));
    ble.disconnected(3);
    // Prepared writes cannot cross a takeover boundary.
    uint8_t payload[] = "old settings";
    esp_ble_gatts_cb_param_t prepared{};
    prepared.write.conn_id = 1; prepared.write.handle = chars[6].handle;
    prepared.write.value = payload; prepared.write.len = sizeof(payload) - 1; prepared.write.is_prep = true;
    assert(!ble.filterGatt(ESP_GATTS_WRITE_EVT, configGattsIf, &prepared));
    assert(lastResponse == ESP_GATT_OK);
    connect(2); auth(2);
    esp_ble_gatts_cb_param_t execute{};
    execute.exec_write.conn_id = 2; execute.exec_write.exec_write_flag = ESP_GATT_PREP_WRITE_EXEC;
    ble.filterGatt(ESP_GATTS_EXEC_WRITE_EVT, configGattsIf, &execute);
    assert(lastResponse == ESP_GATT_INVALID_OFFSET && committed.empty());
    prepared.write.conn_id = 2;
    ble.filterGatt(ESP_GATTS_WRITE_EVT, configGattsIf, &prepared);
    ble.filterGatt(ESP_GATTS_EXEC_WRITE_EVT, configGattsIf, &execute);
    assert(lastResponse == ESP_GATT_OK && committed == "old settings");
    ble.disconnectAll();
    assert(!ble.isConnected() && !canWrite(2));
    ble.disconnected(1); ble.disconnected(2);
    // Two connections arrive before either finishes pairing; the latest wins
    // even when authentication completes in reverse order.
    bluetoothAccess.open = true;
    connect(1); connect(2); auth(2); auth(1);
    assert(ble._ownerId == 2 && !canWrite(1));
    // Fresh key exchange outside enrollment must not replace a known bond.
    ble.disconnected(1);
    bluetoothAccess.open = false;
    connect(1);
    esp_ble_gap_cb_param_t keyEvent{};
    keyEvent.ble_security.ble_key.bd_addr[5] = 1;
    ble.handleGap(ESP_GAP_BLE_KEY_EVT, &keyEvent);
    auth(1);
    assert(ble._ownerId == 2 && removedBonds.count(1));
    ble.disconnected(1, 0x13);
    assert(Serial.output.find("DISCONNECT conn=1 reason=0x13 was_controller=0") != std::string::npos);
    // Waiting for the client cannot grant control. A failed handshake is
    // reported by AUTH_CMPL and leaves the current owner intact.
    bluetoothAccess.open = true;
    connect(3);
    assert(readAccess(3) == 1 && ble._ownerId == 2 && encryptedRequests == 0);
    auth(3, false);
    assert(readAccess(3) == 3 && ble._ownerId == 2);
    ble.disconnected(3);
    connect(1);
    fakeMillis += 30000;
    ble.pollAdvertising();
    assert(readAccess(1) == 3 && ble._ownerId == 2);
    assert(Serial.output.find("AUTH_TIMEOUT conn=1 elapsed=30000 pairing=open") != std::string::npos);
    ble.disconnectAll();
    ble.disconnected(1); ble.disconnected(2); ble.disconnected(3);
    bluetoothAccess.open = false;
    removedBonds.clear();

    // Real macOS trace: bonded authentication completes before GATTS CONNECT.
    // Do not delete that bond or wait for a second AUTH event that never arrives.
    bluetoothAccess.bonds.insert(1);
    auth(1);
    assert(!ble.isConnected() && removedBonds.empty());
    const auto encryptionBeforeEarlyAuth = encryptedRequests;
    connect(1);
    assert(readAccess(1) == 2 && canWrite(1));
    assert(encryptedRequests == encryptionBeforeEarlyAuth && removedBonds.empty());
    ble.disconnected(1);
    connect(1);
    assert(readAccess(1) == 1); // completed authentication is consumed only once
    ble.disconnected(1);

    // A failed early authentication cannot become a valid controller.
    auth(1, false); connect(1);
    assert(readAccess(1) == 3 && !canWrite(1));
    assert(removedBonds.empty()); // preserve the existing bond
    ble.disconnected(1);

    // Early events must retain the same enrollment restrictions as normal ones.
    auth(42); connect(42);
    assert(readAccess(42) == 0 && !bluetoothAccess.bonds.count(42));
    assert(removedBonds.count(42));
    ble.disconnected(42);
    keyEvent.ble_security.ble_key.bd_addr[5] = 1;
    ble.handleGap(ESP_GAP_BLE_KEY_EVT, &keyEvent); // closed at key exchange
    bluetoothAccess.open = true;
    auth(1); connect(1);
    assert(readAccess(1) == 0 && !canWrite(1));
    ble.disconnected(1);
    keyEvent.ble_security.ble_key.bd_addr[5] = 4;
    ble.handleGap(ESP_GAP_BLE_KEY_EVT, &keyEvent);
    auth(4); connect(4);
    assert(readAccess(4) == 2 && bluetoothAccess.bonds.count(4));
    ble.disconnected(4);

    // Expired or reset-buffered outcomes cannot authorize a later connection.
    bluetoothAccess.open = false;
    auth(1); fakeMillis += 5000; connect(1);
    assert(readAccess(1) == 1);
    ble.disconnected(1);
    auth(1); ble.disconnectAll(); connect(1);
    assert(readAccess(1) == 1);
    ble.disconnected(1);

    esp_ble_gap_cb_param_t request{};
    request.ble_security.ble_req.bd_addr[5] = 1;
    ble.handleGap(ESP_GAP_BLE_SEC_REQ_EVT, &request);
    assert(!securityAccepted); // fresh pairing requires a window even before CONNECT
    connect(1);
    ble.handleGap(ESP_GAP_BLE_SEC_REQ_EVT, &request);
    assert(!securityAccepted); // a known connected peer cannot re-pair while closed
    assert(Serial.output.find("SECURITY_REQUEST conn=1 decision=deny pairing=closed") != std::string::npos);
    ble.disconnected(1);
    // A separate reconnect using saved keys still authenticates while closed.
    connect(1); auth(1);
    assert(readAccess(1) == 2 && canWrite(1));
    ble.disconnected(1);
    request.ble_security.ble_req.bd_addr[5] = 99;
    ble.handleGap(ESP_GAP_BLE_SEC_REQ_EVT, &request);
    assert(!securityAccepted);
    connect(99); // rejected before the window opens
    bluetoothAccess.open = true;
    ble.handleGap(ESP_GAP_BLE_SEC_REQ_EVT, &request);
    assert(!securityAccepted); // opening pairing cannot revive a rejected link
    ble.disconnected(99);
    ble.handleGap(ESP_GAP_BLE_SEC_REQ_EVT, &request);
    assert(securityAccepted);
    connect(99);
    ble.handleGap(ESP_GAP_BLE_SEC_REQ_EVT, &request);
    assert(securityAccepted); // new phone may pair inside the window
    ble.disconnected(99);
    request.ble_security.ble_req.bd_addr[5] = 1;
    ble.handleGap(ESP_GAP_BLE_SEC_REQ_EVT, &request);
    assert(securityAccepted); // known phone may also re-pair inside the window
    connect(1);
    ble.handleGap(ESP_GAP_BLE_SEC_REQ_EVT, &request);
    assert(securityAccepted);
    ble.disconnected(1);

    // A success callback alone cannot grant access without a saved bond.
    bluetoothAccess.open = true;
    connect(88);
    esp_ble_gap_cb_param_t noBond{};
    noBond.ble_security.auth_cmpl.bd_addr[5] = 88;
    ble.handleGap(ESP_GAP_BLE_AUTH_CMPL_EVT, &noBond);
    assert(!canWrite(88) && readAccess(88) == 3);
    ble.disconnected(88);

    // Firmware-update writes reach the transport only from the controller,
    // skip Arduino's value copy, and never use prepared writes.
    struct RecordingOta : OtaTransport {
        std::vector<std::string> controls, chunks;
        uint16_t mtu = 0;
        uint8_t lastPeer = 0;
        void control(const uint8_t* bytes, size_t length, const uint8_t* peer) override {
            controls.emplace_back(reinterpret_cast<const char*>(bytes), length);
            lastPeer = peer[5];
        }
        void data(const uint8_t* bytes, size_t length) override {
            chunks.emplace_back(reinterpret_cast<const char*>(bytes), length);
        }
        void mtuChanged(uint16_t value) override { mtu = value; }
    } ota;
    BLECharacteristic otaChars[4];
    for (int i = 0; i < 4; ++i) {
        otaChars[i].handle = 60 + i * 2;
        otaChars[i].cccd.handle = otaChars[i].handle + 1;
        ble._securedChars[16 + i] = &otaChars[i];
    }
    ble._otaStatusChar = &otaChars[3];
    ble.setOtaTransport(&ota);
    uint8_t otaBytes[] = {2, 1, 9};
    auto otaWrite = [&](uint16_t id, int attribute, bool needResponse, bool prepared = false) {
        esp_ble_gatts_cb_param_t p{};
        p.write.conn_id = id; p.write.handle = otaChars[attribute].handle; p.write.bda[5] = uint8_t(id);
        p.write.value = otaBytes; p.write.len = sizeof(otaBytes);
        p.write.need_rsp = needResponse; p.write.is_prep = prepared;
        lastResponse = -1;
        return ble.filterGatt(ESP_GATTS_WRITE_EVT, configGattsIf, &p);
    };
    connect(1); auth(1);
    const int arduinoDispatches = dispatches;
    assert(!otaWrite(1, 1, true) && lastResponse == ESP_GATT_OK);
    assert(ota.controls.size() == 1 && ota.controls[0] == std::string("\x02\x01\x09", 3));
    assert(ota.lastPeer == 1);  // the writer's address, for connection parameters
    assert(!otaWrite(1, 2, false) && lastResponse == -1);  // write without response
    assert(ota.chunks.size() == 1 && dispatches == arduinoDispatches);
    assert(!otaWrite(1, 2, true, true) && lastResponse == ESP_GATT_REQ_NOT_SUPPORTED);
    // A begin command longer than the default MTU arrives as a long write.
    assert(!otaWrite(1, 1, true, true) && lastResponse == ESP_GATT_OK);
    esp_ble_gatts_cb_param_t executeLong{};
    executeLong.exec_write.conn_id = 1; executeLong.exec_write.exec_write_flag = ESP_GATT_PREP_WRITE_EXEC;
    executeLong.exec_write.bda[5] = 1;
    ble._otaControlChar = &otaChars[1];
    assert(!ble.filterGatt(ESP_GATTS_EXEC_WRITE_EVT, configGattsIf, &executeLong) && lastResponse == ESP_GATT_OK);
    assert(ota.controls.size() == 2 && ota.controls[1] == std::string("\x02\x01\x09", 3));
    assert(dispatches == arduinoDispatches);
    assert(!otaWrite(1, 0, true) && lastResponse == ESP_GATT_WRITE_NOT_PERMIT);  // firmware info is read-only
    assert(ota.chunks.size() == 1);
    connect(3);  // unapproved phone
    assert(!otaWrite(3, 1, true) && lastResponse == ESP_GATT_INSUF_AUTHORIZATION);
    assert(ota.controls.size() == 2);
    esp_ble_gatts_cb_param_t mtuEvent{};
    mtuEvent.mtu.conn_id = 1; mtuEvent.mtu.mtu = 517;
    ble.filterGatt(ESP_GATTS_MTU_EVT, configGattsIf, &mtuEvent);
    assert(ota.mtu == 517);
    const uint8_t otaStatus[18] = {1, 2};
    const size_t sentBefore = packets.size();
    ble.updateOtaStatus(otaStatus, sizeof(otaStatus));
    assert(packets.size() == sentBefore);  // not subscribed yet
    ble.peer(1)->subscriptions |= 1UL << 19;
    ble.updateOtaStatus(otaStatus, sizeof(otaStatus));
    assert(packets.size() == sentBefore + 1 && packets.back().handle == otaChars[3].handle);
    assert(packets.back().data.size() == 18 && !packets.back().indication);
    // An unplayable-song warning waits for the controller's notice subscription.
    assert(!ble.noticeSubscribed());
    ble.peer(1)->subscriptions |= 1UL << 13;
    assert(ble.noticeSubscribed());
    bluetoothAccess.available = false;  // during a bond reset nothing is shown
    assert(!ble.noticeSubscribed());
    bluetoothAccess.available = true;
    ble.setOtaTransport(nullptr);
    ble.disconnected(3);
    ble.disconnected(1);

    // A reset blocks controls immediately, before the asynchronous disconnect.
    connect(1); auth(1);
    assert(canWrite(1));
    bluetoothAccess.available = false;
    assert(!canWrite(1));
    ble.disconnectAll();
    assert(ble.hasLinks());
    ble.disconnected(1);
    assert(!ble.hasLinks());

    // Low memory: refuse value updates instead of aborting, and still answer.
    {
        BLECharacteristic response, attribute;
        ble._configResponseChar = &response;
        ble._configAttributes[0] = &attribute;
        // A full-size page: too big for the heap, while the short error fits.
        const String reply = "{\"id\":42,\"ok\":true,\"op\":\"scanThemes\",\"themes\":[\"" +
            std::string(400, 'x') + "\"]}";
        fakeLargestBlock = reply.size() + BLE_VALUE_HEAP_RESERVE - 1;
        ble.updateConfigResponse(reply);
        assert(response.value == "{\"id\":42,\"ok\":false,\"error\":\"The toy is low on memory. Try again.\"}");
        assert(Serial.output.find("Low memory: value not updated") != std::string::npos);
        // On hardware a refused reply saw largest=1908: the error must still fit.
        response.value = "old";
        fakeLargestBlock = 1908;
        ble.updateConfigResponse(reply);
        assert(response.value.find("low on memory") != std::string::npos);
        fakeLargestBlock = 100;  // not even the short error fits: keep the old value
        response.value = "old";
        ble.updateConfigResponse(reply);
        assert(response.value == "old");
        fakeLargestBlock = 100000;
        BLECharacteristic::throwOnSet = true;  // the backstop when the check passes
        ble.updateConfigResponse(reply);
        assert(response.value == "old");
        BLECharacteristic::throwOnSet = false;
        ble.updateConfigResponse(reply);
        assert(response.value == reply);
        // Unchanged attributes are compared in place, without a value copy.
        ble.updateConfigAttribute(0, "{\"a\":1}");
        const int copies = BLECharacteristic::valueCopies;
        ble.updateConfigAttribute(0, "{\"a\":1}");
        assert(BLECharacteristic::valueCopies == copies && attribute.value == "{\"a\":1}");
        assert(BLEParentService::responseRequestId("{\"id\":7,\"ok\":true}") == 7);
        assert(BLEParentService::responseRequestId("{}") == 0);
        ble._configResponseChar = nullptr;
        ble._configAttributes[0] = nullptr;
    }
    // Service Changed: once per bonded identity and GATT layout.
    bluetoothAccess.available = true;
    ble._layoutPending = false;
    ble._gattLayout = 0x1234;
    serviceChanges.clear();
    storedLayouts.clear();
    auto layoutResult = [&](int status) {
        esp_ble_gatts_cb_param_t p{};
        p.service_change.status = status;
        assert(!ble.filterGatt(ESP_GATTS_SEND_SERVICE_CHANGE_EVT, configGattsIf, &p));
        ble.pollAdvertising();
    };
    connect(1); auth(1);
    ble.pollAdvertising();
    assert(serviceChanges == std::vector<uint8_t>{1});
    ble.pollAdvertising();
    assert(serviceChanges.size() == 1); // one request per authentication
    layoutResult(ESP_OK);
    assert(storedLayouts.at("000000000001") == 0x1234);
    ble.disconnected(1);
    connect(1); auth(1); ble.pollAdvertising();
    assert(serviceChanges.size() == 1); // this client already has the table
    ble.peer(1)->newKeys = true;  // a fresh bond may still use an old cache
    ble.peer(1)->layoutCheck = true;
    ble.pollAdvertising();
    assert(serviceChanges.size() == 2);
    layoutResult(ESP_OK);
    ble.disconnected(1);
    ble._gattLayout = 0x5678;
    connect(1); auth(1); ble.pollAdvertising();
    assert(serviceChanges.size() == 3);
    layoutResult(1); // not delivered: keep the old record and retry next time
    assert(storedLayouts.at("000000000001") == 0x1234);
    ble.disconnected(1);
    connect(1); auth(1); ble.pollAdvertising();
    assert(serviceChanges.size() == 4);
    fakeMillis += 5000; ble.pollAdvertising();
    assert(!ble._layoutPending && storedLayouts.at("000000000001") == 0x1234);
    assert(Serial.output.find("SERVICE_CHANGED conn=1 status=timeout") != std::string::npos);
    ble.disconnected(1);

    std::cout << "BLE authorization and takeover tests passed\n";
}

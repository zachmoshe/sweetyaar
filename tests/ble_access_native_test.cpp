#include <cassert>
#include <array>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <map>
#include <set>
#include <string>
#include <vector>
#include "ChargerStatus.h"
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
    ESP_GATTS_REG_EVT, ESP_BLE_SEC_ENCRYPT_NO_MITM };
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
    struct { uint16_t conn_id = 0, trans_id = 0, handle = 0, offset = 0; } read;
    struct { uint16_t conn_id = 0, trans_id = 0, handle = 0, len = 0, offset = 0;
        bool need_rsp = true, is_prep = false; uint8_t* value = nullptr; } write;
    struct { uint16_t conn_id = 0, trans_id = 0; int exec_write_flag = 0; } exec_write;
    struct { uint16_t conn_id = 0; uint8_t remote_bda[6] = {}; } connect;
    struct { uint16_t conn_id = 0, reason = 0; } disconnect;
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
uint32_t millis() { return fakeMillis; }
struct BLE2902 {
    uint16_t handle = 0;
    uint16_t getHandle() { return handle; }
    void setAccessPermissions(int) {}
};
struct BLECharacteristicCallbacks;
struct BLECharacteristic {
    enum { PROPERTY_READ = 1, PROPERTY_WRITE = 2, PROPERTY_NOTIFY = 4, PROPERTY_INDICATE = 8 };
    uint16_t handle = 0;
    BLE2902 cccd;
    std::string value;
    uint16_t getHandle() { return handle; }
    BLE2902* getDescriptorByUUID(const char*) { return &cccd; }
    std::string getValue() { return value; }
    void setValue(const char* next) { value = next; }
    void setValue(uint8_t* next, size_t length) { value.assign(reinterpret_cast<char*>(next), length); }
    void addDescriptor(BLE2902* descriptor) { delete descriptor; }
    void setCallbacks(BLECharacteristicCallbacks*);
    void setAccessPermissions(int) {}
};
struct BLECharacteristicCallbacks {
    virtual ~BLECharacteristicCallbacks() = default;
    virtual void onWrite(BLECharacteristic*) {}
};
void BLECharacteristic::setCallbacks(BLECharacteristicCallbacks* callbacks) { delete callbacks; }
struct BLEUUID { explicit BLEUUID(const char*) {} };
struct BLEService {
    std::array<BLECharacteristic, 17> characteristics;
    size_t count = 0;
    bool started = false;
    BLECharacteristic* createCharacteristic(const char*, int) { return &characteristics.at(count++); }
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

    // A reset blocks controls immediately, before the asynchronous disconnect.
    connect(1); auth(1);
    assert(canWrite(1));
    bluetoothAccess.available = false;
    assert(!canWrite(1));
    ble.disconnectAll();
    assert(ble.hasLinks());
    ble.disconnected(1);
    assert(!ble.hasLinks());

    std::cout << "BLE authorization and takeover tests passed\n";
}

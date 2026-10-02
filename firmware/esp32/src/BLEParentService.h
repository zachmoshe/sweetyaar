#pragma once
#include <Arduino.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>
#include <freertos/FreeRTOS.h>
#include <freertos/portmacro.h>
#include "Config.h"
#include "ChargerStatus.h"

// ---------------------------------------------------------------------------
// BLEParentService — GATT server for parent controls
//
// Exposes parent-control and config characteristics:
//   volume     (uint8, read/write/notify)   — 0–100, local WAV volume
//   killswitch (uint8, read/write/notify)   — write 1 to activate, 0 to cancel
//   theme      (string, read/write/notify)  — active song theme folder id
//   status     (string, read/notify)        — user-facing state description
//   themes     (JSON string, read)          — available song themes
//   command    (uint8, write)               — 1=song, 2=animal, 3=stop,
//                                              4=loop on, 5=loop off
//   configCmd  (JSON string, write)         — settings/scan command
//   configResp (JSON string, read/notify)   — settings/scan response
//   battery    (uint8, read/notify)          — 0=unknown, 1=good, 2=medium,
//                                              3=low, 4=charging
//   charger    (6 bytes, read/notify)        — versioned activity/conditions/events
//
// Callbacks fire in a BLE stack task; they set thread-safe flags that the
// main loop reads via the pollXxx() methods.
//
// Usage:
//   BLEParentService ble;
//   ble.begin("SweetYaar");       // call once in setup()
//   ble.updateStatus("idle");     // push state string to notify clients
//
//   // In loop():
//   if (uint8_t v; ble.pollVolumeChange(v))   { ... apply volume ... }
//   if (bool on; ble.pollKillswitch(on))      { ... handle killswitch ... }
//   if (String t; ble.pollThemeChange(t))     { ... switch theme ... }
// ---------------------------------------------------------------------------

class BLEParentService {
public:
    BLEParentService() = default;

    // Call once after NVS is ready. On security configuration failure, returns
    // false without creating the GATT service or starting advertising.
    bool begin(const String& deviceName);

    // Push current values to the subscribed, authenticated controller.
    void updateVolume(uint8_t volumePct);
    void updateKillswitch(bool active);
    void updateTheme(const String& theme);
    void updateStatus(const String& status);
    void updateThemes(const String& themesJson);
    void updateConfigResponse(const String& responseJson);
    // JSON values are read in full; notifications only signal a changed value.
    void updateConfigAttribute(size_t index, const String& value);
    void updateBatteryState(uint8_t state);
    void updateChargerStatus(const ChargerStatus::Snapshot& snapshot);
    void updateDeviceName(const String& deviceName);

    // Push a one-shot notice for the app to display. |noticeJson| is the full
    // payload, e.g. {"severity":"error","message":"..."}. The app shows it on
    // notify; the device decides the wording and severity.
    void updateNotice(const String& noticeJson);

    // Poll for new BLE-requested volume; returns true and fills |out| once per event
    bool pollVolumeChange(uint8_t& out);

    // Poll for killswitch event; out=true means activate, false=cancel
    bool pollKillswitch(bool& out);

    // Poll for theme change; fills |out| with new theme name
    bool pollThemeChange(String& out);

    // Poll for app command; out: 1=song, 2=animal, 3=stop, 4=loop on, 5=loop off
    bool pollCommand(uint8_t& out);

    // Poll for JSON config command from the app
    bool pollConfigCommand(String& out);

    // True only when an authenticated controller owns this remote.
    bool isConnected() const;
    bool hasLinks();

    // Maintain takeover delivery and advertising from the main loop.
    void pollAdvertising(bool canNotify = true);
    void disconnectAll();

private:
    BLEServer*         _server   = nullptr;
    BLECharacteristic* _volChar  = nullptr;
    BLECharacteristic* _killChar = nullptr;
    BLECharacteristic* _themeChar = nullptr;
    BLECharacteristic* _statusChar = nullptr;
    BLECharacteristic* _themesChar = nullptr;
    BLECharacteristic* _commandChar = nullptr;
    BLECharacteristic* _configCommandChar = nullptr;
    BLECharacteristic* _configResponseChar = nullptr;
    BLECharacteristic* _noticeChar = nullptr;
    BLECharacteristic* _batteryChar = nullptr;
    BLECharacteristic* _chargerChar = nullptr;
    BLECharacteristic* _accessChar = nullptr;
    uint8_t _lastChargerValue[ChargerStatus::ENCODED_SIZE] = {};
    bool _hasChargerValue = false;
    BLECharacteristic* _configAttributes[BLE_CONFIG_ATTRIBUTE_COUNT] = {};
    void notifyChanged(BLECharacteristic* characteristic);
    void notifyOwner(BLECharacteristic* characteristic, bool invalidation = false);
    void handleGap(esp_gap_ble_cb_event_t event, esp_ble_gap_cb_param_t* param);
    bool filterGatt(esp_gatts_cb_event_t event, esp_gatt_if_t interface,
                    esp_ble_gatts_cb_param_t* param);
    void connected(esp_ble_gatts_cb_param_t* param);
    void disconnected(uint16_t connection, uint16_t reason = 0);
    void disconnectPeer(uint16_t connection);
    void clearPending(); // caller holds _mux
    static constexpr uint16_t NO_CONNECTION = 0xffff;
    // Public, per-connection diagnostic; it never authorizes control access.
    enum class AccessState : uint8_t {
        PairingRequired = 0, Authenticating = 1, Ready = 2,
        AuthenticationFailed = 3, TakenOver = 4
    };
    static const char* accessStateName(AccessState state);
    static constexpr uint32_t REJECTION_GRACE_MS = 10000;
    struct Peer {
        uint16_t id = NO_CONNECTION;
        uint8_t address[6] = {};
        uint8_t identity[6] = {};
        uint32_t connectedAt = 0;
        uint32_t sequence = 0;
        uint32_t retiredAt = 0;
        uint32_t subscriptions = 0;
        uint32_t rejectedAt = 0;
        AccessState rejectionReason = AccessState::AuthenticationFailed;
        bool known = false;
        bool authenticated = false;
        bool newKeys = false;
        bool reject = false;
        bool retiring = false;
        bool noticeSent = false;
        bool noticeConfirmed = false;
        bool disconnectRequested = false;
    };
    Peer _peers[3];
    // GAP security can finish before Arduino delivers GATTS CONNECT (macOS
    // bonded reconnects do this). Keep only outcome metadata, never key bytes.
    struct EarlySecurity {
        uint8_t address[6] = {};
        uint32_t observedAt = 0;
        bool used = false;
        bool newKeys = false;
        bool keysOutsidePairing = false;
        bool hasAuth = false;
        bool success = false;
        uint8_t failReason = 0;
        uint8_t authMode = 0;
    };
    EarlySecurity _earlySecurity[3];
    EarlySecurity* earlySecurity(const uint8_t* address, bool create = false);
    uint32_t _connectionSequence = 0;
    volatile uint16_t _ownerId = NO_CONNECTION;
    uint16_t _preparedOwner = NO_CONNECTION;
    uint16_t _preparedHandle = 0;
    uint16_t _preparedLength = 0;
    uint8_t _preparedValue[512] = {};
    BLECharacteristic* _securedChars[16] = {};
    Peer* peer(uint16_t id);
    Peer* peerByAddress(const uint8_t* address);
    int characteristicIndex(uint16_t handle, bool descriptor = false);
    esp_gap_ble_cb_t _originalGap = nullptr;
    esp_gatts_cb_t _originalGatt = nullptr;
    static BLEParentService* _instance;

    // Pending events set by BLE callbacks, consumed by poll methods
    volatile bool    _newVolume     = false;
    volatile uint8_t _pendingVolume = 0;

    volatile bool    _newKillswitch   = false;
    volatile bool    _pendingKillswitch = false;

    volatile bool    _newTheme = false;
    char             _pendingTheme[64] = {0};

    volatile bool    _newCommand = false;
    volatile uint8_t _pendingCommand = 0;

    volatile bool    _newConfigCommand = false;
    char             _pendingConfigCommand[384] = {0};

    volatile bool    _restartAdvPending = false;
    portMUX_TYPE     _mux = portMUX_INITIALIZER_UNLOCKED;

    // Server callbacks (connect/disconnect)
    class ServerCB : public BLEServerCallbacks {
    public:
        explicit ServerCB(BLEParentService* owner) : _owner(owner) {}
        void onConnect(BLEServer*, esp_ble_gatts_cb_param_t* param) override {
            _owner->connected(param);
        }
        void onDisconnect(BLEServer*, esp_ble_gatts_cb_param_t* param) override {
            _owner->disconnected(param->disconnect.conn_id, param->disconnect.reason);
        }
    private:
        BLEParentService* _owner;
    };

    // Characteristic write callbacks
    class VolumeCB : public BLECharacteristicCallbacks {
    public:
        explicit VolumeCB(BLEParentService* owner) : _owner(owner) {}
        void onWrite(BLECharacteristic* c) override {
            std::string value = c->getValue();
            if (value.empty()) return;
            uint8_t val = static_cast<uint8_t>(value[0]);
            if (val > 100) val = 100;
            portENTER_CRITICAL(&_owner->_mux);
            _owner->_pendingVolume = val;
            _owner->_newVolume     = true;
            portEXIT_CRITICAL(&_owner->_mux);
        }
    private:
        BLEParentService* _owner;
    };

    class KillswitchCB : public BLECharacteristicCallbacks {
    public:
        explicit KillswitchCB(BLEParentService* owner) : _owner(owner) {}
        void onWrite(BLECharacteristic* c) override {
            std::string value = c->getValue();
            if (value.empty()) return;
            uint8_t val = static_cast<uint8_t>(value[0]);
            portENTER_CRITICAL(&_owner->_mux);
            _owner->_pendingKillswitch = (val != 0);
            _owner->_newKillswitch     = true;
            portEXIT_CRITICAL(&_owner->_mux);
        }
    private:
        BLEParentService* _owner;
    };

    class ThemeCB : public BLECharacteristicCallbacks {
    public:
        explicit ThemeCB(BLEParentService* owner) : _owner(owner) {}
        void onWrite(BLECharacteristic* c) override {
            std::string value = c->getValue();
            portENTER_CRITICAL(&_owner->_mux);
            size_t n = value.copy(_owner->_pendingTheme, sizeof(_owner->_pendingTheme) - 1);
            _owner->_pendingTheme[n] = '\0';
            _owner->_newTheme = true;
            portEXIT_CRITICAL(&_owner->_mux);
        }
    private:
        BLEParentService* _owner;
    };

    class CommandCB : public BLECharacteristicCallbacks {
    public:
        explicit CommandCB(BLEParentService* owner) : _owner(owner) {}
        void onWrite(BLECharacteristic* c) override {
            std::string value = c->getValue();
            if (value.size() != 1) return;
            const uint8_t command = static_cast<uint8_t>(value[0]);
            if (command < 1 || command > 5) return;
            portENTER_CRITICAL(&_owner->_mux);
            _owner->_pendingCommand = command;
            _owner->_newCommand = true;
            portEXIT_CRITICAL(&_owner->_mux);
        }
    private:
        BLEParentService* _owner;
    };

    class ConfigCommandCB : public BLECharacteristicCallbacks {
    public:
        explicit ConfigCommandCB(BLEParentService* owner) : _owner(owner) {}
        void onWrite(BLECharacteristic* c) override {
            std::string value = c->getValue();
            portENTER_CRITICAL(&_owner->_mux);
            size_t n = value.copy(_owner->_pendingConfigCommand,
                                  sizeof(_owner->_pendingConfigCommand) - 1);
            _owner->_pendingConfigCommand[n] = '\0';
            _owner->_newConfigCommand = true;
            portEXIT_CRITICAL(&_owner->_mux);
        }
    private:
        BLEParentService* _owner;
    };
};

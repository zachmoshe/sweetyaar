#pragma once
#include <Arduino.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>
#include <freertos/FreeRTOS.h>
#include <freertos/portmacro.h>
#include "Config.h"

// ---------------------------------------------------------------------------
// BLEParentService — GATT server for parent controls
//
// Exposes parent-control and config characteristics:
//   volume     (uint8, read/write/notify)   — 0–100, local WAV volume
//   killswitch (uint8, read/write/notify)   — write 1 to activate, 0 to cancel
//   theme      (string, read/write/notify)  — active song theme folder id
//   status     (string, read/notify)        — user-facing state description
//   themes     (JSON string, read)          — available song themes
//   command    (uint8, write)               — 1=song, 2=animal, 3=stop
//   configCmd  (JSON string, write)         — settings/scan command
//   configResp (JSON string, read/notify)   — settings/scan response
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

    // Start BLE advertising; call after NVS is ready
    void begin(const String& deviceName);

    // Push current values to all subscribed clients
    void updateVolume(uint8_t volumePct);
    void updateKillswitch(bool active);
    void updateTheme(const String& theme);
    void updateStatus(const String& status);
    void updateThemes(const String& themesJson);
    void updateConfigResponse(const String& responseJson);
    void updateDeviceName(const String& deviceName);

    // Push a one-shot notice for the app to display. |noticeJson| is the full
    // payload, e.g. {"severity":"error","message":"..."}. The app shows it on
    // notify; the device decides the wording and severity.
    void updateNotice(const String& noticeJson);

    // Non-destructive peek: returns true if a new volume value has arrived
    bool hasVolumeChange() const { return _newVolume; }

    // Poll for new BLE-requested volume; returns true and fills |out| once per event
    bool pollVolumeChange(uint8_t& out);

    // Poll for killswitch event; out=true means activate, false=cancel
    bool pollKillswitch(bool& out);

    // Poll for theme change; fills |out| with new theme name
    bool pollThemeChange(String& out);

    // Poll for app command; out: 1=song, 2=animal, 3=stop
    bool pollCommand(uint8_t& out);

    // Poll for JSON config command from the app
    bool pollConfigCommand(String& out);

    // True if at least one BLE central is connected
    bool isConnected() const;

    // Call from main loop to safely restart advertising after a disconnect
    void pollAdvertising();

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

    volatile bool    _connected = false;
    volatile bool    _restartAdvPending = false;
    portMUX_TYPE     _mux = portMUX_INITIALIZER_UNLOCKED;

    // Server callbacks (connect/disconnect)
    class ServerCB : public BLEServerCallbacks {
    public:
        explicit ServerCB(BLEParentService* owner) : _owner(owner) {}
        void onConnect(BLEServer*) override {
            _owner->_connected = true;
            Serial.println("[BLE] Client connected");
        }
        void onDisconnect(BLEServer*) override {
            _owner->_connected = false;
            _owner->_restartAdvPending = true;  // defer out of BT stack callback
            Serial.println("[BLE] Client disconnected");
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
            if (value.empty()) return;
            portENTER_CRITICAL(&_owner->_mux);
            char first = value[0];
            if (first == '{') {
                size_t n = value.copy(_owner->_pendingConfigCommand,
                                      sizeof(_owner->_pendingConfigCommand) - 1);
                _owner->_pendingConfigCommand[n] = '\0';
                _owner->_newConfigCommand = true;
            } else {
                _owner->_pendingCommand = static_cast<uint8_t>(first);
                _owner->_newCommand = true;
            }
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

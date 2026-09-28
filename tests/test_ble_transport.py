"""Exercise production BLE transport methods without an ESP32 radio."""

import shutil

import pytest

from helpers import run_checked
from test_catalog_pagination import production_function


def test_config_transport_preserves_themes(repo_root, tmp_path):
    compiler = shutil.which("c++")
    if not compiler:
        pytest.skip("A C++ compiler is required for BLE transport tests.")
    src = repo_root / "firmware/esp32/src"
    source = (src / "BLEParentService.cpp").read_text()
    header = (src / "BLEParentService.h").read_text()
    methods = []
    for name in ("updateThemes", "updateConfigResponse"):
        start = source.index(f"void BLEParentService::{name}(")
        methods.append(source[start:source.index("\n}", start) + 2])
    start = header.index("    class CommandCB :")
    command_callback = header[start:header.index("\n    };", start) + 7]

    # Compile the actual method bodies and playback callback. Only the BLE
    # characteristic, Arduino String and critical-section boundaries are stubbed.
    program = tmp_path / "ble_transport.cpp"
    program.write_text(r'''
#include <cassert>
#include <cstdint>
#include <string>
using String = std::string;
#define portENTER_CRITICAL(mux) ((void)(mux))
#define portEXIT_CRITICAL(mux) ((void)(mux))
struct BLECharacteristic {
    std::string value;
    int notifications = 0;
    void setValue(const char* next) { value = next; }
    std::string getValue() { return value; }
    void notify() { ++notifications; }
};
struct BLECharacteristicCallbacks {
    virtual void onWrite(BLECharacteristic*) = 0;
};
class BLEParentService {
public:
    BLECharacteristic* _themesChar = nullptr;
    BLECharacteristic* _configResponseChar = nullptr;
    bool _connected = false;
    int _mux = 0;
    uint8_t _pendingCommand = 0;
    bool _newCommand = false;
    char _pendingConfigCommand[384] = {};
    bool _newConfigCommand = false;
    void notifyChanged(BLECharacteristic* c) { if (_connected) c->notify(); }
    void updateThemes(const String&);
    void updateConfigResponse(const String&);
''' + command_callback + "\n};\n" + "\n".join(methods) + r'''
int main() {
    BLEParentService ble;
    BLECharacteristic themes, response, command;
    ble._themesChar = &themes;
    ble._configResponseChar = &response;
    const std::string catalog = R"([{"id":"lullabies","name":"Lullabies"}])";
    ble.updateThemes(catalog);
    for (bool connected : {false, true}) {
        ble._connected = connected;
        const int before = response.notifications;
        for (const char* reply : {R"({"id":1,"ok":true,"op":"syncTime"})",
                                 R"({"id":2,"ok":true,"op":"scanThemes"})"}) {
            ble.updateConfigResponse(reply);
            assert(response.value == reply);
            assert(themes.value == catalog);
            assert(themes.notifications == 0);
        }
        assert(response.notifications == before + (connected ? 2 : 0));
    }
    ble._configResponseChar = nullptr;
    ble.updateConfigResponse(R"({"id":3,"ok":false})");
    assert(themes.value == catalog);

    BLEParentService::CommandCB callback(&ble);
    for (uint8_t value = 1; value <= 5; ++value) {
        ble._newCommand = false;
        command.value.assign(1, static_cast<char>(value));
        callback.onWrite(&command);
        assert(ble._newCommand && ble._pendingCommand == value);
        assert(!ble._newConfigCommand);
    }
    for (const std::string value : {std::string(), std::string(1, '\0'),
                                   std::string(1, '\6'), std::string("{"),
                                   std::string(R"({"id":1,"op":"syncTime"})")}) {
        ble._newCommand = false;
        command.value = value;
        callback.onWrite(&command);
        assert(!ble._newCommand);
        assert(!ble._newConfigCommand);
    }
}
''')
    executable = tmp_path / "ble_transport"
    run_checked([compiler, "-std=c++17", "-Wall", "-Wextra", program, "-o", executable])
    run_checked([executable])


def test_config_attributes_notify_small_signals_and_keep_complete_read_values(repo_root, tmp_path):
    compiler = shutil.which("c++")
    if not compiler:
        pytest.skip("A C++ compiler is required for BLE transport tests.")
    source = (repo_root / "firmware/esp32/src/BLEParentService.cpp").read_text()
    program = tmp_path / "config_attributes.cpp"
    program.write_text(r'''
#include <cassert>
#include <cstdint>
#include <string>
using String = std::string;
constexpr size_t BLE_CONFIG_MAX_BYTES = 512;
constexpr size_t BLE_CONFIG_ATTRIBUTE_COUNT = 5;
constexpr int ESP_GATT_IF_NONE = -1;
constexpr int ESP_OK = 0;
using esp_err_t = int;
int configGattsIf = 7;
struct { template<typename... T> void printf(T...) {} } Serial;
struct BLE2902 { bool subscribed = true; bool getNotifications() { return subscribed; } } descriptor;
struct BLECharacteristic {
    String value;
    void setValue(const char* text) { value = text; }
    String getValue() { return value; }
    BLE2902* getDescriptorByUUID(const char*) { return &descriptor; }
    uint16_t getHandle() { return 42; }
};
struct BLEServer { uint16_t getConnId() { return 12; } } server;
int notifications = 0;
int esp_ble_gatts_send_indicate(int interface, uint16_t connection, uint16_t handle,
                                 size_t length, uint8_t* data, bool confirmed) {
    assert(interface == 7 && connection == 12 && handle == 42);
    assert(length == 1 && data[0] == 1 && !confirmed); // fits even ATT MTU 23
    ++notifications;
    return ESP_OK;
}
class BLEParentService {
public:
    BLEServer* _server = &server;
    bool _connected = true;
    BLECharacteristic* _configAttributes[BLE_CONFIG_ATTRIBUTE_COUNT] = {};
    void notifyChanged(BLECharacteristic* characteristic);
    void updateConfigAttribute(size_t index, const String& value);
};
''' + production_function(source, "BLEParentService::notifyChanged") + "\n" +
        production_function(source, "BLEParentService::updateConfigAttribute") + r'''
int main() {
    BLEParentService ble;
    BLECharacteristic characteristic;
    ble._configAttributes[0] = &characteristic;
    const String fullValue(512, 'x');
    ble.updateConfigAttribute(0, fullValue);
    assert(characteristic.getValue() == fullValue && notifications == 1);
    ble.updateConfigAttribute(0, fullValue);
    assert(notifications == 1); // unchanged state doesn't flood the radio
    ble.updateConfigAttribute(0, String(513, 'x'));
    assert(characteristic.getValue() == fullValue && notifications == 1);
    descriptor.subscribed = false;
    ble.updateConfigAttribute(0, "unsubscribed");
    assert(notifications == 1 && characteristic.getValue() == "unsubscribed");
    descriptor.subscribed = true;
    ble._connected = false;
    ble.updateConfigAttribute(0, "disconnected");
    assert(notifications == 1 && characteristic.getValue() == "disconnected");
}
''')
    executable = tmp_path / "config_attributes"
    run_checked([compiler, "-std=c++17", "-Wall", "-Wextra", program, "-o", executable])
    run_checked([executable])

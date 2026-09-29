#include "BLEParentService.h"

namespace {
esp_gatt_if_t configGattsIf = ESP_GATT_IF_NONE;
}

void BLEParentService::begin(const String& deviceName) {
    BLEDevice::init(deviceName.c_str());
    // Arduino BLE exposes no small-payload notify overload. Capture this
    // server's interface so invalidations fit even the minimum ATT MTU (23).
    BLEDevice::setCustomGattsHandler([](esp_gatts_cb_event_t event, esp_gatt_if_t interface,
                                       esp_ble_gatts_cb_param_t* param) {
        if (event == ESP_GATTS_REG_EVT && param->reg.status == ESP_GATT_OK) {
            configGattsIf = interface;
        }
    });
    esp_err_t mtuResult = BLEDevice::setMTU(185);
    if (mtuResult != ESP_OK) {
        Serial.printf("[BLE] MTU request failed: %d\n", mtuResult);
    }

    _server = BLEDevice::createServer();
    _server->setCallbacks(new ServerCB(this));

    // Sixteen characteristics plus descriptors need more than the Arduino BLE
    // default of 15 handles. Under-allocating here can boot fine
    // and then crash Bluedroid when a central connects.
    BLEService* svc = _server->createService(BLEUUID(BLE_SERVICE_UUID), 64);

    // --- Volume characteristic (read/write/notify) -------------------------
    _volChar = svc->createCharacteristic(
        BLE_VOL_UUID,
        BLECharacteristic::PROPERTY_READ  |
        BLECharacteristic::PROPERTY_WRITE |
        BLECharacteristic::PROPERTY_NOTIFY);
    _volChar->addDescriptor(new BLE2902());
    _volChar->setCallbacks(new VolumeCB(this));

    // --- Killswitch characteristic (read/write/notify) ---------------------
    _killChar = svc->createCharacteristic(
        BLE_KILL_UUID,
        BLECharacteristic::PROPERTY_READ  |
        BLECharacteristic::PROPERTY_WRITE |
        BLECharacteristic::PROPERTY_NOTIFY);
    _killChar->addDescriptor(new BLE2902());
    _killChar->setCallbacks(new KillswitchCB(this));

    // --- Theme characteristic (read/write/notify) --------------------------
    _themeChar = svc->createCharacteristic(
        BLE_THEME_UUID,
        BLECharacteristic::PROPERTY_READ  |
        BLECharacteristic::PROPERTY_WRITE |
        BLECharacteristic::PROPERTY_NOTIFY);
    _themeChar->addDescriptor(new BLE2902());
    _themeChar->setCallbacks(new ThemeCB(this));

    // --- Status characteristic (read/notify) -------------------------------
    _statusChar = svc->createCharacteristic(
        BLE_STATUS_UUID,
        BLECharacteristic::PROPERTY_READ  |
        BLECharacteristic::PROPERTY_NOTIFY);
    _statusChar->addDescriptor(new BLE2902());

    // --- Themes characteristic (read-only JSON) ----------------------------
    _themesChar = svc->createCharacteristic(
        BLE_THEMES_UUID,
        BLECharacteristic::PROPERTY_READ);

    // --- Command characteristic (write-only app buttons) -------------------
    _commandChar = svc->createCharacteristic(
        BLE_COMMAND_UUID,
        BLECharacteristic::PROPERTY_WRITE);
    _commandChar->setCallbacks(new CommandCB(this));

    // --- Config command/response characteristics --------------------------
    _configCommandChar = svc->createCharacteristic(
        BLE_CONFIG_COMMAND_UUID,
        BLECharacteristic::PROPERTY_READ |
        BLECharacteristic::PROPERTY_WRITE);
    _configCommandChar->setCallbacks(new ConfigCommandCB(this));
    _configCommandChar->setValue("{}");

    _configResponseChar = svc->createCharacteristic(
        BLE_CONFIG_RESPONSE_UUID,
        BLECharacteristic::PROPERTY_READ |
        BLECharacteristic::PROPERTY_NOTIFY);
    _configResponseChar->addDescriptor(new BLE2902());
    _configResponseChar->setValue("{\"id\":0,\"ok\":true}");

    const char* configUuids[] = { BLE_CONFIG_GENERAL_UUID, BLE_CONFIG_SLEEP_UUID,
        BLE_CONFIG_BEDTIME_UUID, BLE_CONFIG_RUNTIME_UUID, BLE_CATALOG_NOTICE_UUID };
    for (size_t i = 0; i < BLE_CONFIG_ATTRIBUTE_COUNT; ++i) {
        _configAttributes[i] = svc->createCharacteristic(configUuids[i],
            BLECharacteristic::PROPERTY_READ | BLECharacteristic::PROPERTY_NOTIFY);
        _configAttributes[i]->addDescriptor(new BLE2902());
        _configAttributes[i]->setValue("{}");
    }

    // --- Notice channel ---------------------------------------------------
    // Device-to-app notices (errors / warnings). The app reacts to
    // notifications only; it does not read-and-replay on connect.
    _noticeChar = svc->createCharacteristic(
        BLE_NOTICE_UUID,
        BLECharacteristic::PROPERTY_READ |
        BLECharacteristic::PROPERTY_NOTIFY);
    _noticeChar->addDescriptor(new BLE2902());
    _noticeChar->setValue("{}");

    // --- Battery state channel --------------------------------------------
    // The app receives only the coarse state, never the noisy cell voltage.
    _batteryChar = svc->createCharacteristic(
        BLE_BATTERY_UUID,
        BLECharacteristic::PROPERTY_READ |
        BLECharacteristic::PROPERTY_NOTIFY);
    _batteryChar->addDescriptor(new BLE2902());
    uint8_t initialBatteryState = 0;
    _batteryChar->setValue(&initialBatteryState, 1);

    _chargerChar = svc->createCharacteristic(
        BLE_CHARGER_UUID,
        BLECharacteristic::PROPERTY_READ | BLECharacteristic::PROPERTY_NOTIFY);
    _chargerChar->addDescriptor(new BLE2902());
    updateChargerStatus(ChargerStatus::Snapshot{});

    svc->start();

    BLEAdvertising* adv = BLEDevice::getAdvertising();
    adv->addServiceUUID(BLE_SERVICE_UUID);
    adv->setScanResponse(true);
    adv->setMinPreferred(0x06);   // help iPhone connections (min connection interval hint)
    adv->setMaxPreferred(0x12);   // max connection interval hint
    adv->setMinInterval(0xA0);    // 100ms — coexistence headroom for Classic BT
    adv->setMaxInterval(0x190);   // 250ms
    BLEDevice::startAdvertising();

    Serial.printf("[BLE] Advertising as \"%s\" service=%s configCmd=%s configResp=%s\n",
                  deviceName.c_str(),
                  BLE_SERVICE_UUID,
                  BLE_CONFIG_COMMAND_UUID,
                  BLE_CONFIG_RESPONSE_UUID);
}

void BLEParentService::updateVolume(uint8_t volumePct) {
    if (!_volChar) return;
    if (volumePct > 100) volumePct = 100;
    _volChar->setValue(&volumePct, 1);
    if (_connected) _volChar->notify();
}

void BLEParentService::updateKillswitch(bool active) {
    if (!_killChar) return;
    uint8_t value = active ? 1 : 0;
    _killChar->setValue(&value, 1);
    if (_connected) _killChar->notify();
}

void BLEParentService::updateTheme(const String& theme) {
    if (!_themeChar) return;
    _themeChar->setValue(theme.c_str());
    if (_connected) _themeChar->notify();
}

void BLEParentService::updateStatus(const String& status) {
    if (!_statusChar) return;
    _statusChar->setValue(status.c_str());
    if (_connected) _statusChar->notify();
}

void BLEParentService::updateThemes(const String& themesJson) {
    if (!_themesChar) return;
    _themesChar->setValue(themesJson.c_str());
}

void BLEParentService::updateConfigResponse(const String& responseJson) {
    if (_configResponseChar) {
        _configResponseChar->setValue(responseJson.c_str());
        notifyChanged(_configResponseChar);
    }
}

void BLEParentService::notifyChanged(BLECharacteristic* characteristic) {
    if (!_connected || configGattsIf == ESP_GATT_IF_NONE) return;
    auto* descriptor = static_cast<BLE2902*>(characteristic->getDescriptorByUUID("2902"));
    if (!descriptor || !descriptor->getNotifications()) return;
    uint8_t changed = 1;
    // Keep the full readable value intact; a notification is an invalidation,
    // not JSON. The client serializes subsequent GATT reads, including blobs.
    const esp_err_t result = esp_ble_gatts_send_indicate(configGattsIf, _server->getConnId(),
        characteristic->getHandle(), sizeof(changed), &changed, false);
    if (result != ESP_OK) Serial.printf("[BLE] Config change notification failed: %d\n", result);
}

void BLEParentService::updateConfigAttribute(size_t index, const String& value) {
    if (index >= BLE_CONFIG_ATTRIBUTE_COUNT || !_configAttributes[index]) return;
    if (value.length() > BLE_CONFIG_MAX_BYTES) {
        Serial.printf("[BLE] Config attribute %u exceeds 512 bytes\n", unsigned(index));
        return;
    }
    auto* characteristic = _configAttributes[index];
    if (characteristic->getValue() == value.c_str()) return;
    characteristic->setValue(value.c_str());
    notifyChanged(characteristic);
}

void BLEParentService::updateBatteryState(uint8_t state) {
    if (!_batteryChar) return;
    if (state > 4) state = 0;
    _batteryChar->setValue(&state, 1);
    if (_connected) _batteryChar->notify();
}

void BLEParentService::updateNotice(const String& noticeJson) {
    if (!_noticeChar) return;
    _noticeChar->setValue(noticeJson.c_str());
    if (_connected) _noticeChar->notify();
}

void BLEParentService::updateChargerStatus(const ChargerStatus::Snapshot& snapshot) {
    if (!_chargerChar) return;
    uint8_t bytes[ChargerStatus::ENCODED_SIZE];
    ChargerStatus::encode(snapshot, bytes);
    if (_hasChargerValue && memcmp(bytes, _lastChargerValue, sizeof(bytes)) == 0) return;
    memcpy(_lastChargerValue, bytes, sizeof(bytes));
    _hasChargerValue = true;
    _chargerChar->setValue(bytes, sizeof(bytes));
    // The entire snapshot fits in the minimum ATT notification payload (20 B).
    if (_connected) _chargerChar->notify();
}

void BLEParentService::updateDeviceName(const String& deviceName) {
    esp_ble_gap_set_device_name(deviceName.c_str());
    if (_server) {
        BLEDevice::stopAdvertising();
        BLEDevice::startAdvertising();
    }
    Serial.printf("[BLE] Device name set to \"%s\"\n", deviceName.c_str());
}

bool BLEParentService::pollVolumeChange(uint8_t& out) {
    portENTER_CRITICAL(&_mux);
    bool hasValue = _newVolume;
    if (hasValue) {
        out = _pendingVolume;
        _newVolume = false;
    }
    portEXIT_CRITICAL(&_mux);
    if (!hasValue) return false;
    return true;
}

bool BLEParentService::pollKillswitch(bool& out) {
    portENTER_CRITICAL(&_mux);
    bool hasValue = _newKillswitch;
    if (hasValue) {
        out = _pendingKillswitch;
        _newKillswitch = false;
    }
    portEXIT_CRITICAL(&_mux);
    if (!hasValue) return false;
    return true;
}

bool BLEParentService::pollThemeChange(String& out) {
    char theme[sizeof(_pendingTheme)];
    portENTER_CRITICAL(&_mux);
    bool hasValue = _newTheme;
    if (hasValue) {
        memcpy(theme, _pendingTheme, sizeof(theme));
        _newTheme = false;
    }
    portEXIT_CRITICAL(&_mux);
    if (!hasValue) return false;
    theme[sizeof(theme) - 1] = '\0';
    out = String(theme);
    return true;
}

bool BLEParentService::pollCommand(uint8_t& out) {
    portENTER_CRITICAL(&_mux);
    bool hasValue = _newCommand;
    if (hasValue) {
        out = _pendingCommand;
        _newCommand = false;
    }
    portEXIT_CRITICAL(&_mux);
    if (!hasValue) return false;
    return true;
}

bool BLEParentService::pollConfigCommand(String& out) {
    char command[sizeof(_pendingConfigCommand)];
    portENTER_CRITICAL(&_mux);
    bool hasValue = _newConfigCommand;
    if (hasValue) {
        memcpy(command, _pendingConfigCommand, sizeof(command));
        _newConfigCommand = false;
    }
    portEXIT_CRITICAL(&_mux);
    if (!hasValue) return false;
    command[sizeof(command) - 1] = '\0';
    out = String(command);
    return true;
}

bool BLEParentService::isConnected() const {
    return _connected;
}

void BLEParentService::pollAdvertising() {
    if (_restartAdvPending) {
        _restartAdvPending = false;
        BLEDevice::startAdvertising();
    }
}

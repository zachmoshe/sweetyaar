#include "BLEParentService.h"

void BLEParentService::begin(const String& deviceName) {
    BLEDevice::init(deviceName.c_str());
    esp_err_t mtuResult = BLEDevice::setMTU(185);
    if (mtuResult != ESP_OK) {
        Serial.printf("[BLE] MTU request failed: %d\n", mtuResult);
    }

    _server = BLEDevice::createServer();
    _server->setCallbacks(new ServerCB(this));

    // Eight characteristics plus descriptors need more than the Arduino BLE
    // Arduino BLE default of 15 handles. Under-allocating here can boot fine
    // and then crash Bluedroid when a central connects.
    BLEService* svc = _server->createService(BLEUUID(BLE_SERVICE_UUID), 48);

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

    // --- Notice channel ---------------------------------------------------
    // Device-to-app notices (errors / warnings). The app reacts to
    // notifications only; it does not read-and-replay on connect.
    _noticeChar = svc->createCharacteristic(
        BLE_NOTICE_UUID,
        BLECharacteristic::PROPERTY_READ |
        BLECharacteristic::PROPERTY_NOTIFY);
    _noticeChar->addDescriptor(new BLE2902());
    _noticeChar->setValue("{}");

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
        if (_connected) _configResponseChar->notify();
    }
    // Legacy/cache-safe config transport: command writes JSON, themes read
    // returns the response. This keeps config usable when CoreBluetooth caches
    // the old six-characteristic GATT table and cannot see configResponse yet.
    if (_themesChar) {
        _themesChar->setValue(responseJson.c_str());
    }
}

void BLEParentService::updateNotice(const String& noticeJson) {
    if (!_noticeChar) return;
    _noticeChar->setValue(noticeJson.c_str());
    if (_connected) _noticeChar->notify();
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

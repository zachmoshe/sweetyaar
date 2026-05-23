#include "BLEParentService.h"

void BLEParentService::begin(const String& deviceName) {
    BLEDevice::init(deviceName.c_str());
    esp_err_t mtuResult = BLEDevice::setMTU(185);
    if (mtuResult != ESP_OK) {
        Serial.printf("[BLE] MTU request failed: %d\n", mtuResult);
    }

    _server = BLEDevice::createServer();
    _server->setCallbacks(new ServerCB(this));

    // Six characteristics plus four CCCD descriptors need more than the
    // Arduino BLE default of 15 handles. Under-allocating here can boot fine
    // and then crash Bluedroid when a central connects.
    BLEService* svc = _server->createService(BLEUUID(BLE_SERVICE_UUID), 24);

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

    svc->start();

    BLEAdvertising* adv = BLEDevice::getAdvertising();
    adv->addServiceUUID(BLE_SERVICE_UUID);
    adv->setScanResponse(true);
    adv->setMinPreferred(0x06);  // help iPhone connections
    adv->setMinPreferred(0x12);  // maintainer coex example uses both hints
    BLEDevice::startAdvertising();

    Serial.printf("[BLE] Advertising as \"%s\"\n", deviceName.c_str());
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

bool BLEParentService::isConnected() const {
    return _connected;
}

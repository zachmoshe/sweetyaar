#include "BLEParentService.h"
#include "BluetoothAccess.h"
#include <BLESecurity.h>

namespace {
esp_gatt_if_t configGattsIf = ESP_GATT_IF_NONE;
}
BLEParentService* BLEParentService::_instance = nullptr;

void BLEParentService::begin(const String& deviceName) {
    BLEDevice::init(deviceName.c_str());
    _instance = this;
    // Filter before Arduino's handlers: its custom hooks run AFTER values and
    // CCCDs have already been changed, which is too late for access control.
    _originalGap = esp_ble_gap_get_callback();
    _originalGatt = esp_ble_gatts_get_callback();
    esp_ble_gap_register_callback([](esp_gap_ble_cb_event_t event, esp_ble_gap_cb_param_t* param) {
        _instance->handleGap(event, param);
    });
    esp_ble_gatts_register_callback([](esp_gatts_cb_event_t event, esp_gatt_if_t interface,
                                       esp_ble_gatts_cb_param_t* param) {
        if (_instance->filterGatt(event, interface, param))
            _instance->_originalGatt(event, interface, param);
    });
    BLESecurity security;
    security.setAuthenticationMode(ESP_LE_AUTH_REQ_SC_BOND);
    security.setCapability(ESP_IO_CAP_NONE);
    security.setInitEncryptionKey(ESP_BLE_ENC_KEY_MASK | ESP_BLE_ID_KEY_MASK);
    security.setRespEncryptionKey(ESP_BLE_ENC_KEY_MASK | ESP_BLE_ID_KEY_MASK);
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

    // Seventeen characteristics plus descriptors need more than the Arduino BLE
    // default of 15 handles. Under-allocating here can boot fine
    // and then crash Bluedroid when a central connects.
    BLEService* svc = _server->createService(BLEUUID(BLE_SERVICE_UUID), 68);

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
        BLECharacteristic::PROPERTY_INDICATE);
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

    BLECharacteristic* secured[] = {_volChar, _killChar, _themeChar, _statusChar,
        _themesChar, _commandChar, _configCommandChar, _configResponseChar,
        _configAttributes[0], _configAttributes[1], _configAttributes[2],
        _configAttributes[3], _configAttributes[4], _noticeChar, _batteryChar, _chargerChar};
    for (size_t i = 0; i < 16; ++i) {
        _securedChars[i] = secured[i];
        const bool writable = i == 0 || i == 1 || i == 2 || i == 5 || i == 6;
        secured[i]->setAccessPermissions(static_cast<esp_gatt_perm_t>(
            (i == 5 ? 0 : ESP_GATT_PERM_READ_ENCRYPTED) |
            (writable ? ESP_GATT_PERM_WRITE_ENCRYPTED : 0)));
        auto* cccd = secured[i]->getDescriptorByUUID("2902");
        if (cccd) cccd->setAccessPermissions(ESP_GATT_PERM_READ_ENCRYPTED | ESP_GATT_PERM_WRITE_ENCRYPTED);
    }
    // The app reads this before encrypted controls so a refused connection can
    // explain why. filterGatt supplies a value specific to the requesting peer.
    _accessChar = svc->createCharacteristic(BLE_ACCESS_UUID, BLECharacteristic::PROPERTY_READ);
    _accessChar->setAccessPermissions(ESP_GATT_PERM_READ);
    uint8_t access = static_cast<uint8_t>(AccessState::Authenticating);
    _accessChar->setValue(&access, 1);
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
    notifyOwner(_volChar);
}

void BLEParentService::updateKillswitch(bool active) {
    if (!_killChar) return;
    uint8_t value = active ? 1 : 0;
    _killChar->setValue(&value, 1);
    notifyOwner(_killChar);
}

void BLEParentService::updateTheme(const String& theme) {
    if (!_themeChar) return;
    _themeChar->setValue(theme.c_str());
    notifyOwner(_themeChar);
}

void BLEParentService::updateStatus(const String& status) {
    if (!_statusChar) return;
    _statusChar->setValue(status.c_str());
    notifyOwner(_statusChar);
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
    notifyOwner(characteristic, true);
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
    notifyOwner(_batteryChar);
}

void BLEParentService::updateNotice(const String& noticeJson) {
    if (!_noticeChar) return;
    _noticeChar->setValue(noticeJson.c_str());
    notifyOwner(_noticeChar);
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
    notifyOwner(_chargerChar);
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
    bool hasValue = isConnected() && _newVolume;
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
    bool hasValue = isConnected() && _newKillswitch;
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
    bool hasValue = isConnected() && _newTheme;
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
    bool hasValue = isConnected() && _newCommand;
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
    bool hasValue = isConnected() && _newConfigCommand;
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
    return _ownerId != NO_CONNECTION;
}
bool BLEParentService::hasLinks() {
    portENTER_CRITICAL(&_mux);
    bool active = false;
    for (const auto& p : _peers) active |= p.id != NO_CONNECTION;
    portEXIT_CRITICAL(&_mux);
    return active;
}

// Security and ownership are checked before dispatching reads/writes to Arduino.
BLEParentService::Peer* BLEParentService::peer(uint16_t id) {
    for (auto& p : _peers) if (p.id == id && id != NO_CONNECTION) return &p;
    return nullptr;
}

BLEParentService::Peer* BLEParentService::peerByAddress(const uint8_t* address) {
    uint8_t identity[6];
    bool resolved = BluetoothAccess::bleIdentity(address, identity);
    for (auto& p : _peers) {
        if (p.id == NO_CONNECTION) continue;
        if (memcmp(p.address, address, 6) == 0) return &p;
        if (resolved) {
            uint8_t candidateIdentity[6];
            const bool matched = p.known ? (memcpy(candidateIdentity, p.identity, 6), true)
                : BluetoothAccess::bleIdentity(p.address, candidateIdentity);
            if (matched && memcmp(candidateIdentity, identity, 6) == 0) return &p;
        }
    }
    return nullptr;
}

void BLEParentService::clearPending() {
    _newVolume = _newKillswitch = _newTheme = _newCommand = _newConfigCommand = false;
    _preparedOwner = NO_CONNECTION;
    _preparedLength = 0;
}

BLEParentService::EarlySecurity* BLEParentService::earlySecurity(const uint8_t* address, bool create) {
    const uint32_t now = millis();
    uint8_t identity[6];
    const bool resolved = BluetoothAccess::bleIdentity(address, identity);
    for (auto& item : _earlySecurity) {
        EarlySecurity snapshot;
        portENTER_CRITICAL(&_mux);
        if (item.used && now - item.observedAt >= (item.hasAuth ? 5000u : 30000u)) item = EarlySecurity{};
        snapshot = item;
        portEXIT_CRITICAL(&_mux);
        if (!snapshot.used) continue;
        uint8_t otherIdentity[6];
        if (memcmp(snapshot.address, address, 6) == 0 ||
            (resolved && BluetoothAccess::bleIdentity(snapshot.address, otherIdentity) &&
             memcmp(identity, otherIdentity, 6) == 0)) return &item;
    }
    if (create) {
        portENTER_CRITICAL(&_mux);
        for (auto& item : _earlySecurity) {
            if (item.used) continue;
            item = EarlySecurity{};
            item.used = true;
            item.observedAt = now;
            memcpy(item.address, address, 6);
            portEXIT_CRITICAL(&_mux);
            return &item;
        }
        portEXIT_CRITICAL(&_mux);
    }
    return nullptr;
}

void BLEParentService::connected(esp_ble_gatts_cb_param_t* param) {
    const auto& connection = param->connect;
    bool known = bluetoothAccess.bleBonded(connection.remote_bda);
    uint8_t identity[6] = {};
    if (known) BluetoothAccess::bleIdentity(connection.remote_bda, identity);
    auto* early = earlySecurity(connection.remote_bda);
    EarlySecurity security;
    Peer* slot = nullptr;
    portENTER_CRITICAL(&_mux);
    for (auto& p : _peers) if (p.id == NO_CONNECTION) { slot = &p; break; }
    if (slot) {
        if (early && early->used) {
            security = *early;
            *early = EarlySecurity{};
        }
        *slot = Peer{};
        slot->id = connection.conn_id;
        memcpy(slot->address, connection.remote_bda, 6);
        memcpy(slot->identity, identity, 6);
        slot->known = known;
        slot->connectedAt = millis();
        slot->sequence = ++_connectionSequence;
        slot->newKeys = security.newKeys;
        slot->reject = !bluetoothAccess.ready() || security.keysOutsidePairing ||
            (!known && !bluetoothAccess.pairingOpen());
        slot->rejectedAt = slot->connectedAt;
        slot->rejectionReason = AccessState::PairingRequired;
    }
    _restartAdvPending = true; // keep a slot available for takeover
    portEXIT_CRITICAL(&_mux);
    Serial.printf("[BLE] t=%lu CONNECT conn=%u peer=%02X:%02X:%02X:%02X:%02X:%02X bonded=%d pairing=%s decision=%s\n",
        static_cast<unsigned long>(millis()), connection.conn_id,
        connection.remote_bda[0], connection.remote_bda[1], connection.remote_bda[2],
        connection.remote_bda[3], connection.remote_bda[4], connection.remote_bda[5],
        known, bluetoothAccess.pairingOpen() ? "open" : "closed",
        !slot ? "no-free-slot" : slot->reject ? "pairing-required" : "authenticate");
    if (!slot) {
        disconnectPeer(connection.conn_id);
        return;
    }
    if (security.hasAuth) {
        // Replay the already completed security result after the peer exists.
        // Starting encryption again on this encrypted link may emit no event.
        esp_ble_gap_cb_param_t result{};
        auto& auth = result.ble_security.auth_cmpl;
        memcpy(auth.bd_addr, security.address, 6);
        auth.success = security.success;
        auth.fail_reason = security.failReason;
        auth.auth_mode = static_cast<decltype(auth.auth_mode)>(security.authMode);
        handleGap(ESP_GAP_BLE_AUTH_CMPL_EVT, &result);
        return;
    }
    // The app reads one encrypted status attribute when access is pending.
    // Let that client operation initiate bonding/encryption: an additional
    // peripheral Security Request can cause duplicate Android pairing dialogs.
    // Encrypted permissions and AUTH_CMPL approval still gate every control.
}

void BLEParentService::disconnected(uint16_t connection, uint16_t reason) {
    portENTER_CRITICAL(&_mux);
    const bool wasOwner = _ownerId == connection;
    if (auto* p = peer(connection)) *p = Peer{};
    if (_ownerId == connection) {
        _ownerId = NO_CONNECTION;
        clearPending();
    }
    _restartAdvPending = true;
    portEXIT_CRITICAL(&_mux);
    Serial.printf("[BLE] t=%lu DISCONNECT conn=%u reason=0x%02X was_controller=%d\n",
        static_cast<unsigned long>(millis()), connection, reason, wasOwner);
}

void BLEParentService::disconnectPeer(uint16_t connection) {
    bool close = true;
    portENTER_CRITICAL(&_mux);
    if (auto* p = peer(connection)) {
        close = !p->disconnectRequested;
        p->disconnectRequested = true;
    }
    portEXIT_CRITICAL(&_mux);
    if (close) {
        Serial.printf("[BLE] t=%lu DISCONNECT_REQUEST conn=%u\n", static_cast<unsigned long>(millis()), connection);
        _server->disconnect(connection);
    }
}

const char* BLEParentService::accessStateName(AccessState state) {
    switch (state) {
        case AccessState::PairingRequired: return "pairing-required";
        case AccessState::Authenticating: return "authenticating";
        case AccessState::Ready: return "ready";
        case AccessState::TakenOver: return "taken-over";
        default: return "authentication-failed";
    }
}

void BLEParentService::handleGap(esp_gap_ble_cb_event_t event, esp_ble_gap_cb_param_t* param) {
    if (event == ESP_GAP_BLE_ADV_START_COMPLETE_EVT || event == ESP_GAP_BLE_ADV_STOP_COMPLETE_EVT) {
        const auto status = event == ESP_GAP_BLE_ADV_START_COMPLETE_EVT
            ? param->adv_start_cmpl.status : param->adv_stop_cmpl.status;
        if (status != ESP_BT_STATUS_SUCCESS) {
            Serial.printf("[BLE] ADVERTISING %s failed status=0x%02X\n",
                event == ESP_GAP_BLE_ADV_START_COMPLETE_EVT ? "start" : "stop", status);
        }
    }
    if (event == ESP_GAP_BLE_PASSKEY_NOTIF_EVT) {
        return; // Arduino's default handler logs the passcode
    }
    if (event == ESP_GAP_BLE_SEC_REQ_EVT) {
        auto* p = peerByAddress(param->ble_security.ble_req.bd_addr);
        // A peripheral receives this event for fresh pairing. Saved-key
        // encryption does not need this grant, even for an approved peer.
        portENTER_CRITICAL(&_mux);
        const bool allow = (!p || !p->reject) && bluetoothAccess.pairingOpen();
        const uint16_t connection = p ? p->id : NO_CONNECTION;
        portEXIT_CRITICAL(&_mux);
        const esp_err_t result = esp_ble_gap_security_rsp(param->ble_security.ble_req.bd_addr, allow);
        Serial.printf("[BLE] t=%lu SECURITY_REQUEST conn=%u decision=%s pairing=%s result=0x%X\n",
            static_cast<unsigned long>(millis()), connection, allow ? "allow" : "deny",
            bluetoothAccess.pairingOpen() ? "open" : "closed", unsigned(result));
        return; // prevent Arduino's unconditional positive security response
    }
    if (event == ESP_GAP_BLE_KEY_EVT) {
        auto* p = peerByAddress(param->ble_security.ble_key.bd_addr);
        if (p) {
            portENTER_CRITICAL(&_mux);
            p->newKeys = true;
            if (!bluetoothAccess.pairingOpen() && !p->reject) {
                p->reject = true;
                p->rejectedAt = millis();
                p->rejectionReason = AccessState::PairingRequired;
            }
            portEXIT_CRITICAL(&_mux);
        } else if (auto* early = earlySecurity(param->ble_security.ble_key.bd_addr, true)) {
            portENTER_CRITICAL(&_mux);
            early->newKeys = true;
            early->keysOutsidePairing |= !bluetoothAccess.pairingOpen();
            early->observedAt = millis();
            portEXIT_CRITICAL(&_mux);
        }
        return; // key material must never be logged
    }
    if (event == ESP_GAP_BLE_AUTH_CMPL_EVT) {
        auto& auth = param->ble_security.auth_cmpl;
        auto* p = peerByAddress(auth.bd_addr);
        if (!p) {
            auto* early = earlySecurity(auth.bd_addr, true);
            if (early) {
                portENTER_CRITICAL(&_mux);
                early->hasAuth = true;
                early->success = auth.success;
                early->failReason = auth.fail_reason;
                early->authMode = auth.auth_mode;
                early->observedAt = millis();
                portEXIT_CRITICAL(&_mux);
            }
            if (!early) Serial.println("[BLE] Authentication result dropped: no free connection slot");
            return; // Never delete an approved bond just because CONNECT is late.
        }
        Peer snapshot;
        portENTER_CRITICAL(&_mux);
        snapshot = *p;
        portEXIT_CRITICAL(&_mux);
        const bool pairing = bluetoothAccess.pairingOpen();
        const char* denial = !bluetoothAccess.ready() ? "bond-maintenance"
            : snapshot.reject ? accessStateName(snapshot.rejectionReason)
            : !auth.success ? "stack-authentication-failed"
            : !(auth.auth_mode & ESP_LE_AUTH_BOND) ? "bonding-not-negotiated"
            : (!pairing && (snapshot.newKeys || !snapshot.known)) ? "pairing-window-closed"
            : !bluetoothAccess.bleBonded(auth.bd_addr) ? "bond-not-saved" : nullptr;
        Serial.printf("[BLE] t=%lu AUTH conn=%u peer=%02X:%02X:%02X:%02X:%02X:%02X success=%d fail_reason=0x%02X mode=0x%02X bonded_before=%d new_keys=%d pairing=%s decision=%s\n",
            static_cast<unsigned long>(millis()), snapshot.id,
            auth.bd_addr[0], auth.bd_addr[1], auth.bd_addr[2], auth.bd_addr[3], auth.bd_addr[4], auth.bd_addr[5],
            auth.success, auth.success ? 0 : auth.fail_reason, auth.auth_mode,
            snapshot.known, snapshot.newKeys, pairing ? "open" : "closed", denial ? denial : "accept");
        if (denial) {
            portENTER_CRITICAL(&_mux);
            if (!p->reject) {
                p->reject = true;
                p->rejectedAt = millis();
                p->rejectionReason = !bluetoothAccess.pairingOpen() && (!snapshot.known || snapshot.newKeys)
                    ? AccessState::PairingRequired : AccessState::AuthenticationFailed;
            }
            portEXIT_CRITICAL(&_mux);
            if (auth.success && (!snapshot.known || snapshot.newKeys))
                esp_ble_remove_bond_device(auth.bd_addr);
            return;
        }
        uint16_t previousOwner, owner;
        portENTER_CRITICAL(&_mux);
        previousOwner = _ownerId;
        if (!p->reject && !p->authenticated) {
            auto* previous = peer(_ownerId);
            // Pairing completion can arrive out of order. An older attempt
            // must not steal control from a newer authenticated connection.
            const bool newest = !previous || int32_t(p->sequence - previous->sequence) > 0;
            auto* retired = newest ? previous : p;
            if (retired) {
                retired->retiring = true;
                retired->retiredAt = millis();
                retired->noticeSent = retired->noticeConfirmed = false;
            }
            p->authenticated = true;
            if (newest) {
                clearPending();
                _ownerId = p->id;
            }
        }
        owner = _ownerId;
        portEXIT_CRITICAL(&_mux);
        Serial.printf("[BLE] t=%lu CONTROL authenticated_conn=%u owner=%u previous=%u\n",
            static_cast<unsigned long>(millis()), snapshot.id, owner, previousOwner);
        return;
    }
    _originalGap(event, param);
}

int BLEParentService::characteristicIndex(uint16_t handle, bool descriptor) {
    for (int i = 0; i < 16; ++i) {
        if (!_securedChars[i]) continue;
        if (!descriptor && _securedChars[i]->getHandle() == handle) return i;
        auto* cccd = _securedChars[i]->getDescriptorByUUID("2902");
        if (descriptor && cccd && cccd->getHandle() == handle) return i;
    }
    return -1;
}

bool BLEParentService::filterGatt(esp_gatts_cb_event_t event, esp_gatt_if_t interface,
                                 esp_ble_gatts_cb_param_t* param) {
    if (event == ESP_GATTS_CONF_EVT && _noticeChar && param->conf.handle == _noticeChar->getHandle()) {
        portENTER_CRITICAL(&_mux);
        if (auto* p = peer(param->conf.conn_id)) p->noticeConfirmed = param->conf.status == ESP_GATT_OK;
        portEXIT_CRITICAL(&_mux);
    }
    uint16_t connection, transaction;
    bool response = true;
    if (event == ESP_GATTS_READ_EVT) {
        connection = param->read.conn_id; transaction = param->read.trans_id;
    } else if (event == ESP_GATTS_WRITE_EVT) {
        connection = param->write.conn_id; transaction = param->write.trans_id;
        response = param->write.need_rsp;
    } else if (event == ESP_GATTS_EXEC_WRITE_EVT) {
        connection = param->exec_write.conn_id; transaction = param->exec_write.trans_id;
    } else return true;

    auto* p = peer(connection);
    portENTER_CRITICAL(&_mux);
    const bool authenticated = p && p->authenticated;
    const bool allowed = bluetoothAccess.ready() && p && !p->reject && authenticated && connection == _ownerId;
    const auto access = !p ? AccessState::AuthenticationFailed
        : p->reject ? p->rejectionReason
        : authenticated ? (allowed ? AccessState::Ready : AccessState::TakenOver)
        : AccessState::Authenticating;
    const bool accessRead = event == ESP_GATTS_READ_EVT && _accessChar && param->read.handle == _accessChar->getHandle();
    portEXIT_CRITICAL(&_mux);
    if (accessRead) {
        esp_gatt_rsp_t reply{};
        reply.attr_value.handle = param->read.handle;
        reply.attr_value.offset = param->read.offset;
        reply.attr_value.len = param->read.offset == 0 ? 1 : 0;
        reply.attr_value.value[0] = static_cast<uint8_t>(access);
        esp_ble_gatts_send_response(interface, connection, transaction,
            param->read.offset <= 1 ? ESP_GATT_OK : ESP_GATT_INVALID_OFFSET, &reply);
        return false;
    }
    if (!allowed) {
        // Attribute encryption is enforced by Bluedroid before this callback.
        // Reaching here without an approved owner is an application-level
        // authorization failure, including the gap between encryption and
        // AUTH_CMPL. Returning INSUF_AUTHENTICATION in that gap makes Android
        // retry bonding and can display a second pairing request.
        if (response) esp_ble_gatts_send_response(interface, connection, transaction,
            ESP_GATT_INSUF_AUTHORIZATION, nullptr);
        return false;
    }
    if (event == ESP_GATTS_EXEC_WRITE_EVT) {
        const bool execute = param->exec_write.exec_write_flag == ESP_GATT_PREP_WRITE_EXEC;
        esp_gatt_status_t status = ESP_GATT_OK;
        if (execute && _preparedOwner == connection) {
            esp_ble_gatts_cb_param_t write{};
            write.write.conn_id = connection;
            write.write.handle = _preparedHandle;
            write.write.len = _preparedLength;
            write.write.value = _preparedValue;
            _originalGatt(ESP_GATTS_WRITE_EVT, interface, &write);
        } else if (execute) status = ESP_GATT_INVALID_OFFSET;
        _preparedOwner = NO_CONNECTION;
        _preparedLength = 0;
        esp_ble_gatts_send_response(interface, connection, transaction, status, nullptr);
        return false;
    }
    if (event == ESP_GATTS_WRITE_EVT) {
        const auto& write = param->write;
        const int index = characteristicIndex(write.handle, true);
        const int attribute = characteristicIndex(write.handle);
        const bool writable = attribute == 0 || attribute == 1 || attribute == 2 || attribute == 5 || attribute == 6;
        if (index < 0 && !writable) {
            if (response) esp_ble_gatts_send_response(interface, connection, transaction, ESP_GATT_WRITE_NOT_PERMIT, nullptr);
            return false;
        }
        if (write.is_prep) {
            // Arduino's prepared-value buffer is shared across connections.
            // Own it here so a takeover cannot commit the previous phone's data.
            esp_gatt_status_t status = ESP_GATT_OK;
            if (index >= 0 || characteristicIndex(write.handle) < 0) status = ESP_GATT_REQ_NOT_SUPPORTED;
            else if (write.offset + write.len > sizeof(_preparedValue)) status = ESP_GATT_INVALID_ATTR_LEN;
            else if (write.offset != 0 && (_preparedOwner != connection ||
                     _preparedHandle != write.handle || write.offset != _preparedLength)) status = ESP_GATT_INVALID_OFFSET;
            if (status == ESP_GATT_OK) {
                _preparedOwner = connection;
                _preparedHandle = write.handle;
                memcpy(_preparedValue + write.offset, write.value, write.len);
                _preparedLength = write.offset + write.len;
            }
            esp_gatt_rsp_t reply{};
            reply.attr_value.handle = write.handle;
            reply.attr_value.offset = write.offset;
            reply.attr_value.len = write.len;
            if (write.len <= sizeof(reply.attr_value.value)) memcpy(reply.attr_value.value, write.value, write.len);
            else status = ESP_GATT_INVALID_ATTR_LEN;
            if (response) esp_ble_gatts_send_response(interface, connection, transaction, status, &reply);
            return false;
        }
        if (index >= 0 && write.len == 2) {
            portENTER_CRITICAL(&_mux);
            if (write.value[0] & 3) p->subscriptions |= 1UL << index;
            else p->subscriptions &= ~(1UL << index);
            portEXIT_CRITICAL(&_mux);
        }
    }
    return true;
}

void BLEParentService::notifyOwner(BLECharacteristic* characteristic, bool invalidation) {
    if (!characteristic || configGattsIf == ESP_GATT_IF_NONE) return;
    const int index = characteristicIndex(characteristic->getHandle());
    uint16_t owner = NO_CONNECTION;
    portENTER_CRITICAL(&_mux);
    auto* p = peer(_ownerId);
    if (bluetoothAccess.ready() && p && !p->reject && p->authenticated && index >= 0 && (p->subscriptions & (1UL << index))) owner = p->id;
    portEXIT_CRITICAL(&_mux);
    if (owner == NO_CONNECTION) return;
    uint8_t changed = 1;
    std::string value;
    if (!invalidation) value = characteristic->getValue();
    esp_ble_gatts_send_indicate(configGattsIf, owner, characteristic->getHandle(),
        invalidation ? 1 : value.size(), invalidation ? &changed : reinterpret_cast<uint8_t*>(&value[0]),
        characteristic == _noticeChar);
}

void BLEParentService::disconnectAll() {
    uint16_t ids[3];
    portENTER_CRITICAL(&_mux);
    for (size_t i = 0; i < 3; ++i) { ids[i] = _peers[i].id; _peers[i].reject = true; }
    for (auto& early : _earlySecurity) early = EarlySecurity{};
    _ownerId = NO_CONNECTION;
    clearPending();
    portEXIT_CRITICAL(&_mux);
    for (auto id : ids) if (id != NO_CONNECTION) disconnectPeer(id);
}

void BLEParentService::pollAdvertising(bool canNotify) {
    const uint32_t now = millis();
    for (size_t i = 0; i < 3; ++i) {
        Peer snapshot;
        portENTER_CRITICAL(&_mux);
        snapshot = _peers[i];
        portEXIT_CRITICAL(&_mux);
        if (snapshot.id == NO_CONNECTION) continue;
        if (snapshot.reject) {
            if (now - snapshot.rejectedAt >= REJECTION_GRACE_MS) disconnectPeer(snapshot.id);
        } else if (!snapshot.authenticated &&
            (now - snapshot.connectedAt >= 30000 || (!snapshot.known && !bluetoothAccess.pairingOpen()))) {
            bool rejected = false;
            portENTER_CRITICAL(&_mux);
            if (_peers[i].id == snapshot.id && !_peers[i].authenticated && !_peers[i].reject) {
                _peers[i].reject = true;
                _peers[i].rejectedAt = now;
                _peers[i].rejectionReason = !snapshot.known && !bluetoothAccess.pairingOpen()
                    ? AccessState::PairingRequired : AccessState::AuthenticationFailed;
                rejected = true;
            }
            portEXIT_CRITICAL(&_mux);
            if (rejected) Serial.printf("[BLE] t=%lu AUTH_TIMEOUT conn=%u elapsed=%lu pairing=%s\n",
                static_cast<unsigned long>(now), snapshot.id,
                static_cast<unsigned long>(now - snapshot.connectedAt),
                bluetoothAccess.pairingOpen() ? "open" : "closed");
        } else if (snapshot.retiring && canNotify) {
            if (!snapshot.noticeSent) {
                // Fits even the default 23-byte ATT MTU. Indication confirmation
                // precedes disconnect; the bounded grace also covers old apps.
                uint8_t message[] = "{\"type\":\"takeover\"}";
                const bool subscribed = snapshot.subscriptions & (1UL << 13);
                const bool sent = !subscribed || esp_ble_gatts_send_indicate(configGattsIf, snapshot.id,
                    _noticeChar->getHandle(), sizeof(message) - 1, message, true) == ESP_OK;
                if (!sent && now - snapshot.retiredAt >= 1000) {
                    disconnectPeer(snapshot.id);
                    continue;
                }
                portENTER_CRITICAL(&_mux);
                if (_peers[i].id == snapshot.id) {
                    _peers[i].noticeSent = sent;
                    if (sent) _peers[i].retiredAt = now;
                }
                portEXIT_CRITICAL(&_mux);
            } else if ((snapshot.noticeConfirmed && now - snapshot.retiredAt >= 200) ||
                       now - snapshot.retiredAt >= 1000) {
                disconnectPeer(snapshot.id);
            }
        }
    }
    if (_restartAdvPending) {
        _restartAdvPending = false;
        BLEDevice::startAdvertising();
    }
}

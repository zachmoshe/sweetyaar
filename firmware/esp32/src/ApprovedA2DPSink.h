#pragma once
#include "LowLatencyA2DPSinkQueued.h"
#include "BluetoothAccess.h"
#include "ClassicBluetooth.h"

class ApprovedA2DPSink : public LowLatencyA2DPSinkQueued {
public:
    using LowLatencyA2DPSinkQueued::LowLatencyA2DPSinkQueued;
    void refreshAccess() { set_scan_mode_connectable(!is_connected()); }
    void revokeSession() {
        _sessionApproved = false;
        set_i2s_active(false);
        // The library's disconnect() uses its auto-reconnect address, which
        // is not recorded when auto-reconnect is disabled. Close the live peer.
        if (is_connected()) esp_a2d_sink_disconnect(*get_current_peer_address());
        ClassicBluetooth::disconnectAll();
        refreshAccess();
    }
protected:
    void set_scan_mode_connectable(bool connectable) override {
        // Also applies to the library's automatic startup/disconnect paths.
        ClassicBluetooth::setAccess(connectable);
    }
    void set_discoverability(esp_bt_discovery_mode_t) override {
        refreshAccess(); // callers cannot accidentally reopen enrollment
    }
    void app_gap_callback(esp_bt_gap_cb_event_t event, esp_bt_gap_cb_param_t* param) override {
        if (event == ESP_BT_GAP_ACL_CONN_CMPL_STAT_EVT) {
            ClassicBluetooth::connected(param->acl_conn_cmpl_stat.bda,
                param->acl_conn_cmpl_stat.stat == ESP_BT_STATUS_HCI_SUCCESS);
            logPeer("ACL_CONNECT", param->acl_conn_cmpl_stat.bda, param->acl_conn_cmpl_stat.stat, "received");
        } else if (event == ESP_BT_GAP_ACL_DISCONN_CMPL_STAT_EVT) {
            ClassicBluetooth::disconnected(param->acl_disconn_cmpl_stat.bda);
            logPeer("ACL_DISCONNECT", param->acl_disconn_cmpl_stat.bda, param->acl_disconn_cmpl_stat.reason, "received");
        }
        if (event == ESP_BT_GAP_CFM_REQ_EVT) {
            const bool allow = bluetoothAccess.pairingOpen();
            const auto result = esp_bt_gap_ssp_confirm_reply(param->cfm_req.bda, allow);
            logPeer("PAIRING_REQUEST", param->cfm_req.bda, result, allow ? "allow" : "deny-window-closed");
            return;
        }
        if (event == ESP_BT_GAP_PIN_REQ_EVT) {
            esp_bt_pin_code_t pin = {};
            const auto result = esp_bt_gap_pin_reply(param->pin_req.bda, false, 0, pin);
            logPeer("LEGACY_PIN_REQUEST", param->pin_req.bda, result, "deny-unsupported");
            return;
        }
        if (event == ESP_BT_GAP_KEY_REQ_EVT) {
            const auto result = esp_bt_gap_ssp_passkey_reply(param->key_req.bda, false, 0);
            logPeer("PASSKEY_REQUEST", param->key_req.bda, result, "deny-unsupported");
            return;
        }
        if (event == ESP_BT_GAP_KEY_NOTIF_EVT) {
            return; // suppress the library's passcode log
        }
        if (event == ESP_BT_GAP_AUTH_CMPL_EVT) {
            const bool success = param->auth_cmpl.stat == ESP_BT_STATUS_SUCCESS;
            const bool allowed = ClassicBluetooth::authenticated(param->auth_cmpl.bda, success);
            logPeer("AUTH_COMPLETE", param->auth_cmpl.bda, param->auth_cmpl.stat,
                !success ? "stack-authentication-failed" : allowed ? "accept" : "bond-not-authorized");
            if (success && !allowed) {
                esp_bt_gap_remove_bond_device(param->auth_cmpl.bda);
                esp_a2d_sink_disconnect(param->auth_cmpl.bda);
            }
            return;
        }
        LowLatencyA2DPSinkQueued::app_gap_callback(event, param);
    }
    void handle_connection_state(uint16_t event, void* data) override {
        auto* param = static_cast<esp_a2d_cb_param_t*>(data);
        const char* state = "unknown";
        switch (param->conn_stat.state) {
            case ESP_A2D_CONNECTION_STATE_CONNECTING: state = "connecting"; break;
            case ESP_A2D_CONNECTION_STATE_CONNECTED: state = "connected"; break;
            case ESP_A2D_CONNECTION_STATE_DISCONNECTING: state = "disconnecting"; break;
            case ESP_A2D_CONNECTION_STATE_DISCONNECTED: state = "disconnected"; break;
        }
        logPeer("A2DP_CONNECTION", param->conn_stat.remote_bda,
            param->conn_stat.state == ESP_A2D_CONNECTION_STATE_DISCONNECTED ? param->conn_stat.disc_rsn : 0, state);
        if (param->conn_stat.state == ESP_A2D_CONNECTION_STATE_CONNECTED) {
            _sessionApproved = ClassicBluetooth::canUseAudio(param->conn_stat.remote_bda);
            if (!_sessionApproved) {
                logPeer("A2DP_REJECT", param->conn_stat.remote_bda, 0, "device-not-approved");
                esp_a2d_sink_disconnect(param->conn_stat.remote_bda);
                return; // do not start audio or report an authorized connection
            }
        } else if (param->conn_stat.state == ESP_A2D_CONNECTION_STATE_DISCONNECTED) {
            _sessionApproved = false;
        }
        LowLatencyA2DPSinkQueued::handle_connection_state(event, data);
        if (param->conn_stat.state == ESP_A2D_CONNECTION_STATE_CONNECTED &&
            !ClassicBluetooth::canUseAudio(param->conn_stat.remote_bda)) {
            // A physical reset can race the queued connection callback.
            revokeSession();
        }
    }
    void handle_audio_state(uint16_t event, void* data) override {
        if (_sessionApproved) LowLatencyA2DPSinkQueued::handle_audio_state(event, data);
    }
    size_t write_audio(const uint8_t* data, size_t size) override {
        return _sessionApproved ? LowLatencyA2DPSinkQueued::write_audio(data, size) : 0;
    }
private:
    static void logPeer(const char* event, const uint8_t* address, int code, const char* decision) {
        Serial.printf("[BT] t=%lu %s peer=%02X:%02X:%02X:%02X:%02X:%02X code=0x%02X pairing=%s decision=%s\n",
            static_cast<unsigned long>(millis()), event,
            address[0], address[1], address[2], address[3], address[4], address[5], unsigned(code),
            bluetoothAccess.pairingOpen() ? "open" : "closed", decision);
    }
    std::atomic<bool> _sessionApproved{false};
};

#pragma once

#include "Config.h"
#include "LowLatencyA2DPSinkQueued.h"

#if SWEETYAAR_BT_DEBUG

class DebugA2DPSinkQueued : public LowLatencyA2DPSinkQueued {
public:
    using LowLatencyA2DPSinkQueued::LowLatencyA2DPSinkQueued;

protected:
    void app_gap_callback(esp_bt_gap_cb_event_t event,
                          esp_bt_gap_cb_param_t* param) override {
        logGapEvent(event, param);
        BluetoothA2DPSinkQueued::app_gap_callback(event, param);
    }

    void app_a2d_callback(esp_a2d_cb_event_t event,
                          esp_a2d_cb_param_t* param) override {
        logA2dEvent(event, param);
        BluetoothA2DPSinkQueued::app_a2d_callback(event, param);
    }

    void app_rc_ct_callback(esp_avrc_ct_cb_event_t event,
                            esp_avrc_ct_cb_param_t* param) override {
        logAvrcCtEvent(event, param);
        BluetoothA2DPSinkQueued::app_rc_ct_callback(event, param);
    }

    void app_rc_tg_callback(esp_avrc_tg_cb_event_t event,
                            esp_avrc_tg_cb_param_t* param) override {
        logAvrcTgEvent(event, param);
        BluetoothA2DPSinkQueued::app_rc_tg_callback(event, param);
    }

    void av_hdl_stack_evt(uint16_t event, void* pParam) override {
        Serial.printf("[BTDBG] STACK event=%s(%u) free=%u largest=%u\n",
                      stackEventName(event), event,
                      heap_caps_get_free_size(MALLOC_CAP_8BIT),
                      heap_caps_get_largest_free_block(MALLOC_CAP_8BIT));
        BluetoothA2DPSinkQueued::av_hdl_stack_evt(event, pParam);
        Serial.printf("[BTDBG] STACK handled event=%s(%u) conn=%d audio=%d free=%u largest=%u\n",
                      stackEventName(event), event,
                      static_cast<int>(get_connection_state()),
                      static_cast<int>(get_audio_state()),
                      heap_caps_get_free_size(MALLOC_CAP_8BIT),
                      heap_caps_get_largest_free_block(MALLOC_CAP_8BIT));
    }

    void handle_connection_state(uint16_t event, void* pParam) override {
        logA2dHandlerEvent(event, static_cast<esp_a2d_cb_param_t*>(pParam));
        BluetoothA2DPSinkQueued::handle_connection_state(event, pParam);
    }

private:
    static const char* stackEventName(uint16_t event) {
        switch (event) {
            case BT_APP_EVT_STACK_UP: return "BT_APP_EVT_STACK_UP";
            default: return "UNKNOWN";
        }
    }

    static const char* gapEventName(esp_bt_gap_cb_event_t event) {
        switch (event) {
            case ESP_BT_GAP_DISC_RES_EVT: return "DISC_RES";
            case ESP_BT_GAP_DISC_STATE_CHANGED_EVT: return "DISC_STATE_CHANGED";
            case ESP_BT_GAP_RMT_SRVCS_EVT: return "RMT_SRVCS";
            case ESP_BT_GAP_RMT_SRVC_REC_EVT: return "RMT_SRVC_REC";
            case ESP_BT_GAP_AUTH_CMPL_EVT: return "AUTH_CMPL";
            case ESP_BT_GAP_PIN_REQ_EVT: return "PIN_REQ";
            case ESP_BT_GAP_CFM_REQ_EVT: return "CFM_REQ";
            case ESP_BT_GAP_KEY_NOTIF_EVT: return "KEY_NOTIF";
            case ESP_BT_GAP_KEY_REQ_EVT: return "KEY_REQ";
            case ESP_BT_GAP_READ_RSSI_DELTA_EVT: return "READ_RSSI_DELTA";
            case ESP_BT_GAP_CONFIG_EIR_DATA_EVT: return "CONFIG_EIR_DATA";
            case ESP_BT_GAP_SET_AFH_CHANNELS_EVT: return "SET_AFH_CHANNELS";
#if ESP_IDF_VERSION >= ESP_IDF_VERSION_VAL(4, 0, 0)
            case ESP_BT_GAP_READ_REMOTE_NAME_EVT: return "READ_REMOTE_NAME";
            case ESP_BT_GAP_MODE_CHG_EVT: return "MODE_CHG";
#endif
            case ESP_BT_GAP_REMOVE_BOND_DEV_COMPLETE_EVT: return "REMOVE_BOND_DEV_COMPLETE";
            case ESP_BT_GAP_QOS_CMPL_EVT: return "QOS_CMPL";
            case ESP_BT_GAP_ACL_CONN_CMPL_STAT_EVT: return "ACL_CONN_CMPL_STAT";
            case ESP_BT_GAP_ACL_DISCONN_CMPL_STAT_EVT: return "ACL_DISCONN_CMPL_STAT";
            default: return "UNKNOWN";
        }
    }

    static const char* a2dEventName(esp_a2d_cb_event_t event) {
        switch (event) {
            case ESP_A2D_CONNECTION_STATE_EVT: return "CONNECTION_STATE";
            case ESP_A2D_AUDIO_STATE_EVT: return "AUDIO_STATE";
            case ESP_A2D_AUDIO_CFG_EVT: return "AUDIO_CFG";
#if ESP_IDF_VERSION >= ESP_IDF_VERSION_VAL(4, 0, 0)
            case ESP_A2D_PROF_STATE_EVT: return "PROF_STATE";
#endif
            default: return "UNKNOWN";
        }
    }

    static const char* avrcCtEventName(esp_avrc_ct_cb_event_t event) {
        switch (event) {
            case ESP_AVRC_CT_CONNECTION_STATE_EVT: return "CONNECTION_STATE";
            case ESP_AVRC_CT_PASSTHROUGH_RSP_EVT: return "PASSTHROUGH_RSP";
            case ESP_AVRC_CT_METADATA_RSP_EVT: return "METADATA_RSP";
            case ESP_AVRC_CT_CHANGE_NOTIFY_EVT: return "CHANGE_NOTIFY";
            case ESP_AVRC_CT_REMOTE_FEATURES_EVT: return "REMOTE_FEATURES";
#if ESP_IDF_VERSION >= ESP_IDF_VERSION_VAL(4, 0, 0)
            case ESP_AVRC_CT_GET_RN_CAPABILITIES_RSP_EVT: return "GET_RN_CAPABILITIES_RSP";
#endif
            default: return "UNKNOWN";
        }
    }

    static const char* avrcTgEventName(esp_avrc_tg_cb_event_t event) {
        switch (event) {
            case ESP_AVRC_TG_CONNECTION_STATE_EVT: return "CONNECTION_STATE";
            case ESP_AVRC_TG_REMOTE_FEATURES_EVT: return "REMOTE_FEATURES";
            case ESP_AVRC_TG_PASSTHROUGH_CMD_EVT: return "PASSTHROUGH_CMD";
            case ESP_AVRC_TG_SET_ABSOLUTE_VOLUME_CMD_EVT: return "SET_ABSOLUTE_VOLUME";
            case ESP_AVRC_TG_REGISTER_NOTIFICATION_EVT: return "REGISTER_NOTIFICATION";
            default: return "UNKNOWN";
        }
    }

    static void formatBda(const uint8_t* bda, char* out, size_t outSize) {
        if (!bda || outSize < 18) {
            if (outSize > 0) out[0] = '\0';
            return;
        }
        snprintf(out, outSize, "%02X:%02X:%02X:%02X:%02X:%02X",
                 bda[0], bda[1], bda[2], bda[3], bda[4], bda[5]);
    }

    void logGapEvent(esp_bt_gap_cb_event_t event, esp_bt_gap_cb_param_t* param) {
        char bda[18] = "";
        Serial.printf("[BTDBG] GAP event=%s(%d)", gapEventName(event), static_cast<int>(event));
        if (param) {
            switch (event) {
                case ESP_BT_GAP_AUTH_CMPL_EVT:
                    formatBda(param->auth_cmpl.bda, bda, sizeof(bda));
                    Serial.printf(" status=%d bda=%s name=\"%s\"",
                                  static_cast<int>(param->auth_cmpl.stat),
                                  bda, param->auth_cmpl.device_name);
                    break;
                case ESP_BT_GAP_PIN_REQ_EVT:
                    formatBda(param->pin_req.bda, bda, sizeof(bda));
                    Serial.printf(" bda=%s min16=%d", bda, param->pin_req.min_16_digit);
                    break;
                case ESP_BT_GAP_CFM_REQ_EVT:
                    formatBda(param->cfm_req.bda, bda, sizeof(bda));
                    Serial.printf(" bda=%s passkey=%lu", bda,
                                  static_cast<unsigned long>(param->cfm_req.num_val));
                    break;
                case ESP_BT_GAP_KEY_NOTIF_EVT:
                    formatBda(param->key_notif.bda, bda, sizeof(bda));
                    Serial.printf(" bda=%s passkey=%lu", bda,
                                  static_cast<unsigned long>(param->key_notif.passkey));
                    break;
                case ESP_BT_GAP_KEY_REQ_EVT:
                    formatBda(param->key_req.bda, bda, sizeof(bda));
                    Serial.printf(" bda=%s", bda);
                    break;
                case ESP_BT_GAP_READ_RSSI_DELTA_EVT:
                    formatBda(param->read_rssi_delta.bda, bda, sizeof(bda));
                    Serial.printf(" status=%d bda=%s rssi_delta=%d",
                                  static_cast<int>(param->read_rssi_delta.stat),
                                  bda,
                                  static_cast<int>(param->read_rssi_delta.rssi_delta));
                    break;
                case ESP_BT_GAP_CONFIG_EIR_DATA_EVT:
                    Serial.printf(" status=%d eir_types=%u",
                                  static_cast<int>(param->config_eir_data.stat),
                                  static_cast<unsigned>(param->config_eir_data.eir_type_num));
                    break;
                case ESP_BT_GAP_SET_AFH_CHANNELS_EVT:
                    Serial.printf(" status=%d",
                                  static_cast<int>(param->set_afh_channels.stat));
                    break;
#if ESP_IDF_VERSION >= ESP_IDF_VERSION_VAL(4, 0, 0)
                case ESP_BT_GAP_READ_REMOTE_NAME_EVT:
                    formatBda(param->read_rmt_name.bda, bda, sizeof(bda));
                    Serial.printf(" status=%d bda=%s name=\"%s\"",
                                  static_cast<int>(param->read_rmt_name.stat),
                                  bda, param->read_rmt_name.rmt_name);
                    break;
                case ESP_BT_GAP_MODE_CHG_EVT:
                    formatBda(param->mode_chg.bda, bda, sizeof(bda));
                    Serial.printf(" bda=%s mode=%d", bda, static_cast<int>(param->mode_chg.mode));
                    break;
#endif
                case ESP_BT_GAP_REMOVE_BOND_DEV_COMPLETE_EVT:
                    formatBda(param->remove_bond_dev_cmpl.bda, bda, sizeof(bda));
                    Serial.printf(" status=%d bda=%s",
                                  static_cast<int>(param->remove_bond_dev_cmpl.status),
                                  bda);
                    break;
                case ESP_BT_GAP_QOS_CMPL_EVT:
                    formatBda(param->qos_cmpl.bda, bda, sizeof(bda));
                    Serial.printf(" status=%d bda=%s t_poll=%lu",
                                  static_cast<int>(param->qos_cmpl.stat),
                                  bda,
                                  static_cast<unsigned long>(param->qos_cmpl.t_poll));
                    break;
                case ESP_BT_GAP_ACL_CONN_CMPL_STAT_EVT:
                    formatBda(param->acl_conn_cmpl_stat.bda, bda, sizeof(bda));
                    Serial.printf(" status=%d handle=%u bda=%s",
                                  static_cast<int>(param->acl_conn_cmpl_stat.stat),
                                  static_cast<unsigned>(param->acl_conn_cmpl_stat.handle),
                                  bda);
                    break;
                case ESP_BT_GAP_ACL_DISCONN_CMPL_STAT_EVT:
                    formatBda(param->acl_disconn_cmpl_stat.bda, bda, sizeof(bda));
                    Serial.printf(" reason=%d handle=%u bda=%s",
                                  static_cast<int>(param->acl_disconn_cmpl_stat.reason),
                                  static_cast<unsigned>(param->acl_disconn_cmpl_stat.handle),
                                  bda);
                    break;
                default:
                    break;
            }
        }
        Serial.printf(" free=%u largest=%u\n",
                      heap_caps_get_free_size(MALLOC_CAP_8BIT),
                      heap_caps_get_largest_free_block(MALLOC_CAP_8BIT));
    }

    void logA2dEvent(esp_a2d_cb_event_t event, esp_a2d_cb_param_t* param) {
        char bda[18] = "";
        Serial.printf("[BTDBG] A2DP cb event=%s(%d)", a2dEventName(event), static_cast<int>(event));
        if (param) {
            switch (event) {
                case ESP_A2D_CONNECTION_STATE_EVT:
                    formatBda(param->conn_stat.remote_bda, bda, sizeof(bda));
                    Serial.printf(" state=%d reason=%d bda=%s",
                                  static_cast<int>(param->conn_stat.state),
                                  static_cast<int>(param->conn_stat.disc_rsn),
                                  bda);
                    break;
                case ESP_A2D_AUDIO_STATE_EVT:
                    Serial.printf(" state=%d", static_cast<int>(param->audio_stat.state));
                    break;
                case ESP_A2D_AUDIO_CFG_EVT:
#if ESP_IDF_VERSION >= ESP_IDF_VERSION_VAL(5, 5, 0)
                    Serial.printf(" codec=%d sf=0x%02X ch=0x%02X block=0x%02X alloc=0x%02X",
                                  static_cast<int>(param->audio_cfg.mcc.type),
                                  param->audio_cfg.mcc.cie.sbc_info.samp_freq,
                                  param->audio_cfg.mcc.cie.sbc_info.ch_mode,
                                  param->audio_cfg.mcc.cie.sbc_info.block_len,
                                  param->audio_cfg.mcc.cie.sbc_info.alloc_mthd);
#else
                    Serial.printf(" codec=%d sbc=%02X %02X %02X %02X",
                                  static_cast<int>(param->audio_cfg.mcc.type),
                                  param->audio_cfg.mcc.cie.sbc[0],
                                  param->audio_cfg.mcc.cie.sbc[1],
                                  param->audio_cfg.mcc.cie.sbc[2],
                                  param->audio_cfg.mcc.cie.sbc[3]);
#endif
                    break;
                default:
                    break;
            }
        }
        Serial.printf(" free=%u largest=%u\n",
                      heap_caps_get_free_size(MALLOC_CAP_8BIT),
                      heap_caps_get_largest_free_block(MALLOC_CAP_8BIT));
    }

    void logA2dHandlerEvent(uint16_t event, esp_a2d_cb_param_t* param) {
        char bda[18] = "";
        Serial.printf("[BTDBG] A2DP handler event=%s(%u)", a2dEventName(static_cast<esp_a2d_cb_event_t>(event)), event);
        if (param && event == ESP_A2D_CONNECTION_STATE_EVT) {
            formatBda(param->conn_stat.remote_bda, bda, sizeof(bda));
            Serial.printf(" state=%d reason=%d bda=%s",
                          static_cast<int>(param->conn_stat.state),
                          static_cast<int>(param->conn_stat.disc_rsn),
                          bda);
        }
        Serial.println();
    }

    void logAvrcCtEvent(esp_avrc_ct_cb_event_t event, esp_avrc_ct_cb_param_t* param) {
        char bda[18] = "";
        Serial.printf("[BTDBG] AVRCP-CT cb event=%s(%d)", avrcCtEventName(event), static_cast<int>(event));
        if (param && event == ESP_AVRC_CT_CONNECTION_STATE_EVT) {
            formatBda(param->conn_stat.remote_bda, bda, sizeof(bda));
            Serial.printf(" connected=%d bda=%s", param->conn_stat.connected, bda);
        }
        Serial.println();
    }

    void logAvrcTgEvent(esp_avrc_tg_cb_event_t event, esp_avrc_tg_cb_param_t* param) {
        char bda[18] = "";
        Serial.printf("[BTDBG] AVRCP-TG cb event=%s(%d)", avrcTgEventName(event), static_cast<int>(event));
        if (param && event == ESP_AVRC_TG_CONNECTION_STATE_EVT) {
            formatBda(param->conn_stat.remote_bda, bda, sizeof(bda));
            Serial.printf(" connected=%d bda=%s", param->conn_stat.connected, bda);
        }
        Serial.println();
    }
};

#endif  // SWEETYAAR_BT_DEBUG

#include <Arduino.h>
#include <esp_heap_caps.h>

#include "AudioTools.h"
#include "Config.h"
#include "LowLatencyA2DPSinkQueued.h"

I2SStream i2s;
static bool btConnected = false;
static bool reopenPairing = false;
static bool reopenCooldownStarted = false;
static uint32_t reopenAtMs = 0;
static const uint32_t BT_REOPEN_DELAY_MS = 1500;

static const char* sampleRateName(uint8_t oct0);
static const char* channelModeName(uint8_t oct1);

static void setAmpMuted(bool muted) {
    bool driveHigh = muted ? AMP_MUTE_ACTIVE_HIGH : !AMP_MUTE_ACTIVE_HIGH;
    digitalWrite(PIN_AMP_MUTE, driveHigh ? HIGH : LOW);
}

class DiagnosticA2DPSinkQueued : public LowLatencyA2DPSinkQueued {
public:
    using LowLatencyA2DPSinkQueued::LowLatencyA2DPSinkQueued;

protected:
    void handle_audio_cfg(uint16_t event, void* pParam) override {
        auto* a2d = static_cast<esp_a2d_cb_param_t*>(pParam);
        uint8_t oct0 = a2d->audio_cfg.mcc.cie.sbc[0];
        uint8_t oct1 = a2d->audio_cfg.mcc.cie.sbc[1];
        uint8_t oct2 = a2d->audio_cfg.mcc.cie.sbc[2];
        uint8_t oct3 = a2d->audio_cfg.mcc.cie.sbc[3];
        Serial.printf("[BTTEST] SBC cfg type=%d raw=%02X %02X %02X %02X sf=%s ch=%s\n",
                      static_cast<int>(a2d->audio_cfg.mcc.type), oct0, oct1, oct2, oct3,
                      sampleRateName(oct0), channelModeName(oct1));

        BluetoothA2DPSinkQueued::handle_audio_cfg(event, pParam);
    }
};

DiagnosticA2DPSinkQueued a2dp(i2s);

static const char* sampleRateName(uint8_t oct0) {
    if (oct0 & (0x01 << 6)) {
        return "32000";
    }
    if (oct0 & (0x01 << 5)) {
        return "44100";
    }
    if (oct0 & (0x01 << 4)) {
        return "48000";
    }
    return "unknown";
}

static const char* channelModeName(uint8_t oct1) {
    if (oct1 & 0x08) {
        return "mono";
    }
    if (oct1 & 0x04) {
        return "dual";
    }
    if (oct1 & 0x02) {
        return "stereo";
    }
    if (oct1 & 0x01) {
        return "joint";
    }
    return "unknown";
}

static const char* audioStateName(esp_a2d_audio_state_t state) {
    switch (state) {
        case ESP_A2D_AUDIO_STATE_STARTED:
            return "STARTED";
        case ESP_A2D_AUDIO_STATE_STOPPED:
            return "STOPPED";
        case ESP_A2D_AUDIO_STATE_REMOTE_SUSPEND:
            return "REMOTE_SUSPEND";
        default:
            return "UNKNOWN";
    }
}

static void connectionStateChanged(esp_a2d_connection_state_t state, void*) {
    if (state == ESP_A2D_CONNECTION_STATE_CONNECTED) {
        btConnected = true;
        Serial.println("[BTTEST] Connected");
        setAmpMuted(false);
    } else if (state == ESP_A2D_CONNECTION_STATE_DISCONNECTED) {
        btConnected = false;
        reopenPairing = true;
        Serial.println("[BTTEST] Disconnected");
        setAmpMuted(true);
    }
}

static void audioStateChanged(esp_a2d_audio_state_t state, void*) {
    Serial.printf("[BTTEST] Audio state: %s\n", audioStateName(state));
}

static void sampleRateChanged(uint16_t rate) {
    Serial.printf("[BTTEST] A2DP sample rate: %u Hz\n", rate);
}

static void peerNameChanged(char* peerName) {
    Serial.printf("[BTTEST] Peer name: %s\n", peerName);
}

static void rssiChanged(esp_bt_gap_cb_param_t::read_rssi_delta_param& rssi) {
    Serial.printf("[BTTEST] RSSI delta: %d status=%d\n", rssi.rssi_delta, rssi.stat);
}

void setup() {
    Serial.begin(115200);
    delay(800);

    Serial.println("\n=== SweetYaar BT Diagnostic ===");
    Serial.println("[BTTEST] Minimal A2DP -> I2SStream path, no SD/BLE/app logic");
    Serial.println("[BTTEST] Using low-latency queued sink with no fixed I2S drain delay");
    Serial.printf("[BTTEST] Pins: BCLK=%d LRC/WS=%d DIN=%d MUTE_CTL=%d\n",
                  HW_I2S_BCLK, HW_I2S_WS, HW_I2S_DOUT, PIN_AMP_MUTE);

    pinMode(PIN_AMP_MUTE, OUTPUT);
    setAmpMuted(true);

    auto cfg = i2s.defaultConfig(TX_MODE);
    cfg.sample_rate = SAMPLE_RATE;
    cfg.channels = CHANNELS;
    cfg.bits_per_sample = BITS_PER_SAMPLE;
    cfg.i2s_format = I2S_STD_FORMAT;
    cfg.pin_bck = HW_I2S_BCLK;
    cfg.pin_ws = HW_I2S_WS;
    cfg.pin_data = HW_I2S_DOUT;
    cfg.buffer_count = 12;
    cfg.buffer_size = 512;
    i2s.begin(cfg);

    a2dp.set_i2s_ringbuffer_size(32 * 1024);
    a2dp.set_i2s_ringbuffer_prefetch_percent(65);
    a2dp.set_i2s_write_size_upto(4096);
    a2dp.set_i2s_stack_size(4096);
    a2dp.set_on_connection_state_changed(connectionStateChanged);
    a2dp.set_on_audio_state_changed(audioStateChanged);
    a2dp.set_sample_rate_callback(sampleRateChanged);
    a2dp.set_peer_name_callback(peerNameChanged);
    a2dp.set_rssi_callback(rssiChanged);
    a2dp.set_rssi_active(true);
    a2dp.set_auto_reconnect(false, 0);
    a2dp.start("SweetYaar-BTTest");
    a2dp.set_auto_reconnect(false, 0);

    Serial.println("[BTTEST] Pair/connect to SweetYaar-BTTest");
}

void loop() {
    static uint32_t lastRssiMs = 0;
    static uint32_t lastStatsMs = 0;
    if (btConnected && millis() - lastRssiMs >= 3000) {
        lastRssiMs = millis();
        a2dp.update_rssi();
    }
    if (btConnected && millis() - lastStatsMs >= 3000) {
        lastStatsMs = millis();
        a2dp.printStats("BTTEST");
    }
    if (reopenPairing && !btConnected) {
        if (!reopenCooldownStarted) {
            reopenCooldownStarted = true;
            reopenAtMs = millis() + BT_REOPEN_DELAY_MS;
            a2dp.set_discoverability(ESP_BT_NON_DISCOVERABLE);
            a2dp.set_connectable(false);
            Serial.printf("[BTTEST] Pausing new connections for %lu ms (free=%u largest=%u)\n",
                          static_cast<unsigned long>(BT_REOPEN_DELAY_MS),
                          heap_caps_get_free_size(MALLOC_CAP_8BIT),
                          heap_caps_get_largest_free_block(MALLOC_CAP_8BIT));
        } else if ((int32_t)(millis() - reopenAtMs) >= 0) {
            reopenPairing = false;
            reopenCooldownStarted = false;
            a2dp.set_auto_reconnect(false, 0);
            a2dp.clean_last_connection();
            a2dp.set_discoverability(ESP_BT_GENERAL_DISCOVERABLE);
            a2dp.set_connectable(true);
            Serial.printf("[BTTEST] Open for new connections (free=%u largest=%u)\n",
                          heap_caps_get_free_size(MALLOC_CAP_8BIT),
                          heap_caps_get_largest_free_block(MALLOC_CAP_8BIT));
        }
    }
    delay(100);
}

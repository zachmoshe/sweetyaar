#include "OtaUpdate.h"

#include <esp_bt.h>
#include <esp_gap_ble_api.h>
#include <esp_heap_caps.h>
#include <esp_ota_ops.h>
#include <esp_system.h>
#include <mbedtls/sha256.h>
#include <rom/miniz.h>

#include "Config.h"
#include "OtaSession.h"

// Arduino marks a pending image valid before setup() unless this returns true;
// confirmRunningImage() decides instead, after the services have started.
extern "C" bool verifyRollbackLater() { return true; }

namespace OtaUpdate {
namespace {

constexpr uint32_t UPDATE_MODE_MAGIC = 0x0DA7E5A1UL;
constexpr uint32_t STATUS_INTERVAL_MS = 150;
constexpr uint32_t RESTART_DELAY_MS = 400;  // let the write response leave first
constexpr uint32_t DISCONNECT_GRACE_MS = 150;  // time for the link-termination packet

RTC_NOINIT_ATTR uint32_t rtcUpdateModeMagic;

class EspSink : public Ota::Sink {
public:
    Ota::Error open(const Ota::Image& image) override {
        abort();
        _partition = esp_ota_get_next_update_partition(nullptr);
        if (!_partition) return Ota::Error::Flash;
        if (image.imageSize > _partition->size) return Ota::Error::Size;
        _zlib = image.encoding == Ota::EncodingZlib;
        if (_zlib) {
            _inflater = static_cast<tinfl_decompressor*>(malloc(sizeof(tinfl_decompressor)));
            _dict = static_cast<uint8_t*>(malloc(TINFL_LZ_DICT_SIZE));
            if (!_inflater || !_dict) {
                abort();
                return Ota::Error::NoMemory;
            }
            tinfl_init(_inflater);
        }
        // Erase sector by sector as data arrives; erasing 3 MB up front
        // would stall flash access for seconds.
        if (esp_ota_begin(_partition, OTA_WITH_SEQUENTIAL_WRITES, &_handle) != ESP_OK) {
            _handle = 0;
            abort();
            return Ota::Error::Flash;
        }
        mbedtls_sha256_init(&_sha);
        mbedtls_sha256_starts_ret(&_sha, 0);
        _hashing = true;
        _written = 0;
        _dictOffset = 0;
        _done = false;
        _expected = image.imageSize;
        return Ota::Error::None;
    }

    Ota::Error write(const uint8_t* encoded, size_t length) override {
        if (!_handle) return Ota::Error::WrongMode;
        if (!_zlib) {
            _done = _written + length >= _expected;
            return output(encoded, length);
        }
        size_t inOffset = 0;
        while (inOffset < length || !_done) {
            size_t inBytes = length - inOffset;
            size_t outBytes = TINFL_LZ_DICT_SIZE - _dictOffset;
            const tinfl_status status = tinfl_decompress(_inflater, encoded + inOffset, &inBytes,
                _dict, _dict + _dictOffset, &outBytes,
                TINFL_FLAG_PARSE_ZLIB_HEADER | TINFL_FLAG_HAS_MORE_INPUT);
            inOffset += inBytes;
            if (outBytes) {
                const Ota::Error result = output(_dict + _dictOffset, outBytes);
                if (result != Ota::Error::None) return result;
                _dictOffset = (_dictOffset + outBytes) & (TINFL_LZ_DICT_SIZE - 1);
            }
            if (status < 0) return Ota::Error::Decompress;
            if (status == TINFL_STATUS_DONE) {
                _done = true;
                // Bytes after the zlib trailer would mean a different file.
                return inOffset == length ? Ota::Error::None : Ota::Error::Decompress;
            }
            if (status == TINFL_STATUS_NEEDS_MORE_INPUT && inOffset >= length) break;
        }
        return Ota::Error::None;
    }

    uint32_t written() const override { return _written; }
    bool complete() const override { return _done; }

    void digest(uint8_t out[32]) override {
        mbedtls_sha256_finish_ret(&_sha, out);
        mbedtls_sha256_free(&_sha);
        _hashing = false;
    }

    Ota::Error install() override {
        // esp_ota_end() checks the image structure and its appended hash.
        const esp_err_t ended = esp_ota_end(_handle);
        _handle = 0;
        release();
        if (ended == ESP_ERR_OTA_VALIDATE_FAILED) return Ota::Error::InvalidImage;
        if (ended != ESP_OK) return Ota::Error::Flash;
        return esp_ota_set_boot_partition(_partition) == ESP_OK ? Ota::Error::None : Ota::Error::Flash;
    }

    void abort() override {
        if (_handle) esp_ota_abort(_handle);
        _handle = 0;
        release();
    }

private:
    Ota::Error output(const uint8_t* bytes, size_t length) {
        if (_written + length > _expected) return Ota::Error::Size;
        if (esp_ota_write(_handle, bytes, length) != ESP_OK) return Ota::Error::Flash;
        mbedtls_sha256_update_ret(&_sha, bytes, length);
        _written += length;
        return Ota::Error::None;
    }

    void release() {
        if (_hashing) mbedtls_sha256_free(&_sha);
        _hashing = false;
        free(_inflater);
        free(_dict);
        _inflater = nullptr;
        _dict = nullptr;
    }

    const esp_partition_t* _partition = nullptr;
    esp_ota_handle_t _handle = 0;
    mbedtls_sha256_context _sha;
    bool _hashing = false;
    bool _zlib = false;
    bool _done = false;
    tinfl_decompressor* _inflater = nullptr;
    uint8_t* _dict = nullptr;
    size_t _dictOffset = 0;
    uint32_t _written = 0;
    uint32_t _expected = 0;
};

enum class Restart : uint8_t { None, ToUpdateMode, ToNormal };

class Transport : public OtaTransport {
public:
    void control(const uint8_t* data, size_t length, const uint8_t* peer) override;
    void data(const uint8_t* data, size_t length) override {
        if (session.data(data, length)) touch();
        else statusDirty = true;  // tell the app where to resume
    }
    void mtuChanged(uint16_t value) override {
        Serial.printf("[OTA] ATT MTU %u\n", value);
        mtu = value;
        statusDirty = true;
    }

    void touch() {
        lastActivityMs = millis();
        statusDirty = true;
    }

    void restart(Restart kind) {
        restartKind = kind;
        restartAtMs = millis() + RESTART_DELAY_MS;
        statusDirty = true;
    }

    EspSink sink;
    Ota::Session session{sink};
    BLEParentService* ble = nullptr;
    bool (*updateAllowed)() = nullptr;
    volatile uint16_t mtu = 23;
    volatile bool statusDirty = true;
    volatile uint32_t lastActivityMs = 0;
    volatile Restart restartKind = Restart::None;
    volatile uint32_t restartAtMs = 0;
    uint32_t lastStatusMs = 0;
    uint8_t lastStatus[Ota::STATUS_SIZE] = {};
};

Transport transport;
bool updateModeActive = false;

// The phone chooses the connection interval; macOS otherwise stays at 30 ms.
// Throughput is about one 512-byte write per connection event.
void requestFastConnection(const uint8_t* peer) {
    esp_ble_conn_update_params_t params{};
    memcpy(params.bda, peer, sizeof(params.bda));
    params.min_int = 6;    // 7.5 ms
    params.max_int = 12;   // 15 ms
    params.latency = 0;
    params.timeout = 400;  // 4 s
    const esp_err_t result = esp_ble_gap_update_conn_params(&params);
    Serial.printf("[OTA] Requested 7.5-15 ms connection interval result=0x%X\n", unsigned(result));
}

void Transport::control(const uint8_t* data, size_t length, const uint8_t* peer) {
    touch();
    if (length == 0 || restartKind != Restart::None) return;
    switch (data[0]) {
        case Ota::CommandEnterUpdateMode:
            if (updateModeActive) return;
            if (!updateAllowed || !updateAllowed()) {
                session.reportError(Ota::Error::BatteryLow);
                Serial.println("[OTA] Update mode refused: battery low");
                return;
            }
            Serial.println("[OTA] Restarting into update mode");
            session.reportError(Ota::Error::None);  // clear an earlier refusal
            restart(Restart::ToUpdateMode);
            return;
        case Ota::CommandBegin: {
            Ota::Image image;
            if (!updateModeActive) {
                session.reportError(Ota::Error::WrongMode);
            } else if (!Ota::parseBegin(data, length, image)) {
                session.reportError(Ota::Error::BadRequest);
            } else {
                requestFastConnection(peer);
                const uint32_t resumeAt = session.received();
                const Ota::Error result = session.begin(image);
                Serial.printf("[OTA] Begin encoding=%u encoded=%lu image=%lu resume=%lu result=%u free=%u\n",
                    image.encoding, static_cast<unsigned long>(image.encodedSize),
                    static_cast<unsigned long>(image.imageSize),
                    static_cast<unsigned long>(session.received() ? resumeAt : 0),
                    static_cast<unsigned>(result), heap_caps_get_free_size(MALLOC_CAP_8BIT));
            }
            return;
        }
        case Ota::CommandFinish: {
            const Ota::Error result = session.finish();
            Serial.printf("[OTA] Finish result=%u state=%u\n", static_cast<unsigned>(result),
                static_cast<unsigned>(session.state()));
            if (session.state() == Ota::State::Installing) restart(Restart::ToNormal);
            return;
        }
        case Ota::CommandCancel:
            if (!updateModeActive) return;
            session.cancel();
            Serial.println("[OTA] Cancelled; restarting normal firmware");
            restart(Restart::ToNormal);
            return;
        default:
            session.reportError(Ota::Error::BadRequest);
            return;
    }
}

}  // namespace

bool consumeUpdateModeRequest() {
    const bool requested = rtcUpdateModeMagic == UPDATE_MODE_MAGIC &&
        esp_reset_reason() == ESP_RST_SW;
    // One request, one boot: a crash or power loss in update mode always
    // returns to normal firmware.
    rtcUpdateModeMagic = 0;
    updateModeActive = requested;
    return requested;
}

bool updateMode() {
    return updateModeActive;
}

bool startBleOnlyController() {
    esp_bt_controller_mem_release(ESP_BT_MODE_CLASSIC_BT);
    esp_bt_controller_config_t config = BT_CONTROLLER_INIT_CONFIG_DEFAULT();
    config.mode = ESP_BT_MODE_BLE;
    const esp_err_t init = esp_bt_controller_init(&config);
    const esp_err_t enable = init == ESP_OK ? esp_bt_controller_enable(ESP_BT_MODE_BLE) : init;
    Serial.printf("[OTA] BLE-only controller init=0x%X enable=0x%X free=%u\n",
        static_cast<unsigned>(init), static_cast<unsigned>(enable),
        heap_caps_get_free_size(MALLOC_CAP_8BIT));
    return enable == ESP_OK;
}

void attach(BLEParentService& ble, bool updateModeRunning, bool (*updateAllowed)()) {
    transport.ble = &ble;
    transport.updateAllowed = updateAllowed;
    transport.lastActivityMs = millis();
    if (updateModeRunning) transport.session.enterUpdateMode();
    String info = String("{\"version\":\"") + FIRMWARE_VERSION + "\",\"board\":\"" +
        FIRMWARE_BOARD_ID + "\",\"mode\":\"" + (updateModeRunning ? "update" : "normal") + "\"}";
    ble.updateFirmwareInfo(info);
    ble.setOtaTransport(&transport);
    transport.statusDirty = true;
    poll(millis());
}

void poll(uint32_t nowMs) {
    if (!transport.ble) return;
    if (transport.statusDirty && (nowMs - transport.lastStatusMs >= STATUS_INTERVAL_MS ||
                                  transport.session.state() != Ota::State::Receiving)) {
        transport.statusDirty = false;
        uint8_t status[Ota::STATUS_SIZE];
        transport.session.encodeStatus(status, transport.mtu);
        if (memcmp(status, transport.lastStatus, sizeof(status)) != 0) {
            memcpy(transport.lastStatus, status, sizeof(status));
            transport.lastStatusMs = nowMs;
            transport.ble->updateOtaStatus(status, sizeof(status));
        }
    }
    const Restart restart = transport.restartKind;
    if (restart != Restart::None && int32_t(nowMs - transport.restartAtMs) >= 0) {
        rtcUpdateModeMagic = restart == Restart::ToUpdateMode ? UPDATE_MODE_MAGIC : 0;
        // Close the link first: after a bare restart a phone only notices
        // at its supervision timeout, which was about 7 s on Android.
        transport.ble->disconnectAll();
        delay(DISCONNECT_GRACE_MS);
        Serial.flush();
        esp_restart();
    }
    // Signed: the Bluetooth task can record activity after nowMs was sampled.
    if (updateModeActive && restart == Restart::None &&
        int32_t(nowMs - transport.lastActivityMs) >= int32_t(OTA_UPDATE_MODE_IDLE_MS)) {
        Serial.println("[OTA] No update traffic for 2 minutes; restarting normal firmware");
        transport.session.cancel();
        transport.restart(Restart::ToNormal);
    }
}

void confirmRunningImage(bool healthy) {
    const esp_partition_t* running = esp_ota_get_running_partition();
    esp_ota_img_states_t state;
    if (!running || esp_ota_get_state_partition(running, &state) != ESP_OK ||
        state != ESP_OTA_IMG_PENDING_VERIFY) {
        return;
    }
    if (healthy) {
        esp_ota_mark_app_valid_cancel_rollback();
        Serial.printf("[OTA] Firmware %s confirmed after update\n", FIRMWARE_VERSION);
    } else {
        Serial.println("[OTA] New firmware failed its startup check; rolling back");
        Serial.flush();
        esp_ota_mark_app_invalid_rollback_and_reboot();
    }
}

}  // namespace OtaUpdate

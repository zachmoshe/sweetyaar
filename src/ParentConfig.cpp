#include "ParentConfig.h"
#include <SD.h>
#include <ArduinoJson.h>
#include "Config.h"

namespace {

uint32_t readSecondsMs(JsonObjectConst obj, const char* key, uint32_t fallbackMs) {
    long fallbackSeconds = static_cast<long>(fallbackMs / 1000UL);
    long seconds = obj[key] | fallbackSeconds;
    if (seconds < 1) {
        return fallbackMs;
    }
    if (seconds > 24L * 60L * 60L) {
        seconds = 24L * 60L * 60L;
    }
    return static_cast<uint32_t>(seconds) * 1000UL;
}

}  // namespace

bool ParentConfig::load() {
    _defaultVolumePct = DEFAULT_VOLUME_PCT;
    _defaultTheme     = DEFAULT_THEME;
    _disabledThemeCount = 0;
    _sleepEnabled = DEFAULT_SLEEP_ENABLED;
    _sleepNormalIdleMs = SLEEP_NORMAL_IDLE_MS;
    _sleepVibrationWakeIdleMs = SLEEP_VIB_WAKE_IDLE_MS;
    _sleepBleIdleMs = SLEEP_BLE_IDLE_MS;

    File f = SD.open(SD_CONFIG_FILE);
    if (!f) {
        Serial.printf("[Config] %s not found; using firmware defaults\n", SD_CONFIG_FILE);
        return false;
    }

    JsonDocument doc;
    DeserializationError err = deserializeJson(doc, f);
    f.close();
    if (err) {
        Serial.printf("[Config] Failed to parse %s: %s; using defaults\n",
                      SD_CONFIG_FILE, err.c_str());
        return false;
    }

    int vol = doc["defaultVolumePct"] | DEFAULT_VOLUME_PCT;
    if (vol < 0) vol = 0;
    if (vol > 100) vol = 100;
    _defaultVolumePct = static_cast<uint8_t>(vol);

    const char* theme = doc["defaultTheme"] | DEFAULT_THEME;
    if (theme && theme[0] != '\0') {
        _defaultTheme = theme;
    }

    if (doc["disabledThemes"].is<JsonArray>()) {
        for (JsonVariantConst item : doc["disabledThemes"].as<JsonArray>()) {
            const char* disabledTheme = item | "";
            if (disabledTheme && disabledTheme[0] != '\0' &&
                _disabledThemeCount < CONFIG_MAX_DISABLED_THEMES) {
                _disabledThemes[_disabledThemeCount++] = disabledTheme;
            }
        }
    }

    if (doc["sleep"].is<JsonObject>()) {
        JsonObject sleep = doc["sleep"].as<JsonObject>();
        _sleepEnabled = sleep["enabled"] | DEFAULT_SLEEP_ENABLED;
        _sleepNormalIdleMs = readSecondsMs(sleep, "normalIdleSec", SLEEP_NORMAL_IDLE_MS);
        _sleepVibrationWakeIdleMs = readSecondsMs(
            sleep, "vibrationWakeIdleSec", SLEEP_VIB_WAKE_IDLE_MS);
        _sleepBleIdleMs = readSecondsMs(sleep, "bleIdleSec", SLEEP_BLE_IDLE_MS);
    }

    Serial.printf("[Config] defaultVolume=%u defaultTheme=%s disabledThemes=%d "
                  "sleep=%d normal=%lus vibWake=%lus ble=%lus\n",
                  _defaultVolumePct, _defaultTheme.c_str(), _disabledThemeCount,
                  _sleepEnabled ? 1 : 0,
                  static_cast<unsigned long>(_sleepNormalIdleMs / 1000UL),
                  static_cast<unsigned long>(_sleepVibrationWakeIdleMs / 1000UL),
                  static_cast<unsigned long>(_sleepBleIdleMs / 1000UL));
    return true;
}

bool ParentConfig::isThemeDisabled(const String& theme) const {
    for (int i = 0; i < _disabledThemeCount; i++) {
        if (_disabledThemes[i] == theme) {
            return true;
        }
    }
    return false;
}

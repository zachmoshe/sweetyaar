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

uint16_t parseTimeMinutes(const char* value, uint16_t fallback) {
    if (value == nullptr || value[0] == '\0') {
        return fallback;
    }

    int hour = -1;
    int minute = -1;
    char extra = '\0';
    int matched = sscanf(value, "%d:%d%c", &hour, &minute, &extra);
    if (matched < 2 || hour < 0 || hour > 23 || minute < 0 || minute > 59) {
        return fallback;
    }
    return static_cast<uint16_t>(hour * 60 + minute);
}

uint16_t readTimeMinutes(JsonObjectConst obj, const char* key, uint16_t fallback) {
    if (obj[key].is<int>()) {
        int minutes = obj[key].as<int>();
        if (minutes >= 0 && minutes < 24 * 60) {
            return static_cast<uint16_t>(minutes);
        }
        return fallback;
    }
    return parseTimeMinutes(obj[key] | "", fallback);
}

uint8_t readPercent(JsonObjectConst obj, const char* key, uint8_t fallback) {
    int value = obj[key] | fallback;
    if (value < 0) value = 0;
    if (value > 100) value = 100;
    return static_cast<uint8_t>(value);
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
    _bedtimeEnabled = DEFAULT_BEDTIME_ENABLED;
    _bedtimeStartMinutes = DEFAULT_BEDTIME_START_MINUTES;
    _bedtimeEndMinutes = DEFAULT_BEDTIME_END_MINUTES;
    _bedtimeTheme = DEFAULT_BEDTIME_THEME;
    _bedtimeVolumeCapPct = DEFAULT_BEDTIME_VOLUME_CAP_PCT;

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

    if (doc["bedtime"].is<JsonObject>()) {
        JsonObject bedtime = doc["bedtime"].as<JsonObject>();
        _bedtimeEnabled = bedtime["enabled"] | DEFAULT_BEDTIME_ENABLED;
        _bedtimeStartMinutes = readTimeMinutes(
            bedtime, "startTime", DEFAULT_BEDTIME_START_MINUTES);
        _bedtimeEndMinutes = readTimeMinutes(
            bedtime, "endTime", DEFAULT_BEDTIME_END_MINUTES);
        const char* bedtimeTheme = bedtime["theme"] | DEFAULT_BEDTIME_THEME;
        if (bedtimeTheme && bedtimeTheme[0] != '\0') {
            _bedtimeTheme = bedtimeTheme;
        }
        _bedtimeVolumeCapPct = readPercent(
            bedtime, "volumeCapPct", DEFAULT_BEDTIME_VOLUME_CAP_PCT);
    }

    Serial.printf("[Config] defaultVolume=%u defaultTheme=%s disabledThemes=%d "
                  "sleep=%d normal=%lus vibWake=%lus ble=%lus "
                  "bedtime=%d start=%02u:%02u end=%02u:%02u theme=%s cap=%u\n",
                  _defaultVolumePct, _defaultTheme.c_str(), _disabledThemeCount,
                  _sleepEnabled ? 1 : 0,
                  static_cast<unsigned long>(_sleepNormalIdleMs / 1000UL),
                  static_cast<unsigned long>(_sleepVibrationWakeIdleMs / 1000UL),
                  static_cast<unsigned long>(_sleepBleIdleMs / 1000UL),
                  _bedtimeEnabled ? 1 : 0,
                  _bedtimeStartMinutes / 60, _bedtimeStartMinutes % 60,
                  _bedtimeEndMinutes / 60, _bedtimeEndMinutes % 60,
                  _bedtimeTheme.c_str(), _bedtimeVolumeCapPct);
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

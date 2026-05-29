#include "ParentConfig.h"
#include <SD.h>
#include <ArduinoJson.h>
#include "Config.h"

bool ParentConfig::load() {
    _defaultVolumePct = DEFAULT_VOLUME_PCT;
    _defaultTheme     = DEFAULT_THEME;
    _disabledThemeCount = 0;

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

    if (doc["disabledThemes"].is<JsonArrayConst>()) {
        for (JsonVariantConst item : doc["disabledThemes"].as<JsonArrayConst>()) {
            const char* disabledTheme = item | "";
            if (disabledTheme && disabledTheme[0] != '\0' &&
                _disabledThemeCount < CONFIG_MAX_DISABLED_THEMES) {
                _disabledThemes[_disabledThemeCount++] = disabledTheme;
            }
        }
    }

    Serial.printf("[Config] defaultVolume=%u defaultTheme=%s disabledThemes=%d\n",
                  _defaultVolumePct, _defaultTheme.c_str(), _disabledThemeCount);
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

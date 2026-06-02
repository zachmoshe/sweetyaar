#pragma once
#include <Arduino.h>
#include "Config.h"

// ---------------------------------------------------------------------------
// ParentConfig — parent-editable settings loaded from SD:/config.json
//
// These are toy/content settings, not device identity. If the SD card is
// missing or config.json is absent, safe firmware defaults are used.
// ---------------------------------------------------------------------------
class ParentConfig {
public:
    ParentConfig() = default;

    // Load settings from SD_CONFIG_FILE. SD must already be mounted.
    bool load();

    uint8_t defaultVolumePct() const { return _defaultVolumePct; }
    String defaultTheme() const { return _defaultTheme; }
    bool isThemeDisabled(const String& theme) const;
    bool sleepEnabled() const { return _sleepEnabled; }
    uint32_t sleepNormalIdleMs() const { return _sleepNormalIdleMs; }
    uint32_t sleepVibrationWakeIdleMs() const { return _sleepVibrationWakeIdleMs; }
    uint32_t sleepBleIdleMs() const { return _sleepBleIdleMs; }

private:
    uint8_t _defaultVolumePct = DEFAULT_VOLUME_PCT;
    String  _defaultTheme     = DEFAULT_THEME;
    String  _disabledThemes[CONFIG_MAX_DISABLED_THEMES];
    int     _disabledThemeCount = 0;
    bool    _sleepEnabled = DEFAULT_SLEEP_ENABLED;
    uint32_t _sleepNormalIdleMs = SLEEP_NORMAL_IDLE_MS;
    uint32_t _sleepVibrationWakeIdleMs = SLEEP_VIB_WAKE_IDLE_MS;
    uint32_t _sleepBleIdleMs = SLEEP_BLE_IDLE_MS;
};

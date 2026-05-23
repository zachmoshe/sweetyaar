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

private:
    uint8_t _defaultVolumePct = DEFAULT_VOLUME_PCT;
    String  _defaultTheme     = DEFAULT_THEME;
};

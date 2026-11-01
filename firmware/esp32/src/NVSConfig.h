#pragma once
#include <Arduino.h>
#include <Preferences.h>

// ---------------------------------------------------------------------------
// NVSConfig — device-local settings stored in ESP32 NVS (flash)
//
// Parent-editable toy/content settings live on SD:/config.json. NVS only keeps
// settings that should survive SD card replacement: the BT name and the
// parents' choice to share the diagnostic log automatically.
// The data is stored as a compact JSON blob in a single NVS key.
// ---------------------------------------------------------------------------
class NVSConfig {
public:
    NVSConfig() = default;

    // Open NVS namespace; call once in setup()
    void begin();

    // Bluetooth device name (shown during BT discovery)
    String getBtName() const;
    void   setBtName(const String& name);

    // Automatic log sharing: on or off, and the first log sequence it may
    // upload (0: everything on the toy).
    struct LogSharing {
        bool enabled = false;
        uint32_t from = 0;
    };
    LogSharing getLogSharing() const;
    void setLogSharing(const LogSharing& sharing);

private:
    mutable Preferences _prefs;

    String readDeviceConfigJson() const;
    void   writeDeviceConfigJson(const String& json);
};

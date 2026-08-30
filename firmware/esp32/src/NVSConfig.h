#pragma once
#include <Arduino.h>
#include <Preferences.h>

// ---------------------------------------------------------------------------
// NVSConfig — device-local settings stored in ESP32 NVS (flash)
//
// Parent-editable toy/content settings live on SD:/config.json. NVS only keeps
// settings that should survive SD card replacement, currently the BT name.
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

private:
    mutable Preferences _prefs;

    String readDeviceConfigJson() const;
    void   writeDeviceConfigJson(const String& json);
};

#pragma once

#include <Arduino.h>
#include "Config.h"

enum class BatteryState : uint8_t {
    Unknown = 0,
    Good = 1,
    Medium = 2,
    Low = 3,
    Charging = 4,
};

static_assert(static_cast<uint8_t>(BatteryState::Unknown) == 0, "BLE battery encoding changed");
static_assert(static_cast<uint8_t>(BatteryState::Good) == 1, "BLE battery encoding changed");
static_assert(static_cast<uint8_t>(BatteryState::Medium) == 2, "BLE battery encoding changed");
static_assert(static_cast<uint8_t>(BatteryState::Low) == 3, "BLE battery encoding changed");
static_assert(static_cast<uint8_t>(BatteryState::Charging) == 4, "BLE battery encoding changed");

class BatteryMonitor {
public:
    // Call after the rest of boot initialization has settled. This blocks for
    // roughly 500 ms while five ADC readings seed the first published state.
    void begin();

    // Call from loop(). Returns true only when the public battery state changes.
    bool poll();

    BatteryState state() const { return _state; }
    uint8_t encodedState() const { return static_cast<uint8_t>(_state); }

private:
    uint16_t readBatteryMillivolts() const;
    void addVoltageSample(uint16_t batteryMillivolts);
    void updateVoltageState(uint16_t averagedMillivolts);
    void updateChargerState();
    void updatePublicState();
    uint16_t averageMillivolts() const;

    BatteryState _state = BatteryState::Unknown;
    BatteryState _voltageState = BatteryState::Unknown;
    uint16_t _samples[BATTERY_ROLLING_SAMPLE_COUNT] = {0};
    uint8_t _sampleCount = 0;
    uint8_t _nextSample = 0;
    uint8_t _chargerPins = 0xFF;
    bool _charging = false;
    bool _hasValidVoltage = false;
    uint32_t _lastPeriodicSampleMs = 0;
};

const char* batteryStateName(BatteryState state);

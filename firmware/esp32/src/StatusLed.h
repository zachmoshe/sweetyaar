#pragma once

#include <Arduino.h>
#include <atomic>

#include "StatusLedPolicy.h"

// Owns the addressable LED bus and its blink clock. Producers only set semantic
// signals; service() is the sole place that selects a pattern and transmits a
// pixel frame. This remains safe if a producer later moves to another task.
class StatusLed {
public:
    StatusLed();

    // Call before enabling 5V_PERIPH_SW. Establishes inactive DIN (LOW for
    // direct drive) to avoid back-powering or a spurious edge during power-up.
    void prepareForPeripheralPowerOn();

    // Call after 5V_PERIPH_SW has settled.
    void begin();

    // Thread-safe semantic input. Patterns and physical LED assignment stay
    // private to this controller. Set PairingReset once per reset action;
    // service() clears that one-shot signal after its flash.
    void setSignal(StatusSignal signal, bool active);

    // Global cap applied equally to every available color channel. A change
    // takes effect immediately without changing the active pattern.
    void setMaxBrightnessPct(uint8_t brightnessPct);
    uint8_t maxBrightnessPct() const { return _maxBrightnessPct; }

    // Called from loop() with one shared millis() sample. It changes the LED
    // only when the selected mode or blink phase changes.
    void service(uint32_t nowMs);

    // Send an explicit black frame while 5V_PERIPH_SW is still powered.
    void prepareForPeripheralPowerOff();

    // Call only after 5V_PERIPH_SW is disabled; releases GPIO2 to high-Z so
    // firmware cannot drive HIGH into the unpowered LED during deep sleep.
    void releaseAfterPeripheralPowerOff();

private:
    std::atomic<uint32_t> _signals{statusSignalBit(StatusSignal::Initializing)};
    bool _initialized = false;
    bool _phaseOn = false;
    uint8_t _maxBrightnessPct = 100;
    uint32_t _phaseStartedMs = 0;
    StatusLedMode _mode = StatusLedMode::Off;
    LedColor _lastColor{0, 0, 0, 0};

    void showColor(LedColor color, bool force = false);
};

extern StatusLed statusLed;

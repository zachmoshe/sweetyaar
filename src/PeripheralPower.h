#pragma once

#include <Arduino.h>
#include <driver/rtc_io.h>

#include "Config.h"

inline gpio_num_t peripheralPowerGpio() {
    return static_cast<gpio_num_t>(PIN_PERIPH_EN);
}

inline void releasePeripheralPowerSleepHold() {
    gpio_num_t pin = peripheralPowerGpio();
    rtc_gpio_hold_dis(pin);
    rtc_gpio_pullup_dis(pin);
    rtc_gpio_pulldown_dis(pin);
    rtc_gpio_deinit(pin);
}

inline void setPeripheralPowerEnabled(bool enabled) {
    releasePeripheralPowerSleepHold();
    pinMode(PIN_PERIPH_EN, OUTPUT);
    digitalWrite(PIN_PERIPH_EN, enabled ? HIGH : LOW);
}

inline void enablePeripheralPower(uint32_t settleMs = 50) {
    setPeripheralPowerEnabled(true);
    if (settleMs > 0) {
        delay(settleMs);
    }
}

inline void disablePeripheralPower() {
    setPeripheralPowerEnabled(false);
}

inline void holdPeripheralPowerOffForDeepSleep() {
    gpio_num_t pin = peripheralPowerGpio();
    rtc_gpio_hold_dis(pin);
    rtc_gpio_init(pin);
    rtc_gpio_set_direction(pin, RTC_GPIO_MODE_OUTPUT_ONLY);
    rtc_gpio_set_level(pin, 0);
    rtc_gpio_pullup_dis(pin);
    rtc_gpio_pulldown_en(pin);
    rtc_gpio_hold_en(pin);
}

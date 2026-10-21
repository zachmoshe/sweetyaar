#pragma once

#include <Arduino.h>
#include <driver/rtc_io.h>
#include <rom/ets_sys.h>

#include "Config.h"

inline gpio_num_t peripheralPowerGpio() {
    return static_cast<gpio_num_t>(PIN_PERIPH_PWR_EN);
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
    pinMode(PIN_PERIPH_PWR_EN, OUTPUT);
    digitalWrite(PIN_PERIPH_PWR_EN, enabled ? HIGH : LOW);
}

// Charges C_AMP3 in short enable pulses so the 5 V converter never reaches its
// full current limit; GPIO13 also pulses the SD and battery-sense switches.
inline void prechargePeripheral5V() {
    static portMUX_TYPE mux = portMUX_INITIALIZER_UNLOCKED;
    const gpio_num_t pin = peripheralPowerGpio();
    for (uint32_t i = 0; i < PERIPH_5V_PRECHARGE_PULSES; ++i) {
        // A delayed falling edge would become a full-current start.
        portENTER_CRITICAL(&mux);
        gpio_set_level(pin, 1);
        ets_delay_us(PERIPH_5V_PRECHARGE_ON_US);
        gpio_set_level(pin, 0);
        portEXIT_CRITICAL(&mux);
        ets_delay_us(PERIPH_5V_PRECHARGE_OFF_US);
    }
}

inline void enablePeripheralPower(uint32_t settleMs = 50) {
    setPeripheralPowerEnabled(false);
    prechargePeripheral5V();
    digitalWrite(PIN_PERIPH_PWR_EN, HIGH);
    if (settleMs > 0) {
        delay(settleMs);
    }
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

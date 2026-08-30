#include "StatusLed.h"

#include "Config.h"

namespace {
constexpr uint32_t PWM_FREQUENCY_HZ = 5000;
constexpr uint8_t PWM_RESOLUTION_BITS = 8;
constexpr uint8_t PWM_CHANNEL_RED = 0;
constexpr uint8_t PWM_CHANNEL_GREEN = 1;
constexpr uint8_t PWM_CHANNEL_BLUE = 2;
}

StatusLed statusLed;

void StatusLed::begin() {
    ledcSetup(PWM_CHANNEL_RED, PWM_FREQUENCY_HZ, PWM_RESOLUTION_BITS);
    ledcSetup(PWM_CHANNEL_GREEN, PWM_FREQUENCY_HZ, PWM_RESOLUTION_BITS);
    ledcSetup(PWM_CHANNEL_BLUE, PWM_FREQUENCY_HZ, PWM_RESOLUTION_BITS);

    ledcAttachPin(PIN_LED_RED, PWM_CHANNEL_RED);
    ledcAttachPin(PIN_LED_GREEN, PWM_CHANNEL_GREEN);
    ledcAttachPin(PIN_LED_BLUE, PWM_CHANNEL_BLUE);

    _initialized = true;
    off();
}

void StatusLed::setColor(LedColor color) {
    if (!_initialized) {
        return;
    }

    ledcWrite(PWM_CHANNEL_RED, color.red);
    ledcWrite(PWM_CHANNEL_GREEN, color.green);
    ledcWrite(PWM_CHANNEL_BLUE, color.blue);
}

void StatusLed::off() {
    if (!_initialized) {
        return;
    }

    ledcWrite(PWM_CHANNEL_RED, 0);
    ledcWrite(PWM_CHANNEL_GREEN, 0);
    ledcWrite(PWM_CHANNEL_BLUE, 0);
}

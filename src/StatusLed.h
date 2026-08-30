#pragma once

#include <Arduino.h>

struct LedColor {
    uint8_t red;
    uint8_t green;
    uint8_t blue;
};

namespace LedColors {
static constexpr LedColor RED   = {255, 0, 0};
static constexpr LedColor GREEN = {0, 255, 0};
static constexpr LedColor BLUE  = {0, 0, 255};
static constexpr LedColor WHITE = {255, 255, 255};
}

class StatusLed {
public:
    void begin();
    void setColor(LedColor color);
    void off();

private:
    bool _initialized = false;
};

extern StatusLed statusLed;

#pragma once

#include <cstdint>

namespace BedtimeMode {

static constexpr uint16_t MINUTES_PER_DAY = 24U * 60U;
static constexpr uint32_t SECONDS_PER_DAY = 24UL * 60UL * 60UL;

enum class Override : uint8_t {
    None,
    ForceOn,
    ForceOff,
};

struct Evaluation {
    bool automaticActive = false;
    bool active = false;
};

uint16_t clampMinuteOfDay(uint16_t minute);
bool isMinuteInWindow(uint16_t minute, uint16_t startMinute, uint16_t endMinute);
Evaluation evaluate(bool enabled, bool timeKnown, uint16_t minute,
                    uint16_t startMinute, uint16_t endMinute,
                    Override overrideMode);
uint32_t secondsUntilNextMinuteOfDay(uint32_t currentSecondOfDay,
                                     uint16_t targetMinute);
const char* overrideName(Override overrideMode);

}  // namespace BedtimeMode

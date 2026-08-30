#include "BedtimeMode.h"

namespace BedtimeMode {

uint16_t clampMinuteOfDay(uint16_t minute) {
    return minute < MINUTES_PER_DAY ? minute : static_cast<uint16_t>(MINUTES_PER_DAY - 1);
}

bool isMinuteInWindow(uint16_t minute, uint16_t startMinute, uint16_t endMinute) {
    minute = clampMinuteOfDay(minute);
    startMinute = clampMinuteOfDay(startMinute);
    endMinute = clampMinuteOfDay(endMinute);

    if (startMinute == endMinute) {
        return true;
    }
    if (startMinute < endMinute) {
        return minute >= startMinute && minute < endMinute;
    }
    return minute >= startMinute || minute < endMinute;
}

Evaluation evaluate(bool enabled, bool timeKnown, uint16_t minute,
                    uint16_t startMinute, uint16_t endMinute,
                    Override overrideMode) {
    Evaluation out;
    if (!enabled || !timeKnown) {
        return out;
    }

    out.automaticActive = isMinuteInWindow(minute, startMinute, endMinute);
    switch (overrideMode) {
        case Override::ForceOn:
            out.active = true;
            break;
        case Override::ForceOff:
            out.active = false;
            break;
        case Override::None:
        default:
            out.active = out.automaticActive;
            break;
    }
    return out;
}

uint32_t secondsUntilNextMinuteOfDay(uint32_t currentSecondOfDay,
                                     uint16_t targetMinute) {
    currentSecondOfDay %= SECONDS_PER_DAY;
    targetMinute = clampMinuteOfDay(targetMinute);

    uint32_t targetSecond = static_cast<uint32_t>(targetMinute) * 60UL;
    if (targetSecond <= currentSecondOfDay) {
        targetSecond += SECONDS_PER_DAY;
    }
    return targetSecond - currentSecondOfDay;
}

const char* overrideName(Override overrideMode) {
    switch (overrideMode) {
        case Override::ForceOn:
            return "on";
        case Override::ForceOff:
            return "off";
        case Override::None:
        default:
            return "none";
    }
}

}  // namespace BedtimeMode

#include <cassert>
#include <cstdint>
#include <iostream>

#include "BedtimeMode.h"

namespace {

constexpr uint16_t minutes(uint16_t hour, uint16_t minute) {
    return static_cast<uint16_t>(hour * 60 + minute);
}

void testOvernightWindow() {
    const uint16_t start = minutes(18, 30);
    const uint16_t end = minutes(6, 30);

    assert(!BedtimeMode::isMinuteInWindow(minutes(18, 29), start, end));
    assert(BedtimeMode::isMinuteInWindow(minutes(18, 30), start, end));
    assert(BedtimeMode::isMinuteInWindow(minutes(23, 59), start, end));
    assert(BedtimeMode::isMinuteInWindow(minutes(0, 0), start, end));
    assert(BedtimeMode::isMinuteInWindow(minutes(6, 29), start, end));
    assert(!BedtimeMode::isMinuteInWindow(minutes(6, 30), start, end));
}

void testSameDayWindow() {
    const uint16_t start = minutes(10, 0);
    const uint16_t end = minutes(13, 0);

    assert(!BedtimeMode::isMinuteInWindow(minutes(9, 59), start, end));
    assert(BedtimeMode::isMinuteInWindow(minutes(10, 0), start, end));
    assert(BedtimeMode::isMinuteInWindow(minutes(12, 59), start, end));
    assert(!BedtimeMode::isMinuteInWindow(minutes(13, 0), start, end));
}

void testEvaluateDisabledAndUnknownTime() {
    auto disabled = BedtimeMode::evaluate(
        false, true, minutes(20, 0), minutes(18, 30), minutes(6, 30),
        BedtimeMode::Override::ForceOn);
    assert(!disabled.automaticActive);
    assert(!disabled.active);

    auto unknown = BedtimeMode::evaluate(
        true, false, minutes(20, 0), minutes(18, 30), minutes(6, 30),
        BedtimeMode::Override::ForceOn);
    assert(!unknown.automaticActive);
    assert(!unknown.active);
}

void testOverrides() {
    auto forceOn = BedtimeMode::evaluate(
        true, true, minutes(14, 0), minutes(18, 30), minutes(6, 30),
        BedtimeMode::Override::ForceOn);
    assert(!forceOn.automaticActive);
    assert(forceOn.active);

    auto forceOff = BedtimeMode::evaluate(
        true, true, minutes(20, 0), minutes(18, 30), minutes(6, 30),
        BedtimeMode::Override::ForceOff);
    assert(forceOff.automaticActive);
    assert(!forceOff.active);
}

void testNextBoundarySeconds() {
    assert(BedtimeMode::secondsUntilNextMinuteOfDay(
        14UL * 3600UL, minutes(6, 30)) == 16UL * 3600UL + 30UL * 60UL);
    assert(BedtimeMode::secondsUntilNextMinuteOfDay(
        20UL * 3600UL, minutes(18, 30)) == 22UL * 3600UL + 30UL * 60UL);
}

}  // namespace

int main() {
    testOvernightWindow();
    testSameDayWindow();
    testEvaluateDisabledAndUnknownTime();
    testOverrides();
    testNextBoundarySeconds();
    std::cout << "bedtime-mode native test passed\n";
    return 0;
}

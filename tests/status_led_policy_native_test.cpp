#include <cassert>
#include <cstdint>
#include <iostream>
#include <string>

#include "StatusLedPolicy.h"

namespace {
bool sameColor(LedColor left, LedColor right) {
    return left.red == right.red &&
           left.green == right.green &&
           left.blue == right.blue &&
           left.white == right.white;
}

void expectPattern(uint32_t signals,
                   StatusLedMode mode,
                   LedColor color,
                   uint16_t onMs,
                   uint16_t offMs) {
    StatusLedPattern pattern = selectStatusLedPattern(signals);
    assert(pattern.mode == mode);
    assert(sameColor(pattern.color, color));
    assert(pattern.onMs == onMs);
    assert(pattern.offMs == offMs);
}
}  // namespace

int main() {
    const StatusLedModeDefinition btPlaying =
        statusLedModeDefinition(StatusLedMode::BluetoothPlaying);
    assert(std::string(btPlaying.condition) == "BT audio playing");
    assert(std::string(btPlaying.colorName) == "blue");
    assert(btPlaying.pattern.mode == StatusLedMode::BluetoothPlaying);

    expectPattern(0, StatusLedMode::Off, LedColors::OFF, 0, 0);
    expectPattern(statusSignalBit(StatusSignal::Initializing),
                  StatusLedMode::Initializing, LedColors::YELLOW, 0, 0);
    expectPattern(statusSignalBit(StatusSignal::Ready),
                  StatusLedMode::Ready, LedColors::GREEN, 1000, 1000);
    expectPattern(statusSignalBit(StatusSignal::LocalPlayback),
                  StatusLedMode::LocalPlayback, LedColors::GREEN, 500, 500);
    expectPattern(statusSignalBit(StatusSignal::BluetoothPlaying),
                  StatusLedMode::BluetoothPlaying, LedColors::BLUE, 500, 500);
    expectPattern(statusSignalBit(StatusSignal::BluetoothConnected),
                  StatusLedMode::BluetoothConnected, LedColors::BLUE, 1000, 1000);
    expectPattern(statusSignalBit(StatusSignal::Killswitch),
                  StatusLedMode::Killswitch, LedColors::PURPLE, 1000, 250);
    expectPattern(statusSignalBit(StatusSignal::Error),
                  StatusLedMode::Error, LedColors::RED, 250, 250);

    const uint32_t initError = statusSignalBit(StatusSignal::Initializing) |
                               statusSignalBit(StatusSignal::Error);
    expectPattern(initError,
                  StatusLedMode::Initializing, LedColors::YELLOW, 0, 0);

    const uint32_t errorBtReady = statusSignalBit(StatusSignal::Error) |
                                  statusSignalBit(StatusSignal::BluetoothConnected) |
                                  statusSignalBit(StatusSignal::Ready);
    expectPattern(errorBtReady, StatusLedMode::Error, LedColors::RED, 250, 250);

    const uint32_t btPlayingConnected =
        statusSignalBit(StatusSignal::BluetoothPlaying) |
        statusSignalBit(StatusSignal::BluetoothConnected);
    expectPattern(btPlayingConnected,
                  StatusLedMode::BluetoothPlaying, LedColors::BLUE, 500, 500);

    const uint32_t btKillswitchPlayback =
        statusSignalBit(StatusSignal::BluetoothConnected) |
        statusSignalBit(StatusSignal::Killswitch) |
        statusSignalBit(StatusSignal::LocalPlayback);
    expectPattern(btKillswitchPlayback,
                  StatusLedMode::BluetoothConnected, LedColors::BLUE, 1000, 1000);

    const uint32_t killswitchPlaybackReady =
        statusSignalBit(StatusSignal::Killswitch) |
        statusSignalBit(StatusSignal::LocalPlayback) |
        statusSignalBit(StatusSignal::Ready);
    expectPattern(killswitchPlaybackReady,
                  StatusLedMode::Killswitch, LedColors::PURPLE, 1000, 250);

    std::cout << "status-led policy native test passed\n";
    return 0;
}

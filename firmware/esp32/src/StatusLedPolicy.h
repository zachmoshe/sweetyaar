#pragma once

#include <stdint.h>

struct LedColor {
    uint8_t red;
    uint8_t green;
    uint8_t blue;
    uint8_t white;
};

namespace LedColors {
static constexpr LedColor OFF    = {0, 0, 0, 0};
static constexpr LedColor RED    = {255, 0, 0, 0};
static constexpr LedColor GREEN  = {0, 255, 0, 0};
static constexpr LedColor BLUE   = {0, 0, 255, 0};
static constexpr LedColor YELLOW = {255, 255, 0, 0};
static constexpr LedColor PURPLE = {255, 0, 255, 0};
static constexpr LedColor WHITE  = {0, 0, 0, 255};
}

// These are semantic inputs, not physical LED modes. The controller resolves
// simultaneous signals by priority and consumes the one-shot PairingReset.
enum class StatusSignal : uint8_t {
    Initializing = 0,
    Error,
    BluetoothPlaying,
    BluetoothConnected,
    LocalPlayback,
    Killswitch,
    Ready,
    Pairing,
    PairingReset, // One red flash requested by the approval-reset action.
};

constexpr uint32_t statusSignalBit(StatusSignal signal) {
    return 1UL << static_cast<uint8_t>(signal);
}

enum class StatusLedMode : uint8_t {
    Off,
    Initializing,
    Error,
    BluetoothPlaying,
    BluetoothConnected,
    LocalPlayback,
    Killswitch,
    Ready,
    Pairing,
    PairingReset,
};

struct StatusLedPattern {
    StatusLedMode mode;
    LedColor color;
    uint16_t onMs;
    uint16_t offMs;
};

struct StatusLedModeDefinition {
    const char* condition;
    const char* colorName;
    StatusLedPattern pattern;
};

StatusLedModeDefinition statusLedModeDefinition(StatusLedMode mode);
StatusLedPattern selectStatusLedPattern(uint32_t signals);

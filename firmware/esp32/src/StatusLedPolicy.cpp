#include "StatusLedPolicy.h"

namespace {
bool hasSignal(uint32_t signals, StatusSignal signal) {
    return (signals & statusSignalBit(signal)) != 0;
}
}  // namespace

StatusLedModeDefinition statusLedModeDefinition(StatusLedMode mode) {
    switch (mode) {
        case StatusLedMode::Pairing:
            return {"pairing window open", "blue",
                    {StatusLedMode::Pairing, LedColors::BLUE, 200, 200}};
        case StatusLedMode::PairingReset:
            return {"Bluetooth approvals cleared", "red",
                    {StatusLedMode::PairingReset, LedColors::RED, 250, 0}};
        case StatusLedMode::Initializing:
            return {"initialization", "yellow",
                    {StatusLedMode::Initializing, LedColors::YELLOW, 0, 0}};
        case StatusLedMode::Error:
            return {"persistent error", "red",
                    {StatusLedMode::Error, LedColors::RED, 250, 250}};
        case StatusLedMode::BluetoothPlaying:
            return {"BT audio playing", "blue",
                    {StatusLedMode::BluetoothPlaying, LedColors::BLUE, 500, 500}};
        case StatusLedMode::BluetoothConnected:
            return {"BT connected, idle", "blue",
                    {StatusLedMode::BluetoothConnected, LedColors::BLUE, 1000, 1000}};
        case StatusLedMode::LocalPlayback:
            return {"local playback", "green",
                    {StatusLedMode::LocalPlayback, LedColors::GREEN, 500, 500}};
        case StatusLedMode::Killswitch:
            return {"Quiet time", "purple",
                    {StatusLedMode::Killswitch, LedColors::PURPLE, 1000, 250}};
        case StatusLedMode::Ready:
            return {"ready/idle", "green",
                    {StatusLedMode::Ready, LedColors::GREEN, 1000, 1000}};
        case StatusLedMode::Off:
        default:
            return {"deep sleep/off", "off",
                    {StatusLedMode::Off, LedColors::OFF, 0, 0}};
    }
}

StatusLedPattern selectStatusLedPattern(uint32_t signals) {
    if (hasSignal(signals, StatusSignal::PairingReset)) {
        return statusLedModeDefinition(StatusLedMode::PairingReset).pattern;
    }
    // Initialization deliberately masks faults until initialization finishes;
    // a latched Error signal then becomes visible immediately.
    if (hasSignal(signals, StatusSignal::Initializing)) {
        return statusLedModeDefinition(StatusLedMode::Initializing).pattern;
    }
    if (hasSignal(signals, StatusSignal::Pairing)) {
        // The full enrollment window must remain visible even during audio
        // and after either transport connects.
        return statusLedModeDefinition(StatusLedMode::Pairing).pattern;
    }
    if (hasSignal(signals, StatusSignal::Error)) {
        return statusLedModeDefinition(StatusLedMode::Error).pattern;
    }
    if (hasSignal(signals, StatusSignal::BluetoothPlaying)) {
        return statusLedModeDefinition(StatusLedMode::BluetoothPlaying).pattern;
    }
    // BLE remote ownership does not change the toy's operational mode/color.
    // Only a Classic audio connection uses the normal blue BT indication.
    if (hasSignal(signals, StatusSignal::BluetoothConnected)) {
        return statusLedModeDefinition(StatusLedMode::BluetoothConnected).pattern;
    }
    if (hasSignal(signals, StatusSignal::Killswitch)) {
        return statusLedModeDefinition(StatusLedMode::Killswitch).pattern;
    }
    if (hasSignal(signals, StatusSignal::LocalPlayback)) {
        return statusLedModeDefinition(StatusLedMode::LocalPlayback).pattern;
    }
    if (hasSignal(signals, StatusSignal::Ready)) {
        return statusLedModeDefinition(StatusLedMode::Ready).pattern;
    }
    return statusLedModeDefinition(StatusLedMode::Off).pattern;
}

#include "SystemSoundOutput.h"

extern const uint8_t readyStart[] asm("_binary_assets_sounds_ready_wav_start");
extern const uint8_t readyEnd[] asm("_binary_assets_sounds_ready_wav_end");
extern const uint8_t errorStart[] asm("_binary_assets_sounds_error_wav_start");
extern const uint8_t errorEnd[] asm("_binary_assets_sounds_error_wav_end");
extern const uint8_t pairingStart[] asm("_binary_assets_sounds_pairing_wav_start");
extern const uint8_t pairingEnd[] asm("_binary_assets_sounds_pairing_wav_end");
extern const uint8_t batteryStart[] asm("_binary_assets_sounds_battery_wav_start");
extern const uint8_t batteryEnd[] asm("_binary_assets_sounds_battery_wav_end");
extern const uint8_t chargerStart[] asm("_binary_assets_sounds_charger_wav_start");
extern const uint8_t chargerEnd[] asm("_binary_assets_sounds_charger_wav_end");

SystemSoundAsset systemSoundAsset(SystemSound sound) {
    switch (sound) {
        case SystemSound::Ready: return {readyStart, size_t(readyEnd - readyStart)};
        case SystemSound::Error: return {errorStart, size_t(errorEnd - errorStart)};
        case SystemSound::Pairing: return {pairingStart, size_t(pairingEnd - pairingStart)};
        case SystemSound::Battery: return {batteryStart, size_t(batteryEnd - batteryStart)};
        case SystemSound::Charger: return {chargerStart, size_t(chargerEnd - chargerStart)};
        default: return {nullptr, 0};
    }
}

const char* systemSoundName(SystemSound sound) {
    switch (sound) {
        case SystemSound::Ready: return "ready";
        case SystemSound::Error: return "error";
        case SystemSound::Pairing: return "pairing";
        case SystemSound::Battery: return "battery";
        case SystemSound::Charger: return "charger";
        default: return "none";
    }
}

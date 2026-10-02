#include "SystemSoundOutput.h"

extern const uint8_t readyStart[] asm("_binary_assets_sounds_ready_wav_start");
extern const uint8_t readyEnd[] asm("_binary_assets_sounds_ready_wav_end");
extern const uint8_t errorStart[] asm("_binary_assets_sounds_error_wav_start");
extern const uint8_t errorEnd[] asm("_binary_assets_sounds_error_wav_end");
extern const uint8_t pairingStart[] asm("_binary_assets_sounds_pairing_wav_start");
extern const uint8_t pairingEnd[] asm("_binary_assets_sounds_pairing_wav_end");

SystemSoundAsset systemSoundAsset(SystemSound sound) {
    switch (sound) {
        case SystemSound::Ready: return {readyStart, size_t(readyEnd - readyStart)};
        case SystemSound::Error: return {errorStart, size_t(errorEnd - errorStart)};
        case SystemSound::Pairing: return {pairingStart, size_t(pairingEnd - pairingStart)};
        default: return {nullptr, 0};
    }
}

const char* systemSoundName(SystemSound sound) {
    switch (sound) {
        case SystemSound::Ready: return "ready";
        case SystemSound::Error: return "error";
        case SystemSound::Pairing: return "pairing";
        default: return "none";
    }
}

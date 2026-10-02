#include <cassert>
#include <atomic>
#include <cstring>
#include <iostream>
#include "PairingPolicy.h"
#include "BleIdentity.h"
#include "StatusLedPolicy.h"

using Action = PairingPolicy::Action;

// Exercise the real LED scheduler; replace only the physical pixel write.
struct StatusLed {
    bool _initialized = true, _phaseOn = false;
    uint32_t _phaseStartedMs = 0;
    std::atomic<uint32_t> _signals{0};
    StatusLedMode _mode = StatusLedMode::Off;
    LedColor color = LedColors::OFF;
    int writes = 0;
    void showColor(LedColor next) { color = next; ++writes; }
    void service(uint32_t);
};
#include "status_led_service_under_test.inc"

int main() {
    PairingPolicy p;
    assert(!p.open());
    assert(p.update(0, false, true) == Action::None);
    // Fingers need not land in exactly the same loop iteration.
    assert(p.update(10, false, false) == Action::None);
    assert(p.update(60, true, false) == Action::None);
    assert(p.update(3059, true, false) == Action::None);
    assert(p.update(3060, true, false) == Action::Open);
    assert(p.open());
    assert(p.update(10059, true, false) == Action::None);
    assert(p.update(10060, true, false) == Action::Forget);
    assert(!p.open());
    assert(p.update(13060, true, false) == Action::None);
    assert(p.update(20060, true, false) == Action::None);
    // Releasing only one button cannot rearm the gesture.
    assert(p.update(21000, false, false) == Action::None);
    assert(p.update(21060, true, false) == Action::None);
    assert(p.update(40000, true, false) == Action::None);
    p.update(41000, false, true);
    p.update(42000, true, false);
    assert(p.update(45000, true, false) == Action::Open);
    p.update(45050, false, true);
    // Connection events never shorten or extend this absolute window.
    assert(p.update(104999, false, true) == Action::None && p.open());
    assert(p.update(105000, false, true) == Action::Close && !p.open());

    PairingPolicy wrap;
    const uint32_t start = 0xfffff000;
    wrap.update(start, true, false);
    assert(wrap.update(start + 3000, true, false) == Action::Open);
    wrap.update(start + 3100, false, true);
    assert(wrap.update(start + 63000, false, true) == Action::Close);
    PairingPolicy skipped;
    skipped.update(0, true, false);
    assert(skipped.update(13000, true, false) == Action::Forget); // never briefly reopen

    const auto pairing = statusSignalBit(StatusSignal::Pairing);
    auto pattern = selectStatusLedPattern(pairing | statusSignalBit(StatusSignal::Ready));
    assert(pattern.mode == StatusLedMode::Pairing && pattern.onMs == 200 && pattern.offMs == 200);
    const auto playing = statusSignalBit(StatusSignal::BluetoothPlaying);
    pattern = selectStatusLedPattern(pairing | playing);
    assert(pattern.mode == StatusLedMode::Pairing && pattern.onMs == 200 && pattern.offMs == 200);
    pattern = selectStatusLedPattern(playing);
    assert(pattern.mode == StatusLedMode::BluetoothPlaying && pattern.onMs == 500);
    pattern = selectStatusLedPattern(pairing | statusSignalBit(StatusSignal::PairingReset));
    assert(pattern.mode == StatusLedMode::PairingReset && pattern.onMs == 250 && pattern.offMs == 0);

    StatusLed led;
    const auto reset = statusSignalBit(StatusSignal::PairingReset);
    led._signals = reset | statusSignalBit(StatusSignal::Ready);
    led.service(10000);
    assert(led.color.red == 255 && led.writes == 1);
    led.service(10249);
    assert(led.color.red == 255 && led.writes == 1);
    assert(led._signals.load() & reset);
    led.service(10250);
    assert(led._mode == StatusLedMode::Ready && led.color.green == 255 && led.writes == 2);
    assert(led._signals.load() == statusSignalBit(StatusSignal::Ready));
    led.service(11250);
    assert(led.color.green == 0);
    led.service(12250);
    assert(led.color.green == 255);
    led.service(13000);
    led.service(70000);
    assert(led._mode == StatusLedMode::Ready); // consumed request cannot flash again
    led._signals = pairing;
    led.service(71000);
    assert(led.color.blue == 255);
    led._signals = pairing | playing;
    led.service(71199);
    assert(led.color.blue == 255);
    led.service(71200);
    assert(led.color.blue == 0);
    led.service(71400);
    assert(led.color.blue == 255);
    led._signals = playing; // window closes while the audio continues
    led.service(72000);
    led.service(72499);
    assert(led.color.blue == 255);
    led.service(72500);
    assert(led.color.blue == 0);

    // Restore the current state, including changes during the flash. Check
    // wraparound timing and that a later, separate reset can flash again.
    const uint32_t flashStart = 0xfffffff0;
    for (const auto state : {StatusSignal::LocalPlayback, StatusSignal::Killswitch,
                             StatusSignal::Error}) {
        StatusLed current;
        current._signals = reset | statusSignalBit(StatusSignal::Ready);
        current.service(flashStart);
        current._signals = reset | statusSignalBit(state);
        current.service(flashStart + 249);
        assert(current._mode == StatusLedMode::PairingReset && current.color.red == 255);
        current.service(flashStart + 250);
        const auto normal = selectStatusLedPattern(statusSignalBit(state));
        assert(current._mode == normal.mode && current._phaseOn);
        assert(current._signals.load() == statusSignalBit(state));
        assert(current.color.red == normal.color.red && current.color.green == normal.color.green &&
               current.color.blue == normal.color.blue);
        current.service(flashStart + 250 + normal.onMs);
        assert(!current._phaseOn); // normal blinking resumes after the request is consumed
        current.service(flashStart + 250 + normal.onMs + normal.offMs);
        assert(current._phaseOn);
        current.service(flashStart + 2000);
        current._signals.fetch_or(reset); // new action needs no persistent reset state cleared first
        current.service(flashStart + 3000);
        assert(current._mode == StatusLedMode::PairingReset);
        current.service(flashStart + 3250);
        assert(current._mode == normal.mode);
    }

    // Bluetooth Core ah() sample. Test the endian conversion against the
    // published AES key/input/output, with AES itself supplied by mbedTLS.
    const uint8_t address[6] = {0x70,0x81,0x94,0x0d,0xfb,0xaa};
    const uint8_t key[16] = {0x9b,0x7d,0x39,0x0a,0xa6,0x10,0x10,0x34,0x05,0xad,0xc8,0x57,0xa3,0x34,0x02,0xec};
    uint8_t irk[16];
    for (int i = 0; i < 16; ++i) irk[i] = key[15-i];
    const auto encryptSample = [&](const uint8_t* k, const uint8_t* input, uint8_t* output) {
        assert(memcmp(k, key, 16) == 0);
        for (int i = 0; i < 13; ++i) assert(input[i] == 0);
        assert(memcmp(input + 13, address, 3) == 0);
        output[13] = 0x0d; output[14] = 0xfb; output[15] = 0xaa;
        return true;
    };
    assert(bleResolvableAddressMatches(address, irk, encryptSample));
    uint8_t different[6]; memcpy(different, address, 6); different[5] ^= 1;
    assert(!bleResolvableAddressMatches(different, irk, encryptSample));
    different[0] = 0xc0;
    assert(!bleResolvableAddressMatches(different, irk, encryptSample));
    std::cout << "pairing policy tests passed\n";
}

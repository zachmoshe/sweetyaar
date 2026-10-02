#include <cassert>
#include <cstdint>
#include <iostream>
#include <stdexcept>
#include <string>
#include "StateMachine.h"
#include "ClassicBluetooth.h"
#include "bluetooth_reopen_constants.inc"

uint32_t g_fakeMillis = 1000;
StateMachine sm;
bool btReopenPending = false;
uint32_t btReopenAtMs = 0;
uint32_t rtcHeapRestartCount = 0;
uint32_t rtcHeapRestartMagic = 0;

// Healthy heap: these scenarios must not restart or enter deep sleep.
constexpr int MALLOC_CAP_8BIT = 1;
struct { uint32_t getFreeHeap() { return 50000; } } ESP;
unsigned heap_caps_get_free_size(int) { return 50000; }
unsigned heap_caps_get_largest_free_block(int) { return 40000; }
void delay(uint32_t) { throw std::runtime_error("Unexpected blocking delay"); }
void esp_restart() { throw std::runtime_error("Unexpected reboot"); }
void enterIdleDeepSleep() { throw std::runtime_error("Unexpected deep sleep"); }

// Fixture: disconnected phone with a saved bond; pairing remains closed.
struct {
    bool pairingOpen() { return false; }
    bool classicConnectionsAllowed() { return true; }
} bluetoothAccess;
bool radioConnectable = false;
bool radioDiscoverable = false;
bool radioPairable = false;
void BTA_DmSetVisibility(uint16_t discovery, uint16_t connection, uint8_t pairing, uint8_t) {
    radioConnectable = (connection & 0xff) != 0;
    radioDiscoverable = (discovery & 0xff) != 0;
    radioPairable = pairing != 0;
}
#include "classic_scan_access.inc"

struct Sink {
    bool is_connected() { return false; }
    void set_connectable(bool enabled) { set_scan_mode_connectable(enabled); }
    void set_scan_mode_connectable(bool enabled) { ClassicBluetooth::setAccess(enabled); }
    void set_auto_reconnect(bool enabled, int) { assert(!enabled); }
#include "classic_refresh_access.inc"
} sink;
Sink* btSink = &sink;
#include "bluetooth_reopen.inc"

void event(Event value, State expected) {
    sm.postEvent(value);
    sm.process();
    assert(sm.currentState() == expected);
}

void trace(const char* step) {
    std::cout << "t=" << millis() << " " << step
              << " state=" << stateToString(sm.currentState())
              << " pending=" << btReopenPending
              << " connectable=" << radioConnectable << '\n';
    assert(!radioDiscoverable && !radioPairable);
}

int main(int argc, char** argv) {
    assert(argc == 2);
    const std::string scenario = argv[1];
    assert(scenario == "idle" || scenario == "song" || scenario == "short-animal");
    sm.begin();
    event(Event::BT_CONNECTED, State::BT_STREAMING);
    event(Event::BT_DISCONNECTED, State::IDLE);
    // The library restores access on disconnect; main's BT->IDLE entry then
    // schedules its cooldown. Start at that boundary using the real functions.
    sink.refreshAccess();
    assert(radioConnectable);
    const uint32_t disconnectedAt = millis();
    scheduleBluetoothReopen("BT disconnected");
    assert(btReopenPending && !radioConnectable);
    trace("disconnect cooldown scheduled");

    g_fakeMillis = disconnectedAt + 100;
    if (scenario == "song") event(Event::BUTTON1_PRESS, State::PLAYING_SONG);
    if (scenario == "short-animal") event(Event::BUTTON2_PRESS, State::PLAYING_ANIMAL);
    pollBluetoothReopen();
    bool cooldownHeld = !radioConnectable;
    trace("100 ms after disconnect");

    if (scenario == "short-animal") {
        g_fakeMillis = disconnectedAt + 400;
        event(Event::WAV_FINISHED, State::IDLE);
        pollBluetoothReopen();
        cooldownHeld &= !radioConnectable;
        trace("short sound finished before deadline");
    }
    g_fakeMillis = disconnectedAt + BT_REOPEN_DELAY_MS - 1;
    pollBluetoothReopen();
    cooldownHeld &= !radioConnectable;
    trace("just before deadline");

    g_fakeMillis = disconnectedAt + BT_REOPEN_DELAY_MS;
    pollBluetoothReopen();
    const bool restoredAtDeadline = radioConnectable;
    trace("cooldown elapsed");

    g_fakeMillis += 500;
    if (scenario == "song") event(Event::WAV_FINISHED, State::IDLE);
    assert(sm.currentState() == State::IDLE);
    pollBluetoothReopen();
    trace("back at idle after deadline");

    if (!cooldownHeld) {
        std::cerr << "FAIL: Classic connections reopened before the cooldown expired\n";
        return 1;
    }
    if (!restoredAtDeadline || !radioConnectable) {
        std::cerr << "FAIL: approved phone cannot reconnect after cooldown; "
                     "Classic remains non-connectable even after returning to idle\n";
        return 1;
    }
    assert(!btReopenPending);
    std::cout << "Bluetooth cooldown test passed: " << scenario << '\n';
}

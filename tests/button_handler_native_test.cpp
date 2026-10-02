#include "ButtonHandler.h"
#include "PairingPolicy.h"
#include <cassert>
#include <iostream>

uint32_t g_fakeMillis = 0;
static bool down1 = false;
static bool down2 = false;

void pinMode(int pin, int mode) {
    assert(pin == PIN_BTN1 || pin == PIN_BTN2);
    assert(mode == INPUT_PULLUP);
}

int digitalRead(int pin) {
    assert(pin == PIN_BTN1 || pin == PIN_BTN2);
    return (pin == PIN_BTN1 ? down1 : down2) ? LOW : HIGH;
}

struct Fixture {
    ButtonHandler buttons;
    PairingPolicy pairing;
    unsigned songs = 0, animals = 0, stops = 0, opens = 0, forgets = 0;
    bool ignorePlayback = false;

    explicit Fixture(uint32_t start = 100) {
        g_fakeMillis = start;
        down1 = down2 = false;
        buttons.begin();
        poll();
    }

    void poll() {
        buttons.update();
        const auto action = pairing.update(g_fakeMillis, buttons.isBothHeld(), buttons.areBothReleased());
        if (action == PairingPolicy::Action::Open) ++opens;
        if (action == PairingPolicy::Action::Forget) ++forgets;
        // Same event order as the firmware loop, including ignored playback modes.
        if (ignorePlayback) buttons.discardEvents();
        else if (buttons.wasBothPressed()) ++stops;
        else if (buttons.wasBtn1Pressed()) ++songs;
        else if (buttons.wasBtn2Pressed()) ++animals;
    }

    void wait(uint32_t duration) {
        for (uint32_t i = 0; i < duration; ++i) {
            ++g_fakeMillis;
            poll();
        }
    }

    void press(bool first, bool second) {
        down1 = first;
        down2 = second;
        poll();
    }
};

static void testStaggeredChords() {
    for (bool songFirst : {false, true}) {
        for (uint32_t gap : {0u, 1u, 5u, 49u, 99u, 100u, 150u, 249u, 250u}) {
            Fixture f;
            f.press(songFirst, !songFirst);
            f.wait(gap);
            f.press(true, true);
            f.wait(DEBOUNCE_MS);
            assert(f.songs == 0 && f.animals == 0 && f.stops == 1);
            f.wait(2999);
            assert(f.opens == 0);
            f.wait(1);
            assert(f.opens == 1 && f.forgets == 0);
            f.wait(6999);
            assert(f.forgets == 0);
            f.wait(1);
            assert(f.forgets == 1 && !f.pairing.open());
            f.wait(3000);
            assert(f.opens == 1 && f.forgets == 1);
            assert(f.songs == 0 && f.animals == 0 && f.stops == 1);
        }
    }
}

static void testSinglePressAndQuickTaps() {
    for (bool song : {false, true}) {
        Fixture f;
        f.press(song, !song);
        f.wait(DEBOUNCE_MS + 249);
        assert(f.songs == 0 && f.animals == 0);
        f.wait(1);
        assert(f.songs == unsigned(song) && f.animals == unsigned(!song));
        f.wait(500);
        assert(f.songs + f.animals == 1);
        f.press(false, false);
        f.wait(DEBOUNCE_MS);

        // Releasing a short tap resolves it immediately after debounce.
        // A second tap within the grace period must not swallow the first one.
        for (int tap = 0; tap < 2; ++tap) {
            f.press(song, !song);
            f.wait(60);
            f.press(false, false);
            f.wait(DEBOUNCE_MS);
            assert(f.songs + f.animals == unsigned(tap + 2));
        }
        f.wait(500);
        assert(f.songs + f.animals == 3 && f.stops == 0);
    }
}

static void testSeparateButtonsAreNotAChord() {
    Fixture f;
    f.press(true, false);
    f.wait(60);
    f.press(false, false);
    f.wait(DEBOUNCE_MS);
    f.press(false, true);
    f.wait(60);
    f.press(false, false);
    f.wait(500);
    assert(f.songs == 1 && f.animals == 1 && f.stops == 0);
}

static void testLateSecondPressStopsAlreadyStartedSong() {
    Fixture f;
    f.press(true, false);
    f.wait(DEBOUNCE_MS + 251);
    assert(f.songs == 1);
    f.press(true, true);
    f.wait(DEBOUNCE_MS + 500);
    assert(f.stops == 1 && f.animals == 0);
}

static void testPartialReleaseDoesNotRearm() {
    Fixture f;
    f.press(true, true);
    f.wait(DEBOUNCE_MS + 3000);
    assert(f.opens == 1 && f.stops == 1);
    f.press(false, true);
    f.wait(DEBOUNCE_MS);
    f.press(true, true);
    f.wait(DEBOUNCE_MS + 13000);
    assert(f.opens == 1 && f.forgets == 0 && f.stops == 1);
    assert(f.songs == 0 && f.animals == 0);
    f.press(false, false);
    f.wait(DEBOUNCE_MS);
    f.press(true, true);
    f.wait(DEBOUNCE_MS + 3000);
    assert(f.opens == 2 && f.stops == 2);
}

static void testBounceAndWraparound() {
    Fixture bounce;
    for (int i = 0; i < 5; ++i) {
        bounce.press(true, false);
        bounce.wait(5);
        bounce.press(false, true);
        bounce.wait(5);
    }
    bounce.press(false, false);
    bounce.wait(500);
    assert(bounce.songs == 0 && bounce.animals == 0 && bounce.stops == 0);

    Fixture wrap(UINT32_MAX - 100);
    wrap.press(true, false);
    wrap.wait(200);
    wrap.press(true, true);
    wrap.wait(DEBOUNCE_MS + 3000);
    assert(wrap.songs == 0 && wrap.animals == 0 && wrap.stops == 1 && wrap.opens == 1);
}

static void testIgnoredPlaybackKeepsPairingGesture() {
    Fixture f;
    f.ignorePlayback = true;
    f.press(true, false);
    f.wait(200);
    f.press(true, true);
    f.wait(DEBOUNCE_MS + 3000);
    assert(f.opens == 1 && f.songs == 0 && f.animals == 0 && f.stops == 0);
    f.ignorePlayback = false;
    f.wait(500);
    assert(f.songs == 0 && f.animals == 0 && f.stops == 0);
}

int main() {
    testStaggeredChords();
    testSinglePressAndQuickTaps();
    testSeparateButtonsAreNotAChord();
    testLateSecondPressStopsAlreadyStartedSong();
    testPartialReleaseDoesNotRearm();
    testBounceAndWraparound();
    testIgnoredPlaybackKeepsPairingGesture();
    std::cout << "button chord and pairing tests passed\n";
}

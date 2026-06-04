#include <cassert>
#include <cstdint>
#include <iostream>

#include "StateMachine.h"

uint32_t g_fakeMillis = 0;

namespace {

void expectState(const StateMachine& sm, State expected) {
    assert(sm.currentState() == expected);
}

void postAndProcess(StateMachine& sm, Event event, State expected) {
    sm.postEvent(event);
    sm.process();
    expectState(sm, expected);
}

void testLocalPlaybackTransitions() {
    StateMachine sm;
    sm.begin();

    expectState(sm, State::IDLE);
    postAndProcess(sm, Event::BUTTON1_PRESS, State::PLAYING_SONG);
    postAndProcess(sm, Event::BUTTON2_PRESS, State::PLAYING_ANIMAL);
    postAndProcess(sm, Event::BUTTON1_PRESS, State::PLAYING_SONG);
    postAndProcess(sm, Event::BOTH_BUTTONS_PRESS, State::IDLE);

    postAndProcess(sm, Event::BUTTON2_PRESS, State::PLAYING_ANIMAL);
    postAndProcess(sm, Event::WAV_FINISHED, State::IDLE);
}

void testBtStreamingIgnoresLocalControls() {
    StateMachine sm;
    sm.begin();

    postAndProcess(sm, Event::BUTTON1_PRESS, State::PLAYING_SONG);
    postAndProcess(sm, Event::BT_CONNECTED, State::BT_STREAMING);
    postAndProcess(sm, Event::BUTTON1_PRESS, State::BT_STREAMING);
    postAndProcess(sm, Event::BUTTON2_PRESS, State::BT_STREAMING);
    postAndProcess(sm, Event::KILLSWITCH_ON, State::BT_STREAMING);
    postAndProcess(sm, Event::BT_DISCONNECTED, State::IDLE);
}

void testKillswitchTimerAndBtInterruption() {
    StateMachine sm;
    sm.begin();

    g_fakeMillis = 100;
    postAndProcess(sm, Event::KILLSWITCH_ON, State::KILLSWITCH);
    postAndProcess(sm, Event::BUTTON1_PRESS, State::KILLSWITCH);

    g_fakeMillis = 500;
    postAndProcess(sm, Event::KILLSWITCH_ON, State::KILLSWITCH);
    assert(sm.killswitchRemainingMs() == KILLSWITCH_MS);

    postAndProcess(sm, Event::BT_CONNECTED, State::BT_STREAMING);
    g_fakeMillis = 1000;
    postAndProcess(sm, Event::BT_DISCONNECTED, State::KILLSWITCH);

    g_fakeMillis = 500 + KILLSWITCH_MS + 1;
    sm.process();
    expectState(sm, State::IDLE);
}

void testKillswitchCancel() {
    StateMachine sm;
    sm.begin();

    g_fakeMillis = 10;
    postAndProcess(sm, Event::KILLSWITCH_ON, State::KILLSWITCH);
    postAndProcess(sm, Event::KILLSWITCH_OFF, State::IDLE);
}

void testBlePayloadEventsDoNotForceTransitions() {
    StateMachine sm;
    sm.begin();

    sm.postStringEvent(Event::VOLUME_CHANGED, String("37"));
    bool changed = sm.process();
    assert(!changed);
    expectState(sm, State::IDLE);
    assert(sm.pendingVolume() == 37);

    sm.postStringEvent(Event::THEME_CHANGED, String("nature"));
    changed = sm.process();
    assert(!changed);
    expectState(sm, State::IDLE);
    assert(sm.pendingTheme() == String("nature"));
}

}  // namespace

int main() {
    testLocalPlaybackTransitions();
    testBtStreamingIgnoresLocalControls();
    testKillswitchTimerAndBtInterruption();
    testKillswitchCancel();
    testBlePayloadEventsDoNotForceTransitions();
    std::cout << "state-machine native test passed\n";
    return 0;
}

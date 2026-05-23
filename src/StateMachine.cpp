#include "StateMachine.h"
#include <freertos/FreeRTOS.h>
#include <freertos/queue.h>

// ---------------------------------------------------------------------------
const char* stateToString(State s) {
    switch (s) {
        case State::IDLE:           return "idle";
        case State::PLAYING_SONG:   return "playing_song";
        case State::PLAYING_ANIMAL: return "playing_animal";
        case State::BT_STREAMING:   return "bt_streaming";
        case State::KILLSWITCH:     return "killswitch";
        default:                    return "unknown";
    }
}

const char* eventToString(Event e) {
    switch (e) {
        case Event::NONE:               return "NONE";
        case Event::BUTTON1_PRESS:      return "BUTTON1";
        case Event::BUTTON2_PRESS:      return "BUTTON2";
        case Event::BOTH_BUTTONS_PRESS: return "BOTH_BUTTONS";
        case Event::BT_CONNECTED:       return "BT_CONNECTED";
        case Event::BT_DISCONNECTED:    return "BT_DISCONNECTED";
        case Event::WAV_FINISHED:       return "WAV_FINISHED";
        case Event::KILLSWITCH_ON:      return "KILLSWITCH_ON";
        case Event::KILLSWITCH_OFF:     return "KILLSWITCH_OFF";
        case Event::THEME_CHANGED:      return "THEME_CHANGED";
        case Event::VOLUME_CHANGED:     return "VOLUME_CHANGED";
        case Event::KILLSWITCH_EXPIRED: return "KILLSWITCH_EXPIRED";
        default:                        return "?";
    }
}

// ---------------------------------------------------------------------------
void StateMachine::begin() {
    ensureQueue();
}

// ---------------------------------------------------------------------------
bool StateMachine::ensureQueue() {
    if (!_queue) {
        _queue = xQueueCreate(16, sizeof(QueueItem));
    }
    return _queue != nullptr;
}

// ---------------------------------------------------------------------------
void StateMachine::postEvent(Event e) {
    if (!ensureQueue()) {
        return;
    }
    QueueItem item{};
    item.event = e;
    xQueueSend(_queue, &item, 0);  // non-blocking; drop if full
}

void StateMachine::postStringEvent(Event e, const String& payload) {
    if (!ensureQueue()) {
        return;
    }
    QueueItem item{};
    item.event = e;
    if (e == Event::THEME_CHANGED) {
        strncpy(item.theme, payload.c_str(), sizeof(item.theme) - 1);
    } else if (e == Event::VOLUME_CHANGED) {
        item.volume = (uint8_t)payload.toInt();
    }
    xQueueSend(_queue, &item, 0);
}

// ---------------------------------------------------------------------------
bool StateMachine::process() {
    if (!ensureQueue()) {
        return false;
    }

    // Check killswitch timer expiry
    if (_state == State::KILLSWITCH) {
        if (killswitchTimerExpired()) {
            postEvent(Event::KILLSWITCH_EXPIRED);
        }
    }

    State before = _state;
    QueueItem item{};
    while (xQueueReceive(_queue, &item, 0) == pdTRUE) {
        handleEvent(item);
    }

    updateLed();
    return (_state != before);
}

// ---------------------------------------------------------------------------
bool StateMachine::killswitchTimerExpired() const {
    if (_killswitchStartMs == 0) return false;
    return (millis() - _killswitchStartMs) >= KILLSWITCH_MS;
}

// ---------------------------------------------------------------------------
uint32_t StateMachine::killswitchRemainingMs() const {
    if (_killswitchStartMs == 0) return 0;
    uint32_t elapsed = millis() - _killswitchStartMs;
    if (elapsed >= KILLSWITCH_MS) return 0;
    return KILLSWITCH_MS - elapsed;
}

// ---------------------------------------------------------------------------
void StateMachine::transition(State next) {
    Serial.printf("[SM] %s → %s\n", stateToString(_state), stateToString(next));
    _state = next;
}

// ---------------------------------------------------------------------------
void StateMachine::handleEvent(const QueueItem& item) {
    Event e = item.event;
    Serial.printf("[SM] State=%s Event=%s\n", stateToString(_state), eventToString(e));

    // --- VOLUME_CHANGED is state-independent ---
    if (e == Event::VOLUME_CHANGED) {
        _pendingVolume = item.volume;
        return;  // caller handles volume application
    }

    // --- THEME_CHANGED can arrive in any state; store for caller ---
    if (e == Event::THEME_CHANGED) {
        _pendingTheme = String(item.theme);
        return;
    }

    // --- BT_CONNECTED always wins (except KILLSWITCH keeps state) ---
    if (e == Event::BT_CONNECTED) {
        if (_state == State::KILLSWITCH) {
            // BT streaming still allowed during killswitch; but we stay in
            // KILLSWITCH conceptually. Simplification: move to BT_STREAMING;
            // on disconnect return to KILLSWITCH if timer hasn't expired.
            _pendingKillswitchAfterBT = true;
        }
        transition(State::BT_STREAMING);
        return;
    }

    // --- State-specific transitions ---
    switch (_state) {

        case State::IDLE:
            switch (e) {
                case Event::BUTTON1_PRESS:
                    transition(State::PLAYING_SONG);
                    break;
                case Event::BUTTON2_PRESS:
                    transition(State::PLAYING_ANIMAL);
                    break;
                case Event::BOTH_BUTTONS_PRESS:
                    // Already idle — no-op
                    break;
                case Event::KILLSWITCH_ON:
                    _killswitchStartMs = millis();
                    transition(State::KILLSWITCH);
                    break;
                default:
                    break;
            }
            break;

        case State::PLAYING_SONG:
            switch (e) {
                case Event::BUTTON1_PRESS:
                    // "Next song" is handled directly in main.cpp when state is PLAYING_SONG
                    // — wavPlayer.nextSong() is called there, no state transition needed.
                    break;
                case Event::BUTTON2_PRESS:
                    transition(State::PLAYING_ANIMAL);
                    break;
                case Event::BOTH_BUTTONS_PRESS:
                    transition(State::IDLE);
                    break;
                case Event::WAV_FINISHED:
                    transition(State::IDLE);
                    break;
                case Event::KILLSWITCH_ON:
                    _killswitchStartMs = millis();
                    transition(State::KILLSWITCH);
                    break;
                default:
                    break;
            }
            break;

        case State::PLAYING_ANIMAL:
            switch (e) {
                case Event::BUTTON1_PRESS:
                    transition(State::PLAYING_SONG);
                    break;
                case Event::BUTTON2_PRESS:
                    // "Next animal" is handled directly in main.cpp when state is PLAYING_ANIMAL
                    // — wavPlayer.nextAnimal() is called there, no state transition needed.
                    break;
                case Event::BOTH_BUTTONS_PRESS:
                    transition(State::IDLE);
                    break;
                case Event::WAV_FINISHED:
                    transition(State::IDLE);
                    break;
                case Event::KILLSWITCH_ON:
                    _killswitchStartMs = millis();
                    transition(State::KILLSWITCH);
                    break;
                default:
                    break;
            }
            break;

        case State::BT_STREAMING:
            switch (e) {
                case Event::BT_DISCONNECTED:
                    if (_pendingKillswitchAfterBT) {
                        _pendingKillswitchAfterBT = false;
                        if (!killswitchTimerExpired()) {
                            transition(State::KILLSWITCH);
                        } else {
                            transition(State::IDLE);
                        }
                    } else {
                        transition(State::IDLE);
                    }
                    break;
                case Event::KILLSWITCH_ON:
                case Event::KILLSWITCH_OFF:
                    // Parent controls are read-only during BT streaming.
                    break;
                default:
                    break;  // Buttons disabled in BT_STREAMING
            }
            break;

        case State::KILLSWITCH:
            switch (e) {
                case Event::KILLSWITCH_ON:
                    _killswitchStartMs = millis();
                    Serial.println("[SM] Killswitch timer restarted");
                    break;
                case Event::KILLSWITCH_OFF:
                case Event::KILLSWITCH_EXPIRED:
                    _killswitchStartMs = 0;
                    transition(State::IDLE);
                    break;
                default:
                    break;  // All other events ignored
            }
            break;
    }
}

// ---------------------------------------------------------------------------
// LED blink pattern per state
// ---------------------------------------------------------------------------
void StateMachine::updateLed() {
    uint32_t now = millis();
    uint32_t interval = 0;

    switch (_state) {
        case State::IDLE:           interval = 2000; break;  // slow blink: alive
        case State::PLAYING_SONG:   interval = 500;  break;  // medium: playing
        case State::PLAYING_ANIMAL: interval = 300;  break;  // faster: animal
        case State::BT_STREAMING:   interval = 100;  break;  // fast: streaming
        case State::KILLSWITCH:     interval = 1000; break;  // 1s blink: locked
    }

    if ((now - _ledLastToggleMs) >= interval) {
        _ledLastToggleMs = now;
        _ledState = !_ledState;
        digitalWrite(PIN_LED, _ledState ? HIGH : LOW);
    }
}

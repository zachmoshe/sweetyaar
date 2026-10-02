#include "ButtonHandler.h"

void ButtonHandler::begin() {
    pinMode(PIN_BTN1, INPUT_PULLUP);
    pinMode(PIN_BTN2, INPUT_PULLUP);
}

// ---------------------------------------------------------------------------
// update() — call every loop iteration
// ---------------------------------------------------------------------------
void ButtonHandler::update() {
    const uint32_t now = millis();
    updateOne(_b1, PIN_BTN1, now);
    updateOne(_b2, PIN_BTN2, now);

    bool pressed1 = _b1.debounced;
    bool pressed2 = _b2.debounced;

    // Check the chord before releasing any single-button event. Singles wait
    // briefly so staggered presses do not start a song on the way into pairing.
    // A later second press still means Stop, although the first action may
    // already have run. A released tap followed by another tap is not a chord.
    if (pressed1 && pressed2 && !_bothPressActive) {
        _bothPressActive = true;
        _evtBoth = true;
    }
    if (_bothPressActive) {
        _evt1 = _evt2 = false;
        _b1.pendingEvent = _b2.pendingEvent = false;
        if (!pressed1 && !pressed2) _bothPressActive = false;
        return;
    }

    // A released tap cannot become a chord, so it need not wait the full window.
    if (_b1.pendingEvent) {
        if (!pressed1 || (now - _b1.pressedAtMs) >= BOTH_PRESS_WINDOW_MS) {
            _evt1            = true;
            _b1.pendingEvent = false;
        }
    }
    if (_b2.pendingEvent) {
        if (!pressed2 || (now - _b2.pressedAtMs) >= BOTH_PRESS_WINDOW_MS) {
            _evt2            = true;
            _b2.pendingEvent = false;
        }
    }
}

// ---------------------------------------------------------------------------
// updateOne() — debounce a single button
// ---------------------------------------------------------------------------
void ButtonHandler::updateOne(BtnState& b, int pin, uint32_t now) {
    bool raw = (digitalRead(pin) == LOW);  // active LOW

    if (raw != b.raw) {
        b.raw          = raw;
        b.lastChangeMs = now;
    }

    if ((now - b.lastChangeMs) >= DEBOUNCE_MS) {
        bool stable = b.raw;
        if (stable != b.debounced) {
            b.debounced = stable;
            if (stable) {
                // Rising edge (button pressed)
                b.pendingEvent  = true;
                b.pressedAtMs   = now;
            }
        }
    }
}

// ---------------------------------------------------------------------------
// Event consumers — return true once, then reset
// ---------------------------------------------------------------------------
bool ButtonHandler::wasBtn1Pressed() {
    if (_evt1) { _evt1 = false; return true; }
    return false;
}

bool ButtonHandler::wasBtn2Pressed() {
    if (_evt2) { _evt2 = false; return true; }
    return false;
}

bool ButtonHandler::wasBothPressed() {
    if (_evtBoth) { _evtBoth = false; return true; }
    return false;
}

void ButtonHandler::discardEvents() {
    _evt1 = false;
    _evt2 = false;
    _evtBoth = false;
    _b1.pendingEvent = false;
    _b2.pendingEvent = false;
}

bool ButtonHandler::isBothHeld() const {
    return _b1.debounced && _b2.debounced;
}

#include "ButtonHandler.h"

void ButtonHandler::begin() {
    pinMode(PIN_BTN1, INPUT_PULLUP);
    pinMode(PIN_BTN2, INPUT_PULLUP);
}

// ---------------------------------------------------------------------------
// update() — call every loop iteration
// ---------------------------------------------------------------------------
void ButtonHandler::update() {
    updateOne(_b1, PIN_BTN1);
    updateOne(_b2, PIN_BTN2);

    bool pressed1 = _b1.debounced;
    bool pressed2 = _b2.debounced;

    // Both-held tracking
    if (pressed1 && pressed2) {
        if (!_bothCurrentlyHeld) {
            _bothCurrentlyHeld = true;
            _bothHeldSinceMs   = millis();
        }
    } else {
        _bothCurrentlyHeld = false;
        _bothHeldSinceMs   = 0;
    }

    // Simultaneous-press event: if one button just transitioned to pressed
    // while the other was already pressed (within BOTH_PRESS_WINDOW_MS),
    // emit a "both" event and clear any individual events for those presses.
    if (_b1.pendingEvent && _b2.pendingEvent) {
        // Both registered a press — fire both event regardless of timing
        _evtBoth        = true;
        _b1.pendingEvent = false;
        _b2.pendingEvent = false;
        return;
    }

    if (_b1.pendingEvent && pressed2) {
        // btn1 just pressed while btn2 was already held
        if ((millis() - _b2PressedAtMs) < BOTH_PRESS_WINDOW_MS) {
            _evtBoth        = true;
            _b1.pendingEvent = false;
            return;
        }
    }

    if (_b2.pendingEvent && pressed1) {
        // btn2 just pressed while btn1 was already held
        if ((millis() - _b1PressedAtMs) < BOTH_PRESS_WINDOW_MS) {
            _evtBoth        = true;
            _b2.pendingEvent = false;
            return;
        }
    }

    // Flush individual events if no simultaneous press detected yet
    if (_b1.pendingEvent) {
        // Wait a short window to see if btn2 also comes in
        if ((millis() - _b1.pressedAtMs) > BOTH_PRESS_WINDOW_MS) {
            _evt1            = true;
            _b1.pendingEvent = false;
        }
    }
    if (_b2.pendingEvent) {
        if ((millis() - _b2.pressedAtMs) > BOTH_PRESS_WINDOW_MS) {
            _evt2            = true;
            _b2.pendingEvent = false;
        }
    }
}

// ---------------------------------------------------------------------------
// updateOne() — debounce a single button
// ---------------------------------------------------------------------------
void ButtonHandler::updateOne(BtnState& b, int pin) {
    bool raw = (digitalRead(pin) == LOW);  // active LOW

    if (raw != b.raw) {
        b.raw          = raw;
        b.lastChangeMs = millis();
    }

    if ((millis() - b.lastChangeMs) >= DEBOUNCE_MS) {
        bool stable = b.raw;
        if (stable != b.debounced) {
            b.debounced = stable;
            if (stable) {
                // Rising edge (button pressed)
                b.pendingEvent  = true;
                b.pressedAtMs   = millis();

                // Record press time for simultaneous detection
                if (pin == PIN_BTN1) _b1PressedAtMs = b.pressedAtMs;
                if (pin == PIN_BTN2) _b2PressedAtMs = b.pressedAtMs;
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
    return _bothCurrentlyHeld;
}

uint32_t ButtonHandler::bothHeldDurationMs() const {
    if (!_bothCurrentlyHeld) return 0;
    return millis() - _bothHeldSinceMs;
}

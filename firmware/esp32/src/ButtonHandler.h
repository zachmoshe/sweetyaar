#pragma once
#include <Arduino.h>
#include "Config.h"

// ---------------------------------------------------------------------------
// ButtonHandler — debounced button reading with simultaneous-press detection
//
// Usage:
//   ButtonHandler btn;
//   btn.begin();                 // call once in setup()
//
//   // In loop() or a task:
//   btn.update();
//
//   if (btn.wasBtn1Pressed())  { ... }
//   if (btn.wasBtn2Pressed())  { ... }
//   if (btn.wasBothPressed())  { ... }
//   // PairingPolicy times holds using isBothHeld() and areBothReleased().
// ---------------------------------------------------------------------------

class ButtonHandler {
public:
    ButtonHandler() = default;

    // Configure GPIO pins; call once in setup()
    void begin();

    // Poll button state — call every loop iteration (≤10 ms period recommended)
    void update();

    // Consume events: each returns true once per physical press, then resets
    bool wasBtn1Pressed();   // Button 1 short press (not a simultaneous press)
    bool wasBtn2Pressed();   // Button 2 short press (not a simultaneous press)
    bool wasBothPressed();   // Both buttons down; once until both are released

    // Drop any pending/latched press events without changing physical state.
    void discardEvents();

    // True while both buttons are physically held; does NOT consume the event.
    bool isBothHeld() const;
    bool areBothReleased() const { return !_b1.debounced && !_b2.debounced; }

private:
    // Per-button state
    struct BtnState {
        bool     raw        = false;  // current raw reading (LOW = pressed)
        bool     debounced  = false;  // stable debounced state
        uint32_t lastChangeMs = 0;    // time of last raw change
        uint32_t pressedAtMs  = 0;    // time debounced press was detected
        bool     pendingEvent = false;
    };

    BtnState _b1, _b2;

    // Event flags (consumed by wasXxx())
    bool _evt1      = false;
    bool _evt2      = false;
    bool _evtBoth   = false;

    // Suppress individual/repeated events until both buttons are released.
    bool _bothPressActive = false;

    void updateOne(BtnState& b, int pin, uint32_t now);
};

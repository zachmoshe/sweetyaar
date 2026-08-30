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
//   if (btn.isBothHeld(3000))  { ... }  // held ≥ 3 s
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
    bool wasBothPressed();   // Both buttons pressed simultaneously

    // Drop any pending/latched press events without changing physical state.
    void discardEvents();

    // True while both buttons are physically held; does NOT consume the event.
    bool isBothHeld() const;

    // How long (ms) both buttons have been held continuously (0 if not both held)
    uint32_t bothHeldDurationMs() const;

private:
    // Per-button state
    struct BtnState {
        bool     raw        = false;  // current raw reading (LOW = pressed)
        bool     debounced  = false;  // stable debounced state
        bool     lastDebounced = false;
        uint32_t lastChangeMs = 0;    // time of last raw change
        uint32_t pressedAtMs  = 0;    // time debounced press was detected
        bool     pendingEvent = false;
    };

    BtnState _b1, _b2;

    // Event flags (consumed by wasXxx())
    bool _evt1      = false;
    bool _evt2      = false;
    bool _evtBoth   = false;

    // For simultaneous-press detection
    uint32_t _b1PressedAtMs = 0;   // time btn1 last became pressed
    uint32_t _b2PressedAtMs = 0;   // time btn2 last became pressed

    // Both-held tracking
    bool     _bothCurrentlyHeld = false;
    uint32_t _bothHeldSinceMs   = 0;

    void updateOne(BtnState& b, int pin);
};

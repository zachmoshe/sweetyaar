#pragma once
#include <Arduino.h>
#include "Config.h"

// ---------------------------------------------------------------------------
// State machine for SweetYaar
//
// States:
//   IDLE           — quiet, waiting for input
//   PLAYING_SONG   — WAV song playing from SD
//   PLAYING_ANIMAL — single animal sound playing from SD
//   BT_STREAMING   — Bluetooth A2DP audio streaming
//   KILLSWITCH     — 10-minute lockout; buttons disabled
//
// Events are posted from BT callbacks and the main loop. BLE callbacks hand
// pending writes to the main loop, which then posts state-machine events.
// The machine runs entirely in the main loop (not thread-safe by itself),
// while BT callbacks use xQueueSend() to post events safely.
// ---------------------------------------------------------------------------

enum class State {
    IDLE,
    PLAYING_SONG,
    PLAYING_ANIMAL,
    BT_STREAMING,
    KILLSWITCH,
};

enum class Event {
    NONE,
    BUTTON1_PRESS,       // btn1 short press
    BUTTON2_PRESS,       // btn2 short press
    BOTH_BUTTONS_PRESS,  // simultaneous press
    BT_CONNECTED,
    BT_DISCONNECTED,
    WAV_FINISHED,        // song or animal sound ended
    KILLSWITCH_ON,       // BLE killswitch activated
    KILLSWITCH_OFF,      // BLE killswitch cancelled
    THEME_CHANGED,       // BLE theme write received
    VOLUME_CHANGED,      // BLE volume write received
    KILLSWITCH_EXPIRED,  // 10-min timer elapsed
};

const char* stateToString(State s);
const char* eventToString(Event e);

class StateMachine {
public:
    StateMachine() = default;

    // Allocate the event queue before BT/BLE callbacks can fire.
    void begin();

    State currentState() const { return _state; }

    // Post an event; safe to call from any context (uses FreeRTOS queue)
    void postEvent(Event e);

    // Post an event with an associated string payload (theme/volume)
    void postStringEvent(Event e, const String& payload);

    // Process all queued events; MUST be called from main loop
    // Returns true if the state changed
    bool process();

    // Pending payload from the last THEME_CHANGED or VOLUME_CHANGED event
    // (valid only while processing the event in the same loop iteration)
    String pendingTheme() const  { return _pendingTheme;  }
    uint8_t pendingVolume() const { return _pendingVolume; }

    // True if killswitch timer has expired (main loop should post KILLSWITCH_EXPIRED)
    bool killswitchTimerExpired() const;
    uint32_t killswitchRemainingMs() const;

    // LED blink pattern driven by state
    void updateLed();

private:
    State _state = State::IDLE;

    // Used when BT temporarily interrupts an already-active killswitch.
    bool _pendingKillswitchAfterBT = false;

    uint32_t _killswitchStartMs = 0;

    // FreeRTOS event queue
    QueueHandle_t _queue = nullptr;

    struct QueueItem {
        Event  event;
        uint8_t volume;          // valid for VOLUME_CHANGED
        char    theme[64];       // valid for THEME_CHANGED
    };

    String  _pendingTheme;
    uint8_t _pendingVolume = 0;

    // LED
    uint32_t _ledLastToggleMs = 0;
    bool     _ledState        = false;

    void transition(State next);
    void handleEvent(const QueueItem& item);
    bool ensureQueue();
};

#pragma once
#include <stdint.h>

// Main-loop policy; unsigned elapsed times remain correct across millis() wrap.
class PairingPolicy {
public:
    enum class Action { None, Open, Close, Forget };
    static constexpr uint32_t OPEN_HOLD_MS = 3000;
    static constexpr uint32_t FORGET_HOLD_MS = 10000;
    static constexpr uint32_t WINDOW_MS = 60000;

    Action update(uint32_t now, bool bothHeld, bool bothReleased) {
        if (bothReleased) {
            _timing = false;
            _consumed = false;
            _openedThisHold = false;
        } else if (!bothHeld) {
            if (_timing) _consumed = true;
            _timing = false;
        } else if (!_consumed) {
            if (!_timing) {
                _timing = true;
                _heldSince = now;
            }
            const uint32_t held = now - _heldSince;
            if (held >= FORGET_HOLD_MS) {
                _consumed = true;
                _open = false;
                return Action::Forget;
            }
            if (!_openedThisHold && held >= OPEN_HOLD_MS) {
                _openedThisHold = true;
                _open = true;
                _openedAt = now;
                return Action::Open;
            }
        }
        if (_open && now - _openedAt >= WINDOW_MS) {
            _open = false;
            return Action::Close;
        }
        return Action::None;
    }
    bool open() const { return _open; }
private:
    bool _timing = false;
    bool _consumed = false;
    bool _openedThisHold = false;
    bool _open = false;
    uint32_t _heldSince = 0;
    uint32_t _openedAt = 0;
};

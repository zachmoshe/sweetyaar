#pragma once

#include <cstdint>

// A fresh, bounded observation for each sleep attempt; no fault history is kept.
class SleepEntryCheck {
public:
    enum class Result { Sampling, Quiet, Movement, PossiblyDisconnected };

    bool active() const { return _active; }
    void reset() { _active = false; }

    Result update(uint32_t nowMs, bool wakeHigh) {
        if (!_active) {
            _active = true;
            _startedAtMs = _lastSampleAtMs = nowMs;
            _sawHigh = wakeHigh;
            _sawLow = !wakeHigh;
            return Result::Sampling;
        }
        if (nowMs - _lastSampleAtMs < 20) {
            return Result::Sampling;
        }

        _lastSampleAtMs = nowMs;
        _sawHigh |= wakeHigh;
        _sawLow |= !wakeHigh;
        if (nowMs - _startedAtMs < 500) {
            return Result::Sampling;
        }

        reset();
        if (!_sawHigh) return Result::Quiet;
        return _sawLow ? Result::Movement : Result::PossiblyDisconnected;
    }

private:
    uint32_t _startedAtMs = 0;
    uint32_t _lastSampleAtMs = 0;
    bool _active = false;
    bool _sawHigh = false;
    bool _sawLow = false;
};

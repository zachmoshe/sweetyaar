#include "SleepEntryCheck.h"

#include <cassert>
#include <cstdint>
#include <iostream>

using Result = SleepEntryCheck::Result;

template <typename Signal>
Result observe(SleepEntryCheck& check, uint32_t start, Signal highAt) {
    for (uint32_t elapsed = 0; elapsed < 500; elapsed += 20) {
        assert(check.update(start + elapsed, highAt(elapsed)) == Result::Sampling);
        assert(check.active());
    }
    const auto result = check.update(start + 500, highAt(500));
    assert(!check.active());
    return result;
}

int main() {
    SleepEntryCheck check;
    const auto low = [](uint32_t) { return false; };
    const auto high = [](uint32_t) { return true; };

    assert(observe(check, 0, low) == Result::Quiet);
    assert(observe(check, 1000, high) == Result::PossiblyDisconnected);

    // A single HIGH at any sampled point prevents sleep without a fault warning.
    for (uint32_t pulse = 0; pulse <= 500; pulse += 20) {
        assert(observe(check, 2000, [pulse](uint32_t t) { return t == pulse; })
               == Result::Movement);
    }
    // A single LOW means we cannot classify the entire window as open.
    assert(observe(check, 3000, [](uint32_t t) { return t != 240; })
           == Result::Movement);

    // No persistent fault history: a new quiet attempt can sleep immediately
    // after its own complete window, and each all-HIGH attempt reports again.
    assert(observe(check, 4000, high) == Result::PossiblyDisconnected);
    assert(observe(check, 5000, low) == Result::Quiet);
    assert(observe(check, 6000, high) == Result::PossiblyDisconnected);

    // Activity cancels an in-progress window, including its HIGH observations.
    assert(check.update(7000, true) == Result::Sampling);
    assert(check.update(7400, true) == Result::Sampling);
    check.reset();
    assert(!check.active());
    assert(observe(check, 7500, low) == Result::Quiet);

    // Fast polling cannot finish early, and the final sample is included.
    assert(check.update(9000, false) == Result::Sampling);
    for (uint32_t elapsed = 1; elapsed < 500; ++elapsed) {
        assert(check.update(9000 + elapsed, false) == Result::Sampling);
    }
    assert(check.update(9500, true) == Result::Movement);

    // Unsigned elapsed-time arithmetic survives the millis() wraparound.
    assert(observe(check, UINT32_MAX - 250, low) == Result::Quiet);
    assert(observe(check, UINT32_MAX - 250, high) == Result::PossiblyDisconnected);

    std::cout << "sleep-entry check native test passed\n";
}

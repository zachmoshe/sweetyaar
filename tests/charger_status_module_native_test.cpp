#include <cassert>
#include <cstring>
#include <iostream>

#include "ChargerStatus.h"

using namespace ChargerStatus;

int main() {
    uint8_t bytes[ENCODED_SIZE];
    encode(Snapshot{}, bytes);
    const uint8_t unavailable[] = {1, 0, 0, 0, 0, 0};
    assert(sizeof(bytes) <= 20 && std::memcmp(bytes, unavailable, sizeof(bytes)) == 0);
    Snapshot snapshot;
    snapshot.available = snapshot.valid = true;
    snapshot.state = State::Charging;
    snapshot.conditions = ThermalRegulation | InputVoltageLimit | SafetyTimerExpired;
    snapshot.reportedEvents = BatteryOvercurrent;
    encode(snapshot, bytes);
    const uint8_t simultaneous[] = {1, 4, 3, 0x60, 2, 1};
    assert(std::memcmp(bytes, simultaneous, sizeof(bytes)) == 0);
    assert(evaluate(Inputs{}) == State::Unknown);
    const State enabledStates[] = {
        State::NotCharging, State::Charging, State::Charging, State::Finished,
    };
    // Exercise all combinations, including stale or contradictory phase bits.
    // Host intent and observation validity take precedence over those bits.
    for (unsigned phase = 0; phase < 4; ++phase) {
        for (unsigned context = 0; context < 16; ++context) {
            Inputs inputs;
            inputs.valid = (context & 1) != 0;
            inputs.inputPresent = (context & 2) != 0;
            inputs.hostChargeEnabled = (context & 4) != 0;
            inputs.sampledAfterEnableChange = (context & 8) != 0;
            inputs.phase = static_cast<ChargePhase>(phase);

            State expected = State::Unknown;
            if (inputs.valid) {
                if (!inputs.inputPresent) expected = State::NoInput;
                else if (!inputs.hostChargeEnabled) expected = State::Disabled;
                else if (inputs.sampledAfterEnableChange) expected = enabledStates[phase];
            }
            assert(evaluate(inputs) == expected);
        }
    }

    Inputs invalidPhase;
    invalidPhase.valid = true;
    invalidPhase.inputPresent = true;
    invalidPhase.hostChargeEnabled = true;
    invalidPhase.sampledAfterEnableChange = true;
    invalidPhase.phase = static_cast<ChargePhase>(0xFF);
    assert(evaluate(invalidPhase) == State::Unknown);

    assert(std::strcmp(name(State::Unknown), "UNKNOWN") == 0);
    assert(std::strcmp(name(State::NoInput), "NO_INPUT") == 0);
    assert(std::strcmp(name(State::Disabled), "DISABLED") == 0);
    assert(std::strcmp(name(State::NotCharging), "NOT_CHARGING") == 0);
    assert(std::strcmp(name(State::Charging), "CHARGING") == 0);
    assert(std::strcmp(name(State::Finished), "FINISHED") == 0);
    assert(std::strcmp(name(static_cast<State>(0xFF)), "UNKNOWN") == 0);
    std::cout << "charger status module test passed\n";
}

#include "ChargerStatus.h"

namespace ChargerStatus {

void encode(const Snapshot& snapshot, uint8_t (&bytes)[ENCODED_SIZE]) {
    bytes[0] = 1;
    bytes[1] = static_cast<uint8_t>(snapshot.state);
    bytes[2] = (snapshot.available ? 1U : 0U) | (snapshot.valid ? 2U : 0U);
    bytes[3] = static_cast<uint8_t>(snapshot.conditions);
    bytes[4] = static_cast<uint8_t>(snapshot.conditions >> 8U);
    bytes[5] = snapshot.reportedEvents;
}

State evaluate(const Inputs& inputs) {
    if (!inputs.valid) {
        return State::Unknown;
    }
    if (!inputs.inputPresent) {
        return State::NoInput;
    }
    if (!inputs.hostChargeEnabled) {
        return State::Disabled;
    }
    if (!inputs.sampledAfterEnableChange) {
        // In particular, a DONE_OR_HOST_DISABLED sample from before enabling
        // charging cannot establish that this charge cycle has finished.
        return State::Unknown;
    }

    switch (inputs.phase) {
        case ChargePhase::NotCharging:
            return State::NotCharging;
        case ChargePhase::ConstantCurrent:
        case ChargePhase::ConstantVoltage:
            return State::Charging;
        case ChargePhase::DoneOrHostDisabled:
            // The driver verifies CHG_DIS=0; /CE must also have been enabled
            // at the time of this sample. This is charge completion, not SOC.
            return State::Finished;
    }
    return State::Unknown;
}

const char* name(State state) {
    switch (state) {
        case State::Unknown: return "UNKNOWN";
        case State::NoInput: return "NO_INPUT";
        case State::Disabled: return "DISABLED";
        case State::NotCharging: return "NOT_CHARGING";
        case State::Charging: return "CHARGING";
        case State::Finished: return "FINISHED";
    }
    return "UNKNOWN";
}

}  // namespace ChargerStatus

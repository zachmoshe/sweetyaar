#pragma once

#include <stdint.h>
#include <stddef.h>

// Interprets decoded charger observations together with firmware intent.
// This layer performs no I2C access, GPIO writes, or charging control.
namespace ChargerStatus {

enum class ChargePhase : uint8_t {
    NotCharging = 0,
    ConstantCurrent = 1,
    ConstantVoltage = 2,
    DoneOrHostDisabled = 3,
};

enum class State : uint8_t {
    Unknown = 0,
    NoInput = 1,
    Disabled = 2,
    NotCharging = 3,
    Charging = 4,
    Finished = 5,
};

// Stable bit assignments for the versioned BLE diagnostics snapshot.
enum Condition : uint16_t {
    TemperatureOutOfRange = 1U << 0,
    TemperatureReduced = 1U << 1,
    TemperatureSensor = 1U << 2,
    InputCurrentLimit = 1U << 3,
    SystemVoltageLimit = 1U << 4,
    InputVoltageLimit = 1U << 5,
    ThermalRegulation = 1U << 6,
    InputOvervoltage = 1U << 7,
    BatteryUndervoltage = 1U << 8,
    SafetyTimerExpired = 1U << 9,
    SupervisionFailure = 1U << 10,
};

enum ReportedEvent : uint8_t {
    BatteryOvercurrent = 1U << 0,
};

struct Snapshot {
    bool available = false;
    bool valid = false;
    State state = State::Unknown;
    uint16_t conditions = 0;
    // Event bits reported by the latest successful register read.
    uint8_t reportedEvents = 0;
};

constexpr size_t ENCODED_SIZE = 6;
// Version, activity, availability/validity flags, LE conditions, event bits.
void encode(const Snapshot& snapshot, uint8_t (&bytes)[ENCODED_SIZE]);

struct Inputs {
    // True only after successful configuration verification and status reads.
    bool valid = false;
    bool inputPresent = false;
    bool hostChargeEnabled = false;
    // False after any /CE transition, until another successful status read.
    bool sampledAfterEnableChange = false;
    ChargePhase phase = ChargePhase::NotCharging;
};

State evaluate(const Inputs& inputs);
const char* name(State state);

}  // namespace ChargerStatus

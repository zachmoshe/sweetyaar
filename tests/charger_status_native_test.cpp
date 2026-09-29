#include <cassert>
#include <cstdio>
#include <iostream>
#include <string>

#include <Wire.h>
#include "BQ25186Charger.h"
#include "Config.h"

namespace {

bool bedtimeClockReliable = false;
int16_t bedtimeTzOffsetMin = 0;
time_t fakeEpoch = 0;
time_t fakeTime(time_t*) { return fakeEpoch; }
#define time fakeTime
#include "charger_clock.inc"
#undef time

bool contains(const std::string& text) {
    return Serial.output.find(text) != std::string::npos;
}

unsigned count(const std::string& text) {
    unsigned result = 0;
    for (size_t pos = 0; (pos = Serial.output.find(text, pos)) != std::string::npos;
         pos += text.size()) {
        ++result;
    }
    return result;
}

struct Fixture {
    BQ25186Charger charger;

    Fixture() {
        Wire = WireClass{};
        g_fakeMillis = 0;
        bedtimeClockReliable = false;
        bedtimeTzOffsetMin = 0;
        fakeEpoch = 0;
        g_pins.fill(LOW);
        Serial.output.clear();
        Wire.registers[0x0C] = 1; // BQ25186 device ID
        Wire.registers[0x00] = 0x21; // constant current, valid input
        assert(charger.begin(readLocalLogTime));
        assert(contains("[Charger registers] time=UNKNOWN STAT0=0x21 STAT1=0x00 FLAG0=0x00 PG=VALID_INPUT\n"));
        assert(count("[Charger state]") == 1);
        assert(contains("time=UNKNOWN CHARGE_STATUS=CHARGING_CONSTANT_CURRENT"));
        assert(contains("TEMP_STATUS=NORMAL TS_OPEN_STAT=INACTIVE"));
        assert(contains("VIN_OVP_STAT=INACTIVE BUVLO_STAT=INACTIVE"));
        assert(contains("SAFETY_TMR_FAULT_FLAG=NOT_REPORTED"));
        assert(contains("VIN_PGOOD_STAT=VALID_INPUT"));
        assert(contains(" PG=VALID_INPUT"));
        assert(charger.healthy() && charger.charging() && charger.inputPresent());
        // begin() sampled before enabling /CE. A subsequent observation is
        // needed before the higher layer can report a charging phase.
        assert(charger.status() == ChargerStatus::State::Unknown);
        assert(contains("[Charger status] time=UNKNOWN STATUS=UNKNOWN\n"));
        Serial.output.clear();
        g_interruptHandler();
        charger.poll();
        assert(charger.status() == ChargerStatus::State::Charging);
        assert(Serial.output == "[Charger status] time=UNKNOWN STATUS=CHARGING\n");
        Serial.output.clear();
    }

    void interruptRead() {
        Serial.output.clear();
        ++g_fakeMillis;
        assert(g_interruptHandler);
        g_interruptHandler();
        charger.poll();
    }
};

void testChargeAndTemperatureNames() {
    Fixture f;
    const char* charges[] = {
        "NOT_CHARGING", "CHARGING_CONSTANT_CURRENT",
        "CHARGING_CONSTANT_VOLTAGE", "DONE_OR_HOST_DISABLED",
    };
    const char* temperatures[] = {
        "NORMAL", "HOT_OR_COLD_CHARGING_SUSPENDED",
        "COOL_REDUCED_CURRENT", "WARM_REDUCED_VOLTAGE",
    };
    const ChargerStatus::State statuses[] = {
        ChargerStatus::State::NotCharging, ChargerStatus::State::Charging,
        ChargerStatus::State::Charging, ChargerStatus::State::Finished,
    };
    for (unsigned charge = 0; charge < 4; ++charge) {
        for (unsigned temperature = 0; temperature < 4; ++temperature) {
            Wire.registers[0] = static_cast<uint8_t>((charge << 5) | 1);
            Wire.registers[1] = static_cast<uint8_t>(temperature << 3);
            f.interruptRead();
            assert(count("[Charger state]") == 1);
            assert(contains(std::string("CHARGE_STATUS=") + charges[charge] + " "));
            assert(contains(std::string("TEMP_STATUS=") + temperatures[temperature] + " "));
            assert(contains("time=UNKNOWN"));
            assert(f.charger.charging() == (charge == 1 || charge == 2));
            assert(f.charger.inputPresent());
            assert(f.charger.status() == statuses[charge]);
            f.interruptRead();
            assert(Serial.output.empty());
        }
    }
}

void testEachStatusBitChangesTheSnapshot() {
    struct Case { unsigned reg; uint8_t bit; const char* field; const char* value; };
    const Case cases[] = {
        {0, 0x80, "TS_OPEN_STAT", "ACTIVE"},
        {0, 0x10, "ILIM_ACTIVE_STAT", "ACTIVE"},
        {0, 0x08, "VDPPM_ACTIVE_STAT", "ACTIVE"},
        {0, 0x04, "VINDPM_ACTIVE_STAT", "ACTIVE"},
        {0, 0x02, "THERMREG_ACTIVE_STAT", "ACTIVE"},
        {0, 0x01, "VIN_PGOOD_STAT", "NO_VALID_INPUT"},
        {1, 0x80, "VIN_OVP_STAT", "ACTIVE"},
        {1, 0x40, "BUVLO_STAT", "ACTIVE"},
        {1, 0x04, "SAFETY_TMR_FAULT_FLAG", "DETECTED"},
    };
    for (const auto& test : cases) {
        Fixture f;
        Wire.registers[test.reg] ^= test.bit;
        f.interruptRead();
        assert(count("[Charger state]") == 1);
        assert(contains(std::string(test.field) + "=" + test.value + " "));
        // The full snapshot remains available even when only one bit changes.
        assert(contains("CHARGE_STATUS=CHARGING_CONSTANT_CURRENT TEMP_STATUS=NORMAL"));
        f.interruptRead();
        assert(Serial.output.empty());
        Wire.registers[test.reg] ^= test.bit;
        f.interruptRead();
        assert(count("[Charger state]") == 1);
    }
    Fixture f;
    g_pins[PIN_CHARGER_PG] = HIGH;
    f.interruptRead();
    assert(count("[Charger state]") == 1);
    assert(contains(" PG=NO_VALID_INPUT\n"));
    f.interruptRead();
    assert(Serial.output.empty());
}

void testEventFlagsAreSeparateFromState() {
    Fixture f;
    const char* flags[] = {
        "BAT_OCP_FAULT", "BUVLO_FAULT_FLAG", "VIN_OVP_FAULT_FLAG",
        "THERMREG_ACTIVE_FLAG", "VINDPM_ACTIVE_FLAG", "VDPPM_ACTIVE_FLAG",
        "ILIM_ACTIVE_FLAG", "TS_FAULT",
    };
    for (unsigned bit = 0; bit < 8; ++bit) {
        // Even repeated reports are events, never state transitions.
        for (unsigned repeat = 0; repeat < 2; ++repeat) {
            Wire.registers[2] = static_cast<uint8_t>(1U << bit);
            f.interruptRead();
            assert(!contains("[Charger state]"));
            assert(contains(std::string("[Charger events] time=UNKNOWN ") + flags[bit] + "\n"));
            assert(count("[Charger registers]") == 1);
            char rawFlag[20];
            std::snprintf(rawFlag, sizeof(rawFlag), "FLAG0=0x%02X", 1U << bit);
            assert(contains(rawFlag));
            assert(Wire.registers[2] == 0);
            f.interruptRead();
            assert(Serial.output == "[Charger registers] time=UNKNOWN "
                   "STAT0=0x21 STAT1=0x00 FLAG0=0x00 PG=VALID_INPUT\n");
            f.interruptRead();
            assert(Serial.output.empty());
        }
    }
    // A live transition and several events in one read retain both records.
    Wire.registers[0] = 0x41;
    Wire.registers[2] = 0xFF;
    f.interruptRead();
    assert(count("[Charger state]") == 1 && count("[Charger events]") == 1);
    for (const char* flag : flags) assert(contains(flag));
}

void testReservedAndUnusedWakeBitsAppearOnlyInRawLog() {
    Fixture f;
    for (uint8_t bits : {0x20, 0x01, 0x02, 0x23, 0x00}) {
        Wire.registers[1] = bits;
        f.interruptRead();
        assert(count("[Charger registers]") == 1);
        assert(!contains("[Charger state]") && !contains("[Charger events]"));
        assert(f.charger.snapshot().conditions == 0);
        char rawStatus[20];
        std::snprintf(rawStatus, sizeof(rawStatus), "STAT1=0x%02X", bits);
        assert(contains(rawStatus));
        f.interruptRead();
        assert(Serial.output.empty());
    }
}

void testPollScheduling() {
    Fixture f;
    const unsigned initialReads = Wire.reads[0];
    g_fakeMillis = CHARGER_VERIFY_INTERVAL_MS - 1;
    f.charger.poll();
    assert(Wire.reads[0] == initialReads);
    ++g_fakeMillis;
    f.charger.poll();
    assert(Wire.reads[0] == initialReads + 1 && Wire.reads[2] == initialReads + 1);
    assert(Serial.output.empty());
    // An interrupt bypasses the periodic deadline.
    Wire.registers[0] = 0x41;
    f.interruptRead();
    assert(Wire.reads[0] == initialReads + 2);
    assert(contains("[Charger state] time=UNKNOWN CHARGE_STATUS=CHARGING_CONSTANT_VOLTAGE"));
}

void testFailedReadsAndRecovery() {
    for (int failedRegister : {0, 1, 2}) {
        Fixture f;
        Wire.failReadRegister = failedRegister;
        f.interruptRead();
        assert(!f.charger.healthy());
        assert(!f.charger.charging() && !f.charger.inputPresent());
        assert(g_pins[PIN_CHARGER_ENABLE] == LOW);
        assert(contains("[Charger] Disabled: status read failed"));
        assert(!contains("[Charger state]") && !contains("[Charger events]"));
        assert(!contains("[Charger registers]"));
        assert(f.charger.status() == ChargerStatus::State::Unknown);
        assert(contains("STATUS=UNKNOWN"));
        Wire.failReadRegister = -1;
        f.interruptRead();
        assert(f.charger.healthy());
        assert(count("[Charger state]") == 1); // fresh baseline after the gap
        assert(f.charger.status() == ChargerStatus::State::Unknown);
        f.interruptRead();
        assert(f.charger.status() == ChargerStatus::State::Charging);
        assert(contains("STATUS=CHARGING"));
        f.interruptRead();
        assert(Serial.output.empty());
    }
}

void testCompletionDoesNotReuseDisabledSamples() {
    // At boot, DONE_OR_HOST_DISABLED is read while /CE is disabled.
    // Enabling charging afterwards must not reinterpret it as FINISHED.
    Wire = WireClass{};
    Wire.registers[0x0C] = 1;
    Wire.registers[0] = 0x61;
    g_pins.fill(LOW);
    g_fakeMillis = 0;
    Serial.output.clear();
    BQ25186Charger charger;
    assert(charger.status() == ChargerStatus::State::Unknown);
    assert(charger.begin());
    assert(charger.status() == ChargerStatus::State::Unknown);
    assert(!contains("STATUS=FINISHED"));

    // A fresh post-enable read of 11 now confirms completion, even though
    // the chip's raw field did not change. Only the higher-level log changes.
    Serial.output.clear();
    ++g_fakeMillis;
    g_interruptHandler();
    charger.poll();
    assert(charger.status() == ChargerStatus::State::Finished);
    assert(Serial.output == "[Charger status] time=UNKNOWN STATUS=FINISHED\n");

    // A charger reset/configuration mismatch disables /CE during recovery.
    // The sample from that disabled interval cannot report FINISHED either.
    Wire.registers[3] ^= 1;
    Serial.output.clear();
    ++g_fakeMillis;
    g_interruptHandler();
    charger.poll();
    assert(charger.status() == ChargerStatus::State::Unknown);
    assert(contains("Configuration restored and verified"));
    assert(!contains("STATUS=FINISHED"));

    // Unplugging must also stop reporting completion, even with stale 11.
    Wire.registers[0] = 0x60;
    g_interruptHandler();
    charger.poll();
    assert(charger.status() == ChargerStatus::State::NoInput);
    assert(g_pins[PIN_CHARGER_ENABLE] == LOW);

    // An input arriving at the final sleep check leaves /CE disabled until
    // normal supervision resumes. This distinguishes Disabled from NoInput.
    Wire.registers[0] = 0x61;
    Serial.output.clear();
    assert(!charger.prepareForDeepSleep());
    assert(charger.status() == ChargerStatus::State::Disabled);
    assert(contains("STATUS=DISABLED"));
    assert(!contains("STATUS=FINISHED"));
    g_interruptHandler();
    charger.poll();
    assert(charger.status() == ChargerStatus::State::Unknown);

    // Charging may resume after completion, so FINISHED is never latched.
    Wire.registers[0] = 0x21;
    g_interruptHandler();
    charger.poll();
    assert(charger.status() == ChargerStatus::State::Charging);
    Wire.registers[0] = 0x01;
    g_interruptHandler();
    charger.poll();
    assert(charger.status() == ChargerStatus::State::NotCharging);

    Wire.registers[0] = 0x60;
    assert(charger.prepareForDeepSleep());
    assert(charger.status() == ChargerStatus::State::NoInput);
    assert(g_pins[PIN_CHARGER_ENABLE] == LOW);
}

void testAppSnapshotReflectsLatestRead() {
    using namespace ChargerStatus;
    struct Case { unsigned reg; uint8_t value; uint16_t condition; };
    const Case cases[] = {
        {0, 0x80, TemperatureSensor}, {0, 0x10, InputCurrentLimit},
        {0, 0x08, SystemVoltageLimit}, {0, 0x04, InputVoltageLimit},
        {0, 0x02, ThermalRegulation}, {1, 0x80, InputOvervoltage},
        {1, 0x40, BatteryUndervoltage}, {1, 0x08, TemperatureOutOfRange},
        {1, 0x10, TemperatureReduced}, {1, 0x18, TemperatureReduced},
        {1, 0x04, SafetyTimerExpired},
    };
    for (const auto& test : cases) {
        Fixture f;
        assert(f.charger.snapshot().valid && f.charger.snapshot().available);
        assert(f.charger.snapshot().conditions == 0);
        Wire.registers[test.reg] |= test.value;
        f.interruptRead();
        assert(f.charger.snapshot().conditions == test.condition);
        Wire.registers[test.reg] &= ~test.value;
        f.interruptRead();
        assert(f.charger.snapshot().conditions == 0);
    }

    Fixture f;
    Wire.registers[0] |= 0x06; // heat + input-voltage limits coexist
    Wire.registers[1] = 0x04; // safety timer expired
    Wire.registers[2] = 1; // read-clear battery overcurrent event
    f.interruptRead();
    assert(f.charger.snapshot().conditions == (ThermalRegulation | InputVoltageLimit | SafetyTimerExpired));
    assert(f.charger.snapshot().reportedEvents == BatteryOvercurrent);
    // Merely inspecting or polling before the next read does not clear it.
    const unsigned reads = Wire.reads[2];
    f.charger.poll();
    assert(Wire.reads[2] == reads);
    assert(f.charger.snapshot().reportedEvents == BatteryOvercurrent);
    Wire.registers[1] = 0;
    g_fakeMillis += CHARGER_VERIFY_INTERVAL_MS;
    f.charger.poll();
    assert(f.charger.snapshot().conditions == (ThermalRegulation | InputVoltageLimit));
    assert(f.charger.snapshot().reportedEvents == 0); // latest periodic read returned 0

    Wire.registers[2] = 1;
    f.interruptRead();
    assert(f.charger.snapshot().reportedEvents == BatteryOvercurrent);
    f.interruptRead();
    assert(f.charger.snapshot().reportedEvents == 0); // interrupt reads replace it too

    for (int failedRegister : {0, 1, 2}) {
        Wire.registers[2] = 1;
        f.interruptRead();
        assert(f.charger.snapshot().reportedEvents == BatteryOvercurrent);
        Wire.failReadRegister = failedRegister;
        f.interruptRead();
        const auto failed = f.charger.snapshot();
        assert(failed.available && !failed.valid && failed.state == State::Unknown);
        assert(failed.conditions == SupervisionFailure); // no stale conditions
        assert(failed.reportedEvents == 0); // invalid reads don't publish an old event
        Wire.failReadRegister = -1;
        f.interruptRead();
        f.interruptRead();
        assert(f.charger.snapshot().valid);
        assert(f.charger.snapshot().reportedEvents == 0);
    }
}

void testLocalTimeLogging() {
    Fixture f;
    // 2026-01-01 00:00:00 UTC, with the offset provided by the app.
    fakeEpoch = 1767225600;
    bedtimeClockReliable = true;
    bedtimeTzOffsetMin = 180;
    Wire.registers[0] = 0x61;
    Wire.registers[2] = 1;
    f.interruptRead();
    for (const char* category : {"registers", "state", "events", "status"}) {
        assert(contains(std::string("[Charger ") + category +
                        "] time=2026-01-01 03:00:00 "));
    }
    assert(contains("BAT_OCP_FAULT\n"));
    assert(contains("STATUS=FINISHED\n"));

    // Follow a new offset immediately, including fractional hours/date rollover.
    bedtimeTzOffsetMin = -210;
    fakeEpoch += 1;
    f.interruptRead();
    assert(contains("[Charger registers] time=2025-12-31 20:30:01 "));
    fakeEpoch += 60;
    f.interruptRead();
    assert(Serial.output.empty()); // clock ticks do not count as state changes

    // An unset RTC must never be presented as a trustworthy local timestamp.
    fakeEpoch = 0;
    Wire.registers[0] = 0x21;
    f.interruptRead();
    assert(contains("time=UNKNOWN"));
    assert(!contains("1970-"));
}

} // namespace

int main() {
    testChargeAndTemperatureNames();
    testEachStatusBitChangesTheSnapshot();
    testEventFlagsAreSeparateFromState();
    testReservedAndUnusedWakeBitsAppearOnlyInRawLog();
    testPollScheduling();
    testFailedReadsAndRecovery();
    testCompletionDoesNotReuseDisabledSamples();
    testAppSnapshotReflectsLatestRead();
    testLocalTimeLogging();
    std::cout << "charger status native test passed\n";
}

#include "BQ25186Charger.h"

#include <Wire.h>
#include <driver/rtc_io.h>

#include "Config.h"

namespace {

constexpr uint8_t I2C_ADDRESS = 0x6A;

constexpr uint8_t REG_STAT0 = 0x00;
constexpr uint8_t REG_STAT1 = 0x01;
constexpr uint8_t REG_FLAG0 = 0x02;
constexpr uint8_t REG_VBAT_CTRL = 0x03;
constexpr uint8_t REG_ICHG_CTRL = 0x04;
constexpr uint8_t REG_CHARGECTRL0 = 0x05;
constexpr uint8_t REG_CHARGECTRL1 = 0x06;
constexpr uint8_t REG_IC_CTRL = 0x07;
constexpr uint8_t REG_TMR_ILIM = 0x08;
constexpr uint8_t REG_SHIP_RST = 0x09;
constexpr uint8_t REG_SYS_REG = 0x0A;
constexpr uint8_t REG_TS_CONTROL = 0x0B;
constexpr uint8_t REG_MASK_ID = 0x0C;

// STAT1 contributes VIN OVP, battery UVLO, temperature zone, and the safety
// timer indication. Reserved and TS/MR pushbutton event bits are not state.
constexpr uint8_t STAT1_STATE_MASK = 0xDC;

// Production policy, encoded directly from the BQ25186 register map:
// 4.20 V cell, 1.00 A charge, 10% termination, 4.5 V VINDPM, 100 C IC
// thermal regulation, 3 A battery OCP, 3.0 V BUVLO, 1.05 A input limit,
// normal 4.5 V SYS, TS pushbutton actions disabled, and 0 C / 45 C hard TS
// cutoffs with the intermediate COOL/WARM zones disabled.
constexpr uint8_t VALUE_VBAT_CTRL = 0x46;
constexpr uint8_t VALUE_ICHG_CTRL = 0x7F;
constexpr uint8_t VALUE_CHARGECTRL0 = 0x24;
constexpr uint8_t VALUE_CHARGECTRL1 = 0xD0;
constexpr uint8_t VALUE_TMR_ILIM = 0x4F;
constexpr uint8_t VALUE_SHIP_RST = 0x00;
constexpr uint8_t VALUE_SYS_REG = 0x40;
constexpr uint8_t VALUE_TS_CONTROL = 0xCC;
// Enable all supported event sources and require the read-only BQ25186
// Device_ID nibble (0x1). Including this register in verification also catches
// accidental interrupt-mask changes.
constexpr uint8_t VALUE_MASK_ID = 0x01;

// TS enabled, six-hour safety timer. While awake the 40-second BQ25186
// watchdog performs a full SYS power-cycle if I2C traffic stops. It must be
// disabled immediately before intentional ESP32 deep sleep.
constexpr uint8_t VALUE_IC_CTRL_AWAKE = 0x86;
constexpr uint8_t VALUE_IC_CTRL_SLEEP = 0x87;

struct RegisterSetting {
    uint8_t reg;
    uint8_t value;
};

constexpr RegisterSetting CONFIGURATION[] = {
    {REG_VBAT_CTRL, VALUE_VBAT_CTRL},
    {REG_ICHG_CTRL, VALUE_ICHG_CTRL},
    {REG_CHARGECTRL0, VALUE_CHARGECTRL0},
    {REG_CHARGECTRL1, VALUE_CHARGECTRL1},
    {REG_TMR_ILIM, VALUE_TMR_ILIM},
    {REG_SHIP_RST, VALUE_SHIP_RST},
    {REG_SYS_REG, VALUE_SYS_REG},
    {REG_TS_CONTROL, VALUE_TS_CONTROL},
    {REG_MASK_ID, VALUE_MASK_ID},
};

const char* chargeStateName(uint8_t chargeState) {
    switch (chargeState) {
        case 0: return "NOT_CHARGING";
        case 1: return "CHARGING_CONSTANT_CURRENT";
        case 2: return "CHARGING_CONSTANT_VOLTAGE";
        case 3: return "DONE_OR_HOST_DISABLED";
        default: return "UNKNOWN";
    }
}

const char* temperatureStateName(uint8_t temperatureState) {
    switch (temperatureState) {
        case 0: return "NORMAL";
        case 1: return "HOT_OR_COLD_CHARGING_SUSPENDED";
        case 2: return "COOL_REDUCED_CURRENT";
        case 3: return "WARM_REDUCED_VOLTAGE";
        default: return "UNKNOWN";
    }
}

const char* activeStateName(bool active) {
    return active ? "ACTIVE" : "INACTIVE";
}

void logEvents(uint8_t flags, const char* timestamp) {
    if (flags == 0) {
        return;
    }
    // FLAG0 is read-to-clear event evidence, not a live-state snapshot. Keep
    // it visible separately: a transient may be over before STAT is read and
    // BAT_OCP has no equivalent live bit. A persistent fault can reassert flags,
    // so another line is not necessarily another distinct physical event.
    Serial.printf("[Charger events] time=%s%s%s%s%s%s%s%s%s\n",
                  timestamp,
                  (flags & 0x80U) ? " TS_FAULT" : "",
                  (flags & 0x40U) ? " ILIM_ACTIVE_FLAG" : "",
                  (flags & 0x20U) ? " VDPPM_ACTIVE_FLAG" : "",
                  (flags & 0x10U) ? " VINDPM_ACTIVE_FLAG" : "",
                  (flags & 0x08U) ? " THERMREG_ACTIVE_FLAG" : "",
                  (flags & 0x04U) ? " VIN_OVP_FAULT_FLAG" : "",
                  (flags & 0x02U) ? " BUVLO_FAULT_FLAG" : "",
                  (flags & 0x01U) ? " BAT_OCP_FAULT" : "");
}

}  // namespace

volatile bool BQ25186Charger::_interruptPending = false;

void IRAM_ATTR BQ25186Charger::interruptHandler() {
    _interruptPending = true;
}

bool BQ25186Charger::begin(LocalTimeReader readLocalTime) {
    _readLocalTime = readLocalTime;
    setChargeEnabled(false);
    // GPIO34 may have been owned by EXT1 during the preceding deep sleep.
    rtc_gpio_deinit(static_cast<gpio_num_t>(PIN_CHARGER_PG));
    pinMode(PIN_CHARGER_PG, INPUT);
    pinMode(PIN_CHARGER_INT, INPUT);
    attachInterrupt(digitalPinToInterrupt(PIN_CHARGER_INT),
                    BQ25186Charger::interruptHandler, FALLING);
    _interruptPending = false;

    if (!Wire.begin(PIN_CHARGER_SDA, PIN_CHARGER_SCL, 100000)) {
        failClosed("I2C bus initialization failed");
        return false;
    }
    Wire.setTimeOut(25);

    uint8_t maskAndId = 0;
    if (!readRegister(REG_MASK_ID, maskAndId)) {
        failClosed("BQ25186 did not acknowledge at 0x6A");
        return false;
    }
    if ((maskAndId & 0x0FU) != (VALUE_MASK_ID & 0x0FU)) {
        failClosed("unexpected charger device ID");
        return false;
    }
    Serial.printf("[Charger] BQ25186 detected, MASK_ID=0x%02X\n", maskAndId);

    if (!applyConfiguration(VALUE_IC_CTRL_AWAKE) || !readStatus()) {
        failClosed("initial configuration or status read failed");
        return false;
    }

    _healthy = true;
    _lastVerifyMs = millis();
    setChargeEnabled(_inputPresent);
    logStatusChange();
    Serial.printf("[Charger] Configuration verified; charging %s\n",
                  _inputPresent ? "enabled" : "waiting for input");
    return true;
}

void BQ25186Charger::poll() {
    uint32_t now = millis();
    bool periodic = now - _lastVerifyMs >= CHARGER_VERIFY_INTERVAL_MS;
    if (!_interruptPending && !periodic) {
        return;
    }

    _interruptPending = false;
    _lastVerifyMs = now;

    if (!verifyConfiguration(VALUE_IC_CTRL_AWAKE)) {
        setChargeEnabled(false);
        Serial.println("[Charger] Configuration mismatch; attempting fail-closed recovery");
        if (!applyConfiguration(VALUE_IC_CTRL_AWAKE)) {
            failClosed("configuration recovery failed");
            return;
        }
        Serial.println("[Charger] Configuration restored and verified");
    }

    if (!readStatus()) {
        failClosed("status read failed");
        return;
    }

    _healthy = true;
    // The NPN consumes base current while asserted. It is needed only when an
    // external input is valid; /CE is deliberately left disabled otherwise.
    setChargeEnabled(_inputPresent);
    logStatusChange();
}

ChargerStatus::State BQ25186Charger::status() const {
    ChargerStatus::Inputs inputs;
    inputs.valid = _healthy && _hasLastState;
    inputs.inputPresent = _inputPresent;
    inputs.hostChargeEnabled = _chargeEnabled;
    inputs.sampledAfterEnableChange = _sampledAfterEnableChange;
    inputs.phase = static_cast<ChargerStatus::ChargePhase>((_lastStat0 >> 5U) & 0x03U);
    return ChargerStatus::evaluate(inputs);
}

void BQ25186Charger::formatLogTime(char (&timestamp)[20]) const {
    tm localTime{};
    if (_readLocalTime && _readLocalTime(localTime) &&
        strftime(timestamp, sizeof(timestamp), "%Y-%m-%d %H:%M:%S", &localTime)) {
        return;
    }
    snprintf(timestamp, sizeof(timestamp), "UNKNOWN");
}

void BQ25186Charger::logStatusChange() {
    ChargerStatus::State current = status();
    if (!_hasLoggedStatus || current != _lastLoggedStatus) {
        char timestamp[20];
        formatLogTime(timestamp);
        Serial.printf("[Charger status] time=%s STATUS=%s\n",
                      timestamp,
                      ChargerStatus::name(current));
        _hasLoggedStatus = true;
        _lastLoggedStatus = current;
    }
}

ChargerStatus::Snapshot BQ25186Charger::snapshot() const {
    using namespace ChargerStatus;
    Snapshot result;
    result.available = true;
    result.valid = _healthy && _hasLastState;
    result.state = status();
    if (!result.valid) {
        result.conditions = SupervisionFailure;
        return result;
    }
    if (_lastFlags & 0x01U) result.reportedEvents |= BatteryOvercurrent;
    const uint8_t temperature = (_lastStat1 >> 3U) & 3U;
    if (temperature == 1U) result.conditions |= TemperatureOutOfRange;
    if (temperature >= 2U) result.conditions |= TemperatureReduced;
    if (_lastStat0 & 0x80U) result.conditions |= TemperatureSensor;
    if (_lastStat0 & 0x10U) result.conditions |= InputCurrentLimit;
    if (_lastStat0 & 0x08U) result.conditions |= SystemVoltageLimit;
    if (_lastStat0 & 0x04U) result.conditions |= InputVoltageLimit;
    if (_lastStat0 & 0x02U) result.conditions |= ThermalRegulation;
    if (_lastStat1 & 0x80U) result.conditions |= InputOvervoltage;
    if (_lastStat1 & 0x40U) result.conditions |= BatteryUndervoltage;
    if (_lastStat1 & 0x04U) result.conditions |= SafetyTimerExpired;
    return result;
}

bool BQ25186Charger::prepareForDeepSleep() {
    if (!_healthy) {
        Serial.println("[Charger] Refusing deep sleep while charger is unhealthy");
        return false;
    }

    // Read the physical device immediately before sleeping. Valid external
    // power keeps the ESP32 awake so it can continue supervising the charger.
    if (!readStatus()) {
        failClosed("status read failed before deep sleep");
        return false;
    }
    if (_inputPresent) {
        logStatusChange();
        Serial.println("[Charger] External input appeared; keeping system awake");
        return false;
    }

    if (!writeAndVerify(REG_IC_CTRL, VALUE_IC_CTRL_SLEEP) ||
        !verifyConfiguration(VALUE_IC_CTRL_SLEEP)) {
        failClosed("could not disable charger watchdog for deep sleep");
        return false;
    }

    setChargeEnabled(false);
    logStatusChange();
    Serial.println("[Charger] Configuration verified; charging and host watchdog disabled for deep sleep");
    return true;
}

bool BQ25186Charger::writeRegister(uint8_t reg, uint8_t value) {
    Wire.beginTransmission(I2C_ADDRESS);
    Wire.write(reg);
    Wire.write(value);
    uint8_t result = Wire.endTransmission(true);
    if (result != 0) {
        Serial.printf("[Charger] I2C write reg 0x%02X failed (%u)\n", reg, result);
        return false;
    }
    return true;
}

bool BQ25186Charger::readRegister(uint8_t reg, uint8_t& value) {
    Wire.beginTransmission(I2C_ADDRESS);
    Wire.write(reg);
    uint8_t result = Wire.endTransmission(false);
    if (result != 0) {
        Serial.printf("[Charger] I2C select reg 0x%02X failed (%u)\n", reg, result);
        return false;
    }

    if (Wire.requestFrom(static_cast<int>(I2C_ADDRESS), 1, 1) != 1 ||
        Wire.available() != 1) {
        Serial.printf("[Charger] I2C read reg 0x%02X failed\n", reg);
        return false;
    }
    value = static_cast<uint8_t>(Wire.read());
    return true;
}

bool BQ25186Charger::writeAndVerify(uint8_t reg, uint8_t value) {
    if (!writeRegister(reg, value)) {
        return false;
    }
    uint8_t actual = 0;
    if (!readRegister(reg, actual)) {
        return false;
    }
    if (actual != value) {
        Serial.printf("[Charger] Verify reg 0x%02X expected=0x%02X actual=0x%02X\n",
                      reg, value, actual);
        return false;
    }
    return true;
}

bool BQ25186Charger::applyConfiguration(uint8_t icControl) {
    for (const RegisterSetting& setting : CONFIGURATION) {
        if (!writeAndVerify(setting.reg, setting.value)) {
            return false;
        }
    }
    return writeAndVerify(REG_IC_CTRL, icControl);
}

bool BQ25186Charger::verifyConfiguration(uint8_t icControl) {
    for (const RegisterSetting& setting : CONFIGURATION) {
        uint8_t actual = 0;
        if (!readRegister(setting.reg, actual)) {
            return false;
        }
        if (actual != setting.value) {
            Serial.printf("[Charger] Config changed reg 0x%02X expected=0x%02X actual=0x%02X\n",
                          setting.reg, setting.value, actual);
            return false;
        }
    }

    uint8_t actual = 0;
    if (!readRegister(REG_IC_CTRL, actual)) {
        return false;
    }
    if (actual != icControl) {
        Serial.printf("[Charger] Config changed reg 0x%02X expected=0x%02X actual=0x%02X\n",
                      REG_IC_CTRL, icControl, actual);
        return false;
    }
    return true;
}

bool BQ25186Charger::readStatus() {
    uint8_t stat0 = 0;
    uint8_t stat1 = 0;
    uint8_t flags = 0;
    if (!readRegister(REG_STAT0, stat0) ||
        !readRegister(REG_STAT1, stat1) ||
        !readRegister(REG_FLAG0, flags)) {
        return false;
    }

    uint8_t chargeState = static_cast<uint8_t>((stat0 >> 5U) & 0x03U);
    _charging = chargeState == 1U || chargeState == 2U;
    _inputPresent = (stat0 & 0x01U) != 0;
    int8_t pgLevel = digitalRead(PIN_CHARGER_PG) == LOW ? 0 : 1;
    uint8_t stat1State = stat1 & STAT1_STATE_MASK;
    char timestamp[20];
    formatLogTime(timestamp);

    if (!_hasLastState || stat0 != _lastStat0 || stat1 != _lastStat1 ||
        flags != _lastFlags || pgLevel != _lastPgLevel) {
        Serial.printf("[Charger registers] time=%s STAT0=0x%02X STAT1=0x%02X "
                      "FLAG0=0x%02X PG=%s\n",
                      timestamp, stat0, stat1, flags,
                      pgLevel == 0 ? "VALID_INPUT" : "NO_VALID_INPUT");
    }

    if (!_hasLastState || stat0 != _lastStat0 ||
        stat1State != (_lastStat1 & STAT1_STATE_MASK) ||
        pgLevel != _lastPgLevel) {
        Serial.printf("[Charger state] time=%s CHARGE_STATUS=%s TEMP_STATUS=%s "
                      "TS_OPEN_STAT=%s VIN_OVP_STAT=%s BUVLO_STAT=%s "
                      "SAFETY_TMR_FAULT_FLAG=%s VIN_PGOOD_STAT=%s "
                      "ILIM_ACTIVE_STAT=%s VDPPM_ACTIVE_STAT=%s "
                      "VINDPM_ACTIVE_STAT=%s THERMREG_ACTIVE_STAT=%s PG=%s\n",
                      timestamp,
                      chargeStateName(chargeState),
                      temperatureStateName((stat1 >> 3U) & 0x03U),
                      activeStateName(stat0 & 0x80U),
                      activeStateName(stat1 & 0x80U),
                      activeStateName(stat1 & 0x40U),
                      // TI labels this bit RC but says the safety-timer fault
                      // needs a CE/charge-enable/input toggle to clear. Report
                      // the observed indication; do not infer recovery from 0.
                      (stat1 & 0x04U) ? "DETECTED" : "NOT_REPORTED",
                      _inputPresent ? "VALID_INPUT" : "NO_VALID_INPUT",
                      activeStateName(stat0 & 0x10U),
                      activeStateName(stat0 & 0x08U),
                      activeStateName(stat0 & 0x04U),
                      activeStateName(stat0 & 0x02U),
                      pgLevel == 0 ? "VALID_INPUT" : "NO_VALID_INPUT");
    }

    logEvents(flags, timestamp);
    _hasLastState = true;
    _lastStat0 = stat0;
    _lastStat1 = stat1;
    _lastFlags = flags;
    _lastPgLevel = pgLevel;
    _sampledAfterEnableChange = true;
    return true;
}

void BQ25186Charger::setChargeEnabled(bool enabled) {
    if (enabled != _chargeEnabled) {
        _sampledAfterEnableChange = false;
    }
    if (!_chargeEnabled) {
        pinMode(PIN_CHARGER_ENABLE, OUTPUT);
    }
    digitalWrite(PIN_CHARGER_ENABLE, enabled ? HIGH : LOW);
    _chargeEnabled = enabled;
}

void BQ25186Charger::failClosed(const char* reason) {
    setChargeEnabled(false);
    _healthy = false;
    _charging = false;
    _inputPresent = false;
    // The next successful read establishes a fresh snapshot after the gap.
    _hasLastState = false;
    Serial.printf("[Charger] Disabled: %s\n", reason);
    logStatusChange();
}

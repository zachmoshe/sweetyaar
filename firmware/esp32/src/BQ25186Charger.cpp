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
        case 0: return "not charging";
        case 1: return "constant current";
        case 2: return "constant voltage";
        case 3: return "done/host disabled";
        default: return "unknown";
    }
}

}  // namespace

volatile bool BQ25186Charger::_interruptPending = false;

void IRAM_ATTR BQ25186Charger::interruptHandler() {
    _interruptPending = true;
}

bool BQ25186Charger::begin() {
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
        Serial.println("[Charger] External input appeared; keeping system awake");
        return false;
    }

    if (!writeAndVerify(REG_IC_CTRL, VALUE_IC_CTRL_SLEEP) ||
        !verifyConfiguration(VALUE_IC_CTRL_SLEEP)) {
        failClosed("could not disable charger watchdog for deep sleep");
        return false;
    }

    setChargeEnabled(false);
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

    if (stat0 != _lastStat0 || stat1 != _lastStat1 || flags != 0 ||
        pgLevel != _lastPgLevel) {
        Serial.printf("[Charger] STAT0=0x%02X STAT1=0x%02X FLAG0=0x%02X "
                      "PG=%s charge=%s TS=%u\n",
                      stat0, stat1, flags,
                      pgLevel == 0 ? "valid-input" : "no-input",
                      chargeStateName(chargeState),
                      static_cast<unsigned>((stat1 >> 3U) & 0x03U));
    }

    _lastStat0 = stat0;
    _lastStat1 = stat1;
    _lastPgLevel = pgLevel;
    return true;
}

void BQ25186Charger::setChargeEnabled(bool enabled) {
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
    Serial.printf("[Charger] Disabled: %s\n", reason);
}

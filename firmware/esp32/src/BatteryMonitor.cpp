#include "BatteryMonitor.h"

namespace {

// The ADC node is expected to cover roughly 0.53-1.10 V across the charger's
// supported BAT range. Reject readings well outside that window so an unwired
// prototype pin remains UNKNOWN instead of publishing a made-up battery level.
static constexpr uint16_t MIN_VALID_ADC_MV = 400;
static constexpr uint16_t MAX_VALID_ADC_MV = 1150;

const char* chargerPinsName(uint8_t pins) {
    switch (pins) {
        case 0b11: return "complete/sleep/disabled";
        case 0b10: return "charging";
        case 0b01: return "recoverable fault";
        case 0b00: return "latch-off fault";
        default: return "unknown";
    }
}

}  // namespace

const char* batteryStateName(BatteryState state) {
    switch (state) {
        case BatteryState::Good: return "GOOD";
        case BatteryState::Medium: return "MEDIUM";
        case BatteryState::Low: return "LOW";
        case BatteryState::Charging: return "CHARGING";
        case BatteryState::Unknown:
        default: return "UNKNOWN";
    }
}

void BatteryMonitor::begin() {
    pinMode(PIN_CHARGER_STAT1, INPUT);
    pinMode(PIN_CHARGER_STAT2, INPUT);
    pinMode(PIN_BATTERY_ADC, INPUT);
    analogSetPinAttenuation(PIN_BATTERY_ADC, ADC_2_5db);

    uint32_t bootTotalMv = 0;
    uint8_t validBootSamples = 0;
    for (uint8_t i = 0; i < BATTERY_BOOT_SAMPLE_COUNT; ++i) {
        uint16_t batteryMv = readBatteryMillivolts();
        if (batteryMv != 0) {
            bootTotalMv += batteryMv;
            ++validBootSamples;
        }
        delay(BATTERY_BOOT_SAMPLE_INTERVAL_MS);
    }

    // The five closely-spaced readings are one seed observation. Storing their
    // mean once prevents boot from outweighing the later 30-second samples.
    if (validBootSamples == BATTERY_BOOT_SAMPLE_COUNT) {
        addVoltageSample(static_cast<uint16_t>(
            (bootTotalMv + validBootSamples / 2U) / validBootSamples));
    } else {
        Serial.printf("[Battery] Initial ADC invalid (%u/%u valid)\n",
                      validBootSamples, BATTERY_BOOT_SAMPLE_COUNT);
    }

    updateChargerState();
    updatePublicState();
    _lastPeriodicSampleMs = millis();
    Serial.printf("[Battery] Initial state=%s\n", batteryStateName(_state));
}

bool BatteryMonitor::poll() {
    BatteryState previous = _state;
    updateChargerState();

    uint32_t now = millis();
    if (now - _lastPeriodicSampleMs >= BATTERY_SAMPLE_INTERVAL_MS) {
        // Preserve a stable cadence even if one main-loop iteration is late.
        _lastPeriodicSampleMs = now;
        uint16_t batteryMv = readBatteryMillivolts();
        if (batteryMv != 0) {
            addVoltageSample(batteryMv);
        } else {
            Serial.println("[Battery] Ignoring invalid ADC sample");
        }
    }

    updatePublicState();
    if (_state != previous) {
        Serial.printf("[Battery] State %s -> %s\n",
                      batteryStateName(previous), batteryStateName(_state));
        return true;
    }
    return false;
}

uint16_t BatteryMonitor::readBatteryMillivolts() const {
    uint32_t adcMv = analogReadMilliVolts(PIN_BATTERY_ADC);
    if (adcMv < MIN_VALID_ADC_MV || adcMv > MAX_VALID_ADC_MV) {
        Serial.printf("[Battery] Invalid raw ADC=%lumV (valid=%u-%umV)\n",
                      static_cast<unsigned long>(adcMv),
                      MIN_VALID_ADC_MV, MAX_VALID_ADC_MV);
        return 0;
    }

    const uint32_t dividerTotal =
        BATTERY_DIVIDER_TOP_OHMS + BATTERY_DIVIDER_BOTTOM_OHMS;
    return static_cast<uint16_t>(
        (adcMv * dividerTotal + BATTERY_DIVIDER_BOTTOM_OHMS / 2U) /
        BATTERY_DIVIDER_BOTTOM_OHMS);
}

void BatteryMonitor::addVoltageSample(uint16_t batteryMillivolts) {
    _samples[_nextSample] = batteryMillivolts;
    _nextSample = (_nextSample + 1U) % BATTERY_ROLLING_SAMPLE_COUNT;
    if (_sampleCount < BATTERY_ROLLING_SAMPLE_COUNT) {
        ++_sampleCount;
    }
    _hasValidVoltage = true;

    uint16_t averagedMv = averageMillivolts();
    updateVoltageState(averagedMv);
    Serial.printf("[Battery] sample=%umV mean=%umV window=%u/%u\n",
                  batteryMillivolts, averagedMv, _sampleCount,
                  BATTERY_ROLLING_SAMPLE_COUNT);
}

uint16_t BatteryMonitor::averageMillivolts() const {
    if (_sampleCount == 0) return 0;
    uint32_t totalMv = 0;
    for (uint8_t i = 0; i < _sampleCount; ++i) {
        totalMv += _samples[i];
    }
    return static_cast<uint16_t>((totalMv + _sampleCount / 2U) / _sampleCount);
}

void BatteryMonitor::updateVoltageState(uint16_t averagedMillivolts) {
    switch (_voltageState) {
        case BatteryState::Good:
            if (averagedMillivolts <= BATTERY_MEDIUM_TO_LOW_MV) {
                _voltageState = BatteryState::Low;
            } else if (averagedMillivolts <= BATTERY_GOOD_TO_MEDIUM_MV) {
                _voltageState = BatteryState::Medium;
            }
            break;

        case BatteryState::Medium:
            if (averagedMillivolts <= BATTERY_MEDIUM_TO_LOW_MV) {
                _voltageState = BatteryState::Low;
            } else if (averagedMillivolts >= BATTERY_MEDIUM_TO_GOOD_MV) {
                _voltageState = BatteryState::Good;
            }
            break;

        case BatteryState::Low:
            if (averagedMillivolts >= BATTERY_MEDIUM_TO_GOOD_MV) {
                _voltageState = BatteryState::Good;
            } else if (averagedMillivolts >= BATTERY_LOW_TO_MEDIUM_MV) {
                _voltageState = BatteryState::Medium;
            }
            break;

        case BatteryState::Charging:
        case BatteryState::Unknown:
        default:
            if (averagedMillivolts <= BATTERY_MEDIUM_TO_LOW_MV) {
                _voltageState = BatteryState::Low;
            } else if (averagedMillivolts <= BATTERY_GOOD_TO_MEDIUM_MV) {
                _voltageState = BatteryState::Medium;
            } else {
                _voltageState = BatteryState::Good;
            }
            break;
    }
}

void BatteryMonitor::updateChargerState() {
    uint8_t pins = static_cast<uint8_t>(
        (digitalRead(PIN_CHARGER_STAT1) == HIGH ? 0b10 : 0) |
        (digitalRead(PIN_CHARGER_STAT2) == HIGH ? 0b01 : 0));
    if (pins != _chargerPins) {
        _chargerPins = pins;
        Serial.printf("[Battery] STAT1=%u STAT2=%u (%s)\n",
                      (pins >> 1U) & 1U, pins & 1U, chargerPinsName(pins));
    }
    // Require a valid battery reading before accepting CHARGING. This rejects
    // the usual unwired-prototype case; the production circuit always has both.
    _charging = _hasValidVoltage && pins == 0b10;
}

void BatteryMonitor::updatePublicState() {
    _state = _charging ? BatteryState::Charging : _voltageState;
}

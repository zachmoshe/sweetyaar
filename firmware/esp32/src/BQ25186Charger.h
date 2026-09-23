#pragma once

#include <Arduino.h>

// Owns the BQ25186 safety configuration and status reads. Configuration
// verification always reads the physical device; there is no register cache.
class BQ25186Charger {
public:
    // Leaves the physical /CE path disabled unless every configured register
    // was written and read back exactly.
    bool begin();

    // Services /INT and performs a complete register read-back every 10 s.
    void poll();

    // Disable charging and the charger's host watchdog before battery-only
    // ESP32 deep sleep while retaining the verified register policy.
    bool prepareForDeepSleep();

    bool healthy() const { return _healthy; }
    bool charging() const { return _healthy && _charging; }
    bool inputPresent() const { return _healthy && _inputPresent; }

private:
    static void IRAM_ATTR interruptHandler();

    bool writeRegister(uint8_t reg, uint8_t value);
    bool readRegister(uint8_t reg, uint8_t& value);
    bool writeAndVerify(uint8_t reg, uint8_t value);
    bool applyConfiguration(uint8_t icControl);
    bool verifyConfiguration(uint8_t icControl);
    bool readStatus();
    void setChargeEnabled(bool enabled);
    void failClosed(const char* reason);

    static volatile bool _interruptPending;
    bool _healthy = false;
    bool _charging = false;
    bool _inputPresent = false;
    bool _chargeEnabled = false;
    uint8_t _lastStat0 = 0xFF;
    uint8_t _lastStat1 = 0xFF;
    int8_t _lastPgLevel = -1;
    uint32_t _lastVerifyMs = 0;
};

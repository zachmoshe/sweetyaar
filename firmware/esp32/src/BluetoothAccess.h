#pragma once
#include <Arduino.h>
#include <atomic>
// The stack's bonds are the only persistent device identities. The NVS marker
// below is a deletion transaction, not a second list of approved devices.
class BluetoothAccess {
public:
    void begin();
    // Call after both stacks start, then from loop. Returns true when access
    // becomes ready after migration/reset. Wait for links to close before commit.
    bool poll(bool linksActive);
    bool ready() const { return _ready.load(); }
    void openPairing(uint32_t now);
    void closePairing();
    bool pairingOpen() const;
    bool classicBonded(const uint8_t* address) const;
    bool classicConnectionsAllowed();
    bool bleBonded(const uint8_t* address) const;
    // Persist the deletion intent before disconnecting. poll() retries removal
    // and a reboot resumes it; access stays closed until deletion completes.
    bool forgetBonds();
    static bool bleIdentity(const uint8_t* address, uint8_t* identity);
private:
    enum class Maintenance { Migrate, Reset, None };
    Maintenance _maintenance = Maintenance::Migrate;
    bool _storageOk = false;
    uint32_t _lastPoll = 0;
    std::atomic<bool> _ready{false};
    std::atomic<bool> _pairing{false};
    std::atomic<uint32_t> _openedAt{0};
};

extern BluetoothAccess bluetoothAccess;

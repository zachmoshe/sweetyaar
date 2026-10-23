#include "BatteryMonitor.h"
#include "ChargerStatus.h"

#include <cstdio>
#include <string>
#include <vector>

// Execute the production loop handler with real ADC filtering/hysteresis.
// Only the audio and BLE transport boundaries are replaced by recorders.
namespace battery_cues {
bool HAS_BQ25186 = true;
bool ENABLE_BLE_PARENT_SERVICE = true;
BatteryMonitor batteryMonitor;
enum class SystemSound { None, Ready, Battery, Charger, Pairing, Error };
struct {
    bool value = false;
    bool connected = false, valid = true, sampledAfterEnable = true;
    bool healthy() { return valid; }
    bool charging() { return valid && value; }
    bool inputPresent() { return valid && (connected || value); }
    ChargerStatus::State status() {
        ChargerStatus::Inputs inputs;
        inputs.valid = valid;
        inputs.inputPresent = inputPresent();
        inputs.hostChargeEnabled = inputPresent();
        inputs.sampledAfterEnableChange = sampledAfterEnable;
        inputs.phase = value ? ChargerStatus::ChargePhase::ConstantCurrent :
                               ChargerStatus::ChargePhase::NotCharging;
        return ChargerStatus::evaluate(inputs);
    }
} charger;
struct {
    bool busy = false;
    SystemSound sound = SystemSound::None;
    bool active() { return busy; }
    void stop(SystemSound target) {
        if (busy && sound == target) busy = false;
    }
} systemAudio;
struct {
    std::vector<uint8_t> notifications;
    void updateBatteryState(uint8_t value) { notifications.push_back(value); }
} bleService;
unsigned requests = 0, chargerRequests = 0;
bool muted = false;
std::vector<SystemSound> heard;
bool batterySoundPending = false;
bool chargerSoundPlayed = false;
bool btLinkConnected = false, btSettleBlePublishPending = false;
uint32_t btConnectedAtMs = 0;
constexpr uint32_t BT_SETTLE_MS = 400;
void playSystemSound(SystemSound sound) {
    assert(sound == SystemSound::Battery || sound == SystemSound::Charger);
    if (sound == SystemSound::Battery) ++requests;
    else ++chargerRequests;
    if (!muted) heard.push_back(sound);
}
#include "battery_events.inc"
} // namespace battery_cues

static void resetInputs(uint32_t startMs = 1000) {
    g_fakeMillis = startMs;
    g_adcReads = 0;
    g_adcValues.clear();
    g_inputPin = g_adcPin = -1;
}

static void startup() {
    resetInputs();
    g_adcValues = {900, 900, 900, 900, 900};
    BatteryMonitor monitor;
    monitor.begin(true);
    assert(g_fakeMillis == 1000 && g_adcReads == 0);
    assert(g_adcPin == PIN_BATTERY_ADC && g_inputPin == PIN_BATTERY_ADC);
    assert(monitor.state() == BatteryState::Unknown);

    // Frequent calls must leave time for other loop work, with no premature
    // level or CHARGING notification before the fifth valid reading.
    for (uint32_t elapsed = 0; elapsed < 400; ++elapsed) {
        g_fakeMillis = 1000 + elapsed;
        assert(!monitor.poll(true));
        assert(g_adcReads == elapsed / 100 + 1);
        assert(monitor.state() == BatteryState::Unknown);
    }
    g_fakeMillis = 1400;
    assert(monitor.poll(true));
    assert(monitor.state() == BatteryState::Charging);
    assert(g_adcReads == 5 && g_adcValues.empty());
    assert(!monitor.poll(true));
    assert(monitor.poll(false));
    assert(monitor.state() == BatteryState::Good);
    assert(!monitor.poll(false));
}

static void latePoll() {
    resetInputs();
    g_adcValues = {900, 900, 900, 900, 900, 900};
    BatteryMonitor monitor;
    monitor.begin(false);
    // Long setup/loop delays never produce catch-up ADC bursts or substitute
    // periodic sampling before the startup observation is complete.
    for (unsigned sample = 1; sample <= 5; ++sample) {
        g_fakeMillis += 40000;
        assert(monitor.poll(false) == (sample == 5));
        assert(g_adcReads == sample);
        assert(!monitor.poll(false));
        g_fakeMillis += 99;
        assert(!monitor.poll(false));
        assert(g_adcReads == sample);
    }
    g_fakeMillis += 90000;
    assert(!monitor.poll(false));
    assert(g_adcReads == 6);
    assert(!monitor.poll(false));
}

static void seedWeight() {
    resetInputs();
    // Startup mean is 4.17 V, followed by 2.002 V. Counting the mean once
    // yields LOW (3.086 V); counting each boot reading would leave it GOOD.
    g_adcValues = {960, 1000, 1040, 1000, 1000, 480, 0};
    BatteryMonitor monitor;
    monitor.begin(false);
    for (unsigned sample = 0; sample < 5; ++sample) {
        g_fakeMillis = 1000 + sample * 100;
        assert(monitor.poll(false) == (sample == 4));
    }
    assert(monitor.state() == BatteryState::Good);
    g_fakeMillis += 29999;
    assert(!monitor.poll(false));
    assert(g_adcReads == 5);
    ++g_fakeMillis;
    assert(monitor.poll(false));
    assert(monitor.state() == BatteryState::Low);
    g_fakeMillis += 30000;
    assert(!monitor.poll(false));
    assert(monitor.state() == BatteryState::Low);  // Invalid periodic read ignored.
    assert(g_adcReads == 7);
}

static void invalidStartup() {
    // An invalid reading anywhere rejects the entire seed, even if charging.
    for (unsigned invalidIndex = 0; invalidIndex < 5; ++invalidIndex) {
        for (uint32_t invalidMv : {0U, 399U, 1151U}) {
            resetInputs();
            g_adcValues = {900, 900, 900, 900, 900, 900};
            g_adcValues[invalidIndex] = invalidMv;
            BatteryMonitor monitor;
            monitor.begin(true);
            for (unsigned sample = 0; sample < 5; ++sample) {
                g_fakeMillis = 1000 + sample * 100;
                assert(!monitor.poll(true));
                assert(monitor.state() == BatteryState::Unknown);
            }
            g_fakeMillis += 29999;
            assert(!monitor.poll(true));
            assert(g_adcReads == 5);
            ++g_fakeMillis;
            assert(monitor.poll(true));
            assert(monitor.state() == BatteryState::Charging);
            assert(g_adcReads == 6);
        }
    }
}

static void wraparound() {
    // Cross millis() wrap during startup, then separately during the 30 s wait.
    for (uint32_t start : {UINT32_MAX - 150U, UINT32_MAX - 30300U}) {
        resetInputs(start);
        g_adcValues = {900, 900, 900, 900, 900, 900};
        BatteryMonitor monitor;
        monitor.begin(false);
        assert(!monitor.poll(false));
        for (unsigned sample = 1; sample < 5; ++sample) {
            g_fakeMillis += 99;
            assert(!monitor.poll(false));
            assert(g_adcReads == sample);
            ++g_fakeMillis;
            assert(monitor.poll(false) == (sample == 4));
        }
        assert(monitor.state() == BatteryState::Good);
        g_fakeMillis += 29999;
        assert(!monitor.poll(false));
        assert(g_adcReads == 5);
        ++g_fakeMillis;
        assert(!monitor.poll(false));
        assert(g_adcReads == 6);
    }
}

static void restart() {
    resetInputs();
    g_adcValues = {1000, 1000, 1000, 1000, 1000};
    BatteryMonitor monitor;
    monitor.begin(true);
    for (unsigned sample = 0; sample < 5; ++sample) {
        g_fakeMillis += 100;
        monitor.poll(true);
    }
    assert(monitor.state() == BatteryState::Charging);
    g_adcValues = {700, 700, 700, 700, 700};
    monitor.begin(false);
    assert(g_adcReads == 5 && monitor.state() == BatteryState::Unknown);
    for (unsigned sample = 0; sample < 5; ++sample) {
        g_fakeMillis += 100;
        assert(monitor.poll(false) == (sample == 4));
    }
    assert(monitor.state() == BatteryState::Low);
    assert(g_adcReads == 10);
}

static void batterySoundEvents() {
    using namespace battery_cues;
    const auto boot = [](uint32_t adc, bool charging = false,
                         unsigned expectedRequests = 0, bool startupCueActive = false) {
        resetInputs();
        requests = 0;
        chargerRequests = 0;
        muted = false;
        heard.clear();
        batterySoundPending = false;
        chargerSoundPlayed = false;
        battery_cues::HAS_BQ25186 = true;
        systemAudio.busy = startupCueActive;
        systemAudio.sound = SystemSound::Ready;
        charger.value = charging;
        charger.connected = false;
        charger.valid = charger.sampledAfterEnable = true;
        btLinkConnected = btSettleBlePublishPending = false;
        battery_cues::ENABLE_BLE_PARENT_SERVICE = true;
        bleService.notifications.clear();
        batteryMonitor.begin(charging);
        for (unsigned i = 0; i < 5; ++i) {
            g_adcValues.push_back(adc);
            g_fakeMillis += 100;
            pollBatteryState();
        }
        assert(requests == expectedRequests);
    };
    const auto sample = [](uint32_t adc, unsigned count = 1) {
        for (unsigned i = 0; i < count; ++i) {
            g_adcValues.push_back(adc);
            g_fakeMillis += BATTERY_SAMPLE_INTERVAL_MS;
            pollBatteryState();
        }
    };

    boot(0); // No state change until there is a valid reading.
    sample(790);
    assert(batteryMonitor.state() == BatteryState::Medium && requests == 1);
    boot(700, false, 1); // First LOW reading after power-on or wake warns once.
    for (unsigned i = 0; i < 100; ++i) pollBatteryState();
    assert(requests == 1);
    boot(790, false, 1); // First MEDIUM reading also warns once.
    for (unsigned i = 0; i < 100; ++i) pollBatteryState();
    assert(requests == 1);
    for (uint32_t adc : {700U, 790U, 900U}) {
        boot(adc, true); // Charger takes precedence at every battery level.
        assert(chargerRequests == 1);
    }
    boot(900);

    for (uint32_t adc : {700U, 790U}) {
        // Real startup sampling runs while Ready/Error owns the speaker.
        boot(adc, false, 0, true);
        assert(batterySoundPending);
        systemAudio.busy = false;
        pollBatteryState();
        pollBatteryState();
        assert(!batterySoundPending && requests == 1);
    }

    boot(900);
    sample(790, 10); // GOOD -> MEDIUM, then stable.
    assert(batteryMonitor.state() == BatteryState::Medium && requests == 1);
    sample(700, 10); // MEDIUM -> LOW, same cue, then stable.
    assert(batteryMonitor.state() == BatteryState::Low && requests == 2);
    for (unsigned i = 0; i < 100; ++i) pollBatteryState();
    assert(requests == 2);
    sample(790, 10); // LOW -> MEDIUM is a new warning band, so cue again.
    assert(batteryMonitor.state() == BatteryState::Medium && requests == 3);
    sample(900, 10);
    assert(batteryMonitor.state() == BatteryState::Good && requests == 3);
    charger.value = true;
    pollBatteryState();
    assert(batteryMonitor.state() == BatteryState::Charging && requests == 3);
    sample(700, 10); // Public CHARGING is unchanged; no repeat for hidden voltage changes.
    assert(requests == 3);
    charger.value = false;
    pollBatteryState();
    assert(batteryMonitor.state() == BatteryState::Low && requests == 4);

    boot(1000);
    sample(480); // A sudden drop can skip MEDIUM; emit only one cue.
    assert(batteryMonitor.state() == BatteryState::Low && requests == 1);

    boot(900);
    systemAudio.busy = true;
    sample(790, 10);
    assert(batterySoundPending && requests == 0);
    sample(700, 10); // Pending MEDIUM and LOW warnings coalesce into one cue.
    assert(batterySoundPending && requests == 0);
    systemAudio.busy = false;
    pollBatteryState();
    pollBatteryState();
    assert(!batterySoundPending && requests == 1);

    boot(900);
    systemAudio.busy = true;
    sample(790, 10);
    assert(batterySoundPending);
    sample(900, 10); // GOOD cancels a pending warning.
    systemAudio.busy = false;
    pollBatteryState();
    assert(!batterySoundPending && requests == 0);

    boot(900);
    systemAudio.busy = true;
    sample(790, 10);
    charger.value = true;
    pollBatteryState(); // Starting charging cancels a pending warning.
    assert(!batterySoundPending && requests == 0);
    systemAudio.busy = false;
    pollBatteryState();
    assert(!batterySoundPending && requests == 0);

    boot(1000);
    battery_cues::ENABLE_BLE_PARENT_SERVICE = false;
    bleService.notifications.clear();
    sample(480);
    assert(requests == 1 && bleService.notifications.empty());

    boot(1000);
    btLinkConnected = true;
    btConnectedAtMs = g_fakeMillis + BATTERY_SAMPLE_INTERVAL_MS;
    bleService.notifications.clear();
    sample(480);
    assert(requests == 1 && bleService.notifications.empty() && btSettleBlePublishPending);
}

static void chargerSoundEvents() {
    using namespace battery_cues;
    const auto boot = [](bool connected, bool charging, bool busy = false,
                         bool valid = true, bool mutedAtBoot = false, bool hardware = true) {
        resetInputs();
        battery_cues::HAS_BQ25186 = hardware;
        battery_cues::ENABLE_BLE_PARENT_SERVICE = true;
        requests = chargerRequests = 0;
        batterySoundPending = chargerSoundPlayed = false;
        muted = mutedAtBoot;
        heard.clear();
        systemAudio.busy = busy;
        systemAudio.sound = SystemSound::Ready;
        charger.connected = connected;
        charger.value = charging;
        charger.valid = valid;
        charger.sampledAfterEnable = true;
        btLinkConnected = btSettleBlePublishPending = false;
        batteryMonitor.begin(hardware && charger.charging());
        for (unsigned i = 0; i < 5; ++i) {
            g_adcValues.push_back(700); // LOW unless charging overrides it.
            g_fakeMillis += 100;
            pollBatteryState();
        }
    };

    boot(true, true, true); // Boot/wake on a charger waits for Ready.
    assert(requests == 0 && chargerRequests == 0 && !batterySoundPending);
    systemAudio.busy = false;
    pollBatteryState();
    assert((heard == std::vector<SystemSound>{SystemSound::Charger}));
    for (unsigned i = 0; i < 100; ++i) pollBatteryState();
    assert(chargerRequests == 1);

    // Thermal/current pauses with valid input never warn or re-arm charging.
    for (unsigned pause = 0; pause < 3; ++pause) {
        charger.value = false;
        pollBatteryState();
        assert(batteryMonitor.state() == BatteryState::Low);
        charger.value = true;
        pollBatteryState();
        assert(chargerRequests == 1 && requests == 0);
    }
    charger.valid = false; // Communication failure is not a cable removal.
    pollBatteryState();
    charger.valid = true;
    pollBatteryState();
    assert(chargerRequests == 1 && requests == 0);

    charger.connected = charger.value = false;
    pollBatteryState(); // A confirmed unplug re-arms the connection cue.
    assert(requests == 1 && !chargerSoundPlayed);
    charger.connected = true;
    pollBatteryState(); // Presence alone is insufficient.
    assert(chargerRequests == 1);
    charger.value = true;
    charger.sampledAfterEnable = false;
    pollBatteryState(); // Raw CC/CV from before /CE changed is insufficient.
    assert(chargerRequests == 1);
    charger.sampledAfterEnable = true;
    pollBatteryState();
    assert(chargerRequests == 2 && requests == 1);

    boot(true, false); // Cable attached, but paused/full: both cues silent.
    assert(requests == 0 && chargerRequests == 0);
    for (unsigned i = 0; i < 10; ++i) {
        g_adcValues.push_back(790);
        g_fakeMillis += BATTERY_SAMPLE_INTERVAL_MS;
        pollBatteryState();
    }
    assert(batteryMonitor.state() == BatteryState::Medium);
    for (unsigned i = 0; i < 10; ++i) {
        g_adcValues.push_back(700);
        g_fakeMillis += BATTERY_SAMPLE_INTERVAL_MS;
        pollBatteryState();
    }
    assert(batteryMonitor.state() == BatteryState::Low && requests == 0);
    charger.value = true; // First actual charging can confirm this connection.
    pollBatteryState();
    assert(chargerRequests == 1);

    boot(false, false, true); // Pending battery warning is discarded on plug.
    assert(batterySoundPending);
    charger.connected = true;
    pollBatteryState();
    assert(!batterySoundPending && systemAudio.busy);
    charger.value = true;
    for (auto cue : {SystemSound::Ready, SystemSound::Pairing, SystemSound::Error}) {
        systemAudio.sound = cue;
        pollBatteryState();
        assert(systemAudio.busy && chargerRequests == 0);
    }
    systemAudio.busy = false;
    pollBatteryState();
    assert(chargerRequests == 1 && requests == 0);

    boot(false, false);
    systemAudio.busy = true;
    systemAudio.sound = SystemSound::Battery;
    charger.connected = true;
    pollBatteryState(); // Also stop a warning already in progress.
    assert(!systemAudio.busy && chargerRequests == 0);
    charger.value = true;
    pollBatteryState();
    assert(chargerRequests == 1);

    boot(false, false, false, false); // Unknown input at boot suppresses LOW.
    assert(requests == 0 && chargerRequests == 0);
    charger.connected = charger.value = charger.valid = true;
    pollBatteryState();
    assert(chargerRequests == 1 && requests == 0);

    boot(true, true, false, true, true); // Muted cue consumed once.
    assert(chargerSoundPlayed && chargerRequests == 1 && heard.empty());
    muted = false;
    charger.value = false;
    pollBatteryState();
    charger.value = true;
    pollBatteryState();
    assert(heard.empty() && chargerRequests == 1);

    boot(true, true, false, true, false, false); // Generic board has no charger.
    assert(requests == 1 && chargerRequests == 0);
    boot(false, false);
    battery_cues::ENABLE_BLE_PARENT_SERVICE = false;
    charger.connected = charger.value = true;
    pollBatteryState();
    assert(chargerRequests == 1);
}

static void chargerDoesNotRepeatWithTime() {
    using namespace battery_cues;
    resetInputs(UINT32_MAX - 2500); // No replay after time passes or wraps.
    g_adcValues = {900, 900, 900, 900, 900};
    batteryMonitor.begin(true);
    requests = chargerRequests = 0;
    charger.connected = charger.value = charger.valid = charger.sampledAfterEnable = true;
    systemAudio.busy = false;
    chargerSoundPlayed = batterySoundPending = false;
    pollBatteryState();
    assert(chargerRequests == 1);

    for (unsigned tick = 0; tick < 10; ++tick) {
        g_fakeMillis += 1000;
        systemAudio.busy = tick % 2;
        pollBatteryState();
        assert(chargerRequests == 1);
    }
    systemAudio.busy = false;
    charger.value = false;
    pollBatteryState();
    charger.value = true;
    pollBatteryState();
    assert(chargerRequests == 1); // Pausing/resuming charge cannot replay it.
    charger.valid = false;
    g_fakeMillis += 1500;
    pollBatteryState();
    charger.valid = true;
    pollBatteryState();
    g_fakeMillis += 1000;
    pollBatteryState();
    assert(chargerRequests == 1 && requests == 0);

    charger.connected = charger.value = false;
    pollBatteryState();
    assert(!chargerSoundPlayed);
    charger.connected = charger.value = true;
    pollBatteryState();
    assert(chargerRequests == 2); // Only a new connection gets another cue.
}

int main(int argc, char** argv) {
    assert(argc == 2);
    const std::string scenario = argv[1];
    if (scenario == "startup") startup();
    else if (scenario == "late_poll") latePoll();
    else if (scenario == "seed_weight") seedWeight();
    else if (scenario == "invalid_startup") invalidStartup();
    else if (scenario == "wraparound") wraparound();
    else if (scenario == "restart") restart();
    else if (scenario == "sound_events") batterySoundEvents();
    else if (scenario == "charger_sound_events") {
        chargerSoundEvents();
        chargerDoesNotRepeatWithTime();
    }
    else return 1;
    std::puts("battery monitor test passed");
}

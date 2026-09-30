#include "BatteryMonitor.h"

#include <cstdio>
#include <string>

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

int main(int argc, char** argv) {
    assert(argc == 2);
    const std::string scenario = argv[1];
    if (scenario == "startup") startup();
    else if (scenario == "late_poll") latePoll();
    else if (scenario == "seed_weight") seedWeight();
    else if (scenario == "invalid_startup") invalidStartup();
    else if (scenario == "wraparound") wraparound();
    else if (scenario == "restart") restart();
    else return 1;
    std::puts("battery monitor test passed");
}

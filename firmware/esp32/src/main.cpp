#include <Arduino.h>
#include <SPI.h>
#include <SD.h>
#include <esp_heap_caps.h>
#include <esp_random.h>
#include <esp_bt_device.h>
#include <esp_gap_bt_api.h>
#include <esp_sleep.h>
#include <esp_task_wdt.h>
#include <sys/time.h>
#include <time.h>
#include <driver/rtc_io.h>

// --- Audio tools ---
#include "AudioTools.h"
#include "BluetoothA2DPSink.h"

// --- Project modules ---
#include "Config.h"
#include "LowLatencyA2DPSinkQueued.h"
#include "NVSConfig.h"
#include "ParentConfig.h"
#include "ContentCatalog.h"
#include "BedtimeMode.h"
#include "PeripheralPower.h"
#include "ButtonHandler.h"
#include "WavPlayer.h"
#include "BLEParentService.h"
#include "StateMachine.h"
#include "StatusLed.h"
#include "BatteryMonitor.h"
#include "BQ25186Charger.h"
#include "SleepEntryCheck.h"

// ---------------------------------------------------------------------------
// Global objects
// ---------------------------------------------------------------------------
NVSConfig       nvs;
ParentConfig    parentConfig;
ButtonHandler   buttons;
BLEParentService bleService;
StateMachine    sm;
BatteryMonitor  batteryMonitor;
BQ25186Charger  charger;
SleepEntryCheck sleepEntryCheck;

// Audio pipeline:
//   BT A2DP: A2DP sink -> I2SStream -> MAX98357A
//   WAV/SD:  WAV decoder -> VolumeStream -> I2SStream -> MAX98357A
I2SStream       i2sOut;
VolumeStream    volumeOut;
WavPlayer       wavPlayer(volumeOut);
BluetoothA2DPSink* btSink = nullptr;

// Track previous state to detect transitions in the main loop
State prevState = State::IDLE;
bool prevLoopMode = false;
bool sdReady = false;
String activeTheme = DEFAULT_THEME;
String currentPlaybackTheme = DEFAULT_THEME;
String currentDeviceName = DEFAULT_BT_NAME;
String themeIds[BLE_MAX_THEMES];
String themeNames[BLE_MAX_THEMES];
String bleThemesJson = "[]";
int themeCount = 0;
uint8_t currentVolumePct = DEFAULT_VOLUME_PCT;
uint8_t currentEffectiveVolumePct = DEFAULT_VOLUME_PCT;
bool btReopenPending = false;
bool btNameApplyPending = false;
uint32_t btReopenAtMs = 0;
const uint32_t BT_REOPEN_DELAY_MS = 1500;
volatile bool btLinkConnected = false;
volatile bool btAudioActive = false;
uint32_t lastBleStatusPublishMs = 0;
// After BT A2DP connects, hold off BLE notify() calls for this many ms.
// The BTDM HCI transport asserts if BLE packets are injected while A2DP is
// still completing its stream setup (hci_hal_h4.c:553).
static const uint32_t BT_SETTLE_MS = 400;
uint32_t btConnectedAtMs = 0;
bool btSettleBlePublishPending = false;
bool wokeFromVibration = false;
bool realActivitySeenSinceWake = false;
bool lastBleConnected = false;
uint32_t lastActivityMs = 0;
uint32_t lastBleActivityMs = 0;
bool bedtimeClockReliable = false;
int16_t bedtimeTzOffsetMin = 0;
BedtimeMode::Override bedtimeOverride = BedtimeMode::Override::None;
time_t bedtimeOverrideUntilUtc = 0;
bool lastBedtimeActive = false;
String bedtimeThemeOverride;
String lastInvalidBedtimeThemeLog;

RTC_DATA_ATTR uint32_t rtcBedtimeClockMagic = 0;
RTC_DATA_ATTR int16_t rtcBedtimeTzOffsetMin = 0;
static constexpr uint32_t RTC_BEDTIME_CLOCK_MAGIC = 0xBED71AAB;

RTC_DATA_ATTR uint32_t rtcHeapRestartCount = 0;
RTC_DATA_ATTR uint32_t rtcHeapRestartMagic = 0;
static constexpr uint32_t RTC_HEAP_RESTART_MAGIC = 0xBEEFD00DUL;
static constexpr uint32_t MAX_HEAP_RESTARTS = 3;

// ---------------------------------------------------------------------------
// Forward declarations
// ---------------------------------------------------------------------------
void setupWakeState();
void setupLoopTaskWatchdog();
void setupPeripheralPower();
void setAmpMuted(bool muted);
void setupI2S();
void resetI2SOutput(const char* owner);
void setupBT(const String& deviceName);
void printBluetoothAddress(const char* label);
void scheduleBluetoothReopen(const char* reason);
void reopenBluetoothForPairing(const char* reason);
void pollBluetoothReopen();
void applyVolume(uint8_t pct);
void applyEffectiveVolume(const char* reason);
uint8_t effectiveVolumePct();
void handleStateEntry(State prev, State next);
void updateStatusSignalsForState(State state);
void printStatusLedModeLegend();
bool processStateMachineTransitions();
bool handleBleControls();
void handleBleConfigCommands();
void handleBleConfigCommand(const String& commandJson);
void handleBleCommand(uint8_t command);
void publishBleValues();
void sendNotice(const String& severity, const String& message);
void notifyPlaybackFailure(bool animal);
void playSong();
void playNextSong();
void playAnimal();
void playNextAnimal();
void setupBedtimeClock(esp_sleep_wakeup_cause_t wakeCause);
void syncBedtimeClock(time_t epochSec, int16_t tzOffsetMin);
void pollBedtimeMode();
bool bedtimeTimeKnown();
bool bedtimeLocalMinute(uint16_t& minuteOut);
uint32_t bedtimeLocalSecondOfDay();
bool bedtimeAutomaticActive();
bool bedtimeRuntimeActive();
void setBedtimeRuntimeActive(bool active, const char* reason);
void clearExpiredBedtimeOverride();
String bedtimeEffectiveSongTheme();
String bedtimeOverrideName();
String bedtimeTimeString(uint16_t minuteOfDay);
String bedtimeCurrentTimeString();
uint16_t parseBedtimeTimeString(const char* value, uint16_t fallback);
void markActivity(const char* reason);
void markBleActivity(const char* reason);
void pollBleConnectionState();
uint32_t currentSleepTimeoutMs();
uint32_t readSleepSeconds(JsonObjectConst sleep, const char* key, uint32_t fallbackMs);
bool bleIdleAllowsSleep();
bool stateAllowsIdleSleep(State state);
bool canEnterIdleSleep();
void pollIdleSleep();
void preparePinsForPeripheralPowerOff();
void enterIdleDeepSleep();
String bleStatusForState(State state);
void refreshThemeList();
void applyActiveThemeFallback();
void applyDeviceName(const String& deviceName);
void applyPendingBtNameIfPossible();
String buildConfigAttribute(size_t index);
void publishConfigAttributes();
String buildConfigOkResponse(uint32_t requestId, const String& op);
String buildConfigErrorResponse(uint32_t requestId, const String& message);
bool isKnownTheme(const String& theme);
String themeDisplayName(const String& theme);
String fileNameOf(const String& path);
String formatRemaining(uint32_t remainingMs);

// ---------------------------------------------------------------------------
// BT A2DP callbacks (fire from BT task — post to SM queue, never block)
// ---------------------------------------------------------------------------
static void btConnectionStateChanged(esp_a2d_connection_state_t state,
                                     void* /*obj*/) {
    if (state == ESP_A2D_CONNECTION_STATE_CONNECTED) {
        btLinkConnected = true;
        btAudioActive = false;
        statusLed.setSignal(StatusSignal::BluetoothPlaying, false);
        statusLed.setSignal(StatusSignal::BluetoothConnected, true);
        btConnectedAtMs = millis();
        Serial.printf("[BT] Connected (free=%u largest=%u)\n",
                      ESP.getFreeHeap(), ESP.getMaxAllocHeap());
        sm.postEvent(Event::BT_CONNECTED);
    } else if (state == ESP_A2D_CONNECTION_STATE_DISCONNECTED) {
        btLinkConnected = false;
        btAudioActive = false;
        statusLed.setSignal(StatusSignal::BluetoothPlaying, false);
        statusLed.setSignal(StatusSignal::BluetoothConnected, false);
        Serial.println("[BT] Disconnected");
        sm.postEvent(Event::BT_DISCONNECTED);
    }
}

static const char* btAudioStateName(esp_a2d_audio_state_t state) {
    switch (state) {
        case ESP_A2D_AUDIO_STATE_STARTED:
            return "STARTED";
        case ESP_A2D_AUDIO_STATE_STOPPED:
            return "STOPPED";
        case ESP_A2D_AUDIO_STATE_REMOTE_SUSPEND:
            return "REMOTE_SUSPEND";
        default:
            return "UNKNOWN";
    }
}

static void btAudioStateChanged(esp_a2d_audio_state_t state, void*) {
    Serial.printf("[BT] Audio state: %s\n", btAudioStateName(state));
    if (state == ESP_A2D_AUDIO_STATE_STARTED) {
        if (!btAudioActive) {
            markActivity("BT audio started");
        }
        btAudioActive = true;
        statusLed.setSignal(StatusSignal::BluetoothPlaying, true);
    } else if (state == ESP_A2D_AUDIO_STATE_STOPPED ||
               state == ESP_A2D_AUDIO_STATE_REMOTE_SUSPEND) {
        if (btAudioActive) {
            markActivity("BT audio inactive");
        }
        btAudioActive = false;
        statusLed.setSignal(StatusSignal::BluetoothPlaying, false);
    }
}

static void btSampleRateChanged(uint16_t rate) {
    Serial.printf("[BT] A2DP sample rate: %u Hz\n", rate);
}

// ---------------------------------------------------------------------------
// setup()
// ---------------------------------------------------------------------------
void setup() {
    // Keep charging disabled before any startup work; enable only after the
    // charger configuration has been written and verified by charger.begin().
    if (HAS_BQ25186) {
        digitalWrite(PIN_CHARGER_ENABLE, LOW);
        pinMode(PIN_CHARGER_ENABLE, OUTPUT);
    }
    Serial.begin(115200);
    // Assert the selected board's shutdown level before peripheral power starts.
    pinMode(PIN_AMP_MUTE, OUTPUT);
    setAmpMuted(true);

    delay(500);
    Serial.println("\n=== SweetYaar Boot ===");
    Serial.printf("[Audio] GPIO%d mute is active-%s\n",
                  PIN_AMP_MUTE,
                  AMP_MUTE_ACTIVE_HIGH
                      ? "HIGH (generic board)"
                      : "LOW (production board)");
    setupWakeState();
    // Keep LED DIN inactive before 5V_PERIPH_SW starts. With direct drive this
    // is LOW, avoiding back-powering the LED through its input.
    statusLed.prepareForPeripheralPowerOn();
    setupPeripheralPower();

    statusLed.begin();
    printStatusLedModeLegend();

    // Device-local NVS config
    nvs.begin();
    currentDeviceName = nvs.getBtName();
    if (currentDeviceName.length() > 32 || ContentCatalog::jsonEscape(currentDeviceName).length() > 64) {
        Serial.printf("[Config] Ignoring oversized device name: %s\n", currentDeviceName.c_str());
        currentDeviceName = DEFAULT_BT_NAME;
    }
    Serial.printf("[Device] btName=%s\n", currentDeviceName.c_str());

    // Buttons
    buttons.begin();
    sm.begin();

    // I2S (must be set up before BT sink and WAV player)
    setupI2S();

    // Bluetooth A2DP sink. Reserve its audio queue before SD/WAV playback has
    // a chance to fragment heap; otherwise connection-time allocation can fail.
    setupBT(currentDeviceName);

    // Seed the PRNG used for song/animal shuffling. esp_random() is the
    // hardware RNG, now true-random with the BT RF subsystem running. Without
    // this, random() returns the same sequence every boot and "shuffle" picks
    // the identical order each power-on.
    randomSeed(esp_random());

    // SD card + WAV player
    sdReady = wavPlayer.begin();
    if (!sdReady) {
        Serial.println("[WARN] SD init failed; WAV playback unavailable");
        statusLed.setSignal(StatusSignal::Error, true);
    } else {
        if (!parentConfig.load()) {
            statusLed.setSignal(StatusSignal::Error, true);
        }
        // Single SD pass: read the whole content catalog into RAM. Every later
        // theme/song lookup (playback, BLE theme list, settings scans) is served
        // from memory; the card is re-read only on reboot.
        ContentCatalog::buildCatalog();
        refreshThemeList();
    }
    activeTheme = parentConfig.defaultTheme();
    applyActiveThemeFallback();

    // Apply SD-configured volume, or the static firmware default.
    applyVolume(parentConfig.defaultVolumePct());

    // The production /CE circuit remains fail-closed until every BQ25186
    // setting has been written and read back. The generic fixture has no
    // charger and compiles this path out through its board flag.
    if (HAS_BQ25186 && !charger.begin()) {
        statusLed.setSignal(StatusSignal::Error, true);
    }

    // Battery initialization deliberately happens after the high-current boot
    // work. Five readings over roughly 500 ms seed an immediate coarse state;
    // later readings extend the rolling window at 30-second intervals.
    batteryMonitor.begin(HAS_BQ25186 && charger.charging());

    // BLE parent service — shares the controller already started by A2DP.
    if (ENABLE_BLE_PARENT_SERVICE) {
        bleService.begin(currentDeviceName);
        bleService.updateThemes(bleThemesJson);
        publishBleValues();
        pollBedtimeMode();
    } else {
        Serial.println("[BLE] Parent service disabled for A2DP audio test");
    }

    updateStatusSignalsForState(sm.currentState());
    statusLed.setSignal(StatusSignal::Initializing, false);
    statusLed.service(millis());
    lastActivityMs = millis();
    lastBleActivityMs = millis();
    lastBleConnected = ENABLE_BLE_PARENT_SERVICE && bleService.isConnected();
    setupLoopTaskWatchdog();

    Serial.println("[Boot] Ready.");
}

// ---------------------------------------------------------------------------
// loop()
// ---------------------------------------------------------------------------
void loop() {
    esp_task_wdt_reset();

    // Process asynchronous BT events before accepting local/BLE input.
    processStateMachineTransitions();

    // 1. Poll buttons
    buttons.update();

    // 2. Post button events to state machine.
    //    BT_STREAMING and KILLSWITCH: buttons fully ignored.
    //    Same-category presses while WAV is playing advance immediately.
    State cur = sm.currentState();
    if (cur == State::BT_STREAMING || cur == State::KILLSWITCH) {
        buttons.discardEvents();
    } else {
        if (buttons.wasBothPressed()) {
            markActivity("both buttons");
            sm.postEvent(Event::BOTH_BUTTONS_PRESS);
        } else if (buttons.wasBtn1Pressed()) {
            markActivity("button 1");
            if (cur == State::PLAYING_SONG) {
                playNextSong();  // advance track; stay in PLAYING_SONG
                publishBleValues();
            } else {
                sm.postEvent(Event::BUTTON1_PRESS);
            }
        } else if (buttons.wasBtn2Pressed()) {
            markActivity("button 2");
            if (cur == State::PLAYING_ANIMAL) {
                playNextAnimal();  // advance animal; stay in PLAYING_ANIMAL
                publishBleValues();
            } else {
                sm.postEvent(Event::BUTTON2_PRESS);
            }
        }
    }

    // 3. Poll BLE characteristics. Writes are only local-toy controls;
    //    during BT streaming they are ignored and current values are restored.
    bool bleWriteSeen = handleBleControls();
    handleBleConfigCommands();
    pollBedtimeMode();
    pollBleConnectionState();

    if (HAS_BQ25186) {
        charger.poll();
        if (!charger.healthy()) {
            // Latch the visible error; failClosed() has already disabled /CE.
            statusLed.setSignal(StatusSignal::Error, true);
        }
    }

    // Battery state is a separate one-byte BLE value. Avoid injecting a BLE
    // notification into the short Classic-BT connection settle interval.
    if (batteryMonitor.poll(HAS_BQ25186 && charger.charging()) &&
        ENABLE_BLE_PARENT_SERVICE) {
        if (btLinkConnected && millis() - btConnectedAtMs < BT_SETTLE_MS) {
            btSettleBlePublishPending = true;
        } else {
            bleService.updateBatteryState(batteryMonitor.encodedState());
        }
    }

    // 4. WAV player: signal SM when a track ends. Looping deliberately uses
    //    the same next-song path as another song-button press, preserving the
    //    current sequential/shuffled rotation and wrapping at its end.
    if (cur == State::PLAYING_SONG && wavPlayer.isIdle()) {
        if (sm.loopMode()) {
            playNextSong();
            if (wavPlayer.isIdle()) {
                // The live catalog may have become empty or the SD card may
                // have disappeared. Do not spin forever retrying a bad list.
                sm.postEvent(Event::LOOP_OFF);
                sm.postEvent(Event::WAV_FINISHED);
            } else {
                publishBleValues();
            }
        } else {
            sm.postEvent(Event::WAV_FINISHED);
        }
    } else if (cur == State::PLAYING_ANIMAL && wavPlayer.isIdle()) {
        sm.postEvent(Event::WAV_FINISHED);
    }

    // 5. Process state machine
    bool changed = processStateMachineTransitions();
    if (bleWriteSeen && !changed) {
        publishBleValues();
    }
    if (btSettleBlePublishPending && millis() - btConnectedAtMs >= BT_SETTLE_MS) {
        btSettleBlePublishPending = false;
        publishBleValues();
    }
    if (ENABLE_BLE_PARENT_SERVICE && sm.currentState() == State::KILLSWITCH &&
        (millis() - lastBleStatusPublishMs) >= 1000) {
        bleService.updateStatus(bleStatusForState(sm.currentState()));
        lastBleStatusPublishMs = millis();
    }

    // 7. Feed WAV data to I2S (must be called every loop when playing)
    wavPlayer.loop();

    // 8. Re-open BT after a short disconnect cooldown.
    pollBluetoothReopen();
    applyPendingBtNameIfPossible();
    if (ENABLE_BLE_PARENT_SERVICE) bleService.pollAdvertising();
    statusLed.service(millis());
    pollIdleSleep();

    esp_task_wdt_reset();
    delay(wavPlayer.isIdle() ? 5 : 1);  // keep WAV streaming fed while still yielding
}

// ---------------------------------------------------------------------------
// setupLoopTaskWatchdog()
// ---------------------------------------------------------------------------
void setupLoopTaskWatchdog() {
    // Arduino/ESP-IDF already initializes the task watchdog and registers the
    // CPU0 idle task. Use the core helper so its loop wrapper also feeds this
    // CPU1 task before each loop() call.
    enableLoopWDT();
    esp_err_t status = esp_task_wdt_status(nullptr);
    if (status != ESP_OK) {
        Serial.printf("[Watchdog] CPU1 loop task registration failed: %d\n",
                      static_cast<int>(status));
        statusLed.setSignal(StatusSignal::Error, true);
        return;
    }
    Serial.printf("[Watchdog] CPU1 loop task armed (%ds)\n",
                  CONFIG_ESP_TASK_WDT_TIMEOUT_S);
}

// ---------------------------------------------------------------------------
// setupWakeState()
// ---------------------------------------------------------------------------
void setupWakeState() {
    esp_sleep_wakeup_cause_t cause = esp_sleep_get_wakeup_cause();
    wokeFromVibration = (cause == ESP_SLEEP_WAKEUP_EXT0);
    realActivitySeenSinceWake = !wokeFromVibration;

    rtc_gpio_deinit(static_cast<gpio_num_t>(PIN_VIB_WAKE));
    pinMode(PIN_VIB_WAKE, INPUT);

    Serial.printf("[Sleep] Wake cause=%d vibration=%d\n",
                  static_cast<int>(cause), wokeFromVibration ? 1 : 0);
    setupBedtimeClock(cause);
}

// ---------------------------------------------------------------------------
// setupPeripheralPower()
// ---------------------------------------------------------------------------
void setupPeripheralPower() {
    enablePeripheralPower();
    Serial.printf("[Power] Peripherals enabled on GPIO%d\n", PIN_PERIPH_PWR_EN);
}

// ---------------------------------------------------------------------------
// setAmpMuted()
// ---------------------------------------------------------------------------
void setAmpMuted(bool muted) {
    bool driveHigh = muted ? AMP_MUTE_ACTIVE_HIGH : !AMP_MUTE_ACTIVE_HIGH;
    digitalWrite(PIN_AMP_MUTE, driveHigh ? HIGH : LOW);
}

// ---------------------------------------------------------------------------
// markActivity()
// ---------------------------------------------------------------------------
void markActivity(const char* reason) {
    sleepEntryCheck.reset();
    lastActivityMs = millis();
    realActivitySeenSinceWake = true;
    (void)reason;
}

// ---------------------------------------------------------------------------
// markBleActivity()
// ---------------------------------------------------------------------------
void markBleActivity(const char* reason) {
    lastBleActivityMs = millis();
    markActivity(reason);
}

// ---------------------------------------------------------------------------
// pollBleConnectionState()
// ---------------------------------------------------------------------------
void pollBleConnectionState() {
    if (!ENABLE_BLE_PARENT_SERVICE) {
        return;
    }

    bool connected = bleService.isConnected();
    if (connected != lastBleConnected) {
        lastBleConnected = connected;
        markBleActivity(connected ? "BLE connected" : "BLE disconnected");
        if (connected) publishConfigAttributes(); // Fresh clock sample on reconnect.
    }
}

// ---------------------------------------------------------------------------
// setupBedtimeClock()
// ---------------------------------------------------------------------------
void setupBedtimeClock(esp_sleep_wakeup_cause_t wakeCause) {
    // Both vibration and charger wake retain the RTC clock across deep sleep.
    bedtimeClockReliable =
        (wakeCause == ESP_SLEEP_WAKEUP_EXT0 ||
         wakeCause == ESP_SLEEP_WAKEUP_EXT1) &&
        rtcBedtimeClockMagic == RTC_BEDTIME_CLOCK_MAGIC;
    if (bedtimeClockReliable) {
        bedtimeTzOffsetMin = rtcBedtimeTzOffsetMin;
        Serial.printf("[Bedtime] Clock retained from deep sleep (tzOffsetMin=%d)\n",
                      bedtimeTzOffsetMin);
    } else {
        bedtimeTzOffsetMin = 0;
        Serial.println("[Bedtime] Clock unknown until parent app syncs local time");
    }
}

// ---------------------------------------------------------------------------
// syncBedtimeClock()
// ---------------------------------------------------------------------------
void syncBedtimeClock(time_t epochSec, int16_t tzOffsetMin) {
    timeval tv;
    tv.tv_sec = epochSec;
    tv.tv_usec = 0;
    settimeofday(&tv, nullptr);

    bedtimeClockReliable = true;
    bedtimeTzOffsetMin = tzOffsetMin;
    rtcBedtimeClockMagic = RTC_BEDTIME_CLOCK_MAGIC;
    rtcBedtimeTzOffsetMin = tzOffsetMin;

    Serial.printf("[Bedtime] Time synced epoch=%ld tzOffsetMin=%d\n",
                  static_cast<long>(epochSec), tzOffsetMin);
    pollBedtimeMode();
}

// ---------------------------------------------------------------------------
// bedtimeTimeKnown()
// ---------------------------------------------------------------------------
bool bedtimeTimeKnown() {
    if (!bedtimeClockReliable) {
        return false;
    }
    return time(nullptr) >= 946684800;  // 2000-01-01; filters out unset RTC.
}

// ---------------------------------------------------------------------------
// bedtimeLocalMinute()
// ---------------------------------------------------------------------------
bool bedtimeLocalMinute(uint16_t& minuteOut) {
    if (!bedtimeTimeKnown()) {
        return false;
    }

    time_t localEpoch = time(nullptr) + static_cast<time_t>(bedtimeTzOffsetMin) * 60;
    tm localTm;
    gmtime_r(&localEpoch, &localTm);
    minuteOut = static_cast<uint16_t>(localTm.tm_hour * 60 + localTm.tm_min);
    return true;
}

// ---------------------------------------------------------------------------
// bedtimeLocalSecondOfDay()
// ---------------------------------------------------------------------------
uint32_t bedtimeLocalSecondOfDay() {
    if (!bedtimeTimeKnown()) {
        return 0;
    }

    time_t localEpoch = time(nullptr) + static_cast<time_t>(bedtimeTzOffsetMin) * 60;
    tm localTm;
    gmtime_r(&localEpoch, &localTm);
    return static_cast<uint32_t>(localTm.tm_hour) * 3600UL +
           static_cast<uint32_t>(localTm.tm_min) * 60UL +
           static_cast<uint32_t>(localTm.tm_sec);
}

// ---------------------------------------------------------------------------
// bedtimeAutomaticActive()
// ---------------------------------------------------------------------------
bool bedtimeAutomaticActive() {
    uint16_t minute = 0;
    if (!bedtimeLocalMinute(minute)) {
        return false;
    }
    return BedtimeMode::evaluate(
        parentConfig.bedtimeEnabled(), true, minute,
        parentConfig.bedtimeStartMinutes(), parentConfig.bedtimeEndMinutes(),
        BedtimeMode::Override::None).automaticActive;
}

// ---------------------------------------------------------------------------
// bedtimeRuntimeActive()
// ---------------------------------------------------------------------------
bool bedtimeRuntimeActive() {
    uint16_t minute = 0;
    if (!bedtimeLocalMinute(minute)) {
        return false;
    }
    return BedtimeMode::evaluate(
        parentConfig.bedtimeEnabled(), true, minute,
        parentConfig.bedtimeStartMinutes(), parentConfig.bedtimeEndMinutes(),
        bedtimeOverride).active;
}

// ---------------------------------------------------------------------------
// setBedtimeRuntimeActive()
// ---------------------------------------------------------------------------
void setBedtimeRuntimeActive(bool active, const char* reason) {
    if (!parentConfig.bedtimeEnabled()) {
        bedtimeOverride = BedtimeMode::Override::None;
        bedtimeOverrideUntilUtc = 0;
        Serial.printf("[Bedtime] Ignoring runtime %s; mode disabled in settings (%s)\n",
                      active ? "enable" : "disable", reason);
        pollBedtimeMode();
        return;
    }
    if (!bedtimeTimeKnown()) {
        bedtimeOverride = BedtimeMode::Override::None;
        bedtimeOverrideUntilUtc = 0;
        Serial.printf("[Bedtime] Ignoring runtime %s; local time unknown (%s)\n",
                      active ? "enable" : "disable", reason);
        pollBedtimeMode();
        return;
    }

    uint16_t targetMinute = active
        ? parentConfig.bedtimeEndMinutes()
        : parentConfig.bedtimeStartMinutes();
    uint32_t secondsUntilBoundary = BedtimeMode::secondsUntilNextMinuteOfDay(
        bedtimeLocalSecondOfDay(), targetMinute);
    bedtimeOverride = active ? BedtimeMode::Override::ForceOn
                             : BedtimeMode::Override::ForceOff;
    bedtimeOverrideUntilUtc = time(nullptr) + static_cast<time_t>(secondsUntilBoundary);

    Serial.printf("[Bedtime] Runtime override=%s until %s (%s)\n",
                  BedtimeMode::overrideName(bedtimeOverride),
                  bedtimeTimeString(targetMinute).c_str(),
                  reason);
    pollBedtimeMode();
}

// ---------------------------------------------------------------------------
// clearExpiredBedtimeOverride()
// ---------------------------------------------------------------------------
void clearExpiredBedtimeOverride() {
    if (bedtimeOverride == BedtimeMode::Override::None) {
        return;
    }
    if (!parentConfig.bedtimeEnabled() || !bedtimeTimeKnown() ||
        time(nullptr) >= bedtimeOverrideUntilUtc) {
        Serial.printf("[Bedtime] Clearing runtime override=%s\n",
                      BedtimeMode::overrideName(bedtimeOverride));
        bedtimeOverride = BedtimeMode::Override::None;
        bedtimeOverrideUntilUtc = 0;
    }
}

// ---------------------------------------------------------------------------
// pollBedtimeMode()
// ---------------------------------------------------------------------------
void pollBedtimeMode() {
    clearExpiredBedtimeOverride();

    bool active = bedtimeRuntimeActive();
    // Automatic mode and manual override can change without changing active.
    static bool lastAutomatic = false;
    static BedtimeMode::Override lastOverride = BedtimeMode::Override::None;
    const bool automatic = bedtimeAutomaticActive();
    const bool metadataChanged = automatic != lastAutomatic || bedtimeOverride != lastOverride;
    lastAutomatic = automatic;
    lastOverride = bedtimeOverride;
    if (active == lastBedtimeActive) {
        if (metadataChanged) publishBleValues();
        return;
    }

    lastBedtimeActive = active;
    if (!active && !bedtimeThemeOverride.isEmpty()) {
        Serial.printf("[Bedtime] Clearing theme override \"%s\"\n",
                      bedtimeThemeOverride.c_str());
        bedtimeThemeOverride = "";
    }
    Serial.printf("[Bedtime] Runtime %s (auto=%d override=%s timeKnown=%d)\n",
                  active ? "active" : "inactive",
                  bedtimeAutomaticActive() ? 1 : 0,
                  BedtimeMode::overrideName(bedtimeOverride),
                  bedtimeTimeKnown() ? 1 : 0);
    applyEffectiveVolume("bedtime state");

    // A runtime mode change takes effect immediately for mode reporting,
    // volume, and the theme selected for future songs. Keep the current WAV
    // untouched; a song-button press or the next fresh playback start applies
    // the newly effective theme.
    publishBleValues();
}

// ---------------------------------------------------------------------------
// bedtimeEffectiveSongTheme()
// ---------------------------------------------------------------------------
String bedtimeEffectiveSongTheme() {
    if (!bedtimeRuntimeActive()) {
        return activeTheme;
    }

    if (!bedtimeThemeOverride.isEmpty() && isKnownTheme(bedtimeThemeOverride)) {
        return bedtimeThemeOverride;
    }

    String theme = parentConfig.bedtimeTheme();
    theme.trim();
    if (!theme.isEmpty() && isKnownTheme(theme)) {
        lastInvalidBedtimeThemeLog = "";
        return theme;
    }

    if (lastInvalidBedtimeThemeLog != theme) {
        Serial.printf("[Bedtime] Theme \"%s\" is unavailable; using normal theme \"%s\" (volume cap still applies)\n",
                      theme.c_str(), activeTheme.c_str());
        lastInvalidBedtimeThemeLog = theme;
    }
    return activeTheme;
}

String bedtimeOverrideName() {
    return String(BedtimeMode::overrideName(bedtimeOverride));
}

String bedtimeTimeString(uint16_t minuteOfDay) {
    return ContentCatalog::formatTimeOfDay(minuteOfDay);
}

String bedtimeCurrentTimeString() {
    uint16_t minute = 0;
    if (!bedtimeLocalMinute(minute)) {
        return "";
    }
    return bedtimeTimeString(minute);
}

uint16_t parseBedtimeTimeString(const char* value, uint16_t fallback) {
    if (value == nullptr || value[0] == '\0') {
        return fallback;
    }
    int hour = -1;
    int minute = -1;
    char extra = '\0';
    int matched = sscanf(value, "%d:%d%c", &hour, &minute, &extra);
    if (matched < 2 || hour < 0 || hour > 23 || minute < 0 || minute > 59) {
        return fallback;
    }
    return static_cast<uint16_t>(hour * 60 + minute);
}

// ---------------------------------------------------------------------------
// currentSleepTimeoutMs()
// ---------------------------------------------------------------------------
uint32_t currentSleepTimeoutMs() {
    if (wokeFromVibration && !realActivitySeenSinceWake) {
        return parentConfig.sleepVibrationWakeIdleMs();
    }
    return parentConfig.sleepNormalIdleMs();
}

// ---------------------------------------------------------------------------
// readSleepSeconds()
// ---------------------------------------------------------------------------
uint32_t readSleepSeconds(JsonObjectConst sleep, const char* key, uint32_t fallbackMs) {
    long fallbackSeconds = static_cast<long>(fallbackMs / 1000UL);
    long seconds = sleep[key] | fallbackSeconds;
    if (seconds < 1) {
        return static_cast<uint32_t>(fallbackSeconds);
    }
    if (seconds > 24L * 60L * 60L) {
        seconds = 24L * 60L * 60L;
    }
    return static_cast<uint32_t>(seconds);
}

// ---------------------------------------------------------------------------
// bleIdleAllowsSleep()
// ---------------------------------------------------------------------------
bool bleIdleAllowsSleep() {
    if (!ENABLE_BLE_PARENT_SERVICE || !bleService.isConnected()) {
        return true;
    }
    return (millis() - lastBleActivityMs) >= parentConfig.sleepBleIdleMs();
}

// ---------------------------------------------------------------------------
// stateAllowsIdleSleep()
// ---------------------------------------------------------------------------
bool stateAllowsIdleSleep(State state) {
    if (state == State::IDLE) {
        return !btLinkConnected;
    }
    if (state == State::BT_STREAMING) {
        return btLinkConnected && !btAudioActive;
    }
    return false;
}

// ---------------------------------------------------------------------------
// canEnterIdleSleep()
// ---------------------------------------------------------------------------
bool canEnterIdleSleep() {
    if (!parentConfig.sleepEnabled()) {
        return false;
    }
    if (!stateAllowsIdleSleep(sm.currentState())) {
        return false;
    }
    if (!wavPlayer.isIdle()) {
        return false;
    }
    if (btReopenPending) {
        return false;
    }
    // With valid input power present, remain awake to supervise BQ25186
    // charging and avoid holding the NPN /CE driver on during deep sleep.
    if (HAS_BQ25186 && charger.inputPresent()) {
        return false;
    }
    return bleIdleAllowsSleep();
}

// ---------------------------------------------------------------------------
// pollIdleSleep()
// ---------------------------------------------------------------------------
void pollIdleSleep() {
    if (!canEnterIdleSleep()) {
        sleepEntryCheck.reset();
        return;
    }

    uint32_t timeoutMs = currentSleepTimeoutMs();
    // Also finish a check requested by the low-heap recovery path. Normal
    // activity cancels any pending check in markActivity().
    if (!sleepEntryCheck.active() && (millis() - lastActivityMs) < timeoutMs) {
        return;
    }

    enterIdleDeepSleep();
}

// ---------------------------------------------------------------------------
// preparePinsForPeripheralPowerOff()
// ---------------------------------------------------------------------------
void preparePinsForPeripheralPowerOff() {
    setAmpMuted(true);
    if (i2sOut.isActive()) {
        i2sOut.end();
    }
    SD.end();
    SPI.end();

    pinMode(HW_I2S_BCLK, INPUT);
    pinMode(HW_I2S_WS, INPUT);
    pinMode(HW_I2S_DOUT, INPUT);
    // Keep the hardware-specific MAX98357A shutdown level asserted.
    pinMode(PIN_SD_SCK, INPUT);
    pinMode(PIN_SD_MISO, INPUT);
    pinMode(PIN_SD_MOSI, INPUT);
    pinMode(PIN_SD_CS, INPUT);
}

// ---------------------------------------------------------------------------
// enterIdleDeepSleep()
// ---------------------------------------------------------------------------
void enterIdleDeepSleep() {
    // Sample before disabling charging/watchdogs or shutting down peripherals.
    // Return to loop() between samples so controls and charging stay serviced.
    const auto wakeCheck = sleepEntryCheck.update(
        millis(), digitalRead(PIN_VIB_WAKE) == HIGH);
    if (wakeCheck == SleepEntryCheck::Result::Sampling) {
        return;
    }
    if (wakeCheck != SleepEntryCheck::Result::Quiet) {
        // Use the full normal idle interval, even after a vibration-only wake.
        markActivity("vibration prevented sleep");
        Serial.println("[Sleep] Postponed: wake input was HIGH during the 500ms check");
        if (wakeCheck == SleepEntryCheck::Result::PossiblyDisconnected) {
            sendNotice("warn", "The movement sensor may be stuck or disconnected. "
                       "Sleep was postponed; battery life may be shorter.");
        }
        return;
    }

    if (HAS_BQ25186 && !charger.prepareForDeepSleep()) {
        if (!charger.healthy()) {
            statusLed.setSignal(StatusSignal::Error, true);
        }
        lastActivityMs = millis();
        Serial.println("[Sleep] Aborted: charger could not be prepared safely");
        return;
    }

    Serial.printf("[Sleep] Entering deep sleep after %lus idle (wake GPIO%d HIGH)\n",
                  static_cast<unsigned long>((millis() - lastActivityMs) / 1000UL),
                  PIN_VIB_WAKE);

    statusLed.prepareForPeripheralPowerOff();
    wavPlayer.stop();
    preparePinsForPeripheralPowerOff();
    holdPeripheralPowerOffForDeepSleep();
    statusLed.releaseAfterPeripheralPowerOff();

    rtc_gpio_deinit(static_cast<gpio_num_t>(PIN_VIB_WAKE));
    rtc_gpio_init(static_cast<gpio_num_t>(PIN_VIB_WAKE));
    rtc_gpio_set_direction(static_cast<gpio_num_t>(PIN_VIB_WAKE), RTC_GPIO_MODE_INPUT_ONLY);
    rtc_gpio_pullup_dis(static_cast<gpio_num_t>(PIN_VIB_WAKE));
    rtc_gpio_pulldown_dis(static_cast<gpio_num_t>(PIN_VIB_WAKE));
    esp_sleep_enable_ext0_wakeup(static_cast<gpio_num_t>(PIN_VIB_WAKE), 1);
    if (HAS_BQ25186) {
        // /PG is externally pulled HIGH without a valid input and is driven LOW
        // by the BQ25186 when USB/AUX power becomes valid.
        gpio_num_t pgPin = static_cast<gpio_num_t>(PIN_CHARGER_PG);
        rtc_gpio_deinit(pgPin);
        rtc_gpio_init(pgPin);
        rtc_gpio_set_direction(pgPin, RTC_GPIO_MODE_INPUT_ONLY);
        rtc_gpio_pullup_dis(pgPin);
        rtc_gpio_pulldown_dis(pgPin);
        esp_sleep_enable_ext1_wakeup(1ULL << PIN_CHARGER_PG,
                                     ESP_EXT1_WAKEUP_ALL_LOW);
    }

    // Movement after the check may wake us immediately; never wait here with
    // the peripherals off and the charger watchdog already disabled.
    Serial.flush();
    esp_deep_sleep_start();
}

// ---------------------------------------------------------------------------
// setupI2S()
// ---------------------------------------------------------------------------
void setupI2S() {
    resetI2SOutput("init");
    volumeOut.setOutput(static_cast<Print&>(i2sOut));
    volumeOut.begin(AudioInfo(SAMPLE_RATE, CHANNELS, BITS_PER_SAMPLE));
}

// ---------------------------------------------------------------------------
// printBluetoothAddress()
// ---------------------------------------------------------------------------
void printBluetoothAddress(const char* label) {
    const uint8_t* addr = esp_bt_dev_get_address();
    if (addr == nullptr) {
        Serial.printf("[BT] %s address unavailable\n", label);
        return;
    }

    Serial.printf("[BT] %s address: %02X:%02X:%02X:%02X:%02X:%02X\n",
                  label,
                  addr[0], addr[1], addr[2],
                  addr[3], addr[4], addr[5]);
}

// ---------------------------------------------------------------------------
// resetI2SOutput()
// ---------------------------------------------------------------------------
void resetI2SOutput(const char* owner) {
    if (i2sOut.isActive()) {
        i2sOut.end();
    }

    auto cfg = i2sOut.defaultConfig(TX_MODE);
    cfg.sample_rate     = SAMPLE_RATE;
    cfg.channels        = CHANNELS;
    cfg.bits_per_sample = BITS_PER_SAMPLE;
    cfg.i2s_format      = I2S_STD_FORMAT;
    cfg.pin_bck         = HW_I2S_BCLK;
    cfg.pin_ws          = HW_I2S_WS;
    cfg.pin_data        = HW_I2S_DOUT;
    cfg.buffer_count    = 12;
    cfg.buffer_size     = 512;
    i2sOut.begin(cfg);
    Serial.printf("[I2S] Reset for %s\n", owner);
}

// ---------------------------------------------------------------------------
// setupBT()
// ---------------------------------------------------------------------------
void setupBT(const String& deviceName) {
    auto* sink = new LowLatencyA2DPSinkQueued(i2sOut);
    sink->set_default_bt_mode(ENABLE_BLE_PARENT_SERVICE ? ESP_BT_MODE_BTDM
                                                        : ESP_BT_MODE_CLASSIC_BT);
    sink->set_i2s_ringbuffer_size(BT_A2DP_RINGBUFFER_BYTES);
    sink->set_i2s_ringbuffer_prefetch_percent(65);
    sink->set_i2s_write_size_upto(4096);
    sink->set_i2s_stack_size(BT_A2DP_I2S_TASK_STACK_BYTES);
    sink->set_on_connection_state_changed(btConnectionStateChanged);
    sink->set_on_audio_state_changed(btAudioStateChanged);
    sink->set_sample_rate_callback(btSampleRateChanged);
    sink->set_auto_reconnect(false, 0);
    sink->reserveAudioQueue();
    sink->start(deviceName.c_str());
    printBluetoothAddress("Classic BT");
    sink->set_auto_reconnect(false, 0);
    sink->reserveAudioTask();
    btSink = sink;
    Serial.printf("[BT] A2DP sink started as \"%s\"\n", deviceName.c_str());
}

// ---------------------------------------------------------------------------
// scheduleBluetoothReopen()
// ---------------------------------------------------------------------------
void scheduleBluetoothReopen(const char* reason) {
    if (btSink == nullptr) {
        return;
    }

    btSink->set_discoverability(ESP_BT_NON_DISCOVERABLE);
    btSink->set_connectable(false);
    btReopenPending = true;
    btReopenAtMs = millis() + BT_REOPEN_DELAY_MS;
    Serial.printf("[BT] Pausing new connections for %lu ms (%s, free=%u largest=%u)\n",
                  static_cast<unsigned long>(BT_REOPEN_DELAY_MS),
                  reason,
                  heap_caps_get_free_size(MALLOC_CAP_8BIT),
                  heap_caps_get_largest_free_block(MALLOC_CAP_8BIT));
}

// ---------------------------------------------------------------------------
// reopenBluetoothForPairing()
// ---------------------------------------------------------------------------
void reopenBluetoothForPairing(const char* reason) {
    if (btSink == nullptr) {
        return;
    }

    btSink->set_auto_reconnect(false, 0);
    btSink->clean_last_connection();
    btSink->set_discoverability(ESP_BT_GENERAL_DISCOVERABLE);
    btSink->set_connectable(true);
    Serial.printf("[BT] Open for new connections (%s, free=%u largest=%u)\n",
                  reason,
                  heap_caps_get_free_size(MALLOC_CAP_8BIT),
                  heap_caps_get_largest_free_block(MALLOC_CAP_8BIT));
}

// ---------------------------------------------------------------------------
// pollBluetoothReopen()
// ---------------------------------------------------------------------------
void pollBluetoothReopen() {
    if (!btReopenPending) {
        return;
    }
    if (sm.currentState() != State::IDLE) {
        btReopenPending = false;
        return;
    }
    if ((int32_t)(millis() - btReopenAtMs) < 0) {
        return;
    }

    btReopenPending = false;

    // After a BT session the Bluedroid A2DP stack leaks ~160 KB that is never
    // freed. If the remaining heap is below a safe floor, a future BLE notify
    // will malloc-fail inside Bluedroid and call abort().  Restart cleanly
    // instead of crashing with a garbage stack trace.
    uint32_t freeNow = ESP.getFreeHeap();
    const uint32_t SAFE_HEAP_FLOOR = 20000;
    if (freeNow < SAFE_HEAP_FLOOR) {
        if (rtcHeapRestartMagic != RTC_HEAP_RESTART_MAGIC) {
            rtcHeapRestartCount = 0;
            rtcHeapRestartMagic = RTC_HEAP_RESTART_MAGIC;
        }
        rtcHeapRestartCount++;
        Serial.printf("[BT] Heap critically low after BT session (free=%lu, restart %lu/%lu).\n",
                      static_cast<unsigned long>(freeNow),
                      static_cast<unsigned long>(rtcHeapRestartCount),
                      static_cast<unsigned long>(MAX_HEAP_RESTARTS));
        if (rtcHeapRestartCount >= MAX_HEAP_RESTARTS) {
            Serial.println("[BT] Repeated low-heap restarts; entering deep sleep to break loop.");
            rtcHeapRestartCount = 0;
            rtcHeapRestartMagic = 0;
            delay(200);
            enterIdleDeepSleep();
            return;
        }
        delay(200);
        esp_restart();
    }
    rtcHeapRestartCount = 0;
    rtcHeapRestartMagic = 0;
    reopenBluetoothForPairing("BT cooldown elapsed");
}

// ---------------------------------------------------------------------------
// processStateMachineTransitions()
// ---------------------------------------------------------------------------
bool processStateMachineTransitions() {
    bool changed = sm.process();
    State newState = sm.currentState();
    bool stateChanged = changed || newState != prevState;
    bool loopChanged = sm.loopMode() != prevLoopMode;
    if (stateChanged || loopChanged) {
        if (stateChanged) {
            handleStateEntry(prevState, newState);
        }
        prevState = newState;
        prevLoopMode = sm.loopMode();
        if (millis() - btConnectedAtMs >= BT_SETTLE_MS) {
            publishBleValues();
        } else {
            btSettleBlePublishPending = true;
        }
        if (loopChanged && ENABLE_BLE_PARENT_SERVICE) {
            String eventJson = "{\"type\":\"loop\",\"active\":";
            eventJson += sm.loopMode() ? "true" : "false";
            eventJson += "}";
            // Reuse the optional device-to-app event channel instead of
            // changing the GATT schema and triggering stale-cache failures.
            bleService.updateNotice(eventJson);
        }
        return true;
    }
    return false;
}

// ---------------------------------------------------------------------------
// handleBleControls()
// ---------------------------------------------------------------------------
bool handleBleControls() {
    if (!ENABLE_BLE_PARENT_SERVICE) {
        return false;
    }

    bool writeSeen = false;
    bool btMode = btLinkConnected || sm.currentState() == State::BT_STREAMING;

    uint8_t vol;
    if (bleService.pollVolumeChange(vol)) {
        writeSeen = true;
        if (btMode) {
            Serial.println("[BLE] Ignoring volume write during BT streaming");
        } else {
            sm.postStringEvent(Event::VOLUME_CHANGED, String(vol));
            applyVolume(vol);
        }
    }

    bool killOn;
    if (bleService.pollKillswitch(killOn)) {
        writeSeen = true;
        if (btMode) {
            Serial.println("[BLE] Ignoring killswitch write during BT streaming");
        } else {
            sm.postEvent(killOn ? Event::KILLSWITCH_ON : Event::KILLSWITCH_OFF);
        }
    }

    String newTheme;
    if (bleService.pollThemeChange(newTheme)) {
        writeSeen = true;
        newTheme.trim();
        if (btMode) {
            Serial.println("[BLE] Ignoring theme write during BT streaming");
        } else if (!isKnownTheme(newTheme)) {
            Serial.printf("[BLE] Ignoring unknown theme: %s\n", newTheme.c_str());
        } else {
            activeTheme = newTheme;
            if (bedtimeRuntimeActive()) {
                bedtimeThemeOverride = newTheme;
                lastInvalidBedtimeThemeLog = "";
                Serial.printf("[Bedtime] Theme override \"%s\" while bedtime remains active\n",
                              bedtimeThemeOverride.c_str());
            }
            sm.postStringEvent(Event::THEME_CHANGED, newTheme);
        }
    }

    uint8_t command;
    if (bleService.pollCommand(command)) {
        writeSeen = true;
        if (btMode || sm.currentState() == State::KILLSWITCH) {
            Serial.printf("[BLE] Ignoring command %u while controls are disabled\n", command);
        } else {
            handleBleCommand(command);
        }
    }

    if (writeSeen) {
        markBleActivity("BLE control write");
    }
    return writeSeen;
}

// ---------------------------------------------------------------------------
// handleBleConfigCommands()
// ---------------------------------------------------------------------------
void handleBleConfigCommands() {
    if (!ENABLE_BLE_PARENT_SERVICE) {
        return;
    }

    String commandJson;
    if (bleService.pollConfigCommand(commandJson)) {
        markBleActivity("BLE config command");
        handleBleConfigCommand(commandJson);
    }
}

// ---------------------------------------------------------------------------
// handleBleConfigCommand()
// ---------------------------------------------------------------------------
void handleBleConfigCommand(const String& commandJson) {
    JsonDocument doc;
    DeserializationError err = deserializeJson(doc, commandJson);
    uint32_t requestId = doc["id"] | 0;
    if (err) {
        bleService.updateConfigResponse(buildConfigErrorResponse(requestId, "Invalid config command JSON"));
        return;
    }

    const char* opValue = doc["op"] | "";
    String op = opValue;
    if (op == "scanThemes") {
        int cursor = doc["cursor"] | 0;
        bleService.updateConfigResponse(
            ContentCatalog::buildThemesPageJson(requestId, cursor, BLE_CONFIG_MAX_BYTES));
        return;
    }

    if (op == "scanSongs") {
        const char* theme = doc["theme"] | "";
        int cursor = doc["cursor"] | 0;
        if (theme == nullptr || theme[0] == '\0') {
            bleService.updateConfigResponse(buildConfigErrorResponse(requestId, "Missing theme id"));
            return;
        }
        bleService.updateConfigResponse(
            ContentCatalog::buildSongsPageJson(requestId, String(theme), cursor, BLE_CONFIG_MAX_BYTES));
        return;
    }

    if (op == "syncTime") {
        long epochValue = doc["epochSec"] | 0L;
        int tzOffsetValue = doc["tzOffsetMin"] | 0;
        if (epochValue < 946684800L ||
            tzOffsetValue < -14 * 60 || tzOffsetValue > 14 * 60) {
            bleService.updateConfigResponse(
                buildConfigErrorResponse(requestId, "Invalid time sync payload"));
            return;
        }
        syncBedtimeClock(static_cast<time_t>(epochValue),
                         static_cast<int16_t>(tzOffsetValue));
        publishBleValues();
        bleService.updateConfigResponse(buildConfigOkResponse(requestId, op));
        return;
    }

    if (op == "setBedtimeMode") {
        if (!doc["active"].is<bool>()) {
            bleService.updateConfigResponse(
                buildConfigErrorResponse(requestId, "Missing bedtime active flag"));
            return;
        }
        setBedtimeRuntimeActive(doc["active"].as<bool>(), "BLE runtime toggle");
        publishBleValues();
        bleService.updateConfigResponse(buildConfigOkResponse(requestId, op));
        return;
    }

    if (op == "setConfig") {
        if (!sdReady && (!doc["defaultVolumePct"].isNull() || !doc["defaultTheme"].isNull() ||
            !doc["sleep"].isNull() || !doc["bedtime"].isNull())) {
            bleService.updateConfigResponse(buildConfigErrorResponse(requestId, "SD card unavailable. Settings were not saved."));
            return;
        }
        const char* deviceNameValue = doc["deviceName"] | currentDeviceName.c_str();
        String nextName = deviceNameValue;
        nextName.trim();
        if (nextName.isEmpty()) nextName = DEFAULT_BT_NAME;
        if (nextName.length() > 32 || ContentCatalog::jsonEscape(nextName).length() > 64) {
            bleService.updateConfigResponse(buildConfigErrorResponse(requestId, "Device name is too long (32 UTF-8 bytes maximum)."));
            return;
        }

        uint8_t nextVolume = static_cast<uint8_t>(doc["defaultVolumePct"] | parentConfig.defaultVolumePct());
        if (nextVolume > 100) nextVolume = 100;

        String currentDefaultTheme = parentConfig.defaultTheme();
        const char* defaultThemeValue = doc["defaultTheme"] | currentDefaultTheme.c_str();
        String nextDefaultTheme = defaultThemeValue;
        nextDefaultTheme.trim();
        if (nextDefaultTheme.isEmpty()) nextDefaultTheme = DEFAULT_THEME;

        bool nextSleepEnabled = parentConfig.sleepEnabled();
        uint32_t nextSleepNormalIdleSec = parentConfig.sleepNormalIdleMs() / 1000UL;
        uint32_t nextSleepVibrationWakeIdleSec = parentConfig.sleepVibrationWakeIdleMs() / 1000UL;
        uint32_t nextSleepBleIdleSec = parentConfig.sleepBleIdleMs() / 1000UL;
        if (doc["sleep"].is<JsonObject>()) {
            JsonObject sleep = doc["sleep"].as<JsonObject>();
            nextSleepEnabled = sleep["enabled"] | nextSleepEnabled;
            nextSleepNormalIdleSec = readSleepSeconds(
                sleep, "normalIdleSec", parentConfig.sleepNormalIdleMs());
            nextSleepVibrationWakeIdleSec = readSleepSeconds(
                sleep, "vibrationWakeIdleSec", parentConfig.sleepVibrationWakeIdleMs());
            nextSleepBleIdleSec = readSleepSeconds(
                sleep, "bleIdleSec", parentConfig.sleepBleIdleMs());
        }

        bool nextBedtimeEnabled = parentConfig.bedtimeEnabled();
        uint16_t nextBedtimeStartMinutes = parentConfig.bedtimeStartMinutes();
        uint16_t nextBedtimeEndMinutes = parentConfig.bedtimeEndMinutes();
        String nextBedtimeTheme = parentConfig.bedtimeTheme();
        uint8_t nextBedtimeVolumeCapPct = parentConfig.bedtimeVolumeCapPct();
        if (doc["bedtime"].is<JsonObject>()) {
            JsonObject bedtime = doc["bedtime"].as<JsonObject>();
            nextBedtimeEnabled = bedtime["enabled"] | nextBedtimeEnabled;
            nextBedtimeStartMinutes = parseBedtimeTimeString(
                bedtime["startTime"] | "",
                nextBedtimeStartMinutes);
            nextBedtimeEndMinutes = parseBedtimeTimeString(
                bedtime["endTime"] | "",
                nextBedtimeEndMinutes);
            const char* themeValue = bedtime["theme"] | nextBedtimeTheme.c_str();
            nextBedtimeTheme = themeValue;
            nextBedtimeTheme.trim();
            if (nextBedtimeTheme.isEmpty()) {
                nextBedtimeTheme = DEFAULT_BEDTIME_THEME;
            }
            int cap = bedtime["volumeCapPct"] | nextBedtimeVolumeCapPct;
            if (cap < 0) cap = 0;
            if (cap > 100) cap = 100;
            nextBedtimeVolumeCapPct = static_cast<uint8_t>(cap);
        }

        // Only schedule changes invalidate a manual Daytime/Bedtime choice.
        // A cap or theme edit must not silently switch the current mode.
        bool bedtimeScheduleChanged = nextBedtimeEnabled != parentConfig.bedtimeEnabled() ||
            nextBedtimeStartMinutes != parentConfig.bedtimeStartMinutes() ||
            nextBedtimeEndMinutes != parentConfig.bedtimeEndMinutes();
        bool bedtimeThemeChanged = nextBedtimeTheme != parentConfig.bedtimeTheme();

        if (!ContentCatalog::validThemeId(nextDefaultTheme) ||
            !ContentCatalog::validThemeId(nextBedtimeTheme)) {
            bleService.updateConfigResponse(buildConfigErrorResponse(requestId, "Theme id is too long."));
            return;
        }
        if (sdReady) {
            if (!ContentCatalog::updateSdConfig(
                    nextVolume, nextDefaultTheme, nextSleepEnabled,
                    nextSleepNormalIdleSec, nextSleepVibrationWakeIdleSec,
                    nextSleepBleIdleSec,
                    nextBedtimeEnabled, nextBedtimeStartMinutes,
                    nextBedtimeEndMinutes, nextBedtimeTheme,
                    nextBedtimeVolumeCapPct)) {
                bleService.updateConfigResponse(buildConfigErrorResponse(requestId, "SD write failed"));
                return;
            }
            if (!parentConfig.load()) {
                statusLed.setSignal(StatusSignal::Error, true);
                publishConfigAttributes();
                bleService.updateConfigResponse(buildConfigErrorResponse(requestId, "Could not reload saved settings."));
                return;
            }
            refreshThemeList();
            // Startup defaults are applied by setup(), including after deep
            // sleep. Keep the current session's volume and theme on saves.
            applyActiveThemeFallback();
            lastInvalidBedtimeThemeLog = "";
            if (bedtimeThemeChanged) {
                bedtimeThemeOverride = "";
            }
            if (bedtimeScheduleChanged) {
                bedtimeOverride = BedtimeMode::Override::None;
                bedtimeOverrideUntilUtc = 0;
            }
        }
        pollBedtimeMode();
        // A changed cap takes effect even if Bedtime remains active, without
        // replacing the parent's requested volume with the startup default.
        applyEffectiveVolume("settings update");
        nvs.setBtName(nextName);
        currentDeviceName = nextName;
        applyDeviceName(nextName);
        publishBleValues();
        bleService.updateConfigResponse(buildConfigOkResponse(requestId, op));
        return;
    }

    if (op == "setTheme") {
        const char* themeValue = doc["theme"] | "";
        if (themeValue == nullptr || themeValue[0] == '\0') {
            bleService.updateConfigResponse(buildConfigErrorResponse(requestId, "Missing theme id"));
            return;
        }
        String theme = themeValue;
        bool sdOk = true;
        if (doc["enabled"].is<bool>()) {
            if (!ContentCatalog::setThemeDisabled(theme, !doc["enabled"].as<bool>())) sdOk = false;
        }
        if (doc["shuffle"].is<bool>()) {
            if (!ContentCatalog::setThemeShuffle(theme, doc["shuffle"].as<bool>())) sdOk = false;
        }
        if (!sdOk) {
            bleService.updateConfigResponse(buildConfigErrorResponse(requestId, "SD write failed"));
            return;
        }
        if (!parentConfig.load()) {
            statusLed.setSignal(StatusSignal::Error, true);
            publishConfigAttributes();
            bleService.updateConfigResponse(buildConfigErrorResponse(requestId, "Could not reload saved settings."));
            return;
        }
        refreshThemeList();
        applyActiveThemeFallback();
        lastInvalidBedtimeThemeLog = "";
        if (sm.currentState() == State::PLAYING_SONG &&
            theme == currentPlaybackTheme) {
            // Apply shuffle/availability changes to the next-track rotation
            // without interrupting the file that is already playing.
            wavPlayer.refreshSongList(currentPlaybackTheme);
        }
        publishBleValues();
        bleService.updateConfigResponse(buildConfigOkResponse(requestId, op));
        return;
    }

    if (op == "setSong") {
        const char* themeValue = doc["theme"] | "";
        const char* fileValue = doc["file"] | "";
        if (themeValue == nullptr || themeValue[0] == '\0' ||
            fileValue == nullptr || fileValue[0] == '\0' ||
            !doc["enabled"].is<bool>()) {
            bleService.updateConfigResponse(buildConfigErrorResponse(requestId, "Missing song update fields"));
            return;
        }
        if (!ContentCatalog::setSongDisabled(String(themeValue), String(fileValue), !doc["enabled"].as<bool>())) {
            bleService.updateConfigResponse(buildConfigErrorResponse(requestId, "SD write failed"));
            return;
        }
        refreshThemeList();
        applyActiveThemeFallback();
        lastInvalidBedtimeThemeLog = "";
        if (sm.currentState() == State::PLAYING_SONG) {
            if (String(themeValue) == currentPlaybackTheme) {
                // A song was toggled in the theme that's playing: rebuild the
                // live rotation so the change takes effect on the next track.
                wavPlayer.refreshSongList(currentPlaybackTheme);
            }
        }
        publishBleValues();
        bleService.updateConfigResponse(buildConfigOkResponse(requestId, op));
        return;
    }

    bleService.updateConfigResponse(buildConfigErrorResponse(requestId, "Unknown config command"));
}

// ---------------------------------------------------------------------------
// handleBleCommand()
// ---------------------------------------------------------------------------
void handleBleCommand(uint8_t command) {
    State state = sm.currentState();
    switch (command) {
        case 1:  // Song button
            if (state == State::PLAYING_SONG) {
                playNextSong();
                publishBleValues();
            } else {
                sm.postEvent(Event::BUTTON1_PRESS);
            }
            break;

        case 2:  // Animal button
            if (state == State::PLAYING_ANIMAL) {
                playNextAnimal();
                publishBleValues();
            } else {
                sm.postEvent(Event::BUTTON2_PRESS);
            }
            break;

        case 3:  // Both buttons / stop
            sm.postEvent(Event::BOTH_BUTTONS_PRESS);
            break;

        case 4:  // Enable continuous song loop
            sm.postEvent(Event::LOOP_ON);
            // Apply before end-of-file handling later in this loop iteration,
            // so a toggle at the track boundary cannot miss the boundary.
            processStateMachineTransitions();
            break;

        case 5:  // Disable continuous song loop
            sm.postEvent(Event::LOOP_OFF);
            processStateMachineTransitions();
            break;

        default:
            Serial.printf("[BLE] Ignoring unknown command: %u\n", command);
            break;
    }
}

// ---------------------------------------------------------------------------
// publishBleValues()
// ---------------------------------------------------------------------------
void publishBleValues() {
    if (!ENABLE_BLE_PARENT_SERVICE) {
        return;
    }

    State state = sm.currentState();
    bleService.updateVolume(currentVolumePct);
    bleService.updateKillswitch(state == State::KILLSWITCH);
    bleService.updateTheme(activeTheme);
    bleService.updateStatus(bleStatusForState(state));
    bleService.updateBatteryState(batteryMonitor.encodedState());
    publishConfigAttributes();
    lastBleStatusPublishMs = millis();
}

// ---------------------------------------------------------------------------
// sendNotice() — push a user-facing notice to the app over BLE. The device
// owns the wording and severity; the app just displays it.
//   severity: "error" (persistent until dismissed) or "warn" (auto-dismiss)
// ---------------------------------------------------------------------------
void sendNotice(const String& severity, const String& message) {
    Serial.printf("[Notice] %s: %s\n", severity.c_str(), message.c_str());
    if (severity == "error") {
        statusLed.setSignal(StatusSignal::Error, true);
    }
    if (!ENABLE_BLE_PARENT_SERVICE) {
        return;
    }
    JsonDocument doc;
    doc["severity"] = severity;
    doc["message"] = message;
    String json;
    serializeJson(doc, json);
    bleService.updateNotice(json);
}

// ---------------------------------------------------------------------------
// notifyPlaybackFailure() — called when a play attempt produced no audio.
//   - No SD card               -> persistent error.
//   - SD present but no playable songs/animals (folder empty, or every file
//     was filtered out as invalid/unsupported) -> transient warning.
// Malformed individual files are already filtered at scan time and surfaced in
// the settings song list, so there is no per-file runtime notice.
// ---------------------------------------------------------------------------
void notifyPlaybackFailure(bool animal) {
    // sdReady is only the boot-time mount result; re-probe so a card pulled at
    // runtime is reported as the persistent error rather than an empty-folder
    // warning.
    if (sdReady && !wavPlayer.sdAvailable()) {
        sdReady = false;
        Serial.println("[WARN] SD card no longer readable at play time");
    }
    if (!sdReady) {
        sendNotice("error", "SD card not found. Insert the card and restart the toy.");
    } else if (animal) {
        sendNotice("warn", "No animal sounds on the card.");
    } else {
        sendNotice("warn", "No songs in this theme.");
    }
}

// ---------------------------------------------------------------------------
// Play helpers — every way to start/advance playback funnels through these so
// a failed attempt surfaces a notice no matter which path triggered it (fresh
// start, "next", or theme switch). A successful start leaves the player active
// (isIdle()==false), so no notice fires.
// ---------------------------------------------------------------------------
void playSong() {
    wavPlayer.startSong(currentPlaybackTheme);
    if (wavPlayer.isIdle()) notifyPlaybackFailure(false);
}

void playNextSong() {
    String selectedTheme = bedtimeEffectiveSongTheme();
    if (selectedTheme != currentPlaybackTheme) {
        // Mode/theme changes are intentionally deferred while a song plays.
        // A deliberate song-button press is the point where the new selection
        // replaces the current audio.
        currentPlaybackTheme = selectedTheme;
        wavPlayer.startSong(currentPlaybackTheme);
    } else {
        wavPlayer.nextSong();
    }
    if (wavPlayer.isIdle()) notifyPlaybackFailure(false);
}

void playAnimal() {
    wavPlayer.startRandomAnimal();
    if (wavPlayer.isIdle()) notifyPlaybackFailure(true);
}

void playNextAnimal() {
    wavPlayer.nextAnimal();
    if (wavPlayer.isIdle()) notifyPlaybackFailure(true);
}

// ---------------------------------------------------------------------------
// bleStatusForState()
// ---------------------------------------------------------------------------
String bleStatusForState(State state) {
    switch (state) {
        case State::IDLE:
            return "Idle";

        case State::PLAYING_SONG: {
            String status = "Playing song - ";
            status += themeDisplayName(currentPlaybackTheme);
            String file = fileNameOf(wavPlayer.currentPath());
            if (file.length() > 0) {
                status += " / ";
                status += file;
            }
            return status;
        }

        case State::PLAYING_ANIMAL: {
            String status = "Playing animal";
            String file = fileNameOf(wavPlayer.currentPath());
            if (file.length() > 0) {
                status += " - ";
                status += file;
            }
            return status;
        }

        case State::BT_STREAMING:
            return "BT connected";

        case State::KILLSWITCH:
            return String("Killswitch active (") +
                   formatRemaining(sm.killswitchRemainingMs()) + " left)";

        default:
            return "Idle";
    }
}

// ---------------------------------------------------------------------------
// refreshThemeList()
// ---------------------------------------------------------------------------
void refreshThemeList() {
    themeCount = WavPlayer::listThemes(themeIds, themeNames, BLE_MAX_THEMES);
    bleThemesJson = WavPlayer::buildThemesJson(
        themeIds, themeNames, themeCount, BLE_THEMES_MAX_BYTES);
    Serial.printf("[Theme] %d playable theme(s), BLE payload=%u bytes\n",
                  themeCount, static_cast<unsigned>(bleThemesJson.length()));
    if (ENABLE_BLE_PARENT_SERVICE) {
        bleService.updateThemes(bleThemesJson);
    }
}

// ---------------------------------------------------------------------------
// applyActiveThemeFallback()
// ---------------------------------------------------------------------------
void applyActiveThemeFallback() {
    if (themeCount > 0 && !isKnownTheme(activeTheme)) {
        Serial.printf("[Theme] Theme \"%s\" is unavailable; using \"%s\"\n",
                      activeTheme.c_str(), themeIds[0].c_str());
        activeTheme = themeIds[0];
    }
}

// ---------------------------------------------------------------------------
// applyDeviceName()
// ---------------------------------------------------------------------------
void applyDeviceName(const String& deviceName) {
    bleService.updateDeviceName(deviceName);
    if (btSink != nullptr && !btLinkConnected && sm.currentState() != State::BT_STREAMING) {
        esp_err_t err = esp_bt_gap_set_device_name(deviceName.c_str());
        if (err == ESP_OK) {
            btNameApplyPending = false;
            Serial.printf("[BT] Classic BT name set to \"%s\"\n", deviceName.c_str());
        } else {
            btNameApplyPending = true;
            Serial.printf("[BT] Classic BT name update deferred: %d\n", err);
        }
    } else {
        btNameApplyPending = true;
        Serial.println("[BT] Classic BT name update deferred until audio disconnects");
    }
}

// ---------------------------------------------------------------------------
// applyPendingBtNameIfPossible()
// ---------------------------------------------------------------------------
void applyPendingBtNameIfPossible() {
    if (!btNameApplyPending || btSink == nullptr || btLinkConnected ||
        sm.currentState() == State::BT_STREAMING) {
        return;
    }
    esp_err_t err = esp_bt_gap_set_device_name(currentDeviceName.c_str());
    if (err == ESP_OK) {
        btNameApplyPending = false;
        Serial.printf("[BT] Classic BT name set to \"%s\"\n", currentDeviceName.c_str());
    }
}

// ---------------------------------------------------------------------------
// Readable config groups (published separately from command acknowledgments)
// ---------------------------------------------------------------------------
String buildConfigAttribute(size_t index) {
    JsonDocument doc;
    if (index == 0) {
        doc["deviceName"] = currentDeviceName;
        doc["defaultVolumePct"] = parentConfig.defaultVolumePct();
        doc["defaultTheme"] = parentConfig.defaultTheme();
        doc["sdReady"] = sdReady;
        if (sdReady && !parentConfig.loaded()) {
            doc["error"] = "Settings file is missing or invalid. Restore config.json on the SD card and restart the toy.";
        }
    } else if (index == 1) {
        doc["enabled"] = parentConfig.sleepEnabled();
        doc["normalIdleSec"] = parentConfig.sleepNormalIdleMs() / 1000UL;
        doc["vibrationWakeIdleSec"] = parentConfig.sleepVibrationWakeIdleMs() / 1000UL;
        doc["bleIdleSec"] = parentConfig.sleepBleIdleMs() / 1000UL;
    } else if (index == 2) {
        doc["enabled"] = parentConfig.bedtimeEnabled();
        doc["startTime"] = bedtimeTimeString(parentConfig.bedtimeStartMinutes());
        doc["endTime"] = bedtimeTimeString(parentConfig.bedtimeEndMinutes());
        doc["theme"] = parentConfig.bedtimeTheme();
        doc["volumeCapPct"] = parentConfig.bedtimeVolumeCapPct();
    } else if (index == 3) {
        doc["loop"] = sm.loopMode();
        doc["activeTheme"] = activeTheme;
        doc["timeKnown"] = bedtimeTimeKnown();
        doc["currentTime"] = bedtimeCurrentTimeString();
        doc["currentSecondOfDay"] = bedtimeTimeKnown()
            ? static_cast<int32_t>(bedtimeLocalSecondOfDay()) : -1;
        doc["active"] = bedtimeRuntimeActive();
        doc["autoActive"] = bedtimeAutomaticActive();
        doc["override"] = bedtimeOverrideName();
        doc["effectiveVolumePct"] = effectiveVolumePct();
        doc["effectiveTheme"] = bedtimeEffectiveSongTheme();
    } else {
        doc["message"] = ContentCatalog::catalogWarning();
    }
    String output;
    serializeJson(doc, output);
    return output;
}

void publishConfigAttributes() {
    if (!ENABLE_BLE_PARENT_SERVICE) return;
    for (size_t i = 0; i < BLE_CONFIG_ATTRIBUTE_COUNT; ++i) {
        bleService.updateConfigAttribute(i, buildConfigAttribute(i));
    }
}

String buildConfigOkResponse(uint32_t requestId, const String& op) {
    JsonDocument doc;
    doc["id"] = requestId;
    doc["ok"] = true;
    doc["op"] = op;
    String output;
    serializeJson(doc, output);
    return output;
}

String buildConfigErrorResponse(uint32_t requestId, const String& message) {
    JsonDocument doc;
    doc["id"] = requestId;
    doc["ok"] = false;
    doc["error"] = message;
    String output;
    serializeJson(doc, output);
    return output;
}

// ---------------------------------------------------------------------------
// isKnownTheme()
// ---------------------------------------------------------------------------
bool isKnownTheme(const String& theme) {
    for (int i = 0; i < themeCount; i++) {
        if (themeIds[i] == theme) {
            return true;
        }
    }
    return false;
}

// ---------------------------------------------------------------------------
// themeDisplayName()
// ---------------------------------------------------------------------------
String themeDisplayName(const String& theme) {
    for (int i = 0; i < themeCount; i++) {
        if (themeIds[i] == theme) {
            return themeNames[i];
        }
    }
    return theme;
}

// ---------------------------------------------------------------------------
// fileNameOf()
// ---------------------------------------------------------------------------
String fileNameOf(const String& path) {
    int slash = path.lastIndexOf('/');
    if (slash < 0) return path;
    return path.substring(slash + 1);
}

// ---------------------------------------------------------------------------
// formatRemaining()
// ---------------------------------------------------------------------------
String formatRemaining(uint32_t remainingMs) {
    uint32_t totalSeconds = (remainingMs + 999) / 1000;
    uint32_t minutes = totalSeconds / 60;
    uint32_t seconds = totalSeconds % 60;
    char buf[12];
    snprintf(buf, sizeof(buf), "%02lu:%02lu",
             static_cast<unsigned long>(minutes),
             static_cast<unsigned long>(seconds));
    return String(buf);
}

// ---------------------------------------------------------------------------
// applyVolume() — maps 0–100 to 0.0–1.0 on the VolumeStream
// ---------------------------------------------------------------------------
void applyVolume(uint8_t pct) {
    if (pct > 100) pct = 100;
    currentVolumePct = pct;
    applyEffectiveVolume("volume request");
}

uint8_t effectiveVolumePct() {
    if (btLinkConnected || sm.currentState() == State::BT_STREAMING) {
        return currentVolumePct;
    }
    if (bedtimeRuntimeActive()) {
        uint8_t cap = parentConfig.bedtimeVolumeCapPct();
        return currentVolumePct < cap ? currentVolumePct : cap;
    }
    return currentVolumePct;
}

void applyEffectiveVolume(const char* reason) {
    uint8_t pct = effectiveVolumePct();
    currentEffectiveVolumePct = pct;
    float v = pct / 100.0f;
    volumeOut.setVolume(v);
    if (pct == currentVolumePct) {
        Serial.printf("[Vol] %u%% (%.2f, %s)\n", pct, v, reason);
    } else {
        Serial.printf("[Vol] requested=%u%% effective=%u%% bedtimeCap=%u%% (%.2f, %s)\n",
                      currentVolumePct, pct, parentConfig.bedtimeVolumeCapPct(), v, reason);
    }
}

// ---------------------------------------------------------------------------
// handleStateEntry() — called once when the state machine transitions
// ---------------------------------------------------------------------------
void handleStateEntry(State prev, State next) {
    markActivity("state change");
    updateStatusSignalsForState(next);

    // Stop WAV on any exit from PLAYING states
    bool exitedWav = (prev == State::PLAYING_SONG || prev == State::PLAYING_ANIMAL) &&
                     (next != State::PLAYING_SONG && next != State::PLAYING_ANIMAL);
    if (exitedWav) {
        wavPlayer.stop();
    }

    switch (next) {

        case State::IDLE:
            if (prev == State::BT_STREAMING) {
                scheduleBluetoothReopen("BT disconnected");
            }
            setAmpMuted(true);
            break;

        case State::PLAYING_SONG: {
            // Fresh song start (prev != PLAYING_SONG); "next song" is handled
            // directly in loop() via wavPlayer.nextSong() when btn1 is pressed.
            currentPlaybackTheme = bedtimeEffectiveSongTheme();
            applyEffectiveVolume("song start");
            setAmpMuted(false);
            playSong();
            break;
        }

        case State::PLAYING_ANIMAL:
            applyEffectiveVolume("animal start");
            setAmpMuted(false);
            playAnimal();
            break;

        case State::BT_STREAMING:
            // WAV already stopped above; release mute so A2DP audio flows through
            wavPlayer.stop();  // ensure WAV is stopped
            setAmpMuted(false);
            break;

        case State::KILLSWITCH:
            wavPlayer.stop();
            setAmpMuted(true);
            Serial.printf("[SM] Killswitch active for %lu ms\n", KILLSWITCH_MS);
            break;
    }
}

// ---------------------------------------------------------------------------
// updateStatusSignalsForState() — translates the central operational state to
// semantic LED inputs. The StatusLed controller owns priority, color, cadence,
// and all addressable-LED writes.
// ---------------------------------------------------------------------------
void updateStatusSignalsForState(State state) {
    statusLed.setSignal(StatusSignal::Ready, state == State::IDLE);
    statusLed.setSignal(
        StatusSignal::LocalPlayback,
        state == State::PLAYING_SONG || state == State::PLAYING_ANIMAL);
    statusLed.setSignal(StatusSignal::Killswitch, state == State::KILLSWITCH);
}

// ---------------------------------------------------------------------------
// printStatusLedModeLegend() — print the canonical controller definitions so
// a bench log identifies every color and cadence in the running firmware.
// ---------------------------------------------------------------------------
void printStatusLedModeLegend() {
    static constexpr StatusLedMode MODES[] = {
        StatusLedMode::Initializing,
        StatusLedMode::Ready,
        StatusLedMode::LocalPlayback,
        StatusLedMode::BluetoothConnected,
        StatusLedMode::BluetoothPlaying,
        StatusLedMode::Killswitch,
        StatusLedMode::Error,
        StatusLedMode::Off,
    };

    Serial.println("[LED] Mode legend:");
    for (StatusLedMode mode : MODES) {
        const StatusLedModeDefinition definition = statusLedModeDefinition(mode);
        const StatusLedPattern& pattern = definition.pattern;
        if (mode == StatusLedMode::Off) {
            Serial.printf("[LED]   %s: %s\n",
                          definition.condition, definition.colorName);
        } else if (pattern.onMs == 0 || pattern.offMs == 0) {
            Serial.printf("[LED]   %s: %s solid\n",
                          definition.condition, definition.colorName);
        } else {
            Serial.printf("[LED]   %s: %s %ums on / %ums off\n",
                          definition.condition,
                          definition.colorName,
                          static_cast<unsigned>(pattern.onMs),
                          static_cast<unsigned>(pattern.offMs));
        }
    }
}

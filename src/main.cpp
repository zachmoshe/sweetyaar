#include <Arduino.h>
#include <SPI.h>
#include <esp_heap_caps.h>
#include <esp_log.h>
#include <esp_bt_device.h>

// --- Audio tools ---
#include "AudioTools.h"
#include "BluetoothA2DPSink.h"

// --- Project modules ---
#include "Config.h"
#include "LowLatencyA2DPSinkQueued.h"
#include "DebugA2DPSinkQueued.h"
#include "NVSConfig.h"
#include "ParentConfig.h"
#include "ButtonHandler.h"
#include "WavPlayer.h"
#include "BLEParentService.h"
#include "StateMachine.h"

// ---------------------------------------------------------------------------
// Global objects
// ---------------------------------------------------------------------------
NVSConfig       nvs;
ParentConfig    parentConfig;
ButtonHandler   buttons;
BLEParentService bleService;
StateMachine    sm;

// Audio pipeline:
//   BT A2DP: A2DP sink -> I2SStream -> MAX98357A
//   WAV/SD:  WAV decoder -> VolumeStream -> I2SStream -> MAX98357A
I2SStream       i2sOut;
VolumeStream    volumeOut;
WavPlayer       wavPlayer(volumeOut);
BluetoothA2DPSink* btSink = nullptr;

// Track previous state to detect transitions in the main loop
State prevState = State::IDLE;
bool configMode = false;
String activeTheme = DEFAULT_THEME;
String themeIds[BLE_MAX_THEMES];
String themeNames[BLE_MAX_THEMES];
String bleThemesJson = "[]";
int themeCount = 0;
uint8_t currentVolumePct = DEFAULT_VOLUME_PCT;
bool btReopenPending = false;
uint32_t btReopenAtMs = 0;
const uint32_t BT_REOPEN_DELAY_MS = 1500;
volatile bool btLinkConnected = false;
uint32_t lastBleStatusPublishMs = 0;

// ---------------------------------------------------------------------------
// Forward declarations
// ---------------------------------------------------------------------------
bool shouldEnterConfigMode();
void enterConfigMode();
void loopConfigMode();
void setupI2S();
void resetI2SOutput(const char* owner);
void setupBT(const String& deviceName);
void setupBtDebugLogging();
void printBluetoothAddress(const char* label);
void scheduleBluetoothReopen(const char* reason);
void reopenBluetoothForPairing(const char* reason);
void pollBluetoothReopen();
void pollBtDebug();
void applyVolume(uint8_t pct);
void handleStateEntry(State prev, State next);
bool processStateMachineTransitions();
bool handleBleControls();
void handleBleCommand(uint8_t command);
void publishBleValues();
String bleStatusForState(State state);
void refreshThemeList();
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
        Serial.println("[BT] Connected");
        sm.postEvent(Event::BT_CONNECTED);
    } else if (state == ESP_A2D_CONNECTION_STATE_DISCONNECTED) {
        btLinkConnected = false;
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
}

static void btSampleRateChanged(uint16_t rate) {
    Serial.printf("[BT] A2DP sample rate: %u Hz\n", rate);
}

// ---------------------------------------------------------------------------
// setup()
// ---------------------------------------------------------------------------
void setup() {
    Serial.begin(115200);
    delay(500);
    Serial.println("\n=== SweetYaar Boot ===");
    setupBtDebugLogging();

    // Status LED
    pinMode(PIN_LED, OUTPUT);
    digitalWrite(PIN_LED, HIGH);  // solid on during init

    // Amplifier mute (active HIGH to unmute; start muted)
    pinMode(PIN_AMP_MUTE, OUTPUT);
    digitalWrite(PIN_AMP_MUTE, LOW);

    // Device-local NVS config
    nvs.begin();
    String btName = nvs.getBtName();
    Serial.printf("[Device] btName=%s\n", btName.c_str());

    // Buttons
    buttons.begin();
    sm.begin();

    if (shouldEnterConfigMode()) {
        enterConfigMode();
        return;
    }

    // I2S (must be set up before BT sink and WAV player)
    setupI2S();

    // Bluetooth A2DP sink. Reserve its audio queue before SD/WAV playback has
    // a chance to fragment heap; otherwise connection-time allocation can fail.
    setupBT(btName);

    // SD card + WAV player
    bool sdReady = wavPlayer.begin();
    if (!sdReady) {
        Serial.println("[WARN] SD init failed; WAV playback unavailable");
    } else {
        parentConfig.load();
        refreshThemeList();
    }
    activeTheme = parentConfig.defaultTheme();
    if (themeCount > 0 && !isKnownTheme(activeTheme)) {
        Serial.printf("[Theme] Default theme \"%s\" is unavailable; using \"%s\"\n",
                      activeTheme.c_str(), themeIds[0].c_str());
        activeTheme = themeIds[0];
    }

    // Apply SD-configured volume, or the static firmware default.
    applyVolume(parentConfig.defaultVolumePct());

    // BLE parent service — shares the controller already started by A2DP.
    if (ENABLE_BLE_PARENT_SERVICE) {
        bleService.begin(btName);
        bleService.updateThemes(bleThemesJson);
        publishBleValues();
    } else {
        Serial.println("[BLE] Parent service disabled for A2DP audio test");
    }

    digitalWrite(PIN_LED, LOW);  // init done

    Serial.println("[Boot] Ready.");
}

// ---------------------------------------------------------------------------
// loop()
// ---------------------------------------------------------------------------
void loop() {
    if (configMode) {
        loopConfigMode();
        return;
    }

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
            sm.postEvent(Event::BOTH_BUTTONS_PRESS);
        } else if (buttons.wasBtn1Pressed()) {
            if (cur == State::PLAYING_SONG) {
                wavPlayer.nextSong();  // advance track; stay in PLAYING_SONG
                publishBleValues();
            } else {
                sm.postEvent(Event::BUTTON1_PRESS);
            }
        } else if (buttons.wasBtn2Pressed()) {
            if (cur == State::PLAYING_ANIMAL) {
                wavPlayer.nextAnimal();  // advance animal; stay in PLAYING_ANIMAL
                publishBleValues();
            } else {
                sm.postEvent(Event::BUTTON2_PRESS);
            }
        }
    }

    // 3. Poll BLE characteristics. Writes are only local-toy controls;
    //    during BT streaming they are ignored and current values are restored.
    bool bleWriteSeen = handleBleControls();

    // 4. WAV player: signal SM when track ends
    if (cur == State::PLAYING_SONG || cur == State::PLAYING_ANIMAL) {
        if (wavPlayer.isIdle()) {
            sm.postEvent(Event::WAV_FINISHED);
        }
    }

    // 5. Process state machine
    bool changed = processStateMachineTransitions();
    if (bleWriteSeen && !changed) {
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
    pollBtDebug();

    delay(wavPlayer.isIdle() ? 5 : 1);  // keep WAV streaming fed while still yielding
}

// ---------------------------------------------------------------------------
// shouldEnterConfigMode()
// ---------------------------------------------------------------------------
bool shouldEnterConfigMode() {
    Serial.println("Hold both buttons for 3s during boot to enter config mode...");
    if (digitalRead(PIN_BTN1) != LOW || digitalRead(PIN_BTN2) != LOW) {
        return false;
    }

    uint32_t holdStart = millis();
    while ((digitalRead(PIN_BTN1) == LOW) && (digitalRead(PIN_BTN2) == LOW)) {
        if ((millis() - holdStart) >= PORTAL_HOLD_MS) {
            return true;
        }
        delay(50);
    }
    return false;
}

// ---------------------------------------------------------------------------
// enterConfigMode()
// ---------------------------------------------------------------------------
void enterConfigMode() {
    configMode = true;
    digitalWrite(PIN_AMP_MUTE, LOW);

    Serial.println("[Config] Entering configuration mode");
    Serial.println("[Config] Play-mode services will not start");

    if (!wavPlayer.begin()) {
        Serial.println("[WARN] SD init failed; config portal will not be able to manage files");
    } else {
        parentConfig.load();
    }

    // TODO Phase 5: start Wi-Fi AP, captive DNS, and HTML management portal.
    Serial.println("[Config] Captive portal placeholder; restart without buttons for play mode");
}

// ---------------------------------------------------------------------------
// loopConfigMode()
// ---------------------------------------------------------------------------
void loopConfigMode() {
    static uint32_t lastToggleMs = 0;
    static bool ledOn = false;

    uint32_t now = millis();
    if ((now - lastToggleMs) >= 250) {
        lastToggleMs = now;
        ledOn = !ledOn;
        digitalWrite(PIN_LED, ledOn ? HIGH : LOW);
    }

    // TODO Phase 5: handle captive portal client requests here.
    delay(20);
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
// setupBtDebugLogging()
// ---------------------------------------------------------------------------
void setupBtDebugLogging() {
#if SWEETYAAR_BT_DEBUG
    Serial.println("[BTDBG] Firmware BT debug mode enabled");
    esp_log_level_set("*", ESP_LOG_VERBOSE);
    esp_log_level_set("BT_API", ESP_LOG_VERBOSE);
    esp_log_level_set("BT_AV", ESP_LOG_VERBOSE);
    esp_log_level_set("RCCT", ESP_LOG_VERBOSE);
    esp_log_level_set("BTDM_INIT", ESP_LOG_VERBOSE);
    esp_log_level_set("BT_HCI", ESP_LOG_VERBOSE);
#endif
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
#if SWEETYAAR_BT_DEBUG
    auto* sink = new DebugA2DPSinkQueued(i2sOut);
#else
    auto* sink = new LowLatencyA2DPSinkQueued(i2sOut);
#endif
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
#if SWEETYAAR_BT_DEBUG
    Serial.printf("[BTDBG] A2DP started mode=%s BLE=%d queue=%d stack=%d free=%u largest=%u\n",
                  ENABLE_BLE_PARENT_SERVICE ? "BTDM" : "CLASSIC",
                  ENABLE_BLE_PARENT_SERVICE ? 1 : 0,
                  BT_A2DP_RINGBUFFER_BYTES,
                  BT_A2DP_I2S_TASK_STACK_BYTES,
                  heap_caps_get_free_size(MALLOC_CAP_8BIT),
                  heap_caps_get_largest_free_block(MALLOC_CAP_8BIT));
#endif
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
    reopenBluetoothForPairing("BT cooldown elapsed");
}

// ---------------------------------------------------------------------------
// pollBtDebug()
// ---------------------------------------------------------------------------
void pollBtDebug() {
#if SWEETYAAR_BT_DEBUG
    static uint32_t lastBtDebugMs = 0;
    if (millis() - lastBtDebugMs < 5000) {
        return;
    }
    lastBtDebugMs = millis();

    int conn = -1;
    int audio = -1;
    if (btSink != nullptr) {
        conn = static_cast<int>(btSink->get_connection_state());
        audio = static_cast<int>(btSink->get_audio_state());
    }
    Serial.printf("[BTDBG] heartbeat sm=%s btLink=%d conn=%d audio=%d reopenPending=%d bleClient=%d free=%u largest=%u\n",
                  stateToString(sm.currentState()),
                  btLinkConnected ? 1 : 0,
                  conn,
                  audio,
                  btReopenPending ? 1 : 0,
                  bleService.isConnected() ? 1 : 0,
                  heap_caps_get_free_size(MALLOC_CAP_8BIT),
                  heap_caps_get_largest_free_block(MALLOC_CAP_8BIT));
#endif
}

// ---------------------------------------------------------------------------
// processStateMachineTransitions()
// ---------------------------------------------------------------------------
bool processStateMachineTransitions() {
    bool changed = sm.process();
    State newState = sm.currentState();
    if (changed || newState != prevState) {
        handleStateEntry(prevState, newState);
        prevState = newState;
        publishBleValues();
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
            bool changedTheme = newTheme != activeTheme;
            activeTheme = newTheme;
            sm.postStringEvent(Event::THEME_CHANGED, newTheme);
            if (changedTheme && sm.currentState() == State::PLAYING_SONG) {
                wavPlayer.startSong(activeTheme);
            }
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

    return writeSeen;
}

// ---------------------------------------------------------------------------
// handleBleCommand()
// ---------------------------------------------------------------------------
void handleBleCommand(uint8_t command) {
    State state = sm.currentState();
    switch (command) {
        case 1:  // Song button
            if (state == State::PLAYING_SONG) {
                wavPlayer.nextSong();
                publishBleValues();
            } else {
                sm.postEvent(Event::BUTTON1_PRESS);
            }
            break;

        case 2:  // Animal button
            if (state == State::PLAYING_ANIMAL) {
                wavPlayer.nextAnimal();
                publishBleValues();
            } else {
                sm.postEvent(Event::BUTTON2_PRESS);
            }
            break;

        case 3:  // Both buttons / stop
            sm.postEvent(Event::BOTH_BUTTONS_PRESS);
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
    lastBleStatusPublishMs = millis();
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
            status += themeDisplayName(activeTheme);
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
    float v = pct / 100.0f;
    volumeOut.setVolume(v);
    Serial.printf("[Vol] %u%% (%.2f)\n", pct, v);
}

// ---------------------------------------------------------------------------
// handleStateEntry() — called once when the state machine transitions
// ---------------------------------------------------------------------------
void handleStateEntry(State prev, State next) {
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
            digitalWrite(PIN_AMP_MUTE, LOW);  // mute amp
            break;

        case State::PLAYING_SONG: {
            // Fresh song start (prev != PLAYING_SONG); "next song" is handled
            // directly in loop() via wavPlayer.nextSong() when btn1 is pressed.
            String theme = activeTheme;
            digitalWrite(PIN_AMP_MUTE, HIGH);  // unmute amp
            wavPlayer.startSong(theme);
            break;
        }

        case State::PLAYING_ANIMAL:
            digitalWrite(PIN_AMP_MUTE, HIGH);  // unmute amp
            wavPlayer.startRandomAnimal();
            break;

        case State::BT_STREAMING:
            // WAV already stopped above; unmute amp so A2DP audio flows through
            wavPlayer.stop();  // ensure WAV is stopped
            digitalWrite(PIN_AMP_MUTE, HIGH);
            break;

        case State::KILLSWITCH:
            wavPlayer.stop();
            digitalWrite(PIN_AMP_MUTE, LOW);  // mute amp
            Serial.printf("[SM] Killswitch active for %lu ms\n", KILLSWITCH_MS);
            break;
    }
}

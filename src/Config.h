#pragma once

// ---------------------------------------------------------------------------
// SweetYaar — Hardware pin assignments & compile-time constants
// Target: ESP32-WROOM-32 + MAX98357A + SD card via SPI
// ---------------------------------------------------------------------------

// --- I2S (MAX98357A) --------------------------------------------------------
static constexpr int HW_I2S_BCLK    = 26;  // Bit clock
static constexpr int HW_I2S_WS      = 25;  // Word select / LRCK
static constexpr int HW_I2S_DOUT    = 22;  // Data out to MAX98357A DIN
static constexpr int PIN_AMP_MUTE   = 21;  // MAX98357A SD_MODE: LOW=mute, HIGH=active

// --- SD card (SPI) ----------------------------------------------------------
static constexpr int PIN_SD_SCK     = 18;
static constexpr int PIN_SD_MISO    = 19;
static constexpr int PIN_SD_MOSI    = 23;
static constexpr int PIN_SD_CS      = 5;

// --- Buttons (active LOW, internal pull-up) ---------------------------------
static constexpr int PIN_BTN1       = 32;  // Button 1: Songs
static constexpr int PIN_BTN2       = 33;  // Button 2: Animals

// --- Sleep / power gating ---------------------------------------------------
static constexpr int PIN_VIB_WAKE   = 27;  // Vibration wake switch to GND
static constexpr int PIN_PERIPH_EN  = 13;  // Load-switch enable for SD + amp

// --- Status LED -------------------------------------------------------------
static constexpr int PIN_LED        = 2;   // On-board LED

// ---------------------------------------------------------------------------
// Timing constants
// ---------------------------------------------------------------------------
static constexpr uint32_t DEBOUNCE_MS          = 50;    // Button debounce window
static constexpr uint32_t BOTH_PRESS_WINDOW_MS = 100;   // Max gap for "both pressed"
static constexpr uint32_t KILLSWITCH_MS        = 10UL * 60UL * 1000UL;  // 10 minutes
static constexpr bool     DEFAULT_SLEEP_ENABLED = true;
static constexpr uint32_t SLEEP_NORMAL_IDLE_MS = 10UL * 60UL * 1000UL;
static constexpr uint32_t SLEEP_VIB_WAKE_IDLE_MS = 2UL * 60UL * 1000UL;
static constexpr uint32_t SLEEP_BLE_IDLE_MS = 2UL * 60UL * 1000UL;

// ---------------------------------------------------------------------------
// Audio
// ---------------------------------------------------------------------------
static constexpr int     SAMPLE_RATE        = 44100;
static constexpr int     CHANNELS           = 2;   // Stereo PCM; MAX98357A mixes to mono
static constexpr int     BITS_PER_SAMPLE    = 16;
static constexpr uint8_t DEFAULT_VOLUME_PCT = 75;  // Static default; SD config may override
static constexpr bool    DEFAULT_BEDTIME_ENABLED = true;
static constexpr uint16_t DEFAULT_BEDTIME_START_MINUTES = 18U * 60U + 30U;
static constexpr uint16_t DEFAULT_BEDTIME_END_MINUTES = 6U * 60U + 30U;
static constexpr uint8_t DEFAULT_BEDTIME_VOLUME_CAP_PCT = 45;
static constexpr int     BT_A2DP_RINGBUFFER_BYTES = 16 * 1024;
static constexpr int     BT_A2DP_I2S_TASK_STACK_BYTES = 3072;

// BLE parent controls are live session controls for local SD/WAV playback.
static constexpr bool ENABLE_BLE_PARENT_SERVICE = true;

#ifndef SWEETYAAR_BT_DEBUG
#define SWEETYAAR_BT_DEBUG 0
#endif

// ---------------------------------------------------------------------------
// SD file paths
// ---------------------------------------------------------------------------
static constexpr char SD_CONFIG_FILE[] = "/config.json";
static constexpr char SONGS_ROOT[]    = "/songs";
static constexpr char ANIMALS_PATH[]  = "/animals";
static constexpr char METADATA_FILE[] = "metadata.json";
static constexpr char DEFAULT_THEME[] = "lullabies";
static constexpr char DEFAULT_BEDTIME_THEME[] = "lullabies";
static constexpr char ANIMALS_THEME_ID[] = "__animals";
static constexpr char ANIMALS_DISPLAY_NAME[] = "Animals";

// ---------------------------------------------------------------------------
// BLE UUIDs  (randomly generated, fixed per GATT schema version)
// ---------------------------------------------------------------------------
static constexpr char BLE_SERVICE_UUID[]    = "A1B2C3D4-E5F6-7890-ABCD-EF1234567890";
static constexpr char BLE_VOL_UUID[]        = "A1B2C3D4-E5F6-7890-ABCD-EF1234567891";
static constexpr char BLE_KILL_UUID[]       = "A1B2C3D4-E5F6-7890-ABCD-EF1234567892";
static constexpr char BLE_THEME_UUID[]      = "A1B2C3D4-E5F6-7890-ABCD-EF1234567893";
static constexpr char BLE_STATUS_UUID[]     = "A1B2C3D4-E5F6-7890-ABCD-EF1234567894";
static constexpr char BLE_THEMES_UUID[]     = "A1B2C3D4-E5F6-7890-ABCD-EF1234567895";
static constexpr char BLE_COMMAND_UUID[]    = "A1B2C3D4-E5F6-7890-ABCD-EF1234567896";
static constexpr char BLE_CONFIG_COMMAND_UUID[]  = "A1B2C3D4-E5F6-7890-ABCD-EF1234567897";
static constexpr char BLE_CONFIG_RESPONSE_UUID[] = "A1B2C3D4-E5F6-7890-ABCD-EF1234567898";
static constexpr size_t BLE_THEMES_MAX_BYTES = 512;
static constexpr int BLE_MAX_THEMES = 16;
static constexpr int BLE_CONFIG_THEME_PAGE_SIZE = 1;
static constexpr int BLE_CONFIG_SONG_PAGE_SIZE = 2;
static constexpr int CONFIG_MAX_DISABLED_THEMES = 64;
static constexpr int CONFIG_MAX_DISABLED_SONGS = 128;
static constexpr int CONFIG_SCAN_MAX_THEMES = 64;
static constexpr int CONFIG_SCAN_MAX_SONGS = 128;

// ---------------------------------------------------------------------------
// NVS namespace / keys
//
// Parent-editable toy settings live on the SD card. NVS is reserved for
// device-local settings that must survive SD-card replacement, stored as a
// compact JSON blob under NVS_KEY_DEVICE_CONFIG.
// ---------------------------------------------------------------------------
static constexpr char NVS_NAMESPACE[]         = "sweetyaar";
static constexpr char NVS_KEY_DEVICE_CONFIG[] = "device_config";

static constexpr char DEFAULT_BT_NAME[] = "SweetYaar";

#pragma once

// ---------------------------------------------------------------------------
// SweetYaar — Hardware pin assignments & compile-time constants
// Target: ESP32-WROOM-32 + MAX98357A + SD card via SPI
// ---------------------------------------------------------------------------

// --- I2S (MAX98357A) --------------------------------------------------------
static constexpr int HW_I2S_BCLK    = 26;  // Bit clock
static constexpr int HW_I2S_WS      = 25;  // Word select / LRCK
static constexpr int HW_I2S_DOUT    = 22;  // Data out to MAX98357A DIN
static constexpr int PIN_AMP_MUTE   = 21;  // MAX98357A SD_MODE control

// The production PCB drives SD_MODE directly through 634 kOhm, so LOW mutes.
// The generic board's MMBT3904 inverts that signal; its PlatformIO environment
// overrides this build-time setting to make HIGH mute.
#ifndef SWEETYAAR_AMP_MUTE_ACTIVE_HIGH
#define SWEETYAAR_AMP_MUTE_ACTIVE_HIGH 0
#endif

#if SWEETYAAR_AMP_MUTE_ACTIVE_HIGH != 0 && SWEETYAAR_AMP_MUTE_ACTIVE_HIGH != 1
#error "SWEETYAAR_AMP_MUTE_ACTIVE_HIGH must be 0 or 1"
#endif

static constexpr bool AMP_MUTE_ACTIVE_HIGH =
    SWEETYAAR_AMP_MUTE_ACTIVE_HIGH != 0;

// --- SD card (SPI) ----------------------------------------------------------
static constexpr int PIN_SD_SCK     = 18;
static constexpr int PIN_SD_MISO    = 19;
static constexpr int PIN_SD_MOSI    = 23;
static constexpr int PIN_SD_CS      = 5;
static constexpr uint32_t SD_SPI_FREQUENCY_HZ = 20000000;
// FatFs reserves about 4 KB per file slot even when no file is open. Playback
// holds one WAV; settings read/write/check files sequentially in the other slot.
static constexpr uint8_t SD_MAX_OPEN_FILES = 2;

// --- Buttons (active LOW, internal pull-up) ---------------------------------
static constexpr int PIN_BTN1       = 32;  // Button 1: Songs
static constexpr int PIN_BTN2       = 33;  // Button 2: Animals

// --- Sleep / power gating ---------------------------------------------------
static constexpr int PIN_VIB_WAKE   = 27;  // Externally biased NC vibration switch to GND; wake HIGH
static constexpr int PIN_PERIPH_PWR_EN = 13;  // SD, battery-sense, and 5 V shared enable

// --- Battery / BQ25186 charger ---------------------------------------------
// GPIO34/35 are input-only and use external 10 kOhm pull-ups to 3V3_AON.
// GPIO4 drives the base of the external /CE pull-down transistor: HIGH turns
// the transistor on and enables charging. Its reset-default internal pulldown
// and the physical base pulldown keep charging off through reset and boot;
// the physical pulldown also keeps it off with an unpowered ESP32/open switch.
#ifndef SWEETYAAR_BQ25186_ENABLED
#define SWEETYAAR_BQ25186_ENABLED 1
#endif

#if SWEETYAAR_BQ25186_ENABLED != 0 && SWEETYAAR_BQ25186_ENABLED != 1
#error "SWEETYAAR_BQ25186_ENABLED must be 0 or 1"
#endif

static constexpr bool HAS_BQ25186 = SWEETYAAR_BQ25186_ENABLED != 0;
static constexpr int PIN_CHARGER_ENABLE = 4;
static constexpr int PIN_CHARGER_SDA    = 16;
static constexpr int PIN_CHARGER_SCL    = 17;
static constexpr int PIN_CHARGER_PG     = 34;
static constexpr int PIN_CHARGER_INT    = 35;
static constexpr int PIN_BATTERY_ADC   = 36;
static constexpr uint32_t BATTERY_DIVIDER_TOP_OHMS = 634000;
static constexpr uint32_t BATTERY_DIVIDER_BOTTOM_OHMS = 200000;

// --- Status LED -------------------------------------------------------------
// Production fallback: WS2812B-V6, 24-bit GRB, driven directly from GPIO2.
// Board-specific selections are explicit in platformio.ini. Inversion remains
// available for hardware with an inverting level shifter; neither current
// environment uses it.
#ifndef SWEETYAAR_STATUS_LED_DATA_INVERTED
#define SWEETYAAR_STATUS_LED_DATA_INVERTED 0
#endif

#if SWEETYAAR_STATUS_LED_DATA_INVERTED != 0 && SWEETYAAR_STATUS_LED_DATA_INVERTED != 1
#error "SWEETYAAR_STATUS_LED_DATA_INVERTED must be 0 or 1"
#endif

// Linear cap applied to every LED color channel by StatusLed. This is a product
// tuning value rather than a separate brightness per status pattern.
#ifndef SWEETYAAR_STATUS_LED_MAX_BRIGHTNESS_PCT
#define SWEETYAAR_STATUS_LED_MAX_BRIGHTNESS_PCT 50
#endif

#if SWEETYAAR_STATUS_LED_MAX_BRIGHTNESS_PCT < 0 || SWEETYAAR_STATUS_LED_MAX_BRIGHTNESS_PCT > 100
#error "SWEETYAAR_STATUS_LED_MAX_BRIGHTNESS_PCT must be in the range 0..100"
#endif

// WS2812B-V6 sends GRB (1); select RGB with 0. With an RGBW device the equivalent
// choices are GRBW and RGBW. Verify the actual LED batch before production.
#ifndef SWEETYAAR_STATUS_LED_COLOR_ORDER_GRB
#define SWEETYAAR_STATUS_LED_COLOR_ORDER_GRB 1
#endif

#if SWEETYAAR_STATUS_LED_COLOR_ORDER_GRB != 0 && SWEETYAAR_STATUS_LED_COLOR_ORDER_GRB != 1
#error "SWEETYAAR_STATUS_LED_COLOR_ORDER_GRB must be 0 or 1"
#endif

// Select a 32-bit SK6812-style RGBW frame instead of a 24-bit WS2812-style
// RGB frame. The white channel remains independently addressable.
#ifndef SWEETYAAR_STATUS_LED_RGBW
#define SWEETYAAR_STATUS_LED_RGBW 0
#endif

#if SWEETYAAR_STATUS_LED_RGBW != 0 && SWEETYAAR_STATUS_LED_RGBW != 1
#error "SWEETYAAR_STATUS_LED_RGBW must be 0 or 1"
#endif

// WS2812B-V6 waveform at DIN: zero 300/950 ns, one 650/600 ns, reset 300 us.
// V6 specifies T0H=220..380 ns, T1H/T0L/T1L=580..1000 ns, bit >=1250 ns,
// and reset >280 us. Timing is independent of frame width, order and inversion.
// The ESP32 RMT backend uses 25 ns ticks; reject unrepresentable durations.
#ifndef SWEETYAAR_STATUS_LED_T0H_NS
#define SWEETYAAR_STATUS_LED_T0H_NS 300
#endif
#ifndef SWEETYAAR_STATUS_LED_T1H_NS
#define SWEETYAAR_STATUS_LED_T1H_NS 650
#endif
#ifndef SWEETYAAR_STATUS_LED_BIT_NS
#define SWEETYAAR_STATUS_LED_BIT_NS 1250
#endif
#ifndef SWEETYAAR_STATUS_LED_RESET_US
#define SWEETYAAR_STATUS_LED_RESET_US 300
#endif

#if SWEETYAAR_STATUS_LED_T0H_NS <= 0 || SWEETYAAR_STATUS_LED_T1H_NS <= 0 || \
    SWEETYAAR_STATUS_LED_T0H_NS >= SWEETYAAR_STATUS_LED_BIT_NS || \
    SWEETYAAR_STATUS_LED_T1H_NS >= SWEETYAAR_STATUS_LED_BIT_NS || \
    SWEETYAAR_STATUS_LED_BIT_NS > 65535
#error "Status LED high/low durations must be positive and the bit period <= 65535 ns"
#endif
#if SWEETYAAR_STATUS_LED_T0H_NS % 25 != 0 || SWEETYAAR_STATUS_LED_T1H_NS % 25 != 0 || \
    SWEETYAAR_STATUS_LED_BIT_NS % 25 != 0
#error "Status LED pulse timings must be multiples of 25 ns"
#endif
// The final RMT item's reset duration occupies a 15-bit counter.
#if SWEETYAAR_STATUS_LED_RESET_US < 1 || SWEETYAAR_STATUS_LED_RESET_US > 819
#error "SWEETYAAR_STATUS_LED_RESET_US must be in the range 1..819"
#endif

#ifndef SWEETYAAR_STATUS_LED_PIXEL_COUNT
#define SWEETYAAR_STATUS_LED_PIXEL_COUNT 1
#endif

#if SWEETYAAR_STATUS_LED_PIXEL_COUNT < 1
#error "SWEETYAAR_STATUS_LED_PIXEL_COUNT must be at least 1"
#endif

static constexpr int PIN_STATUS_LED_DATA = 2;
static constexpr uint16_t STATUS_LED_PIXEL_COUNT =
    SWEETYAAR_STATUS_LED_PIXEL_COUNT;
static constexpr bool STATUS_LED_DATA_INVERTED =
    SWEETYAAR_STATUS_LED_DATA_INVERTED != 0;
static constexpr bool STATUS_LED_HAS_WHITE_CHANNEL =
    SWEETYAAR_STATUS_LED_RGBW != 0;
static constexpr uint8_t STATUS_LED_MAX_BRIGHTNESS_PCT =
    SWEETYAAR_STATUS_LED_MAX_BRIGHTNESS_PCT;

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
static constexpr uint32_t BATTERY_SAMPLE_INTERVAL_MS = 30UL * 1000UL;
static constexpr uint32_t CHARGER_VERIFY_INTERVAL_MS = 10UL * 1000UL;
static constexpr uint32_t BATTERY_BOOT_SAMPLE_INTERVAL_MS = 100;
static constexpr uint8_t  BATTERY_BOOT_SAMPLE_COUNT = 5;
static constexpr uint8_t  BATTERY_ROLLING_SAMPLE_COUNT = 10;
static constexpr uint16_t BATTERY_GOOD_TO_MEDIUM_MV = 3400;
static constexpr uint16_t BATTERY_MEDIUM_TO_GOOD_MV = 3500;
static constexpr uint16_t BATTERY_MEDIUM_TO_LOW_MV = 3100;
static constexpr uint16_t BATTERY_LOW_TO_MEDIUM_MV = 3200;

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
static constexpr int     BT_A2DP_RINGBUFFER_BYTES = 8 * 1024;
static constexpr int     BT_A2DP_I2S_TASK_STACK_BYTES = 2048;

// BLE parent controls are live session controls for local SD/WAV playback.
static constexpr bool ENABLE_BLE_PARENT_SERVICE = true;

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
static constexpr char BLE_NOTICE_UUID[]          = "A1B2C3D4-E5F6-7890-ABCD-EF1234567899";
static constexpr char BLE_BATTERY_UUID[]         = "A1B2C3D4-E5F6-7890-ABCD-EF123456789A";
static constexpr size_t BLE_THEMES_MAX_BYTES = 512;
static constexpr int BLE_MAX_THEMES = 16;
static constexpr size_t BLE_CONFIG_MAX_BYTES = 512;
static constexpr size_t BLE_CONFIG_COMMAND_MAX_BYTES = 383;
static constexpr char BLE_CONFIG_GENERAL_UUID[] = "A1B2C3D4-E5F6-7890-ABCD-EF123456789B";
static constexpr char BLE_CONFIG_SLEEP_UUID[] = "A1B2C3D4-E5F6-7890-ABCD-EF123456789C";
static constexpr char BLE_CONFIG_BEDTIME_UUID[] = "A1B2C3D4-E5F6-7890-ABCD-EF123456789D";
static constexpr char BLE_CONFIG_RUNTIME_UUID[] = "A1B2C3D4-E5F6-7890-ABCD-EF123456789E";
static constexpr char BLE_CATALOG_NOTICE_UUID[] = "A1B2C3D4-E5F6-7890-ABCD-EF123456789F";
static constexpr size_t BLE_CONFIG_ATTRIBUTE_COUNT = 5;
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

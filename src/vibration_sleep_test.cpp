#include <Arduino.h>
#include <driver/rtc_io.h>
#include <esp_sleep.h>

#include "PeripheralPower.h"

#ifndef VIB_WAKE_PIN
#define VIB_WAKE_PIN GPIO_NUM_27
#endif

#ifndef VIB_SLEEP_AFTER_MS
#define VIB_SLEEP_AFTER_MS (30UL * 1000UL)
#endif

#ifndef VIB_DETECTION_REFRACTORY_US
#define VIB_DETECTION_REFRACTORY_US (30UL * 1000UL)
#endif

static_assert(VIB_WAKE_PIN == GPIO_NUM_0 || VIB_WAKE_PIN == GPIO_NUM_2 ||
                  VIB_WAKE_PIN == GPIO_NUM_4 || VIB_WAKE_PIN == GPIO_NUM_12 ||
                  VIB_WAKE_PIN == GPIO_NUM_13 || VIB_WAKE_PIN == GPIO_NUM_14 ||
                  VIB_WAKE_PIN == GPIO_NUM_15 || VIB_WAKE_PIN == GPIO_NUM_25 ||
                  VIB_WAKE_PIN == GPIO_NUM_26 || VIB_WAKE_PIN == GPIO_NUM_27 ||
                  VIB_WAKE_PIN == GPIO_NUM_32 || VIB_WAKE_PIN == GPIO_NUM_33 ||
                  VIB_WAKE_PIN == GPIO_NUM_34 || VIB_WAKE_PIN == GPIO_NUM_35 ||
                  VIB_WAKE_PIN == GPIO_NUM_36 || VIB_WAKE_PIN == GPIO_NUM_39,
              "VIB_WAKE_PIN must be an ESP32 RTC-capable GPIO");

volatile uint32_t g_pendingDetections = 0;
volatile uint32_t g_rawEdges = 0;
volatile uint32_t g_lastAcceptedUs = 0;

uint32_t lastActivityMs = 0;
uint32_t detectionCount = 0;

const char* wakeReasonName(esp_sleep_wakeup_cause_t reason) {
    switch (reason) {
        case ESP_SLEEP_WAKEUP_EXT0:
            return "ext0_rtc_gpio";
        case ESP_SLEEP_WAKEUP_EXT1:
            return "ext1_rtc_gpio";
        case ESP_SLEEP_WAKEUP_TIMER:
            return "timer";
        case ESP_SLEEP_WAKEUP_TOUCHPAD:
            return "touchpad";
        case ESP_SLEEP_WAKEUP_ULP:
            return "ulp";
        case ESP_SLEEP_WAKEUP_GPIO:
            return "gpio";
        case ESP_SLEEP_WAKEUP_UART:
            return "uart";
        case ESP_SLEEP_WAKEUP_UNDEFINED:
        default:
            return "power_on_or_reset";
    }
}

void IRAM_ATTR onVibrationEdge() {
    uint32_t nowUs = micros();
    g_rawEdges++;

    if ((uint32_t)(nowUs - g_lastAcceptedUs) >= VIB_DETECTION_REFRACTORY_US) {
        g_lastAcceptedUs = nowUs;
        g_pendingDetections++;
    }
}

void printBootInfo() {
    esp_sleep_wakeup_cause_t wakeReason = esp_sleep_get_wakeup_cause();

    Serial.println();
    Serial.println("=== SweetYaar vibration sleep test ===");
    Serial.printf("[VIB] Wake pin: GPIO%d, active LOW\n", static_cast<int>(VIB_WAKE_PIN));
    Serial.printf("[VIB] Wake reason: %s (%d)\n",
                  wakeReasonName(wakeReason), static_cast<int>(wakeReason));
    Serial.printf("[VIB] Sleep after quiet: %lu ms\n",
                  static_cast<unsigned long>(VIB_SLEEP_AFTER_MS));
    Serial.printf("[VIB] Wiring: GPIO%d -> passive vibration switch -> GND\n",
                  static_cast<int>(VIB_WAKE_PIN));
    Serial.printf("[VIB] Load switch EN: GPIO%d active HIGH while awake\n", PIN_PERIPH_EN);

    if (wakeReason == ESP_SLEEP_WAKEUP_EXT0) {
        Serial.println("DETECTED wake");
    }
}

void configureWakePinForAwakeMode() {
    rtc_gpio_deinit(VIB_WAKE_PIN);
    pinMode(static_cast<uint8_t>(VIB_WAKE_PIN), INPUT_PULLUP);
    attachInterrupt(digitalPinToInterrupt(static_cast<uint8_t>(VIB_WAKE_PIN)),
                    onVibrationEdge, FALLING);
}

void enterDeepSleep() {
    detachInterrupt(digitalPinToInterrupt(static_cast<uint8_t>(VIB_WAKE_PIN)));

    if (digitalRead(static_cast<uint8_t>(VIB_WAKE_PIN)) == LOW) {
        Serial.println("[VIB] Wake switch is still closed; waiting for release before sleep");
        while (digitalRead(static_cast<uint8_t>(VIB_WAKE_PIN)) == LOW) {
            delay(10);
        }
        delay(50);
    }

    Serial.println("[VIB] Holding peripheral rail off and entering deep sleep. Shake/tilt the switch to wake.");
    holdPeripheralPowerOffForDeepSleep();
    Serial.flush();

    rtc_gpio_init(VIB_WAKE_PIN);
    rtc_gpio_set_direction(VIB_WAKE_PIN, RTC_GPIO_MODE_INPUT_ONLY);
    rtc_gpio_pullup_en(VIB_WAKE_PIN);
    rtc_gpio_pulldown_dis(VIB_WAKE_PIN);
    esp_sleep_enable_ext0_wakeup(VIB_WAKE_PIN, 0);
    esp_deep_sleep_start();
}

void setup() {
    Serial.begin(115200);
    delay(500);

    enablePeripheralPower();
    printBootInfo();
    Serial.printf("[Power] Peripherals enabled on GPIO%d for vibration sleep test\n", PIN_PERIPH_EN);
    configureWakePinForAwakeMode();

    lastActivityMs = millis();
    Serial.println("[VIB] Ready. Shake the passive switch; each accepted edge prints DETECTED.");
}

void loop() {
    uint32_t pending = 0;
    uint32_t rawEdges = 0;

    noInterrupts();
    pending = g_pendingDetections;
    g_pendingDetections = 0;
    rawEdges = g_rawEdges;
    interrupts();

    if (pending > 0) {
        detectionCount += pending;
        lastActivityMs = millis();
        Serial.printf("DETECTED count=%lu pending=%lu raw_edges=%lu uptime_ms=%lu\n",
                      static_cast<unsigned long>(detectionCount),
                      static_cast<unsigned long>(pending),
                      static_cast<unsigned long>(rawEdges),
                      static_cast<unsigned long>(millis()));
    }

    if ((uint32_t)(millis() - lastActivityMs) >= VIB_SLEEP_AFTER_MS) {
        enterDeepSleep();
    }

    delay(5);
}

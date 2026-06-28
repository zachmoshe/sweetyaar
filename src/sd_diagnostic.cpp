#include <Arduino.h>
#include <SPI.h>
#include <SD.h>

#include "Config.h"
#include "PeripheralPower.h"

static constexpr uint32_t SD_INIT_TEST_FREQ_HZ = 400000;
static constexpr uint32_t SD_STREAM_TEST_FREQ_HZ = 4000000;

static uint8_t waitForR1(uint16_t attempts = 32) {
    for (uint16_t i = 0; i < attempts; ++i) {
        uint8_t response = SPI.transfer(0xFF);
        if ((response & 0x80) == 0) {
            return response;
        }
    }
    return 0xFF;
}

static uint8_t sendSdCommand(uint8_t command,
                             uint32_t argument,
                             uint8_t crc,
                             uint8_t* extra = nullptr,
                             size_t extraLen = 0) {
    digitalWrite(PIN_SD_CS, LOW);
    SPI.transfer(0xFF);
    SPI.transfer(0x40 | command);
    SPI.transfer((argument >> 24) & 0xFF);
    SPI.transfer((argument >> 16) & 0xFF);
    SPI.transfer((argument >> 8) & 0xFF);
    SPI.transfer(argument & 0xFF);
    SPI.transfer(crc);

    uint8_t r1 = waitForR1();
    for (size_t i = 0; i < extraLen; ++i) {
        extra[i] = SPI.transfer(0xFF);
    }

    digitalWrite(PIN_SD_CS, HIGH);
    SPI.transfer(0xFF);
    return r1;
}

static void rawSpiProbe() {
    Serial.println("\n[Raw SPI probe]");
    SPI.beginTransaction(SPISettings(SD_INIT_TEST_FREQ_HZ, MSBFIRST, SPI_MODE0));

    digitalWrite(PIN_SD_CS, HIGH);
    Serial.printf("Idle levels before clocks: CS=%d MISO=%d\n",
                  digitalRead(PIN_SD_CS), digitalRead(PIN_SD_MISO));

    Serial.print("Idle SPI bytes with CS high:");
    for (int i = 0; i < 4; ++i) {
        Serial.printf(" %02X", SPI.transfer(0xFF));
    }
    Serial.println();

    for (int i = 0; i < 10; ++i) {
        SPI.transfer(0xFF);
    }

    uint8_t cmd0 = sendSdCommand(0, 0, 0x95);
    Serial.printf("CMD0 response: 0x%02X (expected 0x01 if the card hears us)\n", cmd0);

    uint8_t cmd8Extra[4] = {0};
    uint8_t cmd8 = sendSdCommand(8, 0x000001AA, 0x87, cmd8Extra, sizeof(cmd8Extra));
    Serial.printf("CMD8 response: 0x%02X, extra: %02X %02X %02X %02X\n",
                  cmd8, cmd8Extra[0], cmd8Extra[1], cmd8Extra[2], cmd8Extra[3]);

    if (cmd0 == 0x01 && cmd8 == 0x01) {
        Serial.println("Trying manual CMD55/ACMD41 init loop...");
        uint8_t cmd55 = 0xFF;
        uint8_t acmd41 = 0xFF;
        for (int attempt = 1; attempt <= 100; ++attempt) {
            cmd55 = sendSdCommand(55, 0, 0x01);
            acmd41 = sendSdCommand(41, 0x40000000, 0x01);
            if (attempt <= 5 || attempt % 10 == 0 || acmd41 == 0x00) {
                Serial.printf("  attempt %d: CMD55=0x%02X ACMD41=0x%02X\n",
                              attempt, cmd55, acmd41);
            }
            if (acmd41 == 0x00) {
                break;
            }
            delay(10);
        }

        if (acmd41 == 0x00) {
            uint8_t ocr[4] = {0};
            uint8_t cmd58 = sendSdCommand(58, 0, 0x01, ocr, sizeof(ocr));
            Serial.printf("Manual init OK. CMD58=0x%02X OCR: %02X %02X %02X %02X\n",
                          cmd58, ocr[0], ocr[1], ocr[2], ocr[3]);
        } else {
            Serial.printf("Manual init failed. Last CMD55=0x%02X ACMD41=0x%02X\n",
                          cmd55, acmd41);
        }
    }

    if (cmd0 == 0xFF) {
        Serial.println("No response at all. Suspect CS/SCK/MOSI/MISO wiring, module direction labels, or no card power.");
    } else if (cmd0 == 0x00) {
        Serial.println("MISO appears stuck LOW. Suspect MISO wiring, a short to GND, module/socket fault, or wrong module pin label.");
    } else if (cmd0 == 0x01) {
        Serial.println("Card responded to raw SPI. If SD.begin fails, the issue is likely library/module/card init compatibility.");
    } else {
        Serial.println("Card returned an unusual response; wiring may be partially working.");
    }

    SPI.endTransaction();
}

static bool arduinoSdProbe(uint32_t frequencyHz) {
    Serial.printf("\n[Arduino SD probe @ %lu Hz]\n", static_cast<unsigned long>(frequencyHz));
    Serial.println("Waiting 1000ms before SD.begin...");
    delay(1000);
    if (!SD.begin(PIN_SD_CS, SPI, frequencyHz)) {
        Serial.println("SD.begin failed");
        return false;
    }

    uint8_t cardType = SD.cardType();
    Serial.printf("cardType=%u\n", cardType);
    Serial.printf("cardSize=%llu MB\n", SD.cardSize() / (1024ULL * 1024ULL));

    File root = SD.open("/");
    if (!root) {
        Serial.println("Could not open root directory");
        SD.end();
        return false;
    }

    Serial.println("Root directory:");
    while (true) {
        File entry = root.openNextFile();
        if (!entry) {
            break;
        }
        Serial.printf("  %s%s %u bytes\n",
                      entry.name(),
                      entry.isDirectory() ? "/" : "",
                      static_cast<unsigned>(entry.size()));
        entry.close();
    }
    root.close();
    SD.end();
    return true;
}

static void holdOutput(const char* label, uint8_t pin, uint8_t level) {
    digitalWrite(pin, level);
    Serial.printf("  Measure SD %-3s -> GND now: expected about %.1fV for 8s\n",
                  label, level == HIGH ? 3.3 : 0.0);
    delay(8000);
}

static void slowLineProbe() {
    Serial.println("\n[Slow wiring probe]");
    Serial.println("Use DC volts, black probe on SD GND. Measure on the SD breakout's labeled pins.");
    Serial.println("This checks whether CS/CLK/DI actually arrive at the SD board.");

    SPI.end();
    pinMode(PIN_SD_CS, OUTPUT);
    pinMode(PIN_SD_SCK, OUTPUT);
    pinMode(PIN_SD_MOSI, OUTPUT);
    pinMode(PIN_SD_MISO, INPUT_PULLUP);

    digitalWrite(PIN_SD_CS, HIGH);
    digitalWrite(PIN_SD_SCK, LOW);
    digitalWrite(PIN_SD_MOSI, LOW);
    delay(500);

    holdOutput("CS", PIN_SD_CS, LOW);
    holdOutput("CS", PIN_SD_CS, HIGH);
    holdOutput("CLK", PIN_SD_SCK, LOW);
    holdOutput("CLK", PIN_SD_SCK, HIGH);
    holdOutput("DI", PIN_SD_MOSI, LOW);
    holdOutput("DI", PIN_SD_MOSI, HIGH);

    Serial.printf("  Measure SD DO  -> GND now: ESP32 pull-up reads %d; expected high-ish\n",
                  digitalRead(PIN_SD_MISO));
    delay(8000);
}

void setup() {
    Serial.begin(115200);
    delay(1000);

    Serial.println("\n=== SweetYaar SD Diagnostic ===");
    Serial.printf("Pins: CS=%d SCK=%d MISO=%d MOSI=%d\n",
                  PIN_SD_CS, PIN_SD_SCK, PIN_SD_MISO, PIN_SD_MOSI);
    Serial.println("Expected wiring: CS->GPIO5, SCK->GPIO18, MISO->GPIO19, MOSI->GPIO23");

    enablePeripheralPower();
    Serial.printf("[Power] Peripherals enabled on GPIO%d for SD diagnostic\n", PIN_PERIPH_EN);

    pinMode(PIN_SD_CS, OUTPUT);
    digitalWrite(PIN_SD_CS, HIGH);
    pinMode(PIN_SD_MISO, INPUT_PULLUP);
    delay(50);
    Serial.printf("GPIO pull-up probe before SPI.begin: MISO=%d\n", digitalRead(PIN_SD_MISO));

    SPI.begin(PIN_SD_SCK, PIN_SD_MISO, PIN_SD_MOSI, PIN_SD_CS);

    rawSpiProbe();
    arduinoSdProbe(SD_INIT_TEST_FREQ_HZ);
    delay(200);
    arduinoSdProbe(SD_STREAM_TEST_FREQ_HZ);
    slowLineProbe();

    Serial.println("\nDiagnostic complete. Press EN/RST to run again.");
}

void loop() {
    delay(1000);
}

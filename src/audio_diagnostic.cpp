#include <Arduino.h>

#include "AudioTools.h"
#include "Config.h"

struct FormatCase {
    I2SFormat format;
    const char* name;
};

static constexpr FormatCase FORMATS[] = {
    {I2S_STD_FORMAT, "I2S_STD_FORMAT"},
    {I2S_PHILIPS_FORMAT, "I2S_PHILIPS_FORMAT"},
    {I2S_MSB_FORMAT, "I2S_MSB_FORMAT"},
    {I2S_LEFT_JUSTIFIED_FORMAT, "I2S_LEFT_JUSTIFIED_FORMAT"},
};

AudioInfo info(SAMPLE_RATE, CHANNELS, BITS_PER_SAMPLE);
I2SStream i2s;
SineWaveGenerator<int16_t> sine(30000);
GeneratedSoundStream<int16_t> sound(sine);
StreamCopy copier(i2s, sound, 2048);

size_t formatIndex = 0;
uint32_t formatStartedMs = 0;

void startFormat(size_t index) {
    digitalWrite(PIN_AMP_MUTE, LOW);
    delay(30);

    i2s.end();

    auto cfg = i2s.defaultConfig(TX_MODE);
    cfg.copyFrom(info);
    cfg.pin_bck = HW_I2S_BCLK;
    cfg.pin_ws = HW_I2S_WS;
    cfg.pin_data = HW_I2S_DOUT;
    cfg.i2s_format = FORMATS[index].format;
    cfg.buffer_count = 12;
    cfg.buffer_size = 512;
    i2s.begin(cfg);

    sine.begin(info, 440);
    sound.begin(info);

    digitalWrite(PIN_AMP_MUTE, HIGH);
    formatStartedMs = millis();

    Serial.printf("\n[AUDIO] Now playing 440 Hz sine: %s\n", FORMATS[index].name);
    Serial.println("[AUDIO] Listen for the cleanest/loudest steady tone.");
}

void setup() {
    Serial.begin(115200);
    delay(800);

    Serial.println("\n=== SweetYaar Audio Diagnostic ===");
    Serial.printf("Pins: BCLK=%d LRC/WS=%d DIN=%d SD_MODE=%d\n",
                  HW_I2S_BCLK, HW_I2S_WS, HW_I2S_DOUT, PIN_AMP_MUTE);

    pinMode(PIN_AMP_MUTE, OUTPUT);
    digitalWrite(PIN_AMP_MUTE, LOW);

    startFormat(formatIndex);
}

void loop() {
    copier.copy();

    if ((millis() - formatStartedMs) > 5000) {
        formatIndex = (formatIndex + 1) % (sizeof(FORMATS) / sizeof(FORMATS[0]));
        startFormat(formatIndex);
    }
}

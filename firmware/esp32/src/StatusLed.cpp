#include "StatusLed.h"

#include <NeoPixelBus.h>
#include <esp32-hal-matrix.h>

#include "Config.h"

namespace {
#if SWEETYAAR_STATUS_LED_RGBW
#if SWEETYAAR_STATUS_LED_COLOR_ORDER_GRB
using StatusLedFeature = NeoGrbwFeature;
#else
using StatusLedFeature = NeoRgbwFeature;
#endif
using StatusLedPixelColor = RgbwColor;
#else
#if SWEETYAAR_STATUS_LED_COLOR_ORDER_GRB
using StatusLedFeature = NeoGrbFeature;
#else
using StatusLedFeature = NeoRgbFeature;
#endif
using StatusLedPixelColor = RgbColor;
#endif

#if SWEETYAAR_STATUS_LED_RGBW
#if SWEETYAAR_STATUS_LED_DATA_INVERTED
using StatusLedMethod = NeoEsp32Rmt0Sk6812InvertedMethod;
#else
using StatusLedMethod = NeoEsp32Rmt0Sk6812Method;
#endif
#else
#if SWEETYAAR_STATUS_LED_DATA_INVERTED
using StatusLedMethod = NeoEsp32Rmt0Ws2812xInvertedMethod;
#else
using StatusLedMethod = NeoEsp32Rmt0Ws2812xMethod;
#endif
#endif

using StatusLedBus = NeoPixelBus<StatusLedFeature, StatusLedMethod>;
StatusLedBus pixels(STATUS_LED_PIXEL_COUNT, PIN_STATUS_LED_DATA);

uint8_t scaleChannel(uint8_t channel, uint8_t brightnessPct) {
    return static_cast<uint8_t>(
        (static_cast<uint16_t>(channel) * brightnessPct + 50U) / 100U);
}

bool sameColor(LedColor left, LedColor right) {
    return left.red == right.red &&
           left.green == right.green &&
           left.blue == right.blue &&
           left.white == right.white;
}

#if !SWEETYAAR_STATUS_LED_RGBW
uint8_t addWhite(uint8_t channel, uint8_t white) {
    const uint16_t combined = static_cast<uint16_t>(channel) + white;
    return static_cast<uint8_t>(combined > 255U ? 255U : combined);
}
#endif

StatusLedPixelColor pixelColorFor(LedColor color, uint8_t brightnessPct) {
#if SWEETYAAR_STATUS_LED_RGBW
    return RgbwColor(scaleChannel(color.red, brightnessPct),
                     scaleChannel(color.green, brightnessPct),
                     scaleChannel(color.blue, brightnessPct),
                     scaleChannel(color.white, brightnessPct));
#else
    // Preserve a logical white indication on RGB hardware by mixing white
    // equally into the three available channels.
    return RgbColor(scaleChannel(addWhite(color.red, color.white), brightnessPct),
                    scaleChannel(addWhite(color.green, color.white), brightnessPct),
                    scaleChannel(addWhite(color.blue, color.white), brightnessPct));
#endif
}
}  // namespace

StatusLed::StatusLed()
    : _maxBrightnessPct(STATUS_LED_MAX_BRIGHTNESS_PCT) {}

StatusLed statusLed;

void StatusLed::prepareForPeripheralPowerOn() {
    pinMode(PIN_STATUS_LED_DATA, OUTPUT);
    digitalWrite(PIN_STATUS_LED_DATA, STATUS_LED_DATA_INVERTED ? HIGH : LOW);
}

void StatusLed::begin() {
    pixels.Begin();
    pixels.ClearTo(StatusLedPixelColor(0));
    pixels.Show();

    _initialized = true;
    _mode = StatusLedMode::Off;
    _lastColor = LedColors::OFF;
    service(millis());
}

void StatusLed::setSignal(StatusSignal signal, bool active) {
    const uint32_t bit = statusSignalBit(signal);
    if (active) {
        _signals.fetch_or(bit, std::memory_order_relaxed);
    } else {
        _signals.fetch_and(~bit, std::memory_order_relaxed);
    }
}

void StatusLed::setMaxBrightnessPct(uint8_t brightnessPct) {
    if (brightnessPct > 100) {
        brightnessPct = 100;
    }
    if (brightnessPct == _maxBrightnessPct) {
        return;
    }

    _maxBrightnessPct = brightnessPct;
    if (_initialized) {
        showColor(_lastColor, true);
    }
}

void StatusLed::service(uint32_t nowMs) {
    if (!_initialized) {
        return;
    }

    const StatusLedPattern selected =
        selectStatusLedPattern(_signals.load(std::memory_order_relaxed));

    if (selected.mode != _mode) {
        _mode = selected.mode;
        _phaseOn = selected.mode != StatusLedMode::Off;
        _phaseStartedMs = nowMs;
        showColor(_phaseOn ? selected.color : LedColors::OFF);
        return;
    }

    if (selected.onMs == 0 || selected.offMs == 0) {
        return;
    }

    const uint32_t phaseDurationMs = _phaseOn ? selected.onMs : selected.offMs;
    if ((nowMs - _phaseStartedMs) < phaseDurationMs) {
        return;
    }

    _phaseStartedMs = nowMs;
    _phaseOn = !_phaseOn;
    showColor(_phaseOn ? selected.color : LedColors::OFF);
}

void StatusLed::prepareForPeripheralPowerOff() {
    if (!_initialized) {
        return;
    }

    while (!pixels.CanShow()) {
        delay(1);
    }
    pixels.ClearTo(StatusLedPixelColor(0));
    pixels.Show();
    while (!pixels.CanShow()) {
        delay(1);
    }
    _lastColor = LedColors::OFF;
    _mode = StatusLedMode::Off;
    _phaseOn = false;
}

void StatusLed::releaseAfterPeripheralPowerOff() {
    pinMatrixOutDetach(PIN_STATUS_LED_DATA, false, false);
    pinMode(PIN_STATUS_LED_DATA, INPUT);
}

void StatusLed::showColor(LedColor color, bool force) {
    if (!force && sameColor(color, _lastColor)) {
        return;
    }

    const StatusLedPixelColor pixelColor =
        pixelColorFor(color, _maxBrightnessPct);
    pixels.SetPixelColor(0, pixelColor);
    for (uint16_t pixel = 1; pixel < STATUS_LED_PIXEL_COUNT; ++pixel) {
        pixels.SetPixelColor(pixel, StatusLedPixelColor(0));
    }
    pixels.Show();
    _lastColor = color;
}

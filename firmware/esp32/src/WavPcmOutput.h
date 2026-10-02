#pragma once

#include <cstring>
#include "AudioTools/CoreAudio/VolumeStream.h"
#include "Config.h"

// Validated WAV PCM -> WavPcmOutput -> VolumeStream -> stereo I2S.
// Only the file's PCM framing changes, never the stereo output shared with A2DP.
class WavPcmOutput : public audio_tools::AudioOutput {
public:
    explicit WavPcmOutput(audio_tools::VolumeStream& output) : _output(output) { reset(); }

    void reset() {
        cfg = audio_tools::AudioInfo(0, 0, 0);
        _pendingBytes = 0;
    }

    void setAudioInfo(audio_tools::AudioInfo info) override {
        reset();
        if (info.sample_rate != SAMPLE_RATE || info.bits_per_sample != 16 ||
            (info.channels != 1 && info.channels != 2)) return;
        cfg = info;
        _output.setAudioInfo(audio_tools::AudioInfo(SAMPLE_RATE, CHANNELS, BITS_PER_SAMPLE));
    }

    size_t write(uint8_t byte) override { return write(&byte, 1); }

    size_t write(const uint8_t* data, size_t len) override {
        if (!data || (cfg.channels != 1 && cfg.channels != 2)) return 0;
        const size_t inputFrameBytes = cfg.channels * sizeof(int16_t);
        size_t consumed = 0;
        size_t outputBytes = 0;
        while (consumed < len) {
            const size_t needed = inputFrameBytes - _pendingBytes;
            const size_t count = len - consumed < needed ? len - consumed : needed;
            std::memcpy(_pending + _pendingBytes, data + consumed, count);
            _pendingBytes += count;
            consumed += count;
            if (_pendingBytes != inputFrameBytes) continue;

            std::memcpy(_buffer + outputBytes, _pending, 2);
            std::memcpy(_buffer + outputBytes + 2,
                        _pending + (cfg.channels == 1 ? 0 : 2), 2);
            outputBytes += 4;
            _pendingBytes = 0;
            if (outputBytes == sizeof(_buffer)) {
                if (!writeOutput(outputBytes)) return 0;
                outputBytes = 0;
            }
        }
        if (outputBytes && !writeOutput(outputBytes)) return 0;
        return len;
    }

private:
    audio_tools::VolumeStream& _output;
    uint8_t _pending[4] = {};
    size_t _pendingBytes = 0;
    // VolumeStream scales its input in place. This aligned, reusable buffer
    // keeps the source unchanged and avoids allocations on file transitions.
    alignas(int16_t) uint8_t _buffer[512];

    bool writeOutput(size_t len) {
        // I2S writes block. Abort a short write rather than reapplying volume
        // to an already-scaled remainder or silently continuing with lost PCM.
        return _output.write(_buffer, len) == len;
    }
};

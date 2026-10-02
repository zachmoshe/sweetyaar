#include "SystemSoundOutput.h"
#include "Config.h"
#include <cstring>

namespace {
uint16_t read16(const uint8_t* p) { return uint16_t(p[0]) | (uint16_t(p[1]) << 8); }
uint32_t read32(const uint8_t* p) { return uint32_t(read16(p)) | (uint32_t(read16(p + 2)) << 16); }

// Embedded WAVs need no SD mount, file handles or heap-sized sound buffers.
bool pcmFromWav(SystemSoundAsset asset, const uint8_t*& pcm, uint32_t& frames) {
    if (!asset.data || asset.size < 44 || std::memcmp(asset.data, "RIFF", 4) ||
        std::memcmp(asset.data + 8, "WAVE", 4)) return false;
    const uint64_t end = uint64_t(read32(asset.data + 4)) + 8;
    if (end > asset.size || end < 44) return false;
    bool format = false;
    pcm = nullptr;
    for (size_t pos = 12; pos + 8 <= end;) {
        const uint8_t* chunk = asset.data + pos;
        const uint32_t size = read32(chunk + 4);
        pos += 8;
        if (size > end - pos) return false;
        if (!std::memcmp(chunk, "fmt ", 4)) {
            if (size < 16) return false;
            const uint8_t* fmt = asset.data + pos;
            format = read16(fmt) == 1 && read16(fmt + 2) == 1 &&
                     read32(fmt + 4) == SAMPLE_RATE && read16(fmt + 12) == 2 &&
                     read16(fmt + 14) == 16;
        } else if (!std::memcmp(chunk, "data", 4)) {
            if (!size || size % 2) return false;
            pcm = asset.data + pos;
            frames = size / 2;
        }
        pos += size_t(size) + (size & 1);
    }
    return format && pcm;
}
} // namespace

void SystemSoundOutput::setAudioInfo(audio_tools::AudioInfo info) {
    std::lock_guard<std::mutex> guard(_mutex);
    cfg = info;
    _format.setAudioInfo(info);
}

audio_tools::AudioInfo SystemSoundOutput::audioInfo() {
    std::lock_guard<std::mutex> guard(_mutex);
    return cfg;
}

size_t SystemSoundOutput::write(const uint8_t* data, size_t size) {
    std::lock_guard<std::mutex> guard(_mutex);
    return _active ? size : _output.write(data, size);
}

bool SystemSoundOutput::play(SystemSound sound, SystemSoundAsset asset, uint8_t volumePct) {
    std::lock_guard<std::mutex> guard(_mutex);
    if (sound == SystemSound::None || !volumePct ||
        (_active && unsigned(sound) <= unsigned(_sound))) return false;
    const uint8_t* pcm = nullptr;
    uint32_t frames = 0;
    if (!pcmFromWav(asset, pcm, frames)) return false;
    _sound = sound;
    _pcm = pcm;
    _frames = frames;
    _position = 0;
    _volumePct = volumePct > 100 ? 100 : volumePct;
    // Keep the amplifier on until the last sample has left the existing DMA
    // buffers. These zeros also avoid repeating a nonzero tail during idle.
    _drainFrames = I2S_DMA_BUFFER_COUNT * I2S_DMA_BUFFER_FRAMES;
    _active = true;
    return true;
}

void SystemSoundOutput::cancel() {
    std::lock_guard<std::mutex> guard(_mutex);
    _active = false;
    _sound = SystemSound::None;
}

SystemSoundOutput::Result SystemSoundOutput::service() {
    std::lock_guard<std::mutex> guard(_mutex);
    if (!_active) return Result::Idle;
    if (cfg.channels != 2 || cfg.bits_per_sample != 16 || cfg.sample_rate <= 0) {
        _active = false;
        return Result::Failed;
    }
    // Preserve A2DP's negotiated rate, including 48 kHz. Linear interpolation
    // keeps the cue's pitch/duration without racing Bluetooth format changes.
    const uint64_t step = (uint64_t(SAMPLE_RATE) << 32) / cfg.sample_rate;
    int16_t output[512 * 2];
    size_t count = 0;
    while (count < 512 && ((_position >> 32) < _frames || _drainFrames)) {
        int32_t sample = 0;
        const uint32_t index = _position >> 32;
        if (index < _frames) {
            const int32_t first = int16_t(read16(_pcm + index * 2));
            const int32_t next = index + 1 < _frames ? int16_t(read16(_pcm + (index + 1) * 2)) : first;
            const uint32_t fraction = uint32_t(_position);
            sample = first + ((int64_t(next - first) * fraction) >> 32);
            sample = sample * _volumePct / 100;
            _position += step;
        } else {
            --_drainFrames;
        }
        output[count * 2] = output[count * 2 + 1] = int16_t(sample);
        ++count;
    }
    const size_t bytes = count * 2 * sizeof(int16_t);
    if (_output.write(reinterpret_cast<const uint8_t*>(output), bytes) != bytes) {
        _active = false;
        return Result::Failed;
    }
    if ((_position >> 32) >= _frames && !_drainFrames) {
        _active = false;
        _sound = SystemSound::None;
        return Result::Finished;
    }
    return Result::Playing;
}

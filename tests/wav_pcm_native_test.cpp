#include "WavPcmOutput.h"

#include <algorithm>
#include <cassert>
#include <cstdint>
#include <iostream>
#include <vector>

using namespace audio_tools;

class Sink : public AudioOutput {
public:
    std::vector<uint8_t> bytes;
    size_t limit = 512;
    size_t write(const uint8_t* data, size_t size) override {
        assert(size % 4 == 0);
        assert(size <= 512);
        size = std::min(size, limit);
        bytes.insert(bytes.end(), data, data + size);
        return size;
    }
};

static std::vector<uint8_t> encode(const std::vector<int16_t>& samples) {
    std::vector<uint8_t> bytes;
    for (int16_t sample : samples) {
        bytes.push_back(static_cast<uint16_t>(sample) & 255);
        bytes.push_back(static_cast<uint16_t>(sample) >> 8);
    }
    return bytes;
}

int main() {
    Sink sink;
    VolumeStream volume;
    volume.setOutput(static_cast<Print&>(sink));
    volume.begin(AudioInfo(44100, 2, 16));
    WavPcmOutput output(volume);

    std::vector<int16_t> mono;
    for (int i = 0; i < 1001; ++i) mono.push_back(static_cast<int16_t>((i * 137) % 65536 - 32768));
    mono.insert(mono.end(), {0, 1, -1, 32767, -32768});
    std::vector<int16_t> doubled;
    for (int16_t sample : mono) doubled.insert(doubled.end(), {sample, sample});
    std::vector<int16_t> stereo = doubled;
    for (size_t i = 1; i < stereo.size(); i += 2) stereo[i] = static_cast<int16_t>(i * 11);

    // Include byte-split samples, non-aligned frames, large writes, and repeated
    // mono/stereo switches using the same object and volume configuration.
    for (int channels : {1, 2, 1, 2}) {
        const auto input = encode(channels == 1 ? mono : stereo);
        const auto expected = encode(channels == 1 ? doubled : stereo);
        for (size_t chunk : {1, 2, 3, 17, 511, 2048}) {
            sink.bytes.clear();
            output.setAudioInfo(AudioInfo(44100, channels, 16));
            for (size_t offset = 0; offset < input.size(); offset += chunk) {
                const size_t size = std::min(chunk, input.size() - offset);
                assert(output.write(input.data() + offset, size) == size);
            }
            assert(sink.bytes == expected);
            assert(volume.audioInfo().channels == 2);
            assert(volume.volume(1) == 1.0f);
        }
    }

    // A partial sample must not survive a stopped file or next file's header.
    output.setAudioInfo(AudioInfo(44100, 1, 16));
    assert(output.write(0x7f) == 1);
    output.reset();
    sink.bytes.clear();
    output.setAudioInfo(AudioInfo(44100, 1, 16));
    const auto input = encode({-12345, 23456, -32768});
    assert(output.write(input.data(), input.size()) == input.size());
    assert(sink.bytes == encode({-12345, -12345, 23456, 23456, -32768, -32768}));

    // Conversion must preserve the source and apply volume identically to both
    // channels. Compare against the installed VolumeStream processing stereo.
    volume.setVolume(0.5f);
    auto expected = encode({-12345, -12345, 23456, 23456, -32768, -32768});
    sink.bytes.clear();
    volume.write(expected.data(), expected.size());
    expected = sink.bytes;
    sink.bytes.clear();
    output.setAudioInfo(AudioInfo(44100, 1, 16));
    assert(volume.volume() == 0.5f);
    assert(volume.volume(1) == 0.5f);
    assert(output.write(input.data(), input.size()) == input.size());
    assert(input == encode({-12345, 23456, -32768}));
    assert(sink.bytes == expected);

    for (AudioInfo invalid : {AudioInfo(44100, 0, 16), AudioInfo(44100, 3, 16),
                              AudioInfo(22050, 1, 16), AudioInfo(44100, 1, 24)}) {
        sink.bytes.clear();
        output.setAudioInfo(invalid);
        assert(output.write(input.data(), input.size()) == 0);
        assert(sink.bytes.empty());
    }
    output.setAudioInfo(AudioInfo(44100, 1, 16));
    sink.limit = 4;
    assert(output.write(input.data(), input.size()) == 0);  // caller must stop
    std::cout << "WAV mono/stereo PCM tests passed\n";
}

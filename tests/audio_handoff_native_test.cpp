#include "WavPlayer.h"
#include "AudioTools/CoreAudio/VolumeStream.h"
#include "Config.h"
#include "WavPcmOutput.h"
#include "SystemSoundOutput.h"
#include "SystemSoundOutput.cpp"
#include "ContentCatalog.h"
#include "audio_state.inc"

#include <cassert>
#include <fstream>
#include <iostream>
#include <limits>
#include <string>
#include <vector>

using audio_tools::AudioInfo;
using audio_tools::AudioOutput;
using audio_tools::Print;
using audio_tools::VolumeStream;

bool ampMuted = true;
bool checkMute = false;
class RecordingOutput : public AudioOutput {
public:
    unsigned formatChanges = 0;
    size_t pcmBytes = 0;
    std::vector<uint8_t> pcm;
    size_t writeLimit = std::numeric_limits<size_t>::max();
    void setAudioInfo(AudioInfo info) override {
        if (checkMute) assert(ampMuted);  // reconfigure only while muted
        ++formatChanges;
        AudioOutput::setAudioInfo(info);
    }
    size_t write(const uint8_t* data, size_t count) override {
        assert(audioInfo() == AudioInfo(SAMPLE_RATE, CHANNELS, BITS_PER_SAMPLE));
        count = std::min(count, writeLimit);
        pcmBytes += count;
        pcm.insert(pcm.end(), data, data + count);
        return count;
    }
} i2sOut;
SystemSoundOutput systemAudio(i2sOut);
VolumeStream volumeOut;
WavPlayer wavPlayer(volumeOut);
struct {
    template <typename... T> void printf(T...) {}
    void println(const char*) {}
} firmwareSerial;
String currentPlaybackTheme;
const char* wavPath;
int wavChannels;

namespace ContentCatalog {
#include "wav_inspect.inc"
}

#define Serial firmwareSerial
#include "wav_player.inc"
#undef Serial

void resetI2SOutput(const char*) {
    i2sOut.setAudioInfo(AudioInfo(SAMPLE_RATE, CHANNELS, BITS_PER_SAMPLE));
}
void markActivity(const char*) {}
void updateStatusSignalsForState(State) {}
void scheduleBluetoothReopen(const char*) {}
void setAmpMuted(bool muted) { ampMuted = muted; }
void applyEffectiveVolume(const char*) {}
String bedtimeEffectiveSongTheme() { return "nature"; }
void playSong() {
    assert(!ampMuted);
    const size_t before = i2sOut.pcmBytes;
    std::ifstream original(wavPath, std::ios::binary);
    assert(original);
    FakeSD::files["/test.wav"] = std::string(std::istreambuf_iterator<char>(original), {});
    File file = SD.open("/test.wav");
    const auto info = ContentCatalog::inspectWav(file);
    file.close();
    assert(info.supported && info.channels == wavChannels);
    assert(wavPlayer.openFile("/test.wav"));
    wavPlayer._idle = false;
    for (unsigned tick = 0; !wavPlayer.isIdle() && tick < 100; ++tick) wavPlayer.loop();
    assert(wavPlayer.isIdle());
    assert(volumeOut.audioInfo().channels == 2);
    if (i2sOut.pcmBytes - before != 4097 * 4) {
        std::cerr << "Unexpected decoded size for " << wavChannels << " channels: "
                  << i2sOut.pcmBytes - before << " bytes\n";
    }
    assert(i2sOut.pcmBytes - before == 4097 * 4);
    const auto& source = FakeSD::files["/test.wav"];
    std::vector<uint8_t> expected;
    for (size_t offset = info.dataOffset; offset < info.dataOffset + info.dataBytes; offset += wavChannels * 2) {
        expected.insert(expected.end(), source.begin() + offset, source.begin() + offset + 2);
        const size_t right = offset + (wavChannels == 1 ? 0 : 2);
        expected.insert(expected.end(), source.begin() + right, source.begin() + right + 2);
    }
    assert(std::vector<uint8_t>(i2sOut.pcm.begin() + before, i2sOut.pcm.end()) == expected);
}
void playAnimal() { playSong(); }

#define Serial firmwareSerial
#include "audio_handoff.inc"
#undef Serial

int main(int argc, char** argv) {
    assert(argc == 3);
    setupI2S();
    // Reuse one pipeline across repeated BT sessions, as the device does.
    for (int rate : {48000, 44100, 48000}) {
      for (int channels : {1, 2, 1}) {
        wavPath = argv[channels];
        wavChannels = channels;
        for (State destination : {State::IDLE, State::KILLSWITCH,
                                  State::PLAYING_SONG, State::PLAYING_ANIMAL}) {
            checkMute = false;
            systemAudio.setAudioInfo(AudioInfo(rate, CHANNELS, BITS_PER_SAMPLE));
            const unsigned before = i2sOut.formatChanges;
            handleStateEntry(State::IDLE, State::BT_STREAMING);
            assert(i2sOut.audioInfo().sample_rate == rate);  // preserve BT format
            assert(i2sOut.formatChanges == before);

            checkMute = true;
            handleStateEntry(State::BT_STREAMING, destination);
            assert(i2sOut.audioInfo() == AudioInfo(SAMPLE_RATE, CHANNELS, BITS_PER_SAMPLE));
            if (destination == State::IDLE || destination == State::KILLSWITCH) {
                assert(ampMuted);
                handleStateEntry(destination, State::PLAYING_SONG);
            }
            handleStateEntry(State::PLAYING_SONG, State::IDLE);
        }
      }
    }

    // Read failure after opening a valid file (for example a removed card)
    // must stop cleanly instead of looping forever or playing stale bytes.
    assert(wavPlayer.openFile("/test.wav"));
    wavPlayer._idle = false;
    FakeSD::files["/test.wav"].resize(FakeSD::files["/test.wav"].size() - 100);
    for (unsigned tick = 0; !wavPlayer.isIdle() && tick < 100; ++tick) wavPlayer.loop();
    assert(wavPlayer.isIdle());
    assert(wavPlayer.currentPath().isEmpty());

    // A partial output write also closes the file, and a subsequent valid
    // file can start normally with a different channel count.
    wavPath = argv[2];
    wavChannels = 2;
    ampMuted = false;
    playSong();  // restores complete fixture data
    assert(wavPlayer.openFile("/test.wav"));
    wavPlayer._idle = false;
    i2sOut.writeLimit = 4;
    wavPlayer.loop();
    assert(wavPlayer.isIdle());
    i2sOut.writeLimit = std::numeric_limits<size_t>::max();
    wavPath = argv[1];
    wavChannels = 1;
    playSong();
    std::cout << "audio handoff tests passed\n";
}

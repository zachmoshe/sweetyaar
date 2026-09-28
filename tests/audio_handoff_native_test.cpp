#include "AudioTools/CoreAudio/VolumeStream.h"
#include "AudioTools/AudioCodecs/CodecWAV.h"
#include "Config.h"
#include "audio_state.inc"

#include <cassert>
#include <fstream>
#include <iostream>
#include <string>

using audio_tools::AudioInfo;
using audio_tools::AudioOutput;
using audio_tools::EncodedAudioOutput;
using audio_tools::Print;
using audio_tools::VolumeStream;
using audio_tools::WAVDecoder;
using String = std::string;

bool ampMuted = true;
bool checkMute = false;
class RecordingOutput : public AudioOutput {
public:
    unsigned formatChanges = 0;
    size_t pcmBytes = 0;
    void setAudioInfo(AudioInfo info) override {
        if (checkMute) assert(ampMuted);  // reconfigure only while muted
        ++formatChanges;
        AudioOutput::setAudioInfo(info);
    }
    size_t write(const uint8_t*, size_t count) override {
        assert(audioInfo() == AudioInfo(SAMPLE_RATE, CHANNELS, BITS_PER_SAMPLE));
        pcmBytes += count;
        return count;
    }
} i2sOut;
VolumeStream volumeOut;
WAVDecoder decoder;
EncodedAudioOutput encodedOut(&volumeOut, &decoder);
struct { void stop() { encodedOut.end(); } } wavPlayer;
struct { template <typename... T> void printf(T...) {} } firmwareSerial;
String currentPlaybackTheme;
const char* wavPath;

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
    assert(encodedOut.begin());
    std::ifstream wav(wavPath, std::ios::binary);
    assert(wav);
    char data[1024];
    while (wav) {
        wav.read(data, sizeof(data));
        if (wav.gcount()) encodedOut.write(reinterpret_cast<uint8_t*>(data), wav.gcount());
    }
    assert(decoder.audioInfo() == AudioInfo(SAMPLE_RATE, CHANNELS, BITS_PER_SAMPLE));
    assert(i2sOut.pcmBytes > before);
    encodedOut.end();
}
void playAnimal() { playSong(); }

#define Serial firmwareSerial
#include "audio_handoff.inc"
#undef Serial

int main(int argc, char** argv) {
    assert(argc == 2);
    wavPath = argv[1];
    setupI2S();
    // Reuse one pipeline across repeated BT sessions, as the device does.
    for (int rate : {48000, 44100, 48000}) {
        for (State destination : {State::IDLE, State::KILLSWITCH,
                                  State::PLAYING_SONG, State::PLAYING_ANIMAL}) {
            checkMute = false;
            i2sOut.setAudioInfo(AudioInfo(rate, CHANNELS, BITS_PER_SAMPLE));
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
    std::cout << "audio handoff tests passed\n";
}

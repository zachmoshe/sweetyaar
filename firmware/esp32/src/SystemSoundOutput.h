#pragma once

#include <atomic>
#include <mutex>
#include "AudioTools/CoreAudio/AudioOutput.h"

enum class SystemSound : uint8_t { None, Ready, Pairing, Error };

struct SystemSoundAsset {
    const uint8_t* data;
    size_t size;
};

SystemSoundAsset systemSoundAsset(SystemSound sound);
const char* systemSoundName(SystemSound sound);

// Shared speaker output. A short flash-resident cue temporarily replaces other
// audio; Bluetooth keeps consuming its queue and never accumulates stale music.
// The main loop pauses SD feeding while active(), then resumes at the same sample.
class SystemSoundOutput : public audio_tools::AudioOutput {
public:
    template <typename Output>
    explicit SystemSoundOutput(Output& output) : _output(output), _format(output) {}

    enum class Result { Idle, Playing, Finished, Failed };
    bool play(SystemSound sound, SystemSoundAsset asset, uint8_t volumePct);
    Result service();
    bool active() const { return _active.load(); }
    void cancel();

    void setAudioInfo(audio_tools::AudioInfo info) override;
    audio_tools::AudioInfo audioInfo() override;
    size_t write(const uint8_t* data, size_t size) override;
    size_t write(uint8_t byte) override { return write(&byte, 1); }

private:
#ifdef ARDUINO
    Print& _output;
#else
    audio_tools::Print& _output;
#endif
    audio_tools::AudioInfoSupport& _format;
    std::mutex _mutex;
    std::atomic<bool> _active{false};
    SystemSound _sound = SystemSound::None;
    const uint8_t* _pcm = nullptr;
    uint32_t _frames = 0;
    uint64_t _position = 0; // source frame index in 32.32 fixed point
    uint32_t _drainFrames = 0;
    uint8_t _volumePct = 0;
};

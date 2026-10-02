#include "SystemSoundOutput.h"
#include "Config.h"
#include "PairingPolicy.h"
#include "SystemSoundOutput.cpp"
#include <cassert>
#include <fstream>
#include <iostream>
#include <limits>
#include <thread>
#include <vector>

using audio_tools::AudioInfo;
class RecordingOutput : public audio_tools::AudioOutput {
public:
    std::vector<uint8_t> data;
    size_t limit = std::numeric_limits<size_t>::max();
    size_t write(const uint8_t* bytes, size_t size) override {
        size = std::min(size, limit);
        data.insert(data.end(), bytes, bytes + size);
        return size;
    }
};

bool systemSoundsReady = false;
bool systemErrorReported = false;
enum class StatusSignal { Error, Pairing, PairingReset };
struct { void setSignal(StatusSignal, bool) {} } statusLed;
std::vector<SystemSound> requests;
void playSystemSound(SystemSound sound) { requests.push_back(sound); }
#include "sound_events.inc"

namespace pairing_schedule {
uint32_t now = 0;
uint32_t millis() { return now; }
PairingPolicy pairingPolicy;
struct {
    bool held = false, released = true;
    bool isBothHeld() { return held; }
    bool areBothReleased() { return released; }
} buttons;
struct {
    bool ready = true, open = false;
    uint32_t openedAt = 0;
    void openPairing(uint32_t at) { openedAt = at; open = ready; }
    void closePairing() { open = false; }
    bool pairingOpen() { return ready && open && now - openedAt < PairingPolicy::WINDOW_MS; }
    bool forgetBonds() { closePairing(); return true; }
} bluetoothAccess;
struct Sink {
    void refreshAccess() {}
    void revokeSession() {}
} sink, *btSink = &sink;
bool btReopenPending = false;
struct { void disconnectAll() {} } bleService;
struct { void println(const char*) {} } Serial;
void markActivity(const char*) {}
#include "pairing_events.inc"

void tick(uint32_t at, bool held = false) {
    now = at;
    buttons.held = held;
    buttons.released = !held;
    pollBluetoothPairing();
}

void test() {
    requests.clear();
    tick(0);
    tick(15000);
    assert(requests.empty()); // closed at boot
    tick(16000, true);
    tick(19000, true); // open after the three-second gesture
    assert(requests.size() == 1 && requests.back() == SystemSound::Pairing);
    tick(19001);
    for (unsigned repeat = 1; repeat <= 3; ++repeat) {
        tick(19000 + repeat * 15000 - 1);
        assert(requests.size() == repeat);
        tick(19000 + repeat * 15000);
        tick(19000 + repeat * 15000); // no duplicate in the same tick
        assert(requests.size() == repeat + 1);
    }
    tick(78999);
    tick(79000); // timeout wins over a fourth repeat
    tick(100000);
    assert(requests.size() == 4 && !bluetoothAccess.pairingOpen());

    tick(110000, true);
    tick(113000, true);
    tick(113001);
    tick(120000, true);
    tick(123000, true); // reopen restarts the sound interval
    assert(requests.size() == 6);
    tick(128000); // would have been due for the previous window
    tick(137999);
    assert(requests.size() == 6);
    tick(138000);
    assert(requests.size() == 7);
    tick(153000, true);
    tick(156000, true);
    assert(requests.size() == 9); // due repeat, then a fresh window
    tick(163000, true); // ten-second hold clears bonds and closes pairing
    tick(171000, true);
    assert(requests.size() == 9 && !bluetoothAccess.pairingOpen());
    tick(172000);

    const uint32_t start = 0xfffff000;
    tick(start, true);
    tick(start + 3000, true);
    assert(requests.size() == 10);
    for (unsigned repeat = 1; repeat <= 3; ++repeat) {
        tick(start + 3000 + repeat * 15000 - 1);
        assert(requests.size() == 9 + repeat);
        tick(start + 3000 + repeat * 15000);
        assert(requests.size() == 10 + repeat);
    }
    tick(start + 63000);
    assert(requests.size() == 13 && !bluetoothAccess.pairingOpen());

    bluetoothAccess.ready = false; // migration/reset can refuse to open
    tick(100000, true);
    tick(103000, true);
    tick(118000);
    assert(requests.size() == 13);
}
} // namespace pairing_schedule

std::vector<uint8_t> read(const char* path) {
    std::ifstream file(path, std::ios::binary);
    assert(file);
    return {std::istreambuf_iterator<char>(file), {}};
}

void complete(SystemSoundOutput& player) {
    unsigned ticks = 0;
    while (player.active()) {
        assert(player.service() != SystemSoundOutput::Result::Failed);
        assert(++ticks < 200);
    }
}

int main(int argc, char** argv) {
    assert(argc == 5);
    RecordingOutput sink;
    SystemSoundOutput player(sink);
    player.setAudioInfo(AudioInfo(44100, 2, 16));
    const std::vector<uint8_t> music{1, 2, 3, 4, 5, 6, 7, 8};
    assert(player.write(music.data(), music.size()) == music.size());
    assert(sink.data == music);
    const size_t tail = I2S_DMA_BUFFER_COUNT * I2S_DMA_BUFFER_FRAMES;

    // Render every actual embedded asset without any filesystem/SD abstraction
    // inside the player. Exact PCM duplication includes the last source frame.
    for (int assetIndex = 1; assetIndex < argc; ++assetIndex) {
        const auto wav = read(argv[assetIndex]);
        assert(wav.size() >= 44 && wav[36] == 'd');
        const SystemSoundAsset asset{wav.data(), wav.size()};
        for (int pct : {25, 100}) {
            sink.data.clear();
            assert(player.play(SystemSound::Ready, asset, pct));
            assert(!player.play(SystemSound::Ready, asset, pct)); // no repeated restart
            assert(player.write(music.data(), music.size()) == music.size());
            assert(sink.data.empty()); // BT consumed but not mixed into the cue
            complete(player);
            const size_t frames = (wav.size() - 44) / 2;
            assert(sink.data.size() == (frames + tail) * 4);
            for (size_t frame = 0; frame < frames; ++frame) {
                const size_t offset = 44 + 2 * frame;
                int16_t original = int16_t(uint16_t(wav[offset]) | uint16_t(wav[offset + 1]) << 8);
                int16_t expected = int32_t(original) * pct / 100;
                int16_t left, right;
                memcpy(&left, sink.data.data() + frame * 4, 2);
                memcpy(&right, sink.data.data() + frame * 4 + 2, 2);
                assert(left == expected && right == expected);
            }
            for (size_t byte = frames * 4; byte < sink.data.size(); ++byte) assert(sink.data[byte] == 0);
            assert(player.service() == SystemSoundOutput::Result::Idle);
            assert(player.write(music.data(), music.size()) == music.size());
            assert(std::equal(music.begin(), music.end(), sink.data.end() - music.size()));
        }
        sink.data.clear();
        player.setAudioInfo(AudioInfo(48000, 2, 16));
        assert(player.play(SystemSound::Pairing, asset, 100));
        complete(player);
        assert(player.audioInfo().sample_rate == 48000 && sink.audioInfo().sample_rate == 48000);
        const double sourceFrames = (wav.size() - 44) / 2;
        const double renderedFrames = sink.data.size() / 4 - tail;
        assert(std::abs(renderedFrames - sourceFrames * 48000 / 44100) <= 1.01);
        for (size_t i = 0; i < sink.data.size(); i += 4) {
            assert(sink.data[i] == sink.data[i + 2] && sink.data[i + 1] == sink.data[i + 3]);
        }
        player.setAudioInfo(AudioInfo(44100, 2, 16));
    }

    const auto wav = read(argv[2]);
    const SystemSoundAsset asset{wav.data(), wav.size()};
    // A2DP writes from another task while loop() feeds the cue. They must be
    // consumed without interleaving music bytes into the sound or its DMA tail.
    sink.data.clear();
    assert(player.play(SystemSound::Pairing, asset, 100));
    std::atomic<bool> running{true}, writerStarted{false};
    std::thread bluetooth([&] {
        while (running) {
            assert(player.write(music.data(), music.size()) == music.size());
            writerStarted = true;
            std::this_thread::yield();
        }
    });
    while (!writerStarted) std::this_thread::yield();
    complete(player);
    running = false;
    bluetooth.join();
    const size_t realFrames = (wav.size() - 44) / 2;
    for (size_t frame = 0; frame < realFrames; ++frame) {
        assert(sink.data[frame * 4] == wav[44 + frame * 2]);
        assert(sink.data[frame * 4 + 1] == wav[45 + frame * 2]);
    }
    for (size_t byte = realFrames * 4; byte < (realFrames + tail) * 4; ++byte) assert(sink.data[byte] == 0);

    assert(!player.play(SystemSound::Ready, asset, 0)); // respect mute
    assert(!player.active());
    assert(!player.play(SystemSound::Ready, {wav.data(), 43}, 50));
    assert(!player.play(SystemSound::Ready, {wav.data(), wav.size() - 1}, 50));
    auto invalid = wav;
    invalid[22] = 2; // cue input must be mono
    assert(!player.play(SystemSound::Ready, {invalid.data(), invalid.size()}, 50));
    assert(player.play(SystemSound::Ready, asset, 50));
    assert(player.play(SystemSound::Pairing, asset, 50));
    assert(!player.play(SystemSound::Ready, asset, 50));
    assert(player.play(SystemSound::Error, asset, 50));
    assert(!player.play(SystemSound::Pairing, asset, 50));
    player.service();
    player.setAudioInfo(AudioInfo(48000, 2, 16)); // BT negotiates while cue is active
    player.service();
    player.setAudioInfo(AudioInfo(44100, 2, 16)); // disconnect during the same cue
    complete(player);

    assert(player.play(SystemSound::Ready, asset, 50));
    sink.limit = 4;
    assert(player.service() == SystemSoundOutput::Result::Failed);
    assert(!player.active());
    sink.limit = std::numeric_limits<size_t>::max();
    assert(player.play(SystemSound::Ready, asset, 50));
    player.cancel();
    assert(!player.active());
    assert(player.write(music.data(), music.size()) == music.size());

    finishSystemSoundStartup();
    finishSystemSoundStartup();
    assert((requests == std::vector<SystemSound>{SystemSound::Ready}));
    reportSystemError();
    reportSystemError();
    assert((requests == std::vector<SystemSound>{SystemSound::Ready, SystemSound::Error}));
    systemSoundsReady = systemErrorReported = false;
    requests.clear();
    reportSystemError(); // SD/config failure before startup completes
    reportSystemError();
    assert(requests.empty());
    finishSystemSoundStartup();
    reportSystemError();
    assert((requests == std::vector<SystemSound>{SystemSound::Error}));
    pairing_schedule::test();
    std::cout << "system sound tests passed\n";
}

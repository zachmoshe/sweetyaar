#pragma once
#include <Arduino.h>
#include <SD.h>
#include <SPI.h>
#include <ArduinoJson.h>
#include "AudioTools.h"
#include "Config.h"

// ---------------------------------------------------------------------------
// WavPlayer — plays WAV files from SD card through a shared VolumeStream
//
// Design: we manage our own file list and open SD files directly.
// A WAVDecoder is fed raw file bytes each loop(); decoded PCM flows into
// the shared VolumeStream → I2SStream → MAX98357A.
//
// Two modes:
//   Song mode   — sequential (or shuffled) WAV files from a theme folder
//   Animal mode — sequential/shuffled WAV files from /animals/, plays one then stops
//
// Usage:
//   WavPlayer player(volumeStream);
//   player.begin();                    // after SD.begin()
//   player.startSong("lullabies");
//   player.nextSong();
//   player.startRandomAnimal();
//   player.stop();
//   player.loop();                     // MUST be called every loop iteration
//   bool done = player.isIdle();
// ---------------------------------------------------------------------------

class WavPlayer {
public:
    explicit WavPlayer(VolumeStream& output);

    // Open SD card; returns false if SD.begin() fails
    bool begin();

    // Start sequential/shuffled playback from /songs/<theme>/
    void startSong(const String& theme);

    // Advance to next song (stays in song mode)
    void nextSong();

    // Start an animal pass and play one file from /animals/
    void startRandomAnimal();

    // Advance to the next animal sound (stays in animal mode)
    void nextAnimal();

    // Stop immediately and free resources
    void stop();

    bool isIdle()          const { return _idle; }
    bool isPlayingSong()   const { return !_idle && !_animalMode; }
    bool isPlayingAnimal() const { return !_idle &&  _animalMode; }
    String currentPath()   const { return _currentPath; }

    // Feed PCM data to I2S — MUST be called every loop() iteration
    void loop();

    // Update volume (0.0–1.0) on the shared VolumeStream
    void setVolume(float v) { _output.setVolume(v); }

    // List playable song themes from the in-RAM catalog; fills sorted id/name arrays
    static int listThemes(String* outIds, String* outNames, int maxThemes);

    // Build the BLE theme-list JSON value, capped to a complete-entry byte limit
    static String buildThemesJson(const String* ids, const String* names,
                                  int count, size_t maxBytes);

private:
    static constexpr int CHUNK_BYTES = 2048;
    static constexpr int MAX_SONGS   = 64;
    static constexpr int MAX_ANIMALS = 32;

    VolumeStream&       _output;
    // Decode pipeline (WAVDecoder -> VolumeStream). Allocated once via
    // ensureDecoder() and reused for every file; per-file state is reset with
    // begin()/end() rather than reallocating, to avoid heap fragmentation.
    WAVDecoder*         _wavDecoder = nullptr;
    EncodedAudioOutput* _encodedOut = nullptr;
    File                _sdFile;
    String              _currentPath;

    bool _idle       = true;
    bool _animalMode = false;

    // Song list built on startSong()
    String _songFiles[MAX_SONGS];
    int    _songOrder[MAX_SONGS];  // permuted or identity
    int    _songCount  = 0;
    int    _songCursor = 0;        // index into _songOrder

    String _animalFiles[MAX_ANIMALS];
    int    _animalOrder[MAX_ANIMALS];
    int    _animalCount  = 0;
    int    _animalCursor = 0;     // index into _animalOrder

    void buildSongList(const String& theme, bool shuffle);
    void buildAnimalList();
    void shuffleOrder(int* order, int count);
    bool openCurrentSong();
    bool openCurrentAnimal();
    bool openFile(const String& path);
    void teardown();

    // Allocate the decode pipeline exactly once; returns false on alloc failure.
    bool ensureDecoder();
};

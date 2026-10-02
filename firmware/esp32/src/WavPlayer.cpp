#include "WavPlayer.h"
#include "ContentCatalog.h"
#include <SPI.h>


// ---------------------------------------------------------------------------
WavPlayer::WavPlayer(VolumeStream& output) : _output(output), _pcmOutput(output) {}

// ---------------------------------------------------------------------------
bool WavPlayer::begin() {
    SPI.begin(PIN_SD_SCK, PIN_SD_MISO, PIN_SD_MOSI, PIN_SD_CS);
    if (!SD.begin(PIN_SD_CS, SPI, SD_SPI_FREQUENCY_HZ, "/sd", SD_MAX_OPEN_FILES)) {
        Serial.println("[WavPlayer] SD init failed");
        return false;
    }
    Serial.printf("[WavPlayer] SD OK (SPI %lu MHz)\n",
                  static_cast<unsigned long>(SD_SPI_FREQUENCY_HZ / 1000000UL));
    return true;
}

// ---------------------------------------------------------------------------
void WavPlayer::startSong(const String& theme) {
    stop();

    const ContentCatalog::CachedTheme* t = ContentCatalog::findTheme(theme);
    bool shuffle = t ? t->shuffle : false;

    buildSongList(theme, shuffle);
    if (_songCount == 0) {
        Serial.printf("[WavPlayer] No playable songs in theme %s\n", theme.c_str());
        return;
    }

    _animalMode = false;
    _idle       = false;
    _songCursor = 0;
    openCurrentSong();
}

// ---------------------------------------------------------------------------
void WavPlayer::nextSong() {
    if (_songCount == 0) return;
    stop();
    _songCursor = (_songCursor + 1) % _songCount;
    _idle       = false;
    _animalMode = false;
    openCurrentSong();
}

// ---------------------------------------------------------------------------
void WavPlayer::startRandomAnimal() {
    stop();
    buildAnimalList();
    if (_animalCount == 0) {
        Serial.println("[WavPlayer] No animal sounds");
        return;
    }
    _animalMode = true;
    _idle       = false;
    _animalCursor = 0;
    openCurrentAnimal();
}

// ---------------------------------------------------------------------------
void WavPlayer::nextAnimal() {
    if (_animalCount == 0) {
        startRandomAnimal();
        return;
    }
    stop();
    _animalCursor = (_animalCursor + 1) % _animalCount;
    if (_animalCursor == 0) {
        shuffleOrder(_animalOrder, _animalCount);
    }
    _idle       = false;
    _animalMode = true;
    openCurrentAnimal();
}

// ---------------------------------------------------------------------------
void WavPlayer::stop() {
    teardown();
    _idle       = true;
    _animalMode = false;
}

// ---------------------------------------------------------------------------
bool WavPlayer::sdAvailable() {
    File root = SD.open("/");
    bool ok = root && root.isDirectory();
    if (root) root.close();
    return ok;
}

// ---------------------------------------------------------------------------
void WavPlayer::refreshSongList(const String& theme) {
    if (_idle || _animalMode) return;  // only relevant while a song is playing

    const String current = _currentPath;
    const ContentCatalog::CachedTheme* t = ContentCatalog::findTheme(theme);
    bool shuffle = t ? t->shuffle : false;
    buildSongList(theme, shuffle);     // rebuilt from cache; excludes disabled songs

    // Anchor the cursor on the song still playing so "next" advances from here.
    // If it was the one just disabled it won't be found; the cursor stays at 0
    // and the current file simply finishes before a valid one is chosen.
    _songCursor = 0;
    for (int i = 0; i < _songCount; i++) {
        if (_songFiles[_songOrder[i]] == current) {
            _songCursor = i;
            break;
        }
    }
}

// ---------------------------------------------------------------------------
// loop() — feed up to CHUNK_BYTES of WAV data per call; detect end-of-file
// ---------------------------------------------------------------------------
void WavPlayer::loop() {
    if (_idle || !_sdFile) return;

    if (_remainingPcmBytes > 0) {
        uint8_t buf[CHUNK_BYTES];
        const size_t count = _remainingPcmBytes < sizeof(buf) ? _remainingPcmBytes : sizeof(buf);
        const size_t n = _sdFile.read(buf, count);
        if (n != count) {
            Serial.println("[WavPlayer] Cannot read complete PCM block");
            stop();
            return;
        }
        _remainingPcmBytes -= n;
        if (_pcmOutput.write(buf, n) != n) {
            Serial.println("[WavPlayer] Audio output write failed");
            stop();
        }
    } else {
        // One button press plays one file. StateMachine observes WAV_FINISHED;
        // advancing to another song/animal is an explicit button action.
        stop();
    }
}

// ---------------------------------------------------------------------------
// Private: inspect an SD WAV, then stream only its validated PCM data section
// ---------------------------------------------------------------------------
bool WavPlayer::openCurrentSong() {
    for (int attempts = 0; attempts < _songCount; attempts++) {
        if (openFile(_songFiles[_songOrder[_songCursor]])) {
            return true;
        }
        _songCursor = (_songCursor + 1) % _songCount;
    }

    Serial.println("[WavPlayer] No playable song files");
    _idle = true;
    return false;
}

// ---------------------------------------------------------------------------
bool WavPlayer::openCurrentAnimal() {
    for (int attempts = 0; attempts < _animalCount; attempts++) {
        if (openFile(_animalFiles[_animalOrder[_animalCursor]])) {
            return true;
        }
        _animalCursor = (_animalCursor + 1) % _animalCount;
        if (_animalCursor == 0) {
            shuffleOrder(_animalOrder, _animalCount);
        }
    }

    Serial.println("[WavPlayer] No playable animal files");
    _idle = true;
    return false;
}

// ---------------------------------------------------------------------------
bool WavPlayer::openFile(const String& path) {
    teardown();  // ensure clean state

    _sdFile = SD.open(path.c_str());
    if (!_sdFile) {
        _currentPath = "";
        Serial.printf("[WavPlayer] Cannot open: %s\n", path.c_str());
        return false;
    }

    ContentCatalog::WavInfo wavInfo = ContentCatalog::inspectWav(_sdFile);
    if (wavInfo.sizeBytes < 44) {
        Serial.printf("[WavPlayer] Skipping too-small WAV: %s (%u bytes)\n",
                      path.c_str(), static_cast<unsigned>(_sdFile.size()));
        _sdFile.close();
        _currentPath = "";
        return false;
    }
    if (!wavInfo.valid) {
        Serial.printf("[WavPlayer] Skipping invalid WAV: %s (%u bytes)\n",
                      path.c_str(), static_cast<unsigned>(_sdFile.size()));
        _sdFile.close();
        _currentPath = "";
        return false;
    }
    if (!wavInfo.supported) {
        Serial.printf("[WavPlayer] Skipping unsupported WAV: %s (format=%u rate=%lu channels=%u bits=%u)\n",
                      path.c_str(), wavInfo.audioFormat,
                      static_cast<unsigned long>(wavInfo.sampleRate),
                      wavInfo.channels, wavInfo.bitsPerSample);
        _sdFile.close();
        _currentPath = "";
        return false;
    }

    if (!_sdFile.seek(wavInfo.dataOffset)) {
        Serial.printf("[WavPlayer] Cannot seek to WAV data: %s\n", path.c_str());
        _sdFile.close();
        _currentPath = "";
        return false;
    }
    _pcmOutput.setAudioInfo(AudioInfo(wavInfo.sampleRate, wavInfo.channels, wavInfo.bitsPerSample));
    _remainingPcmBytes = wavInfo.dataBytes;

    _currentPath = path;
    Serial.printf("[WavPlayer] Playing: %s\n", path.c_str());
    return true;
}

// ---------------------------------------------------------------------------
void WavPlayer::teardown() {
    if (_sdFile)     { _sdFile.close(); }
    _remainingPcmBytes = 0;
    _pcmOutput.reset();
    _currentPath = "";
}

// ---------------------------------------------------------------------------
void WavPlayer::buildSongList(const String& theme, bool shuffle) {
    _songCount = 0;
    const ContentCatalog::CachedTheme* t = ContentCatalog::findTheme(theme);
    if (t != nullptr) {
        String base = String(SONGS_ROOT) + "/" + theme + "/";
        for (const ContentCatalog::CachedSong& s : t->songs) {
            if (_songCount >= MAX_SONGS) break;
            if (s.supported && !s.disabled) {
                _songFiles[_songCount++] = base + s.file;
            }
        }
    }

    for (int i = 0; i < _songCount; i++) _songOrder[i] = i;
    if (shuffle) {
        shuffleOrder(_songOrder, _songCount);
    }
}

// ---------------------------------------------------------------------------
void WavPlayer::buildAnimalList() {
    _animalCount = 0;
    const ContentCatalog::CachedTheme* t = ContentCatalog::findTheme(ANIMALS_THEME_ID);
    bool shuffle = t ? t->shuffle : true;
    if (t != nullptr) {
        String base = String(ANIMALS_PATH) + "/";
        for (const ContentCatalog::CachedSong& s : t->songs) {
            if (_animalCount >= MAX_ANIMALS) break;
            if (s.supported && !s.disabled) {
                _animalFiles[_animalCount++] = base + s.file;
            }
        }
    }

    for (int i = 0; i < _animalCount; i++) _animalOrder[i] = i;
    if (shuffle) {
        shuffleOrder(_animalOrder, _animalCount);
    }
}

// ---------------------------------------------------------------------------
void WavPlayer::shuffleOrder(int* order, int count) {
    for (int i = count - 1; i > 0; i--) {
        int j = random(i + 1);
        int tmp  = order[i];
        order[i] = order[j];
        order[j] = tmp;
    }
}

// ---------------------------------------------------------------------------
// static — playable song themes for the BLE play controls, served from the
// in-RAM catalog (themes are already sorted by id). Excludes the special
// Animals theme, parent-disabled themes, and themes with nothing to play.
int WavPlayer::listThemes(String* outIds, String* outNames, int maxThemes) {
    if (maxThemes <= 0) return 0;

    int count = 0;
    int total = ContentCatalog::themeCount();
    for (int i = 0; i < total; i++) {
        const ContentCatalog::CachedTheme& t = ContentCatalog::themeAt(i);
        if (t.special || t.disabledByUser || t.playableCount() == 0) {
            continue;
        }
        if (count >= maxThemes) {
            Serial.printf("[WavPlayer] Theme list reached firmware cap (%d); extra themes ignored\n",
                          maxThemes);
            break;
        }
        outIds[count] = t.id;
        outNames[count] = t.name;
        count++;
    }
    return count;
}

// ---------------------------------------------------------------------------
// static
String WavPlayer::buildThemesJson(const String* ids, const String* names,
                                  int count, size_t maxBytes) {
    String json = "[";
    bool truncated = false;

    for (int i = 0; i < count; i++) {
        String entry = "{\"id\":\"" + ContentCatalog::jsonEscape(ids[i]) +
                       "\",\"name\":\"" + ContentCatalog::jsonEscape(names[i]) + "\"}";
        size_t commaBytes = (json.length() > 1) ? 1 : 0;
        size_t projected = json.length() + commaBytes + entry.length() + 1;
        if (projected > maxBytes) {
            truncated = true;
            break;
        }
        if (commaBytes) json += ",";
        json += entry;
    }

    json += "]";
    if (truncated) {
        Serial.printf("[WavPlayer] BLE theme list truncated to %u bytes\n",
                      static_cast<unsigned>(json.length()));
    }
    return json;
}

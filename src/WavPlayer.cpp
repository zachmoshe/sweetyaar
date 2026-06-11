#include "WavPlayer.h"
#include "ContentCatalog.h"

namespace {

String jsonEscape(const String& input) {
    String out;
    out.reserve(input.length() + 8);
    static const char* hex = "0123456789ABCDEF";

    for (size_t i = 0; i < input.length(); i++) {
        unsigned char c = static_cast<unsigned char>(input[i]);
        switch (c) {
            case '"':  out += "\\\""; break;
            case '\\': out += "\\\\"; break;
            case '\b': out += "\\b";  break;
            case '\f': out += "\\f";  break;
            case '\n': out += "\\n";  break;
            case '\r': out += "\\r";  break;
            case '\t': out += "\\t";  break;
            default:
                if (c < 0x20) {
                    out += "\\u00";
                    out += hex[c >> 4];
                    out += hex[c & 0x0F];
                } else {
                    out += static_cast<char>(c);
                }
                break;
        }
    }

    return out;
}

}  // namespace

// ---------------------------------------------------------------------------
WavPlayer::WavPlayer(VolumeStream& output) : _output(output) {}

// ---------------------------------------------------------------------------
bool WavPlayer::begin() {
    SPI.begin(PIN_SD_SCK, PIN_SD_MISO, PIN_SD_MOSI, PIN_SD_CS);
    if (!SD.begin(PIN_SD_CS, SPI, 4000000)) {
        Serial.println("[WavPlayer] SD init failed");
        return false;
    }
    Serial.println("[WavPlayer] SD OK");
    // Claim the decode pipeline up-front, before SD/WAV traffic fragments the
    // heap (same rationale as reserving the BT audio queue early).
    ensureDecoder();
    return true;
}

// ---------------------------------------------------------------------------
bool WavPlayer::ensureDecoder() {
    if (_encodedOut != nullptr) {
        return true;
    }
    _wavDecoder = new WAVDecoder();
    _encodedOut = new EncodedAudioOutput(&_output, _wavDecoder);
    if (_wavDecoder == nullptr || _encodedOut == nullptr) {
        Serial.println("[WavPlayer] Decode pipeline allocation failed");
        return false;
    }
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
// loop() — feed up to CHUNK_BYTES of WAV data per call; detect end-of-file
// ---------------------------------------------------------------------------
void WavPlayer::loop() {
    if (_idle || !_encodedOut || !_sdFile) return;

    if (_sdFile.available()) {
        uint8_t buf[CHUNK_BYTES];
        int n = _sdFile.read(buf, CHUNK_BYTES);
        if (n > 0) {
            _encodedOut->write(buf, n);
        }
    } else {
        // File exhausted
        if (_animalMode) {
            stop();
            // Caller (StateMachine) detects isIdle() → WAV_FINISHED event
        } else {
            // One button press should play exactly one song. Advancing to the
            // next song is an explicit button action handled by nextSong().
            stop();
        }
    }
}

// ---------------------------------------------------------------------------
// Private: open an SD file and wire it through a fresh WAVDecoder
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

    if (!ensureDecoder()) {
        _sdFile.close();
        _currentPath = "";
        return false;
    }
    // Reuse the persistent decoder; begin() resets per-file state (the library
    // requires begin() before each new WAV) so no reallocation is needed.
    _encodedOut->begin();

    _currentPath = path;
    Serial.printf("[WavPlayer] Playing: %s\n", path.c_str());
    return true;
}

// ---------------------------------------------------------------------------
void WavPlayer::teardown() {
    if (_sdFile)     { _sdFile.close(); }
    // Reset the decoder for the next file but keep it allocated for reuse.
    // The pipeline is intentionally never freed (WavPlayer is a lifetime-long
    // singleton); end() returns it to an inactive, ready-to-begin() state.
    if (_encodedOut) { _encodedOut->end(); }
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
        String entry = "{\"id\":\"" + jsonEscape(ids[i]) +
                       "\",\"name\":\"" + jsonEscape(names[i]) + "\"}";
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

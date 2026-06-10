#include "WavPlayer.h"
#include "ContentCatalog.h"

namespace {

String baseNameOf(const String& path) {
    int slash = path.lastIndexOf('/');
    if (slash < 0) return path;
    return path.substring(slash + 1);
}

bool isIgnoredFilesystemEntry(const String& name) {
    String base = baseNameOf(name);
    String lower = base;
    lower.toLowerCase();

    if (lower.length() == 0) {
        return true;
    }

    // macOS AppleDouble/resource-fork files and Unix hidden editor/temp files.
    if (lower.startsWith(".") || lower.startsWith("._")) {
        return true;
    }
    if (lower.endsWith("~")) {
        return true;
    }

    static const char* const ignoredExact[] = {
        // macOS
        ".ds_store",
        ".spotlight-v100",
        ".trashes",
        ".fseventsd",
        ".temporaryitems",
        ".appledouble",
        ".apdisk",
        ".documentrevisions-v100",
        ".volumeicon.icns",
        ".metadata_never_index",
        ".com.apple.timemachine.donotpresent",
        "icon\r",

        // Windows
        "thumbs.db",
        "ehthumbs.db",
        "desktop.ini",
        "$recycle.bin",
        "recycler",
        "recycled",
        "system volume information",

        // Linux / desktop environments / FAT repair folders
        ".trash",
        ".directory",
        "lost+found",
        "found.000",
        "found.001",
    };

    for (size_t i = 0; i < sizeof(ignoredExact) / sizeof(ignoredExact[0]); i++) {
        if (lower == ignoredExact[i]) {
            return true;
        }
    }

    return lower.startsWith(".trash-") || lower.startsWith(".nfs");
}

uint16_t le16(const uint8_t* p) {
    return static_cast<uint16_t>(p[0]) | (static_cast<uint16_t>(p[1]) << 8);
}

uint32_t le32(const uint8_t* p) {
    return static_cast<uint32_t>(p[0]) |
           (static_cast<uint32_t>(p[1]) << 8) |
           (static_cast<uint32_t>(p[2]) << 16) |
           (static_cast<uint32_t>(p[3]) << 24);
}

struct WavInfo {
    bool valid = false;
    bool supported = false;
    uint16_t audioFormat = 0;
    uint16_t channels = 0;
    uint32_t sampleRate = 0;
    uint16_t bitsPerSample = 0;
};

WavInfo readWavInfo(File& entry) {
    WavInfo info;
    if (entry.size() < 44) {
        return info;
    }

    uint8_t h[44];
    size_t n = entry.read(h, sizeof(h));
    entry.seek(0);

    info.valid = n == sizeof(h) &&
                 h[0] == 'R' && h[1] == 'I' && h[2] == 'F' && h[3] == 'F' &&
                 h[8] == 'W' && h[9] == 'A' && h[10] == 'V' && h[11] == 'E' &&
                 h[12] == 'f' && h[13] == 'm' && h[14] == 't' && h[15] == ' ';
    if (!info.valid) {
        return info;
    }

    info.audioFormat = le16(h + 20);
    info.channels = le16(h + 22);
    info.sampleRate = le32(h + 24);
    info.bitsPerSample = le16(h + 34);
    info.supported = info.audioFormat == 1 &&
                     info.channels == CHANNELS &&
                     info.sampleRate == SAMPLE_RATE &&
                     info.bitsPerSample == BITS_PER_SAMPLE;
    return info;
}

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

void sortThemes(String* ids, String* names, int count) {
    for (int i = 1; i < count; i++) {
        String id = ids[i];
        String name = names[i];
        int j = i - 1;
        while (j >= 0 && ids[j].compareTo(id) > 0) {
            ids[j + 1] = ids[j];
            names[j + 1] = names[j];
            j--;
        }
        ids[j + 1] = id;
        names[j + 1] = name;
    }
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
    String dir = String(SONGS_ROOT) + "/" + theme;

    JsonDocument meta = readMetadata(dir);
    bool shuffle = meta["shuffle"] | false;

    buildSongList(dir, shuffle);
    if (_songCount == 0) {
        Serial.printf("[WavPlayer] No WAV in %s\n", dir.c_str());
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
void WavPlayer::buildSongList(const String& themePath, bool shuffle) {
    _songCount = listWavFiles(themePath.c_str(), _songFiles, MAX_SONGS);

    for (int i = 0; i < _songCount; i++) _songOrder[i] = i;

    if (shuffle) {
        shuffleOrder(_songOrder, _songCount);
    }
}

// ---------------------------------------------------------------------------
void WavPlayer::buildAnimalList() {
    JsonDocument meta = readMetadata(ANIMALS_PATH);
    bool shuffle = meta["shuffle"] | true;

    _animalCount = listWavFiles(ANIMALS_PATH, _animalFiles, MAX_ANIMALS);
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
// static
int WavPlayer::listWavFiles(const char* dirPath, String* outFiles, int maxFiles) {
    File dir = SD.open(dirPath);
    if (!dir || !dir.isDirectory()) return 0;

    JsonDocument meta = ContentCatalog::readThemeMetadata(String(dirPath));
    int count = 0;
    while (count < maxFiles) {
        File entry = dir.openNextFile();
        if (!entry) break;
        String originalName = ContentCatalog::baseNameOf(String(entry.name()));
        if (ContentCatalog::isIgnoredFilesystemEntry(originalName)) {
            entry.close();
            continue;
        }
        if (!entry.isDirectory()) {
            String lowerName(originalName);
            lowerName.toLowerCase();
            if (lowerName.endsWith(".wav")) {
                if (ContentCatalog::isSongDisabled(meta, originalName)) {
                    entry.close();
                    continue;
                }
                ContentCatalog::WavInfo wavInfo = ContentCatalog::inspectWav(entry);
                if (!wavInfo.valid) {
                    Serial.printf("[WavPlayer] Skipping invalid WAV: %s (%u bytes)\n",
                                  originalName.c_str(), static_cast<unsigned>(entry.size()));
                    entry.close();
                    continue;
                }
                if (!wavInfo.supported) {
                    Serial.printf("[WavPlayer] Skipping unsupported WAV: %s (format=%u rate=%lu channels=%u bits=%u)\n",
                                  originalName.c_str(), wavInfo.audioFormat,
                                  static_cast<unsigned long>(wavInfo.sampleRate),
                                  wavInfo.channels, wavInfo.bitsPerSample);
                    entry.close();
                    continue;
                }
                String full = String(dirPath);
                if (!full.endsWith("/")) full += "/";
                full += originalName;
                outFiles[count++] = full;
            }
        }
        entry.close();
    }
    dir.close();
    return count;
}

// ---------------------------------------------------------------------------
// static
int WavPlayer::listThemes(String* outIds, String* outNames, int maxThemes) {
    if (maxThemes <= 0) return 0;

    File root = SD.open(SONGS_ROOT);
    if (!root || !root.isDirectory()) {
        return 0;
    }

    int count = 0;
    bool capacityLogged = false;
    while (true) {
        File entry = root.openNextFile();
        if (!entry) break;

        String id = ContentCatalog::baseNameOf(String(entry.name()));
        if (ContentCatalog::isIgnoredFilesystemEntry(id) || !entry.isDirectory()) {
            entry.close();
            continue;
        }
        if (ContentCatalog::isThemeDisabled(id)) {
            entry.close();
            continue;
        }

        String themePath = String(SONGS_ROOT) + "/" + id;
        String probe[1];
        int playable = listWavFiles(themePath.c_str(), probe, 1);
        if (playable <= 0) {
            entry.close();
            continue;
        }

        if (count >= maxThemes) {
            if (!capacityLogged) {
                Serial.printf("[WavPlayer] Theme list reached firmware cap (%d); extra themes ignored\n",
                              maxThemes);
                capacityLogged = true;
            }
            entry.close();
            continue;
        }

        JsonDocument meta = readMetadata(themePath);
        const char* displayName = meta["name"] | "";
        outIds[count] = id;
        outNames[count] = (displayName && displayName[0] != '\0') ? String(displayName) : id;
        count++;
        entry.close();
    }
    root.close();

    sortThemes(outIds, outNames, count);
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

// ---------------------------------------------------------------------------
// static
JsonDocument WavPlayer::readMetadata(const String& themePath) {
    return ContentCatalog::readThemeMetadata(themePath);
}

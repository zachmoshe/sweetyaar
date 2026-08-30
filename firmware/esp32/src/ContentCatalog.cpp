#include "ContentCatalog.h"
#include <esp_heap_caps.h>
#include <utility>

namespace ContentCatalog {
namespace {

uint16_t le16(const uint8_t* p) {
    return static_cast<uint16_t>(p[0]) | (static_cast<uint16_t>(p[1]) << 8);
}

uint32_t le32(const uint8_t* p) {
    return static_cast<uint32_t>(p[0]) |
           (static_cast<uint32_t>(p[1]) << 8) |
           (static_cast<uint32_t>(p[2]) << 16) |
           (static_cast<uint32_t>(p[3]) << 24);
}

bool readFully(File& f, uint8_t* out, size_t len) {
    return f.read(out, len) == len;
}

bool isWavName(const String& name) {
    String lower = name;
    lower.toLowerCase();
    return lower.endsWith(".wav");
}

String pathForThemeId(const String& themeId) {
    if (themeId == ANIMALS_THEME_ID) {
        return String(ANIMALS_PATH);
    }
    return String(SONGS_ROOT) + "/" + themeId;
}

bool loadJsonList(JsonVariantConst value, String* out, int maxItems, int& count) {
    count = 0;
    if (!value.is<JsonArrayConst>()) {
        return false;
    }
    for (JsonVariantConst item : value.as<JsonArrayConst>()) {
        const char* text = item | "";
        if (text == nullptr || text[0] == '\0') {
            continue;
        }
        if (count < maxItems) {
            out[count++] = text;
        }
    }
    return true;
}

bool setListMember(JsonDocument& doc, const char* key, const String& name,
                   bool present, int maxItems) {
    String existing[CONFIG_MAX_DISABLED_SONGS];
    int count = 0;
    loadJsonList(doc[key], existing, maxItems, count);

    bool found = false;
    for (int i = 0; i < count; i++) {
        if (existing[i] == name) {
            found = true;
            break;
        }
    }
    if (present && !found && count < maxItems) {
        existing[count++] = name;
    }

    JsonArray arr = doc[key].to<JsonArray>();
    arr.clear();
    for (int i = 0; i < count; i++) {
        if (!present && existing[i] == name) {
            continue;
        }
        arr.add(existing[i]);
    }
    return true;
}

void appendThemeRow(String& json, const ThemeStats& stats) {
    if (!json.endsWith("[")) json += ",";
    json += "{\"id\":\"";
    json += jsonEscape(stats.id);
    json += "\",\"name\":\"";
    json += jsonEscape(stats.name);
    json += "\",\"enabled\":";
    json += stats.enabled ? "true" : "false";
    json += ",\"disabledByUser\":";
    json += stats.disabledByUser ? "true" : "false";
    json += ",\"shuffle\":";
    json += stats.shuffle ? "true" : "false";
    json += ",\"special\":";
    json += stats.special ? "true" : "false";
    json += ",\"canDisable\":";
    json += stats.canDisable ? "true" : "false";
    json += ",\"canSetDefault\":";
    json += stats.canSetDefault ? "true" : "false";
    json += ",\"activeValid\":";
    json += stats.enabledValidSongs;
    json += ",\"total\":";
    json += stats.totalSongs;
    json += ",\"errors\":";
    json += stats.errorSongs;
    json += "}";
}

void appendSongRow(String& json, const String& fileName, const WavInfo& wav,
                   bool enabled) {
    if (!json.endsWith("[")) json += ",";
    json += "{\"file\":\"";
    json += jsonEscape(fileName);
    json += "\",\"enabled\":";
    json += enabled ? "true" : "false";
    json += ",\"ok\":";
    json += wav.supported ? "true" : "false";
    json += ",\"sizeBytes\":";
    json += wav.sizeBytes;
    json += ",\"durationMs\":";
    json += wav.durationMs;
    if (!wav.supported) {
        json += ",\"error\":\"";
        json += jsonEscape(wav.error);
        json += "\"";
    }
    json += "}";
}

}  // namespace

String baseNameOf(const String& path) {
    int slash = path.lastIndexOf('/');
    if (slash < 0) return path;
    return path.substring(slash + 1);
}

bool isIgnoredFilesystemEntry(const String& name) {
    String base = baseNameOf(name);
    String lower = base;
    lower.toLowerCase();

    if (lower.length() == 0) return true;
    if (lower.startsWith(".") || lower.startsWith("._")) return true;
    if (lower.endsWith("~")) return true;

    static const char* const ignoredExact[] = {
        ".ds_store", ".spotlight-v100", ".trashes", ".fseventsd",
        ".temporaryitems", ".appledouble", ".apdisk",
        ".documentrevisions-v100", ".volumeicon.icns",
        ".metadata_never_index", ".com.apple.timemachine.donotpresent",
        "icon\r", "thumbs.db", "ehthumbs.db", "desktop.ini",
        "$recycle.bin", "recycler", "recycled", "system volume information",
        ".trash", ".directory", "lost+found", "found.000", "found.001",
    };

    for (size_t i = 0; i < sizeof(ignoredExact) / sizeof(ignoredExact[0]); i++) {
        if (lower == ignoredExact[i]) return true;
    }
    return lower.startsWith(".trash-") || lower.startsWith(".nfs");
}

bool isAnimalsTheme(const String& themeId) {
    return themeId == ANIMALS_THEME_ID;
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

String formatTimeOfDay(uint16_t minuteOfDay) {
    if (minuteOfDay >= 24U * 60U) {
        minuteOfDay = 24U * 60U - 1U;
    }
    char buf[6];
    snprintf(buf, sizeof(buf), "%02u:%02u", minuteOfDay / 60U, minuteOfDay % 60U);
    return String(buf);
}

JsonDocument readJsonFile(const String& path) {
    JsonDocument doc;
    File f = SD.open(path.c_str());
    if (!f) return doc;
    DeserializationError err = deserializeJson(doc, f);
    f.close();
    if (err) {
        Serial.printf("[Config] Failed to parse %s: %s\n", path.c_str(), err.c_str());
        doc.clear();
    }
    return doc;
}

JsonDocument readThemeMetadata(const String& themePath) {
    return readJsonFile(themePath + "/" + METADATA_FILE);
}

bool writeJsonFile(const String& path, JsonDocument& doc) {
    SD.remove(path.c_str());
    File f = SD.open(path.c_str(), FILE_WRITE);
    if (!f) {
        Serial.printf("[Config] Cannot write %s\n", path.c_str());
        return false;
    }
    serializeJsonPretty(doc, f);
    f.println();
    f.close();
    return true;
}

bool nameInJsonArray(JsonVariantConst value, const String& name) {
    if (!value.is<JsonArrayConst>()) {
        return false;
    }
    for (JsonVariantConst item : value.as<JsonArrayConst>()) {
        const char* text = item | "";
        if (text && name == text) {
            return true;
        }
    }
    return false;
}

bool isThemeDisabled(const String& themeId) {
    if (isAnimalsTheme(themeId)) {
        return false;
    }
    JsonDocument doc = readJsonFile(SD_CONFIG_FILE);
    return nameInJsonArray(doc["disabledThemes"], themeId);
}

bool isSongDisabled(const JsonDocument& metadata, const String& fileName) {
    return nameInJsonArray(metadata["disabledSongs"], fileName);
}

WavInfo inspectWav(File& entry) {
    WavInfo info;
    info.sizeBytes = entry.size();
    entry.seek(0);

    if (info.sizeBytes < 12) {
        info.error = "File is too small";
        return info;
    }

    uint8_t riff[12];
    if (!readFully(entry, riff, sizeof(riff)) ||
        riff[0] != 'R' || riff[1] != 'I' || riff[2] != 'F' || riff[3] != 'F' ||
        riff[8] != 'W' || riff[9] != 'A' || riff[10] != 'V' || riff[11] != 'E') {
        entry.seek(0);
        info.error = "Missing RIFF/WAVE header";
        return info;
    }

    bool fmtFound = false;
    bool dataFound = false;
    uint32_t pos = 12;

    while (pos + 8 <= info.sizeBytes) {
        entry.seek(pos);
        uint8_t chunk[8];
        if (!readFully(entry, chunk, sizeof(chunk))) {
            break;
        }

        uint32_t chunkSize = le32(chunk + 4);
        uint32_t dataStart = pos + 8;
        if (dataStart > info.sizeBytes || chunkSize > (info.sizeBytes - dataStart)) {
            info.error = "Invalid WAV chunk size";
            entry.seek(0);
            return info;
        }
        uint32_t next = dataStart + chunkSize + (chunkSize & 1);
        if (next < dataStart) {
            info.error = "Invalid WAV chunk size";
            entry.seek(0);
            return info;
        }

        if (chunk[0] == 'f' && chunk[1] == 'm' && chunk[2] == 't' && chunk[3] == ' ') {
            if (chunkSize < 16 || dataStart + 16 > info.sizeBytes) {
                info.error = "Invalid fmt chunk";
                entry.seek(0);
                return info;
            }
            uint8_t fmt[16];
            entry.seek(dataStart);
            if (!readFully(entry, fmt, sizeof(fmt))) {
                info.error = "Cannot read fmt chunk";
                entry.seek(0);
                return info;
            }
            info.audioFormat = le16(fmt + 0);
            info.channels = le16(fmt + 2);
            info.sampleRate = le32(fmt + 4);
            info.bitsPerSample = le16(fmt + 14);
            fmtFound = true;
        } else if (chunk[0] == 'd' && chunk[1] == 'a' && chunk[2] == 't' && chunk[3] == 'a') {
            info.dataBytes = chunkSize;
            dataFound = true;
        }

        pos = next;
    }

    entry.seek(0);
    if (!fmtFound) {
        info.error = "Missing fmt chunk";
        return info;
    }
    if (!dataFound || info.dataBytes == 0) {
        info.error = "Missing audio data";
        return info;
    }

    info.valid = true;
    if (info.audioFormat != 1) {
        info.error = String("Unsupported WAV format: ") + info.audioFormat;
        return info;
    }
    if (info.sampleRate != SAMPLE_RATE) {
        info.error = String("Invalid sample rate: ") + info.sampleRate + " Hz";
        return info;
    }
    if (info.channels != CHANNELS) {
        info.error = String("Invalid channel count: ") + info.channels;
        return info;
    }
    if (info.bitsPerSample != BITS_PER_SAMPLE) {
        info.error = String("Invalid bit depth: ") + info.bitsPerSample + "-bit";
        return info;
    }

    uint32_t bytesPerSecond = info.sampleRate * info.channels * (info.bitsPerSample / 8);
    if (bytesPerSecond > 0) {
        info.durationMs = static_cast<uint32_t>(
            (static_cast<uint64_t>(info.dataBytes) * 1000ULL) / bytesPerSecond);
    }
    info.supported = true;
    return info;
}

String formatWavDetails(const WavInfo& info) {
    if (!info.supported) {
        return info.error;
    }
    String out = String(info.sampleRate / 1000.0f, 1);
    out += " kHz ";
    out += info.channels == 2 ? "stereo " : "mono ";
    out += "PCM";
    return out;
}

// ---------------------------------------------------------------------------
// In-RAM catalog (built once at boot by buildCatalog())
// ---------------------------------------------------------------------------
namespace {

std::vector<CachedTheme> g_themes;  // song themes sorted by id, Animals last
bool g_catalogReady = false;

void sortSongsByName(std::vector<CachedSong>& songs) {
    for (size_t i = 1; i < songs.size(); i++) {
        CachedSong key = std::move(songs[i]);
        size_t j = i;
        while (j > 0 && songs[j - 1].file.compareTo(key.file) > 0) {
            songs[j] = std::move(songs[j - 1]);
            j--;
        }
        songs[j] = std::move(key);
    }
}

// Walk one theme directory exactly once: read its metadata, inspect every WAV
// header, and fill the cached song list. Used for /songs themes and /animals.
void loadThemeContents(CachedTheme& theme, const String& themePath) {
    JsonDocument meta = readThemeMetadata(themePath);
    const char* displayName = meta["name"] | "";
    theme.name = (displayName && displayName[0] != '\0')
        ? String(displayName)
        : (theme.special ? String(ANIMALS_DISPLAY_NAME) : theme.id);
    theme.shuffle = meta["shuffle"] | theme.special;  // animals default to shuffle

    File dir = SD.open(themePath.c_str());
    if (!dir || !dir.isDirectory()) {
        return;
    }
    while (true) {
        File entry = dir.openNextFile();
        if (!entry) break;
        String fileName = baseNameOf(String(entry.name()));
        if (!entry.isDirectory() && !isIgnoredFilesystemEntry(fileName) && isWavName(fileName)) {
            CachedSong song;
            song.file = fileName;
            WavInfo wav = inspectWav(entry);
            song.sizeBytes = wav.sizeBytes;
            song.durationMs = wav.durationMs;
            song.supported = wav.supported;
            if (!wav.supported) {
                song.error = wav.error;
            }
            song.disabled = isSongDisabled(meta, fileName);
            theme.songs.push_back(std::move(song));
        }
        entry.close();
    }
    dir.close();
    sortSongsByName(theme.songs);
}

CachedTheme* mutableFindTheme(const String& themeId) {
    for (CachedTheme& t : g_themes) {
        if (t.id == themeId) return &t;
    }
    return nullptr;
}

}  // namespace

void buildCatalog() {
    uint32_t startMs = millis();
    g_themes.clear();
    g_catalogReady = false;

    JsonDocument config = readJsonFile(SD_CONFIG_FILE);

    File root = SD.open(SONGS_ROOT);
    if (root && root.isDirectory()) {
        while (true) {
            File entry = root.openNextFile();
            if (!entry) break;
            String id = baseNameOf(String(entry.name()));
            bool isDir = entry.isDirectory();
            entry.close();
            if (!isDir || isIgnoredFilesystemEntry(id)) {
                continue;
            }
            CachedTheme theme;
            theme.id = id;
            theme.special = false;
            theme.disabledByUser = nameInJsonArray(config["disabledThemes"], id);
            loadThemeContents(theme, String(SONGS_ROOT) + "/" + id);
            g_themes.push_back(std::move(theme));
        }
        root.close();
    }

    // Sort song themes by id (Animals is appended after, so it stays last).
    for (size_t i = 1; i < g_themes.size(); i++) {
        CachedTheme key = std::move(g_themes[i]);
        size_t j = i;
        while (j > 0 && g_themes[j - 1].id.compareTo(key.id) > 0) {
            g_themes[j] = std::move(g_themes[j - 1]);
            j--;
        }
        g_themes[j] = std::move(key);
    }

    // Animals: reserved, non-disableable theme that always appears last.
    CachedTheme animals;
    animals.id = ANIMALS_THEME_ID;
    animals.special = true;
    animals.disabledByUser = false;
    loadThemeContents(animals, String(ANIMALS_PATH));
    g_themes.push_back(std::move(animals));

    g_catalogReady = true;

    int totalSongs = 0;
    for (const CachedTheme& t : g_themes) {
        totalSongs += static_cast<int>(t.songs.size());
    }
    Serial.printf("[Catalog] Built in %lums: %u themes, %d files (free=%u largest=%u)\n",
                  static_cast<unsigned long>(millis() - startMs),
                  static_cast<unsigned>(g_themes.size()), totalSongs,
                  heap_caps_get_free_size(MALLOC_CAP_8BIT),
                  heap_caps_get_largest_free_block(MALLOC_CAP_8BIT));
}

bool catalogReady() { return g_catalogReady; }

int themeCount() { return static_cast<int>(g_themes.size()); }

const CachedTheme& themeAt(int index) { return g_themes[index]; }

const CachedTheme* findTheme(const String& themeId) {
    return mutableFindTheme(themeId);
}

ThemeStats scanThemeStats(const String& themeId, bool /*validateWavs*/) {
    // Served entirely from the in-RAM catalog — no SD access.
    ThemeStats stats;
    stats.id = themeId;
    stats.special = isAnimalsTheme(themeId);
    stats.canDisable = !stats.special;
    stats.canSetDefault = !stats.special;

    const CachedTheme* theme = findTheme(themeId);
    if (theme == nullptr) {
        stats.name = stats.special ? String(ANIMALS_DISPLAY_NAME) : themeId;
        stats.enabled = false;
        return stats;
    }

    stats.name = theme->name;
    stats.shuffle = theme->shuffle;
    stats.disabledByUser = theme->disabledByUser;
    for (const CachedSong& s : theme->songs) {
        stats.totalSongs++;
        if (!s.supported) {
            stats.errorSongs++;
        } else if (!s.disabled) {
            stats.enabledValidSongs++;
        }
    }

    stats.enabled = !stats.disabledByUser && stats.enabledValidSongs > 0;
    return stats;
}

String buildThemesPageJson(uint32_t requestId, int page, int pageSize) {
    if (page < 0) page = 0;
    if (pageSize <= 0) pageSize = BLE_CONFIG_THEME_PAGE_SIZE;

    int count = themeCount();  // song themes + the reserved Animals row
    int start = page * pageSize;
    int end = start + pageSize;

    String json = "{\"id\":";
    json += requestId;
    json += ",\"ok\":true,\"op\":\"scanThemes\",\"page\":";
    json += page;
    json += ",\"hasMore\":";
    json += (end < count) ? "true" : "false";
    json += ",\"themes\":[";

    for (int i = start; i < count && i < end; i++) {
        ThemeStats stats = scanThemeStats(themeAt(i).id, false);
        appendThemeRow(json, stats);
    }

    json += "]}";
    return json;
}

String buildSongsPageJson(uint32_t requestId, const String& themeId,
                          int page, int pageSize) {
    if (page < 0) page = 0;
    if (pageSize <= 0) pageSize = BLE_CONFIG_SONG_PAGE_SIZE;

    ThemeStats stats = scanThemeStats(themeId, false);
    const CachedTheme* theme = findTheme(themeId);
    int fileCount = theme ? static_cast<int>(theme->songs.size()) : 0;
    int start = page * pageSize;
    int end = start + pageSize;

    String json = "{\"id\":";
    json += requestId;
    json += ",\"ok\":true,\"op\":\"scanSongs\",\"theme\":\"";
    json += jsonEscape(themeId);
    json += "\",\"name\":\"";
    json += jsonEscape(stats.name);
    json += "\",\"themeEnabled\":";
    json += stats.enabled ? "true" : "false";
    json += ",\"disabledByUser\":";
    json += stats.disabledByUser ? "true" : "false";
    json += ",\"shuffle\":";
    json += stats.shuffle ? "true" : "false";
    json += ",\"errors\":";
    json += stats.errorSongs;
    json += ",\"page\":";
    json += page;
    json += ",\"songs\":[";

    int limit = end < fileCount ? end : fileCount;
    for (int i = start; i < limit; i++) {
        const CachedSong& s = theme->songs[i];
        WavInfo wav;
        wav.supported = s.supported;
        wav.sizeBytes = s.sizeBytes;
        wav.durationMs = s.durationMs;
        wav.error = s.error;
        appendSongRow(json, s.file, wav, !s.disabled);
    }

    json += "],\"hasMore\":";
    json += (end < fileCount) ? "true" : "false";
    json += "}";
    return json;
}

bool updateSdConfig(uint8_t defaultVolumePct, const String& defaultTheme,
                    bool sleepEnabled, uint32_t sleepNormalIdleSec,
                    uint32_t sleepVibrationWakeIdleSec, uint32_t sleepBleIdleSec,
                    bool bedtimeEnabled, uint16_t bedtimeStartMinutes,
                    uint16_t bedtimeEndMinutes, const String& bedtimeTheme,
                    uint8_t bedtimeVolumeCapPct) {
    JsonDocument doc = readJsonFile(SD_CONFIG_FILE);
    doc["schemaVersion"] = 2;
    doc["defaultVolumePct"] = defaultVolumePct > 100 ? 100 : defaultVolumePct;
    doc["defaultTheme"] = defaultTheme;
    if (!doc["disabledThemes"].is<JsonArray>()) {
        doc["disabledThemes"].to<JsonArray>();
    }
    JsonObject sleep = doc["sleep"].is<JsonObject>()
        ? doc["sleep"].as<JsonObject>()
        : doc["sleep"].to<JsonObject>();
    sleep["enabled"] = sleepEnabled;
    sleep["normalIdleSec"] = sleepNormalIdleSec;
    sleep["vibrationWakeIdleSec"] = sleepVibrationWakeIdleSec;
    sleep["bleIdleSec"] = sleepBleIdleSec;

    JsonObject bedtime = doc["bedtime"].is<JsonObject>()
        ? doc["bedtime"].as<JsonObject>()
        : doc["bedtime"].to<JsonObject>();
    bedtime["enabled"] = bedtimeEnabled;
    bedtime["startTime"] = formatTimeOfDay(bedtimeStartMinutes);
    bedtime["endTime"] = formatTimeOfDay(bedtimeEndMinutes);
    bedtime["theme"] = bedtimeTheme.isEmpty() ? String(DEFAULT_BEDTIME_THEME) : bedtimeTheme;
    bedtime["volumeCapPct"] = bedtimeVolumeCapPct > 100 ? 100 : bedtimeVolumeCapPct;

    return writeJsonFile(SD_CONFIG_FILE, doc);
}

bool setThemeDisabled(const String& themeId, bool disabled) {
    if (isAnimalsTheme(themeId)) {
        return true;
    }
    JsonDocument doc = readJsonFile(SD_CONFIG_FILE);
    doc["schemaVersion"] = 2;
    if (!doc["defaultVolumePct"].is<int>()) {
        doc["defaultVolumePct"] = DEFAULT_VOLUME_PCT;
    }
    if (!doc["defaultTheme"].is<const char*>()) {
        doc["defaultTheme"] = DEFAULT_THEME;
    }
    setListMember(doc, "disabledThemes", themeId, disabled, CONFIG_MAX_DISABLED_THEMES);
    bool ok = writeJsonFile(SD_CONFIG_FILE, doc);
    if (ok) {
        if (CachedTheme* t = mutableFindTheme(themeId)) {
            t->disabledByUser = disabled;
        }
    }
    return ok;
}

bool setThemeShuffle(const String& themeId, bool shuffle) {
    String themePath = pathForThemeId(themeId);
    String path = themePath + "/" + METADATA_FILE;
    JsonDocument doc = readJsonFile(path);
    doc["schemaVersion"] = 2;
    const char* existingName = doc["name"] | "";
    if (!existingName || existingName[0] == '\0') {
        doc["name"] = isAnimalsTheme(themeId) ? ANIMALS_DISPLAY_NAME : themeId;
    }
    doc["shuffle"] = shuffle;
    if (!doc["disabledSongs"].is<JsonArray>()) {
        doc["disabledSongs"].to<JsonArray>();
    }
    bool ok = writeJsonFile(path, doc);
    if (ok) {
        if (CachedTheme* t = mutableFindTheme(themeId)) {
            t->shuffle = shuffle;
        }
    }
    return ok;
}

bool setSongDisabled(const String& themeId, const String& fileName, bool disabled) {
    String themePath = pathForThemeId(themeId);
    String path = themePath + "/" + METADATA_FILE;
    JsonDocument doc = readJsonFile(path);
    doc["schemaVersion"] = 2;
    const char* existingName = doc["name"] | "";
    if (!existingName || existingName[0] == '\0') {
        doc["name"] = isAnimalsTheme(themeId) ? ANIMALS_DISPLAY_NAME : themeId;
    }
    if (!doc["shuffle"].is<bool>()) {
        doc["shuffle"] = isAnimalsTheme(themeId);
    }
    setListMember(doc, "disabledSongs", fileName, disabled, CONFIG_MAX_DISABLED_SONGS);
    bool ok = writeJsonFile(path, doc);
    if (ok) {
        if (CachedTheme* t = mutableFindTheme(themeId)) {
            for (CachedSong& s : t->songs) {
                if (s.file == fileName) {
                    s.disabled = disabled;
                    break;
                }
            }
        }
    }
    return ok;
}

}  // namespace ContentCatalog

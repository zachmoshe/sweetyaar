#pragma once
#include <Arduino.h>
#include <ArduinoJson.h>
#include <SD.h>
#include <vector>
#include "Config.h"

namespace ContentCatalog {

struct WavInfo {
    bool valid = false;
    bool supported = false;
    uint32_t sizeBytes = 0;
    uint16_t audioFormat = 0;
    uint16_t channels = 0;
    uint32_t sampleRate = 0;
    uint16_t bitsPerSample = 0;
    uint32_t dataOffset = 0;
    uint32_t dataBytes = 0;
    uint32_t durationMs = 0;
    String error;
};

// Optional per-theme credit from metadata.json {"attribution": "<markdown>"}. The toy relays the string
// as-is (the parent app renders its [text](https://...) links); it travels in the paged theme scan, which
// must still fit a 512-byte BLE response, so it is bounded.
static constexpr size_t ATTRIBUTION_MAX_BYTES = 160;

struct ThemeStats {
    String id;
    String name;
    String credit;      // attribution markdown; empty when the theme has none
    bool disabledByUser = false;
    bool enabled = false;
    bool shuffle = false;
    bool special = false;
    bool canDisable = true;
    bool canSetDefault = true;
    int totalSongs = 0;
    int enabledValidSongs = 0;
    int errorSongs = 0;
};

// ---------------------------------------------------------------------------
// In-RAM catalog
//
// At boot the SD folders are only listed (names, no file opens) into these
// structures; every other code path (playback file lists, BLE theme list,
// settings scans) is served from RAM. WAV headers are checked afterwards, one
// file at a time while the toy is idle, and again whenever a file is played;
// each check fills in size, duration and playability. Audio is 44.1 kHz /
// 16-bit PCM, mono or stereo. Edits flip flags in place; the catalog is rebuilt
// only on reboot, because the card is inaccessible while the toy is in use.
// ---------------------------------------------------------------------------
struct CachedSong {
    String   file;             // filename (basename), no directory
    String   error;            // diagnostic for the UI; empty when supported
    uint32_t sizeBytes = 0;    // 0 until the header has been checked
    uint32_t durationMs = 0;
    bool     supported = false;  // playable: PCM 44.1 kHz / 16-bit / mono or stereo
    bool     disabled  = false;  // parent-disabled via metadata.json
    bool     checked   = false;  // header inspected since boot
};

struct CachedTheme {
    String id;
    String name;
    String credit;
    bool   shuffle = false;
    bool   disabledByUser = false;  // from config.json disabledThemes
    bool   special = false;          // the reserved Animals theme
    std::vector<CachedSong> songs;   // sorted by filename

    // Count of songs that would actually play (supported and not disabled).
    int playableCount() const {
        int n = 0;
        for (const CachedSong& s : songs) {
            if (s.supported && !s.disabled) n++;
        }
        return n;
    }
};

// Build (or rebuild) the whole catalog by listing the SD folders. Songs are
// assumed playable until checked. Call once at boot after SD.begin().
void buildCatalog();
// Check one not-yet-checked song header; false once every song is checked.
bool checkNextSong();
// Store a header check of a catalog path such as "/songs/<theme>/<file>".
// Returns true when the song is newly found to be unplayable.
bool recordWavCheck(const String& path, const WavInfo& info);
// Message for songs newly found unplayable since the last call, if any.
bool takeUnplayableReport(String& message);
bool catalogReady();
bool validThemeId(const String& id);
bool themeEntryFits(const CachedTheme& theme);
bool songEntryFits(const CachedTheme& theme, const CachedSong& song);
void validateCatalog();
String catalogWarning();
String utf8Prefix(const String& value, size_t maxBytes);

// All themes, in display order: song themes sorted by id, then Animals last.
int themeCount();
const CachedTheme& themeAt(int index);

// Lookup by id (handles ANIMALS_THEME_ID); nullptr if unknown.
const CachedTheme* findTheme(const String& themeId);

String baseNameOf(const String& path);
bool isIgnoredFilesystemEntry(const String& name);
bool isAnimalsTheme(const String& themeId);
String jsonEscape(const String& input);
String formatTimeOfDay(uint16_t minuteOfDay);

JsonDocument readJsonFile(const String& path);
JsonDocument readThemeMetadata(const String& themePath);
// Write a .tmp file, check byte counts and size, then remove/rename into place.
// No backup or content read-back; every failed operation returns false.
bool writeJsonFile(const String& path, JsonDocument& doc);

bool nameInJsonArray(JsonVariantConst value, const String& name);
bool isThemeDisabled(const String& themeId);
bool isSongDisabled(const JsonDocument& metadata, const String& fileName);

WavInfo inspectWav(File& entry);
String formatWavDetails(const WavInfo& info);

ThemeStats scanThemeStats(const String& themeId, bool validateWavs = true);
String buildThemesPageJson(uint32_t requestId, int cursor, int maxBytes);
String buildSongsPageJson(uint32_t requestId, const String& themeId,
                          int cursor, int maxBytes);

bool updateSdConfig(uint8_t defaultVolumePct, const String& defaultTheme,
                    bool sleepEnabled, uint32_t sleepNormalIdleSec,
                    uint32_t sleepVibrationWakeIdleSec, uint32_t sleepBleIdleSec,
                    bool bedtimeEnabled, uint16_t bedtimeStartMinutes,
                    uint16_t bedtimeEndMinutes, const String& bedtimeTheme,
                    uint8_t bedtimeVolumeCapPct);
bool setThemeDisabled(const String& themeId, bool disabled);
bool setThemeShuffle(const String& themeId, bool shuffle);
bool setSongDisabled(const String& themeId, const String& fileName, bool disabled);

}  // namespace ContentCatalog

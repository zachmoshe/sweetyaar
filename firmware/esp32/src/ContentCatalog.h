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

struct ThemeStats {
    String id;
    String name;
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
// The SD card is read exactly once, at boot, into these structures; every
// other code path (playback file lists, BLE theme list, settings scans) is
// served from RAM. Audio is 44.1 kHz / 16-bit PCM, mono or stereo. The per-song
// record keeps the duration calculated from the file's channel count, without
// retaining format fields; playback re-reads the header. Edits flip flags in
// place; the catalog is rebuilt only on reboot, because the card is inaccessible
// while the toy is in use.
// ---------------------------------------------------------------------------
struct CachedSong {
    String   file;             // filename (basename), no directory
    String   error;            // diagnostic for the UI; empty when supported
    uint32_t sizeBytes = 0;
    uint32_t durationMs = 0;
    bool     supported = false;  // playable: PCM 44.1 kHz / 16-bit / mono or stereo
    bool     disabled  = false;  // parent-disabled via metadata.json
};

struct CachedTheme {
    String id;
    String name;
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

// Build (or rebuild) the whole catalog with a single pass over the SD card.
// Call once at boot after SD.begin().
void buildCatalog();
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

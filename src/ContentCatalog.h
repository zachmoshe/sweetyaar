#pragma once
#include <Arduino.h>
#include <ArduinoJson.h>
#include <SD.h>
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

String baseNameOf(const String& path);
bool isIgnoredFilesystemEntry(const String& name);
bool isAnimalsTheme(const String& themeId);
String jsonEscape(const String& input);
String formatTimeOfDay(uint16_t minuteOfDay);

JsonDocument readJsonFile(const String& path);
JsonDocument readThemeMetadata(const String& themePath);
bool writeJsonFile(const String& path, JsonDocument& doc);

bool nameInJsonArray(JsonVariantConst value, const String& name);
bool isThemeDisabled(const String& themeId);
bool isSongDisabled(const JsonDocument& metadata, const String& fileName);

WavInfo inspectWav(File& entry);
String formatWavDetails(const WavInfo& info);

int listThemeIds(String* outIds, int maxThemes);
ThemeStats scanThemeStats(const String& themeId, bool validateWavs = true);
String buildThemesPageJson(uint32_t requestId, int page, int pageSize);
String buildSongsPageJson(uint32_t requestId, const String& themeId,
                          int page, int pageSize);

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

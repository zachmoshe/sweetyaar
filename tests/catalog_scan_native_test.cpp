// Seed the RAM catalog, then execute the production serializers. No SD or radio
// is required; the serializers and theme statistics are extracted unchanged.
#include "ContentCatalog.h"
#include <iostream>
#include <iterator>
#include <map>
#include <string>
#include <utility>

namespace ContentCatalog {
// The catalog keeps no song names; production reads them from the SD card.
// Here the fixture plays the card: names and error texts per theme id.
std::map<std::string, std::vector<std::pair<String, String>>> g_cardSongs;
bool songNames(const CachedTheme& theme, std::vector<String>& names) {
    names.clear();
    for (const auto& song : g_cardSongs[theme.id.c_str()]) names.push_back(song.first);
    return names.size() == theme.songs.size();
}
namespace {
std::vector<CachedTheme> g_themes;
unsigned g_oversizedEntries = 0;
String g_firstOversizedEntry;
String songErrorText(const CachedTheme& theme, const String& file) {
    for (const auto& song : g_cardSongs[theme.id.c_str()]) if (song.first == file) return song.second;
    return "";
}
}
#include "catalog_scan_production.inc"
}

int main() {
    const std::string input(std::istreambuf_iterator<char>(std::cin), {});
    JsonDocument request;
    if (deserializeJson(request, input)) return 1;

    using namespace ContentCatalog;
    std::vector<std::vector<std::pair<String, String>>> themeSongs;  // fixture order, ids may repeat
    for (JsonObjectConst item : request["themes"].as<JsonArrayConst>()) {
        CachedTheme theme;
        theme.id = item["id"].as<const char*>();
        theme.name = item["name"].as<const char*>();
        theme.credit = String(item["credit"] | "");
        theme.disabledByUser = item["disabledByUser"] | false;
        theme.shuffle = item["shuffle"] | false;
        theme.special = item["special"] | false;
        themeSongs.emplace_back();
        for (JsonObjectConst row : item["songs"].as<JsonArrayConst>()) {
            themeSongs.back().emplace_back(String(row["file"].as<const char*>()), String(row["error"] | ""));
            g_cardSongs[theme.id.c_str()].push_back(themeSongs.back().back());
            CachedSong song;
            song.supported = row["supported"] | true;
            song.disabled = row["disabled"] | false;
            song.sizeBytes = row["sizeBytes"] | 0U;
            song.durationMs = row["durationMs"] | 0U;
            theme.songs.push_back(song);
        }
        g_themes.push_back(theme);
    }

    const std::string op = request["op"].as<const char*>();
    if (op == "sanitize") {
        JsonDocument result;
        auto themes = result["themes"].to<JsonArray>();
        for (auto& theme : g_themes) {
            sanitizeAttribution(theme);
            auto row = themes.add<JsonObject>();
            row["credit"] = theme.credit.c_str();
        }
        std::string output;
        serializeJson(result, output);
        std::cout << output << '\n';
        return 0;
    }
    if (op == "limits") {
        JsonDocument result;
        auto themes = result["themes"].to<JsonArray>();
        for (size_t i = 0; i < g_themes.size(); ++i) {
            const auto& theme = g_themes[i];
            auto row = themes.add<JsonObject>();
            row["fits"] = themeEntryFits(theme);
            auto songs = row["songs"].to<JsonArray>();
            std::vector<String> names;
            for (const auto& song : themeSongs[i]) {
                songs.add(songEntryFits(theme, song.first, song.second));
                names.push_back(song.first);
            }
            // As at boot: oversized songs are dropped while listing, then themes are validated.
            dropOversizedSongs(theme, names, true);
            g_themes[i].songs.resize(names.size());
        }
        validateCatalog();
        result["warning"] = catalogWarning().c_str();
        auto retained = result["retained"].to<JsonArray>();
        for (const auto& theme : g_themes) {
            auto row = retained.add<JsonObject>();
            row["id"] = theme.id.c_str();
            row["credit"] = theme.credit.c_str();
        }
        result["retainedThemes"] = g_themes.size();
        int songs = 0;
        for (const auto& theme : g_themes) songs += theme.songs.size();
        result["retainedSongs"] = songs;
        std::string output;
        serializeJson(result, output);
        std::cout << output << '\n';
        return 0;
    }
    const String theme = request["theme"] | "";
    const int maxBytes = request["maxBytes"] | 0;  // 0 selects production defaults.
    const uint32_t firstId = request["id"] | 1U;
    // One page beyond the end is emitted to check terminal-page behavior too.
    bool checkPastEnd = false;
    int cursor = 0;
    for (int page = 0; page < 4096; ++page) {
        const String response = op == "scanThemes"
            ? buildThemesPageJson(firstId + page, cursor, maxBytes)
            : buildSongsPageJson(firstId + page, theme, cursor, maxBytes);
        JsonDocument parsed;
        if (deserializeJson(parsed, response.c_str())) return 2;
        std::cout << response.c_str() << '\n';
        if (checkPastEnd) return 0;
        checkPastEnd = !parsed["hasMore"].as<bool>();
        cursor = parsed["nextCursor"] | cursor;
    }
    std::cerr << "Scan failed to terminate\n";
    return 3;
}

// Seed the RAM catalog, then execute the production serializers. No SD or radio
// is required; the serializers and theme statistics are extracted unchanged.
#include "ContentCatalog.h"
#include <iostream>
#include <iterator>
#include <string>

namespace ContentCatalog {
namespace {
std::vector<CachedTheme> g_themes;
}
#include "catalog_scan_production.inc"
}

int main() {
    const std::string input(std::istreambuf_iterator<char>(std::cin), {});
    JsonDocument request;
    if (deserializeJson(request, input)) return 1;

    using namespace ContentCatalog;
    for (JsonObjectConst item : request["themes"].as<JsonArrayConst>()) {
        CachedTheme theme;
        theme.id = item["id"].as<const char*>();
        theme.name = item["name"].as<const char*>();
        theme.disabledByUser = item["disabledByUser"] | false;
        theme.shuffle = item["shuffle"] | false;
        theme.special = item["special"] | false;
        for (JsonObjectConst row : item["songs"].as<JsonArrayConst>()) {
            CachedSong song;
            song.file = row["file"].as<const char*>();
            song.error = row["error"] | "";
            song.supported = row["supported"] | true;
            song.disabled = row["disabled"] | false;
            song.sizeBytes = row["sizeBytes"] | 0U;
            song.durationMs = row["durationMs"] | 0U;
            theme.songs.push_back(song);
        }
        g_themes.push_back(theme);
    }

    const std::string op = request["op"].as<const char*>();
    const String theme = request["theme"] | "";
    const int pageSize = request["pageSize"] | 0;  // 0 selects production defaults.
    const uint32_t firstId = request["id"] | 1U;
    // One page beyond the end is emitted to check terminal-page behavior too.
    bool checkPastEnd = false;
    for (int page = 0; page < 4096; ++page) {
        const String response = op == "scanThemes"
            ? buildThemesPageJson(firstId + page, page, pageSize)
            : buildSongsPageJson(firstId + page, theme, page, pageSize);
        JsonDocument parsed;
        if (deserializeJson(parsed, response.c_str())) return 2;
        std::cout << response.c_str() << '\n';
        if (checkPastEnd) return 0;
        checkPastEnd = !parsed["hasMore"].as<bool>();
    }
    std::cerr << "Scan failed to terminate\n";
    return 3;
}

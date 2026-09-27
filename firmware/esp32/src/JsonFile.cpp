#include "ContentCatalog.h"

namespace ContentCatalog {

JsonDocument readJsonFile(const String& path) {
    JsonDocument doc;
    File f = SD.open(path.c_str());
    if (!f) {
        Serial.printf("[Config] Cannot read %s\n", path.c_str());
        return doc;
    }
    DeserializationError err = deserializeJson(doc, f);
    f.close();
    if (err || !doc.is<JsonObject>()) {
        Serial.printf("[Config] Invalid %s: %s\n", path.c_str(),
                      err ? err.c_str() : "expected a JSON object");
        doc.clear();
    }
    return doc;
}

bool writeJsonFile(const String& path, JsonDocument& doc) {
    if (doc.overflowed()) {
        Serial.printf("[Config] Not enough memory to save %s\n", path.c_str());
        return false;
    }

    const String tempPath = path + ".tmp";
    const size_t expected = measureJsonPretty(doc) + 1;  // trailing newline
    // FILE_WRITE truncates any temporary file left by an earlier failed save.
    File f = SD.open(tempPath.c_str(), FILE_WRITE);
    if (!f) {
        Serial.printf("[Config] Cannot write %s\n", tempPath.c_str());
        return false;
    }
    size_t written = serializeJsonPretty(doc, f);
    written += f.write(static_cast<uint8_t>('\n'));
    f.flush();
    f.close();
    if (written != expected) {
        Serial.printf("[Config] Short write to %s (%u/%u bytes)\n",
                      tempPath.c_str(), static_cast<unsigned>(written),
                      static_cast<unsigned>(expected));
        return false;
    }

    // Check metadata after flushing and closing; do not reread/parse contents.
    File saved = SD.open(tempPath.c_str());
    if (!saved) {
        Serial.printf("[Config] Cannot check size of %s\n", tempPath.c_str());
        return false;
    }
    const size_t savedSize = saved.size();
    saved.close();
    if (savedSize != expected) {
        Serial.printf("[Config] Wrong size for %s (%u/%u bytes)\n",
                      tempPath.c_str(), static_cast<unsigned>(savedSize),
                      static_cast<unsigned>(expected));
        return false;
    }

    // FatFs cannot rename over an existing file. Only remove it after the new
    // file is complete. Power loss between remove and rename is an accepted
    // failure window: loading reports the missing file, with no backup recovery.
    if (SD.exists(path.c_str()) && !SD.remove(path.c_str())) {
        Serial.printf("[Config] Cannot replace %s\n", path.c_str());
        return false;
    }
    if (!SD.rename(tempPath.c_str(), path.c_str())) {
        Serial.printf("[Config] Cannot rename %s to %s\n",
                      tempPath.c_str(), path.c_str());
        return false;
    }
    return true;
}

}  // namespace ContentCatalog

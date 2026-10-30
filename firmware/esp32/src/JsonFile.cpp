#include "ContentCatalog.h"
#include "DevLog.h"

namespace ContentCatalog {

JsonDocument readJsonFile(const String& path) {
    JsonDocument doc;
    File f = SD.open(path.c_str());
    if (!f) {
        DLOG(CONFIG_READ_FAILED, path.c_str());
        return doc;
    }
    DeserializationError err = deserializeJson(doc, f);
    f.close();
    if (err || !doc.is<JsonObject>()) {
        DLOG(CONFIG_INVALID, path.c_str(),
                      err ? err.c_str() : "expected a JSON object");
        doc.clear();
    }
    return doc;
}

bool writeJsonFile(const String& path, JsonDocument& doc) {
    if (doc.overflowed()) {
        DLOG(CONFIG_SAVE_NO_MEMORY, path.c_str());
        return false;
    }

    const String tempPath = path + ".tmp";
    const size_t expected = measureJsonPretty(doc) + 1;  // trailing newline
    // FILE_WRITE truncates any temporary file left by an earlier failed save.
    File f = SD.open(tempPath.c_str(), FILE_WRITE);
    if (!f) {
        DLOG(CONFIG_WRITE_FAILED, tempPath.c_str());
        return false;
    }
    size_t written = serializeJsonPretty(doc, f);
    written += f.write(static_cast<uint8_t>('\n'));
    f.flush();
    f.close();
    if (written != expected) {
        DLOG(CONFIG_SHORT_WRITE,
                      tempPath.c_str(), static_cast<unsigned>(written),
                      static_cast<unsigned>(expected));
        return false;
    }

    // Check metadata after flushing and closing; do not reread/parse contents.
    File saved = SD.open(tempPath.c_str());
    if (!saved) {
        DLOG(CONFIG_SIZE_UNKNOWN, tempPath.c_str());
        return false;
    }
    const size_t savedSize = saved.size();
    saved.close();
    if (savedSize != expected) {
        DLOG(CONFIG_WRONG_SIZE,
                      tempPath.c_str(), static_cast<unsigned>(savedSize),
                      static_cast<unsigned>(expected));
        return false;
    }

    // FatFs cannot rename over an existing file. Only remove it after the new
    // file is complete. Power loss between remove and rename is an accepted
    // failure window: loading reports the missing file, with no backup recovery.
    if (SD.exists(path.c_str()) && !SD.remove(path.c_str())) {
        DLOG(CONFIG_REPLACE_FAILED, path.c_str());
        return false;
    }
    if (!SD.rename(tempPath.c_str(), path.c_str())) {
        DLOG(CONFIG_RENAME_FAILED,
                      tempPath.c_str(), path.c_str());
        return false;
    }
    return true;
}

}  // namespace ContentCatalog

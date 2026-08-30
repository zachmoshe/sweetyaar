#include "NVSConfig.h"
#include "Config.h"
#include <ArduinoJson.h>

void NVSConfig::begin() {
    // Ensure the namespace exists; individual accessors open/close as needed.
    _prefs.begin(NVS_NAMESPACE, false);
    _prefs.end();
}

String NVSConfig::getBtName() const {
    String json = readDeviceConfigJson();
    if (!json.isEmpty()) {
        JsonDocument doc;
        DeserializationError err = deserializeJson(doc, json);
        if (!err) {
            const char* name = doc["btName"] | DEFAULT_BT_NAME;
            if (name && name[0] != '\0') {
                return String(name);
            }
        }
    }
    return DEFAULT_BT_NAME;
}

void NVSConfig::setBtName(const String& name) {
    String clean = name;
    clean.trim();
    if (clean.isEmpty()) clean = DEFAULT_BT_NAME;

    String existingJson = readDeviceConfigJson();
    JsonDocument doc;
    if (!existingJson.isEmpty()) {
        deserializeJson(doc, existingJson);
    }
    doc["schemaVersion"] = 1;
    doc["btName"] = clean;

    String json;
    serializeJson(doc, json);
    writeDeviceConfigJson(json);
}

String NVSConfig::readDeviceConfigJson() const {
    _prefs.begin(NVS_NAMESPACE, true);
    String json = _prefs.getString(NVS_KEY_DEVICE_CONFIG, "");
    _prefs.end();
    return json;
}

void NVSConfig::writeDeviceConfigJson(const String& json) {
    _prefs.begin(NVS_NAMESPACE, false);
    _prefs.putString(NVS_KEY_DEVICE_CONFIG, json);
    _prefs.end();
}

#include "ContentCatalog.h"
#include "ParentConfig.h"
#include "BedtimeMode.h"

#include <cassert>
#include <ctime>
#include <iostream>
#include <array>

// Hardware/transport boundaries. The settings handler, configuration I/O and
// volume/bedtime policy below come directly from the production sources.
ParentConfig parentConfig;
bool sdReady = true;
bool btLinkConnected = false;
String currentDeviceName = "SweetYaar";
String activeTheme;
uint8_t currentVolumePct = 0;
uint8_t currentEffectiveVolumePct = 0;
String bedtimeThemeOverride;
String lastInvalidBedtimeThemeLog;
BedtimeMode::Override bedtimeOverride = BedtimeMode::Override::None;
time_t bedtimeOverrideUntilUtc = 0;
bool lastBedtimeActive = false;
String themeIds[] = {"lullabies", "nature", "stories"};
int themeCount = 3;

enum class State { IDLE, BT_STREAMING };
struct {
    State currentState() const { return State::IDLE; }
    bool loopMode() const { return false; }
} sm;
struct { void setVolume(float) {} } volumeOut;
struct { void setBtName(const String&) {} } nvs;
enum class StatusSignal { Error };
struct { void setSignal(StatusSignal, bool) {} } statusLed;
struct {
    String response;
    std::array<String, BLE_CONFIG_ATTRIBUTE_COUNT> attributes;
    std::vector<size_t> changed;
    void updateConfigResponse(const String& value) { response = value; }
    void updateConfigAttribute(size_t index, const String& value) {
        assert(value.length() <= BLE_CONFIG_MAX_BYTES);
        if (attributes[index] != value) {
            attributes[index] = value;
            changed.push_back(index);
        }
    }
} bleService;

void publishConfigAttributes();
void pollBedtimeMode();
void refreshThemeList() {}
void applyDeviceName(const String&) {}
void publishBleValues() { publishConfigAttributes(); }
bool clockKnown = true;
uint32_t localSecond = 12 * 3600;
bool bedtimeTimeKnown() { return clockKnown; }
bool bedtimeLocalMinute(uint16_t& minute) { minute = localSecond / 60; return clockKnown; }
uint32_t bedtimeLocalSecondOfDay() { return localSecond; }
String bedtimeCurrentTimeString() {
    return clockKnown ? ContentCatalog::formatTimeOfDay(localSecond / 60) : String("");
}
void syncBedtimeClock(time_t epoch, int16_t offset) {
    clockKnown = true;
    localSecond = (epoch + offset * 60) % 86400;
    pollBedtimeMode();
}
namespace ContentCatalog { String catalogWarning() { return ""; } }

#include "settings_production.inc"

void prepare(bool bedtime = false) {
    FakeSD::reset();
    FakeSD::files[SD_CONFIG_FILE] = R"({
        "defaultVolumePct":75,"defaultTheme":"lullabies",
        "bedtime":{"enabled":true,"startTime":"18:30","endTime":"06:30",
                   "theme":"lullabies","volumeCapPct":45}
    })";
    assert(parentConfig.load());
    activeTheme = "nature";
    bedtimeThemeOverride = bedtime ? "stories" : "";
    bedtimeOverride = bedtime ? BedtimeMode::Override::ForceOn : BedtimeMode::Override::None;
    bedtimeOverrideUntilUtc = bedtime ? time(nullptr) + 3600 : 0;
    lastBedtimeActive = bedtime;
    applyVolume(bedtime ? 70 : 20);
}

void save(const char* json, bool expectSuccess = true) {
    JsonDocument doc;
    assert(!deserializeJson(doc, json));
    bleService.response = "";
    saveSettings(doc);
    JsonDocument response;
    assert(!deserializeJson(response, bleService.response.c_str()));
    assert(response["ok"].as<bool>() == expectSuccess);
    if (expectSuccess) assert(response.size() == 3); // id, ok, op only
}

void assertLive(uint8_t volume = 20, const char* theme = "nature") {
    assert(currentVolumePct == volume);
    assert(activeTheme == theme);
}

int main(int argc, char** argv) {
    assert(argc == 2);
    const std::string scenario = argv[1];
    prepare();

    if (scenario == "bridge") {
        clockKnown = false;
        publishConfigAttributes();
        std::string line;
        while (std::getline(std::cin, line)) {
            JsonDocument command;
            assert(!deserializeJson(command, line));
            bleService.changed.clear();
            bleService.response = "";
            const String op = command["op"] | "";
            if (op == "setConfig") saveSettings(command);
            else if (op == "syncTime" || op == "setBedtimeMode") runtimeCommand(command);
            else if (op == "advance") {
                localSecond = command["second"].as<uint32_t>();
                if (command["expireOverride"] | false) bedtimeOverrideUntilUtc = 0;
                pollBedtimeMode(); // No app command: firmware pushes the transition.
            }
            JsonDocument result;
            JsonDocument reply;
            if (!bleService.response.isEmpty()) {
                assert(!deserializeJson(reply, bleService.response.c_str()));
                result["reply"] = reply;
            }
            JsonArray attributes = result["attributes"].to<JsonArray>();
            for (const String& value : bleService.attributes) {
                JsonDocument attribute;
                assert(!deserializeJson(attribute, value.c_str()));
                attributes.add(attribute);
            }
            JsonArray changed = result["changed"].to<JsonArray>();
            for (size_t index : bleService.changed) changed.add(index);
            result["volume"] = currentVolumePct;
            std::string output;
            serializeJson(result, output);
            std::cout << output << std::endl;
        }
        return 0;
    }

    if (scenario == "name_limits") {
        const String previousName = currentDeviceName;
        save(R"({"deviceName":"abcdefghijklmnopqrstuvwxyz0123456"})", false);
        assert(currentDeviceName == previousName);
        save(R"({"deviceName":"שששששששששששששששש"})"); // exactly 32 UTF-8 bytes
        const String acceptedName = currentDeviceName;
        save(R"({"deviceName":"ששששששששששששששששש"})", false);
        assert(currentDeviceName == acceptedName);
        save(R"({"defaultTheme":"abcdefghijklmnopqrstuvwxyz012345abcdefghijklmnopqrstuvwxyz012345"})", false);
        assert(parentConfig.defaultTheme() == "lullabies");
        assertLive();
    } else if (scenario == "missing_sd") {
        sdReady = false;
        save(R"({"defaultVolumePct":41})", false);
        assert(parentConfig.defaultVolumePct() == 75);
        assertLive();
    } else if (scenario == "group_limits") {
        JsonDocument doc;
        doc["deviceName"] = std::string(32, '"');
        doc["defaultTheme"] = std::string(63, '"');
        doc["bedtime"]["theme"] = std::string(63, '"');
        doc["bedtime"]["volumeCapPct"] = 100;
        themeIds[0] = std::string(63, '"');
        activeTheme = themeIds[0];
        saveSettings(doc);
        assert(parentConfig.defaultTheme() == themeIds[0]);
        assert(parentConfig.bedtimeTheme() == themeIds[0]);
        bedtimeOverride = BedtimeMode::Override::ForceOn;
        bedtimeOverrideUntilUtc = time(nullptr) + 3600;
        applyVolume(100);
        pollBedtimeMode();
        publishConfigAttributes();
        for (const auto& value : bleService.attributes) {
            assert(!value.isEmpty() && value.length() <= BLE_CONFIG_MAX_BYTES);
        }
        assert(bleService.attributes[3].length() > 400);
    } else if (scenario == "defaults") {
        save(R"({"defaultVolumePct":42})");
        assert(parentConfig.defaultVolumePct() == 42);
        assertLive();  // Reported bug: changing default volume resets live theme.
        save(R"({"defaultTheme":"stories"})");
        assert(parentConfig.defaultTheme() == "stories");
        assert(parentConfig.defaultVolumePct() == 42);
        assertLive();
        save(R"({"deviceName":"SweetYaar Night"})");
        assertLive();
        assert(currentEffectiveVolumePct == 20);
    } else if (scenario == "unrelated") {
        for (auto mode : {BedtimeMode::Override::ForceOn, BedtimeMode::Override::ForceOff}) {
            prepare(true);
            bedtimeOverride = mode;
            lastBedtimeActive = bedtimeRuntimeActive();
            const auto expiry = bedtimeOverrideUntilUtc;
            for (const char* patch : {R"({"deviceName":"Night"})",
                                     R"({"defaultVolumePct":42})",
                                     R"({"defaultTheme":"stories"})",
                                     R"({"sleep":{"normalIdleSec":900}})"}) {
                save(patch);
                assertLive(70);
                assert(bedtimeOverride == mode);
                assert(bedtimeOverrideUntilUtc == expiry);
                assert(bedtimeThemeOverride == "stories");
            }
            assert(parentConfig.sleepNormalIdleMs() == 900000);
        }
    } else if (scenario == "bedtime_cap") {
        prepare(true);
        const auto expiry = bedtimeOverrideUntilUtc;
        for (int cap : {30, 80}) {
            const auto json = std::string("{\"bedtime\":{\"volumeCapPct\":") + std::to_string(cap) + "}}";
            save(json.c_str());
            assertLive(70);
            assert(currentEffectiveVolumePct == (cap == 30 ? 30 : 70));
            assert(bedtimeOverride == BedtimeMode::Override::ForceOn);
            assert(bedtimeOverrideUntilUtc == expiry);
            assert(bedtimeEffectiveSongTheme() == "stories");
        }
    } else if (scenario == "bedtime_theme") {
        prepare(true);
        save(R"({"bedtime":{"theme":"nature"}})");
        assertLive(70);
        assert(bedtimeOverride == BedtimeMode::Override::ForceOn);
        assert(bedtimeThemeOverride.isEmpty());
        assert(bedtimeEffectiveSongTheme() == "nature");
        assert(currentEffectiveVolumePct == 45);
    } else if (scenario == "bedtime_schedule") {
        prepare(true);
        save(R"({"bedtime":{"startTime":"19:00"}})");
        assertLive(70);
        assert(bedtimeOverride == BedtimeMode::Override::None);
        assert(bedtimeOverrideUntilUtc == 0);
        assert(!bedtimeRuntimeActive());  // Test clock is noon.
        assert(currentEffectiveVolumePct == 70);
    } else if (scenario == "bedtime_disabled") {
        prepare(true);
        save(R"({"bedtime":{"enabled":false}})");
        assertLive(70);
        assert(!bedtimeRuntimeActive());
        assert(bedtimeOverride == BedtimeMode::Override::None);
        assert(bedtimeThemeOverride.isEmpty());
        assert(currentEffectiveVolumePct == 70);
    } else if (scenario == "unchanged_bedtime") {
        prepare(true);
        const auto expiry = bedtimeOverrideUntilUtc;
        save(R"({"bedtime":{"enabled":true,"startTime":"18:30","endTime":"06:30",
                              "theme":"lullabies","volumeCapPct":45}})");
        assertLive(70);
        assert(bedtimeOverride == BedtimeMode::Override::ForceOn);
        assert(bedtimeOverrideUntilUtc == expiry);
        assert(bedtimeThemeOverride == "stories");
    } else if (scenario == "failed_save") {
        prepare(true);
        FakeSD::failWriteOpen = true;
        save(R"({"defaultVolumePct":42,"defaultTheme":"stories",
                  "bedtime":{"enabled":false,"theme":"nature"}})", false);
        assertLive(70);
        assert(parentConfig.defaultVolumePct() == 75);
        assert(parentConfig.defaultTheme() == "lullabies");
        assert(bedtimeOverride == BedtimeMode::Override::ForceOn);
        assert(bedtimeThemeOverride == "stories");
        assert(currentEffectiveVolumePct == 45);
    } else if (scenario == "boot_defaults") {
        save(R"({"defaultVolumePct":42})");
        save(R"({"defaultTheme":"stories"})");
        assertLive();
        // A new ParentConfig models reload on cold boot or deep-sleep wake;
        // execute the same default-application statements used by setup().
        parentConfig = ParentConfig();
        assert(parentConfig.load());
        applyBootDefaults();
        assertLive(42, "stories");
        assert(currentEffectiveVolumePct == 42);
    } else {
        assert(false && "Unknown test scenario");
    }
    std::cout << "settings runtime test passed: " << scenario << '\n';
}

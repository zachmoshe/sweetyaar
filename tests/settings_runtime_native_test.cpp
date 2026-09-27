#include "ContentCatalog.h"
#include "ParentConfig.h"
#include "BedtimeMode.h"

#include <cassert>
#include <ctime>
#include <iostream>

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
struct { State currentState() const { return State::IDLE; } } sm;
struct { void setVolume(float) {} } volumeOut;
struct { void setBtName(const String&) {} } nvs;
enum class StatusSignal { Error };
struct { void setSignal(StatusSignal, bool) {} } statusLed;
struct {
    String response;
    void updateConfigResponse(const String& value) { response = value; }
} bleService;

String buildConfigResponse(uint32_t) { return "ok"; }
String buildConfigErrorResponse(uint32_t, const char*) { return "error"; }
void refreshThemeList() {}
void applyDeviceName(const String&) {}
void publishBleValues() {}
bool bedtimeTimeKnown() { return true; }
bool bedtimeLocalMinute(uint16_t& minute) { minute = 12 * 60; return true; }

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
    assert(bleService.response == (expectSuccess ? "ok" : "error"));
}

void assertLive(uint8_t volume = 20, const char* theme = "nature") {
    assert(currentVolumePct == volume);
    assert(activeTheme == theme);
}

int main(int argc, char** argv) {
    assert(argc == 2);
    const std::string scenario = argv[1];
    prepare();

    if (scenario == "defaults") {
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

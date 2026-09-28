"""Reply builders must work when ArduinoJson cannot allocate its pool."""

import shutil

import pytest

from helpers import run_checked
from test_settings_runtime import function_source


def test_config_replies_and_attributes_survive_json_allocation_failure(repo_root, tmp_path):
    compiler = shutil.which("c++")
    if not compiler:
        pytest.skip("A C++ compiler is required for reply tests.")
    json_include = repo_root / "firmware/esp32/.pio/libdeps/sweetyaar/ArduinoJson/src"
    assert (json_include / "ArduinoJson.h").exists()
    main = (repo_root / "firmware/esp32/src/main.cpp").read_text()
    catalog = (repo_root / "firmware/esp32/src/ContentCatalog.cpp").read_text()
    program = tmp_path / "config_reply_memory.cpp"
    program.write_text(r'''
#include <Arduino.h>
#include <ArduinoJson.h>
#include <cassert>
#include <iostream>

struct DeniedAllocator : ArduinoJson::Allocator {
    void* allocate(size_t) override { return nullptr; }
    void* reallocate(void*, size_t) override { return nullptr; }
    void deallocate(void*) override {}
} denied;
class FailedJsonDocument : public JsonDocument {
public:
    FailedJsonDocument() : JsonDocument(&denied) {}
};
constexpr size_t BLE_CONFIG_MAX_BYTES = 512;
String currentDeviceName = "צעצוע\"\\\n";
String activeTheme = "nature\"\\\n";
bool sdReady = true;
bool loaded = true;
bool clockKnown = true;
struct {
    uint8_t defaultVolumePct() { return 37; }
    String defaultTheme() { return activeTheme; }
    bool loaded() { return ::loaded; }
    bool sleepEnabled() { return false; }
    uint32_t sleepNormalIdleMs() { return 86400000; }
    uint32_t sleepVibrationWakeIdleMs() { return 120000; }
    uint32_t sleepBleIdleMs() { return 60000; }
    bool bedtimeEnabled() { return true; }
    uint16_t bedtimeStartMinutes() { return 1110; }
    uint16_t bedtimeEndMinutes() { return 390; }
    String bedtimeTheme() { return activeTheme; }
    uint8_t bedtimeVolumeCapPct() { return 25; }
} parentConfig;
struct { bool loopMode() { return true; } } sm;
String bedtimeTimeString(uint16_t minutes) { return minutes == 1110 ? "18:30" : "06:30"; }
bool bedtimeTimeKnown() { return clockKnown; }
String bedtimeCurrentTimeString() { return clockKnown ? "20:00" : ""; }
uint32_t bedtimeLocalSecondOfDay() { return 72000; }
bool bedtimeRuntimeActive() { return true; }
bool bedtimeAutomaticActive() { return false; }
String bedtimeOverrideName() { return "on"; }
uint8_t effectiveVolumePct() { return 25; }
String bedtimeEffectiveSongTheme() { return activeTheme; }
namespace ContentCatalog {
String catalogWarning() { return "Ignored \"שיר\"\\\n"; }
''' + function_source(catalog, "jsonEscape") + r'''
}
// Inject failure into any document created by the real reply builders.
#define JsonDocument FailedJsonDocument
''' + function_source(main, "buildConfigOkResponse") + "\n" +
        function_source(main, "buildConfigAttribute") + "\n" +
        function_source(main, "buildConfigErrorResponse") + r'''
#undef JsonDocument

int main() {
    // The former builder produces this two-byte response under allocation
    // failure. Validate the failure injection itself.
    FailedJsonDocument exhausted;
    exhausted["id"] = 10;
    exhausted["ok"] = true;
    exhausted["op"] = "setConfig";
    String empty;
    serializeJson(exhausted, empty);
    assert(exhausted.overflowed() && empty == "{}");

    for (uint32_t id : {0u, 10u, 4294967295u}) {
        for (const char* op : {"setConfig", "syncTime", "setBedtimeMode", "setTheme", "setSong", "quote\"\\\n"}) {
            const String text = buildConfigOkResponse(id, op);
            std::cout << "reply=" << text.c_str() << std::endl;
            JsonDocument reply;
            assert(!deserializeJson(reply, text.c_str()));
            assert(reply.size() == 3);
            assert(reply["id"].as<uint32_t>() == id);
            assert(reply["ok"].as<bool>());
            assert(reply["op"].as<std::string>() == op);
        }
        const char* message = "SD write failed: \"שיר\" \\ \n\t";
        const String text = buildConfigErrorResponse(id, message);
        JsonDocument reply;
        assert(!deserializeJson(reply, text.c_str()));
        assert(reply.size() == 3);
        assert(reply["id"].as<uint32_t>() == id);
        assert(!reply["ok"].as<bool>());
        assert(reply["error"].as<std::string>() == message);
    }
    const size_t sizes[] = {4, 4, 5, 10, 1};
    for (size_t group = 0; group < 5; ++group) {
        const String text = buildConfigAttribute(group);
        assert(text.length() <= BLE_CONFIG_MAX_BYTES);
        JsonDocument state;
        assert(!deserializeJson(state, text.c_str()));
        assert(state.size() == sizes[group]);
        if (group == 0) {
            assert(state["deviceName"].as<std::string>() == currentDeviceName.c_str());
            assert(state["defaultVolumePct"] == 37);
            assert(state["defaultTheme"].as<std::string>() == activeTheme.c_str());
            assert(state["sdReady"] == true);
        } else if (group == 1) {
            assert(state["enabled"] == false);
            assert(state["normalIdleSec"] == 86400);
            assert(state["vibrationWakeIdleSec"] == 120);
            assert(state["bleIdleSec"] == 60);
        } else if (group == 2) {
            assert(state["enabled"] == true);
            assert(state["startTime"] == "18:30" && state["endTime"] == "06:30");
            assert(state["theme"].as<std::string>() == activeTheme.c_str());
            assert(state["volumeCapPct"] == 25);
        } else if (group == 3) {
            assert(state["timeKnown"] == true && state["loop"] == true);
            assert(state["currentSecondOfDay"] == 72000);
            assert(state["activeTheme"].as<std::string>() == activeTheme.c_str());
            assert(state["effectiveTheme"].as<std::string>() == activeTheme.c_str());
            assert(state["active"] == true && state["autoActive"] == false);
            assert(state["override"] == "on" && state["effectiveVolumePct"] == 25);
        } else {
            assert(state["message"].as<std::string>() == ContentCatalog::catalogWarning().c_str());
        }
    }
    loaded = false;
    clockKnown = false;
    JsonDocument state;
    assert(!deserializeJson(state, buildConfigAttribute(0).c_str()));
    assert(state["error"].as<std::string>().find("Settings file") == 0);
    assert(!deserializeJson(state, buildConfigAttribute(3).c_str()));
    assert(state["timeKnown"] == false && state["currentSecondOfDay"] == -1);
    assert(state["currentTime"] == "");
}
''')
    exe = tmp_path / "config_reply_memory"
    run_checked([
        compiler, "-std=c++17", "-Wall", "-Wextra",
        "-I", repo_root / "tests/native_stubs", "-I", json_include,
        program, "-o", exe,
    ])
    run_checked([exe])

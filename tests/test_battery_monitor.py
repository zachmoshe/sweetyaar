"""Exercise the production battery monitor with deterministic time and ADC input."""

from __future__ import annotations

import pathlib
import shutil

import pytest

from helpers import run_checked


@pytest.fixture(scope="module")
def battery_monitor_exe(repo_root: pathlib.Path, tmp_path_factory) -> pathlib.Path:
    compiler = shutil.which("c++") or shutil.which("g++") or shutil.which("clang++")
    if not compiler:
        pytest.skip("No C++ compiler found for native battery regression tests.")

    build_dir = tmp_path_factory.mktemp("battery_monitor")
    (build_dir / "Arduino.h").write_text(r"""
#pragma once
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <deque>
constexpr int INPUT = 0, ADC_2_5db = 1;
inline uint32_t g_fakeMillis = 0;
inline unsigned g_adcReads = 0;
inline int g_inputPin = -1, g_adcPin = -1;
inline std::deque<uint32_t> g_adcValues;
inline uint32_t millis() { return g_fakeMillis; }
inline void pinMode(int pin, int mode) {
    assert(mode == INPUT);
    g_inputPin = pin;
}
inline void analogSetPinAttenuation(int pin, int attenuation) {
    assert(attenuation == ADC_2_5db);
    g_adcPin = pin;
}
inline uint32_t analogReadMilliVolts(int pin) {
    assert(pin == g_inputPin && pin == g_adcPin);
    assert(!g_adcValues.empty());
    ++g_adcReads;
    uint32_t result = g_adcValues.front();
    g_adcValues.pop_front();
    return result;
}
// Any reintroduced wait is a regression, even if a later poll eventually works.
inline void delay(uint32_t) { assert(false && "Battery monitor must not delay"); }
struct SerialClass {
    template <typename... Args> void printf(const char*, Args...) {}
    void println(const char*) {}
};
inline SerialClass Serial;
""")
    exe = build_dir / "battery_monitor_test"
    run_checked([
        compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror",
        "-I", build_dir,
        "-I", repo_root / "firmware/esp32/src",
        repo_root / "firmware/esp32/src/BatteryMonitor.cpp",
        repo_root / "tests/battery_monitor_native_test.cpp",
        "-o", exe,
    ])
    return exe


@pytest.mark.parametrize("scenario", [
    "startup", "late_poll", "seed_weight", "invalid_startup", "wraparound", "restart",
])
def test_battery_monitor(battery_monitor_exe: pathlib.Path, scenario: str) -> None:
    result = run_checked([battery_monitor_exe, scenario])
    assert "battery monitor test passed" in result.stdout

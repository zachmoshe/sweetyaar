"""Exercise the real charger driver with scripted I2C, GPIO and serial output."""

from __future__ import annotations

import pathlib
import re
import shutil

import pytest

from helpers import run_checked


def test_charger_status_logging(repo_root: pathlib.Path, tmp_path: pathlib.Path) -> None:
    compiler = shutil.which("c++") or shutil.which("g++") or shutil.which("clang++")
    if not compiler:
        pytest.skip("No C++ compiler found for native charger regression test.")

    stubs = tmp_path / "stubs"
    (stubs / "driver").mkdir(parents=True)
    (stubs / "Arduino.h").write_text(r"""
#pragma once
#include <array>
#include <cstdint>
#include <cstdio>
#include <string>
#include <vector>
#define IRAM_ATTR
constexpr int LOW = 0, HIGH = 1, INPUT = 0, OUTPUT = 1, FALLING = 2;
inline uint32_t g_fakeMillis = 0;
inline std::array<int, 40> g_pins{};
inline void (*g_interruptHandler)() = nullptr;
inline uint32_t millis() { return g_fakeMillis; }
inline void pinMode(int, int) {}
inline int digitalRead(int pin) { return g_pins.at(pin); }
inline void digitalWrite(int pin, int value) { g_pins.at(pin) = value; }
inline int digitalPinToInterrupt(int pin) { return pin; }
inline void attachInterrupt(int, void (*handler)(), int) { g_interruptHandler = handler; }
struct SerialClass {
    std::string output;
    template <typename... Args>
    void printf(const char* format, Args... args) {
        std::vector<char> buffer(std::snprintf(nullptr, 0, format, args...) + 1);
        std::snprintf(buffer.data(), buffer.size(), format, args...);
        output += buffer.data();
    }
    void println(const char* text) { output += std::string(text) + "\n"; }
};
inline SerialClass Serial;
""")
    (stubs / "Wire.h").write_text(r"""
#pragma once
#include <array>
#include <cassert>
#include <cstdint>
#include <vector>
struct WireClass {
    std::array<uint8_t, 13> registers{};
    std::array<unsigned, 13> reads{};
    int failReadRegister = -1;
    uint8_t selected = 0, received = 0;
    int availableBytes = 0;
    std::vector<uint8_t> written;
    bool begin(int, int, int) { return true; }
    void setTimeOut(int) {}
    void beginTransmission(int address) {
        assert(address == 0x6A);
        written.clear();
    }
    void write(uint8_t value) { written.push_back(value); }
    uint8_t endTransmission(bool) {
        assert(written.size() == 1 || written.size() == 2);
        selected = written.at(0);
        if (written.size() == 2) registers.at(selected) = written.at(1);
        return 0;
    }
    int requestFrom(int address, int count, int) {
        assert(address == 0x6A && count == 1);
        ++reads.at(selected);
        availableBytes = selected == failReadRegister ? 0 : 1;
        if (availableBytes) {
            received = registers.at(selected);
            if (selected == 0x02) registers.at(selected) = 0; // FLAG0 read-to-clear
        }
        return availableBytes;
    }
    int available() { return availableBytes; }
    int read() { availableBytes = 0; return received; }
};
inline WireClass Wire;
""")
    (stubs / "driver" / "rtc_io.h").write_text("""
#pragma once
using gpio_num_t = int;
inline void rtc_gpio_deinit(gpio_num_t) {}
""")

    # Exercise the actual local-time provider with a controlled UTC clock.
    main = (repo_root / "firmware/esp32/src/main.cpp").read_text()
    clock_functions = []
    for name in ("bedtimeTimeKnown", "readLocalLogTime"):
        match = re.search(rf"^bool {name}\([^;]*?\) \{{", main, re.MULTILINE)
        assert match, f"Missing production function: {name}"
        clock_functions.append(main[match.start():main.index("\n}", match.end()) + 2])
    (stubs / "charger_clock.inc").write_text("\n".join(clock_functions))

    exe = tmp_path / "charger_status_test"
    run_checked([
        compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror",
        "-I", stubs,
        "-I", repo_root / "firmware/esp32/src",
        repo_root / "firmware/esp32/src/BQ25186Charger.cpp",
        repo_root / "firmware/esp32/src/ChargerStatus.cpp",
        repo_root / "tests/charger_status_native_test.cpp",
        "-o", exe,
    ])
    result = run_checked([exe])
    assert "charger status native test passed" in result.stdout


def test_charger_status_interpretation(repo_root: pathlib.Path, tmp_path: pathlib.Path) -> None:
    compiler = shutil.which("c++") or shutil.which("g++") or shutil.which("clang++")
    if not compiler:
        pytest.skip("No C++ compiler found for native charger regression test.")

    exe = tmp_path / "charger_status_module_test"
    run_checked([
        compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror",
        "-I", repo_root / "firmware/esp32/src",
        repo_root / "firmware/esp32/src/ChargerStatus.cpp",
        repo_root / "tests/charger_status_module_native_test.cpp",
        "-o", exe,
    ])
    result = run_checked([exe])
    assert "charger status module test passed" in result.stdout

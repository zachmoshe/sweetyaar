#pragma once

#include <cstdarg>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <string>

#include "freertos/queue.h"

class String {
public:
    String() = default;
    String(const char* value) : _value(value ? value : "") {}
    String(char* value) : _value(value ? value : "") {}
    String(const std::string& value) : _value(value) {}
    String(int value) : _value(std::to_string(value)) {}
    String(unsigned int value) : _value(std::to_string(value)) {}
    String(long value) : _value(std::to_string(value)) {}
    String(unsigned long value) : _value(std::to_string(value)) {}

    const char* c_str() const { return _value.c_str(); }
    std::size_t length() const { return _value.length(); }
    bool isEmpty() const { return _value.empty(); }
    String operator+(const char* suffix) const { return String(_value + suffix); }
    String substring(std::size_t begin, std::size_t end) const {
        return _value.substr(begin, end - begin);
    }
    void trim() {
        const auto begin = _value.find_first_not_of(" \t\r\n");
        if (begin == std::string::npos) {
            _value.clear();
            return;
        }
        _value = _value.substr(begin, _value.find_last_not_of(" \t\r\n") - begin + 1);
    }

    long toInt() const {
        char* end = nullptr;
        long parsed = std::strtol(_value.c_str(), &end, 10);
        return end == _value.c_str() ? 0 : parsed;
    }

    bool operator==(const String& other) const { return _value == other._value; }
    bool operator!=(const String& other) const { return !(*this == other); }
    bool operator==(const char* other) const { return _value == (other ? other : ""); }
    bool operator!=(const char* other) const { return !(*this == other); }

private:
    std::string _value;
};

inline bool operator==(const char* left, const String& right) {
    return right == left;
}

struct SerialClass {
    template <typename... Args>
    void printf(const char*, Args...) {}

    void println(const char*) {}
};

inline SerialClass Serial;

extern uint32_t g_fakeMillis;

inline uint32_t millis() {
    return g_fakeMillis;
}

static constexpr int HIGH = 1;
static constexpr int LOW = 0;

inline void digitalWrite(int, int) {}

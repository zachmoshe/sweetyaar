#pragma once

#include <cstdarg>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <string>
#include <type_traits>

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
    void reserve(std::size_t size) { _value.reserve(size); }
    std::size_t write(uint8_t value) { _value += static_cast<char>(value); return 1; }
    std::size_t write(const uint8_t* value, std::size_t size) {
        _value.append(reinterpret_cast<const char*>(value), size);
        return size;
    }
    char operator[](std::size_t index) const { return _value[index]; }
    bool endsWith(const char* suffix) const {
        const std::string text(suffix);
        return _value.size() >= text.size() &&
            _value.compare(_value.size() - text.size(), text.size(), text) == 0;
    }
    String& operator+=(const String& value) { _value += value._value; return *this; }
    String& operator+=(const char* value) { _value += value; return *this; }
    String& operator+=(char value) { _value += value; return *this; }
    template <typename T, std::enable_if_t<std::is_integral_v<T>, int> = 0>
    String& operator+=(T value) { _value += std::to_string(value); return *this; }
    String operator+(const char* suffix) const { return String(_value + suffix); }
    String operator+(const String& suffix) const { return String(_value + suffix._value); }
    friend String operator+(const char* prefix, const String& suffix) { return String(prefix) + suffix; }
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
static constexpr int INPUT_PULLUP = 2;

void pinMode(int pin, int mode);
int digitalRead(int pin);

inline void digitalWrite(int, int) {}

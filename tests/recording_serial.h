#pragma once
#include <cstdarg>
#include <cstdio>
#include <string>

struct RecordingSerial {
    std::string output;
    void printf(const char* format, ...) {
        char line[768];
        va_list arguments;
        va_start(arguments, format);
        vsnprintf(line, sizeof(line), format, arguments);
        va_end(arguments);
        output += line;
    }
    void println(const char* message) { output += std::string(message) + "\n"; }
};
inline RecordingSerial Serial;

#pragma once

// Byte layout of the on-flash diagnostic log (format version 1). See
// docs/logging-and-debugging.md; the decoder depends on every value here.

#include <stddef.h>
#include <stdint.h>
#include <string.h>
#include <type_traits>

namespace devlog {

constexpr uint32_t SECTOR_SIZE = 4096;
constexpr uint8_t FORMAT_VERSION = 1;
constexpr size_t SECTOR_HEADER_SIZE = 24;
constexpr size_t RECORD_HEADER_SIZE = 7;  // length, ID, milliseconds since boot
constexpr size_t RECORD_OVERHEAD = RECORD_HEADER_SIZE + 1;  // plus CRC-8
constexpr size_t MAX_PAYLOAD = 240;
constexpr size_t MAX_RECORD = RECORD_OVERHEAD + MAX_PAYLOAD;
constexpr size_t MAX_STRING = 63;
constexpr size_t MAX_ARGS = 32;
constexpr uint8_t ERASED_BYTE = 0xFF;
constexpr uint8_t TRUNCATED_FLAG = 0x80;

enum ArgType : uint8_t {
    ARG_UNSIGNED = 1,  // LEB128 varint
    ARG_SIGNED = 2,    // zigzag LEB128 varint
    ARG_STRING = 3,    // length byte, then at most MAX_STRING bytes
    ARG_FLOAT = 4,     // IEEE 754 single, little-endian
    ARG_BYTES = 5,     // length byte, then raw bytes
};

// CRC-8, polynomial 0x07, initial value 0.
inline uint8_t crc8(const uint8_t* data, size_t length, uint8_t crc = 0) {
    for (size_t i = 0; i < length; ++i) {
        crc ^= data[i];
        for (int bit = 0; bit < 8; ++bit) {
            crc = (crc & 0x80U) ? static_cast<uint8_t>((crc << 1) ^ 0x07U)
                                : static_cast<uint8_t>(crc << 1);
        }
    }
    return crc;
}

inline void putLe16(uint8_t* out, uint16_t value) {
    out[0] = static_cast<uint8_t>(value);
    out[1] = static_cast<uint8_t>(value >> 8);
}

inline void putLe32(uint8_t* out, uint32_t value) {
    for (int i = 0; i < 4; ++i) out[i] = static_cast<uint8_t>(value >> (8 * i));
}

inline uint16_t getLe16(const uint8_t* in) {
    return static_cast<uint16_t>(in[0] | (in[1] << 8));
}

inline uint32_t getLe32(const uint8_t* in) {
    return static_cast<uint32_t>(in[0]) | (static_cast<uint32_t>(in[1]) << 8) |
           (static_cast<uint32_t>(in[2]) << 16) | (static_cast<uint32_t>(in[3]) << 24);
}

// Raw bytes argument (a core dump chunk).
struct Bytes {
    const uint8_t* data;
    size_t length;
};

// Packs self-describing arguments into a record payload: argument count, one
// type nibble per argument, then the values. A value that does not fit is
// dropped together with everything after it, and the count gets
// TRUNCATED_FLAG.
class Packer {
public:
    Packer(uint8_t* buffer, size_t capacity, size_t argCount)
        : _buffer(buffer), _capacity(capacity) {
        if (argCount > MAX_ARGS) argCount = MAX_ARGS;
        _argCount = argCount;
        const size_t typeBytes = (argCount + 1) / 2;
        if (capacity < 1 + typeBytes) {
            _argCount = 0;
            _size = capacity > 0 ? 1 : 0;
            if (_size) _buffer[0] = TRUNCATED_FLAG;
            _truncated = true;
            return;
        }
        _buffer[0] = static_cast<uint8_t>(argCount);
        memset(_buffer + 1, 0, typeBytes);
        _size = 1 + typeBytes;
    }

    size_t size() const { return _size; }
    bool truncated() const { return _truncated; }

    template <typename T>
    typename std::enable_if<std::is_integral<T>::value && std::is_unsigned<T>::value>::type
    add(T value) { addUnsigned(static_cast<uint64_t>(value)); }

    template <typename T>
    typename std::enable_if<std::is_integral<T>::value && std::is_signed<T>::value>::type
    add(T value) { addSigned(static_cast<int64_t>(value)); }

    template <typename T>
    typename std::enable_if<std::is_floating_point<T>::value>::type
    add(T value) { addFloat(static_cast<float>(value)); }

    // ESP-IDF status codes are plain enums; store their numeric value.
    template <typename T>
    typename std::enable_if<std::is_enum<T>::value>::type
    add(T value) { add(static_cast<typename std::underlying_type<T>::type>(value)); }

    void add(const char* value) {
        if (value == nullptr) value = "";
        size_t length = strlen(value);
        if (length > MAX_STRING) length = MAX_STRING;
        uint8_t* out = begin(ARG_STRING, 1 + length);
        if (!out) return;
        out[0] = static_cast<uint8_t>(length);
        memcpy(out + 1, value, length);
    }

    void add(char* value) { add(static_cast<const char*>(value)); }

    void add(Bytes value) {
        size_t length = value.length > 255 ? 255 : value.length;
        uint8_t* out = begin(ARG_BYTES, 1 + length);
        if (!out) return;
        out[0] = static_cast<uint8_t>(length);
        if (length) memcpy(out + 1, value.data, length);
    }

private:
    // Reserves space for the next argument and records its type.
    uint8_t* begin(ArgType type, size_t length) {
        if (_truncated || _next >= _argCount || _size + length > _capacity) {
            if (!_truncated) _buffer[0] |= TRUNCATED_FLAG;
            _truncated = true;
            return nullptr;
        }
        uint8_t& typeByte = _buffer[1 + _next / 2];
        typeByte |= static_cast<uint8_t>((_next % 2) ? (type << 4) : type);
        ++_next;
        uint8_t* out = _buffer + _size;
        _size += length;
        return out;
    }

    void addUnsigned(uint64_t value) {
        uint8_t encoded[10];
        size_t length = 0;
        do {
            uint8_t byte = static_cast<uint8_t>(value & 0x7FU);
            value >>= 7;
            if (value) byte |= 0x80U;
            encoded[length++] = byte;
        } while (value);
        writeVarint(ARG_UNSIGNED, encoded, length);
    }

    void addSigned(int64_t value) {
        uint64_t zigzag = (static_cast<uint64_t>(value) << 1) ^
                          static_cast<uint64_t>(value >> 63);
        uint8_t encoded[10];
        size_t length = 0;
        do {
            uint8_t byte = static_cast<uint8_t>(zigzag & 0x7FU);
            zigzag >>= 7;
            if (zigzag) byte |= 0x80U;
            encoded[length++] = byte;
        } while (zigzag);
        writeVarint(ARG_SIGNED, encoded, length);
    }

    void writeVarint(ArgType type, const uint8_t* encoded, size_t length) {
        uint8_t* out = begin(type, length);
        if (out) memcpy(out, encoded, length);
    }

    void addFloat(float value) {
        uint32_t bits = 0;
        memcpy(&bits, &value, sizeof(bits));
        uint8_t* out = begin(ARG_FLOAT, 4);
        if (out) putLe32(out, bits);
    }

    uint8_t* _buffer;
    size_t _capacity;
    size_t _argCount = 0;
    size_t _next = 0;
    size_t _size = 0;
    bool _truncated = false;
};

// Reads the unsigned argument at index from a payload. Used by the boot scan
// (boot number and streak); the full decoder lives on the host.
inline bool readUnsignedArg(const uint8_t* payload, size_t length, size_t index,
                            uint32_t& value) {
    if (length < 1) return false;
    const size_t argCount = payload[0] & ~TRUNCATED_FLAG;
    const size_t typeBytes = (argCount + 1) / 2;
    if (index >= argCount || length < 1 + typeBytes) return false;
    size_t pos = 1 + typeBytes;
    for (size_t i = 0; i <= index; ++i) {
        const uint8_t type = (payload[1 + i / 2] >> ((i % 2) * 4)) & 0x0FU;
        if (pos >= length) return false;
        if (type == ARG_UNSIGNED || type == ARG_SIGNED) {
            uint64_t decoded = 0;
            int shift = 0;
            while (true) {
                if (pos >= length || shift > 63) return false;
                const uint8_t byte = payload[pos++];
                decoded |= static_cast<uint64_t>(byte & 0x7FU) << shift;
                shift += 7;
                if (!(byte & 0x80U)) break;
            }
            if (i == index) {
                if (type != ARG_UNSIGNED) return false;
                value = static_cast<uint32_t>(decoded);
                return true;
            }
        } else if (type == ARG_STRING || type == ARG_BYTES) {
            pos += 1 + payload[pos];
        } else if (type == ARG_FLOAT) {
            pos += 4;
        } else {
            return false;
        }
        if (i == index) return false;
    }
    return false;
}

}  // namespace devlog

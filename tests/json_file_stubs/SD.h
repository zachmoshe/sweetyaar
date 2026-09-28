#pragma once

#include <algorithm>
#include <cassert>
#include <cstdint>
#include <cstring>
#include <limits>
#include <map>
#include <memory>
#include <string>
#include <vector>

#define FILE_READ "r"
#define FILE_WRITE "w"

namespace FakeSD {
inline std::map<std::string, std::string> files;
inline std::vector<std::string> operations;
inline size_t writeLimit = std::numeric_limits<size_t>::max();
inline size_t written = 0;
inline size_t readCalls = 0;
inline size_t maxOpenFiles = std::numeric_limits<size_t>::max();
inline size_t openFiles = 0;
inline size_t peakOpenFiles = 0;
inline bool failWriteOpen = false;
inline bool failReadOpen = false;
inline bool truncateOnFlush = false;
inline bool failRemove = false;
inline bool failRename = false;

// File copies share an underlying open slot, as Arduino File handles do.
struct OpenFileSlot {
    OpenFileSlot() { peakOpenFiles = std::max(peakOpenFiles, ++openFiles); }
    ~OpenFileSlot() { --openFiles; }
};

inline void reset() {
    assert(openFiles == 0);
    files.clear();
    operations.clear();
    writeLimit = std::numeric_limits<size_t>::max();
    written = readCalls = 0;
    maxOpenFiles = std::numeric_limits<size_t>::max();
    peakOpenFiles = 0;
    failWriteOpen = failReadOpen = truncateOnFlush = failRemove = failRename = false;
}
}  // namespace FakeSD

class File {
public:
    File() = default;
    File(const std::string& path, bool writable)
        : _path(path), _writable(writable), _slot(std::make_shared<FakeSD::OpenFileSlot>()) {}
    explicit operator bool() const { return static_cast<bool>(_slot); }

    size_t write(uint8_t byte) { return write(&byte, 1); }
    size_t write(const uint8_t* data, size_t count) {
        if (!_slot || !_writable) return 0;
        const size_t accepted = std::min(count, FakeSD::writeLimit - FakeSD::written);
        FakeSD::files[_path].append(reinterpret_cast<const char*>(data), accepted);
        FakeSD::written += accepted;
        return accepted;
    }
    int read() {
        ++FakeSD::readCalls;
        if (!_slot || _position >= FakeSD::files[_path].size()) return -1;
        return static_cast<unsigned char>(FakeSD::files[_path][_position++]);
    }
    size_t readBytes(char* data, size_t count) {
        ++FakeSD::readCalls;
        if (!_slot) return 0;
        const auto& contents = FakeSD::files[_path];
        const size_t available = std::min(count, contents.size() - _position);
        std::memcpy(data, contents.data() + _position, available);
        _position += available;
        return available;
    }
    void flush() {
        FakeSD::operations.push_back("flush:" + _path);
        if (_writable && FakeSD::truncateOnFlush && !FakeSD::files[_path].empty()) {
            FakeSD::files[_path].pop_back();
        }
    }
    void close() {
        FakeSD::operations.push_back("close:" + _path);
        _slot.reset();
    }
    size_t size() const {
        FakeSD::operations.push_back("size:" + _path);
        return _slot ? FakeSD::files[_path].size() : 0;
    }

private:
    std::string _path;
    size_t _position = 0;
    bool _writable = false;
    std::shared_ptr<FakeSD::OpenFileSlot> _slot;
};

class SDClass {
public:
    File open(const char* path, const char* mode = FILE_READ) {
        const bool writable = std::strcmp(mode, FILE_WRITE) == 0;
        FakeSD::operations.push_back(std::string(writable ? "write:" : "read:") + path);
        if (FakeSD::openFiles >= FakeSD::maxOpenFiles) return File();
        if (writable) {
            if (FakeSD::failWriteOpen) return File();
            FakeSD::files[path].clear();
        } else if (FakeSD::failReadOpen || !exists(path)) {
            return File();
        }
        return File(path, writable);
    }
    bool exists(const char* path) const { return FakeSD::files.count(path) != 0; }
    bool remove(const char* path) {
        FakeSD::operations.push_back(std::string("remove:") + path);
        if (FakeSD::failRemove) return false;
        return FakeSD::files.erase(path) != 0;
    }
    bool rename(const char* from, const char* to) {
        FakeSD::operations.push_back(std::string("rename:") + from);
        // Match FatFs: renaming over an existing destination is rejected.
        if (FakeSD::failRename || !exists(from) || exists(to)) return false;
        FakeSD::files[to] = FakeSD::files[from];
        FakeSD::files.erase(from);
        return true;
    }
};

inline SDClass SD;

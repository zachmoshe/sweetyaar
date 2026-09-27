#include "ContentCatalog.h"
#include "ParentConfig.h"

#include <cassert>
#include <iostream>

const std::string original = R"({"defaultVolumePct":75,"defaultTheme":"lullabies"})";

void prepare(const std::string& path) {
    FakeSD::reset();
    FakeSD::files[path] = original;
    // An abandoned, longer temporary file must be truncated, not appended to.
    FakeSD::files[path + ".tmp"] = std::string(2048, 'x');
}

void assertOriginalIntact(const std::string& path) {
    assert(FakeSD::files.at(path) == original);
    assert(std::find(FakeSD::operations.begin(), FakeSD::operations.end(),
                     "remove:" + path) == FakeSD::operations.end());
    assert(FakeSD::readCalls == 0);  // size checks never read JSON contents
}

int main() {
    JsonDocument doc;
    doc["defaultVolumePct"] = 42;
    doc["defaultTheme"] = "nature";
    std::string expected;
    serializeJsonPretty(doc, expected);
    expected += '\n';

    for (const std::string path : {"/config.json", "/songs/nature/metadata.json"}) {
        prepare(path);
        assert(ContentCatalog::writeJsonFile(path.c_str(), doc));
        assert(FakeSD::files.at(path) == expected);
        assert(FakeSD::files.size() == 1);  // no temporary file or backup remains
        assert(FakeSD::readCalls == 0);
        const auto& operations = FakeSD::operations;
        const auto flushed = std::find(operations.begin(), operations.end(), "flush:" + path + ".tmp");
        const auto checked = std::find(operations.begin(), operations.end(), "size:" + path + ".tmp");
        const auto removed = std::find(operations.begin(), operations.end(), "remove:" + path);
        const auto renamed = std::find(operations.begin(), operations.end(), "rename:" + path + ".tmp");
        assert(flushed < checked && checked < removed && removed < renamed);

        // Every possible short write, including just the final newline, fails
        // without removing the original. This also covers a completely full SD.
        for (size_t limit = 0; limit < expected.size(); ++limit) {
            prepare(path);
            FakeSD::writeLimit = limit;
            assert(!ContentCatalog::writeJsonFile(path.c_str(), doc));
            assertOriginalIntact(path);
        }

        prepare(path);
        FakeSD::failWriteOpen = true;
        assert(!ContentCatalog::writeJsonFile(path.c_str(), doc));
        assertOriginalIntact(path);

        prepare(path);
        FakeSD::truncateOnFlush = true;  // writes report success, file is short
        assert(!ContentCatalog::writeJsonFile(path.c_str(), doc));
        assertOriginalIntact(path);

        prepare(path);
        FakeSD::failReadOpen = true;  // cannot inspect the final file size
        assert(!ContentCatalog::writeJsonFile(path.c_str(), doc));
        assertOriginalIntact(path);

        prepare(path);
        FakeSD::failRemove = true;
        assert(!ContentCatalog::writeJsonFile(path.c_str(), doc));
        assert(FakeSD::files.at(path) == original);
        assert(FakeSD::files.at(path + ".tmp") == expected);

        prepare(path);
        FakeSD::failRename = true;
        assert(!ContentCatalog::writeJsonFile(path.c_str(), doc));
        assert(!SD.exists(path.c_str()));  // explicitly accepted replacement gap
        assert(FakeSD::files.at(path + ".tmp") == expected);
        assert(FakeSD::readCalls == 0);
    }

    ParentConfig config;
    FakeSD::reset();
    assert(!config.load());
    assert(!config.loaded());
    FakeSD::files[SD_CONFIG_FILE] = expected;
    assert(config.load() && config.loaded());
    assert(config.defaultVolumePct() == 42);

    for (const char* invalid : {"", "{", "[]", "null", "42"}) {
        FakeSD::files[SD_CONFIG_FILE] = invalid;
        assert(!config.load());
        assert(!config.loaded());
    }
    // Neither a valid leftover temp file nor a backup hides a missing config.
    FakeSD::files.erase(SD_CONFIG_FILE);
    FakeSD::files[std::string(SD_CONFIG_FILE) + ".tmp"] = expected;
    FakeSD::files[std::string(SD_CONFIG_FILE) + ".bak"] = expected;
    assert(!config.load() && !config.loaded());

    std::cout << "JSON file failure/recovery-policy tests passed\n";
}

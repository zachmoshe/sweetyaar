#include "ContentCatalog.h"
#include <cassert>
#include <fstream>
#include <iostream>
#include <iterator>

namespace ContentCatalog {
#include "wav_inspect.inc"
}

int main(int argc, char** argv) {
    assert(argc == 2);
    std::ifstream source(argv[1], std::ios::binary);
    assert(source);
    FakeSD::files["/test.wav"] = std::string(std::istreambuf_iterator<char>(source), {});
    File file = SD.open("/test.wav");
    const auto info = ContentCatalog::inspectWav(file);
    assert(file.position() == 0);
    std::cout << info.valid << ' ' << info.supported << ' ' << info.channels
              << ' ' << info.durationMs << '\n';
}

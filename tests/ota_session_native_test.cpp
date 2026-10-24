#include <cassert>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <vector>

#include "OtaSession.h"

using namespace Ota;

// Raw-encoding sink with a stand-in digest; the protocol does not depend on
// which hash the platform computes, only on comparing it with the request.
struct FakeSink : Sink {
    std::vector<uint8_t> flash;
    uint32_t expected = 0;
    int opens = 0, aborts = 0, installs = 0;
    Error failOpen = Error::None, failWrite = Error::None, failInstall = Error::None;

    Error open(const Image& image) override {
        ++opens;
        flash.clear();
        expected = image.imageSize;
        return failOpen;
    }
    Error write(const uint8_t* bytes, size_t length) override {
        if (failWrite != Error::None) return failWrite;
        flash.insert(flash.end(), bytes, bytes + length);
        return Error::None;
    }
    uint32_t written() const override { return uint32_t(flash.size()); }
    bool complete() const override { return flash.size() == expected; }
    void digest(uint8_t out[32]) override { fakeDigest(flash, out); }
    Error install() override { ++installs; return failInstall; }
    void abort() override { ++aborts; }

    static void fakeDigest(const std::vector<uint8_t>& bytes, uint8_t out[32]) {
        uint32_t hash = 2166136261u;
        for (uint8_t byte : bytes) hash = (hash ^ byte) * 16777619u;
        for (int i = 0; i < 32; ++i) out[i] = uint8_t(hash >> (8 * (i % 4))) ^ uint8_t(i);
    }
};

std::vector<uint8_t> beginPacket(const std::vector<uint8_t>& image, uint8_t encoding = EncodingRaw) {
    std::vector<uint8_t> packet(BEGIN_SIZE);
    packet[0] = CommandBegin;
    packet[1] = encoding;
    const uint32_t size = uint32_t(image.size());
    for (int i = 0; i < 4; ++i) packet[2 + i] = packet[6 + i] = uint8_t(size >> (8 * i));
    FakeSink::fakeDigest(image, packet.data() + 10);
    return packet;
}

Image parsed(const std::vector<uint8_t>& packet) {
    Image image;
    assert(parseBegin(packet.data(), packet.size(), image));
    return image;
}

std::vector<uint8_t> chunk(const std::vector<uint8_t>& image, uint32_t offset, uint32_t length) {
    std::vector<uint8_t> packet = {uint8_t(offset), uint8_t(offset >> 8), uint8_t(offset >> 16), uint8_t(offset >> 24)};
    packet.insert(packet.end(), image.begin() + offset, image.begin() + offset + length);
    return packet;
}

bool send(Session& session, const std::vector<uint8_t>& image, uint32_t offset, uint32_t length) {
    const auto packet = chunk(image, offset, length);
    return session.data(packet.data(), packet.size());
}

std::vector<uint8_t> testImage(size_t size, uint8_t seed) {
    std::vector<uint8_t> image(size);
    for (size_t i = 0; i < size; ++i) image[i] = uint8_t(i * 7 + seed);
    return image;
}

uint32_t statusU32(const uint8_t* status, int offset) {
    return uint32_t(status[offset]) | uint32_t(status[offset + 1]) << 8 |
           uint32_t(status[offset + 2]) << 16 | uint32_t(status[offset + 3]) << 24;
}

void testBeginValidation() {
    const auto image = testImage(1000, 1);
    auto packet = beginPacket(image);
    Image parsedImage;
    assert(parseBegin(packet.data(), packet.size(), parsedImage));
    assert(parsedImage.encodedSize == 1000 && parsedImage.imageSize == 1000);
    assert(!parseBegin(packet.data(), packet.size() - 1, parsedImage));
    packet[1] = 7;  // unknown encoding
    assert(!parseBegin(packet.data(), packet.size(), parsedImage));
    packet = beginPacket(image);
    packet[2] = 1;  // raw images must announce equal sizes
    assert(!parseBegin(packet.data(), packet.size(), parsedImage));
    packet = beginPacket(image, EncodingZlib);
    packet[2] = 1;  // a compressed stream may be any size
    assert(parseBegin(packet.data(), packet.size(), parsedImage));
    packet = beginPacket(std::vector<uint8_t>());
    assert(!parseBegin(packet.data(), packet.size(), parsedImage));
}

void testNormalModeRefusesImages() {
    FakeSink sink;
    Session session(sink);
    const auto image = testImage(100, 2);
    assert(session.begin(parsed(beginPacket(image))) == Error::WrongMode);
    assert(sink.opens == 0 && session.state() == State::Idle);
    assert(!send(session, image, 0, 10));
    assert(session.finish() == Error::WrongMode);
    session.reportError(Error::BatteryLow);
    uint8_t status[STATUS_SIZE];
    session.encodeStatus(status, 185);
    assert(status[0] == STATUS_FORMAT && status[1] == uint8_t(State::Idle));
    assert(status[2] == uint8_t(Error::BatteryLow));
    assert(statusU32(status, 4) == 0 && statusU32(status, 8) == 0);
    assert((status[16] | status[17] << 8) == 185);
}

void testInOrderTransferInstalls() {
    FakeSink sink;
    Session session(sink);
    session.enterUpdateMode();
    const auto image = testImage(1000, 3);
    const auto begin = beginPacket(image);
    assert(session.begin(parsed(begin)) == Error::None);
    assert(session.state() == State::Receiving);
    for (uint32_t offset = 0; offset < 1000; offset += 180) {
        assert(send(session, image, offset, std::min<uint32_t>(180, 1000 - offset)));
    }
    uint8_t status[STATUS_SIZE];
    session.encodeStatus(status, 517);
    assert(statusU32(status, 4) == 1000 && statusU32(status, 8) == 1000);
    assert(memcmp(status + 12, begin.data() + 10, 4) == 0);  // session tag
    assert(session.finish() == Error::None);
    assert(session.state() == State::Installing && sink.installs == 1);
    assert(sink.flash == image);
}

void testLostDuplicateAndReorderedChunks() {
    FakeSink sink;
    Session session(sink);
    session.enterUpdateMode();
    const auto image = testImage(600, 4);
    assert(session.begin(parsed(beginPacket(image))) == Error::None);
    assert(send(session, image, 0, 200));
    assert(!send(session, image, 0, 200));    // duplicate
    assert(!send(session, image, 400, 200));  // the chunk at 200 was lost
    assert(session.received() == 200 && session.state() == State::Receiving);
    assert(session.finish() == Error::Size);  // short: stays resumable
    assert(session.state() == State::Receiving);
    assert(send(session, image, 200, 200));
    assert(send(session, image, 400, 200));
    const uint8_t empty[4] = {};
    assert(!session.data(empty, sizeof(empty)));  // header without payload
    assert(session.finish() == Error::None && sink.flash == image);
}

void testResumeAndRestart() {
    FakeSink sink;
    Session session(sink);
    session.enterUpdateMode();
    const auto image = testImage(800, 5);
    assert(session.begin(parsed(beginPacket(image))) == Error::None);
    assert(send(session, image, 0, 300));
    // The app reconnects and announces the same image: keep what arrived.
    assert(session.begin(parsed(beginPacket(image))) == Error::None);
    assert(session.received() == 300 && sink.opens == 1 && sink.aborts == 0);
    // A different image discards the partial one.
    const auto other = testImage(800, 6);
    assert(session.begin(parsed(beginPacket(other))) == Error::None);
    assert(session.received() == 0 && sink.opens == 2 && sink.aborts == 1);
    assert(send(session, other, 0, 800));
    assert(session.finish() == Error::None && sink.flash == other);
}

void testFailuresDiscardData() {
    const auto image = testImage(500, 7);
    {
        FakeSink sink;
        Session session(sink);
        session.enterUpdateMode();
        assert(session.begin(parsed(beginPacket(image))) == Error::None);
        auto oversized = chunk(image, 0, 500);
        oversized.push_back(1);
        assert(!session.data(oversized.data(), oversized.size()));
        assert(session.state() == State::Failed && session.error() == Error::Size);
        assert(session.received() == 0 && sink.aborts == 1);
        // A failed transfer can start again.
        assert(session.begin(parsed(beginPacket(image))) == Error::None);
        assert(send(session, image, 0, 500) && session.finish() == Error::None);
    }
    {
        FakeSink sink;
        Session session(sink);
        session.enterUpdateMode();
        auto begin = beginPacket(image);
        begin[10] ^= 0xff;  // announced checksum does not match the data
        assert(session.begin(parsed(begin)) == Error::None);
        assert(send(session, image, 0, 500));
        assert(session.finish() == Error::Checksum);
        assert(session.state() == State::Failed && sink.installs == 0 && sink.aborts == 1);
    }
    {
        FakeSink sink;
        sink.failWrite = Error::Flash;
        Session session(sink);
        session.enterUpdateMode();
        assert(session.begin(parsed(beginPacket(image))) == Error::None);
        assert(!send(session, image, 0, 100));
        assert(session.state() == State::Failed && session.error() == Error::Flash);
    }
    {
        FakeSink sink;
        sink.failOpen = Error::NoMemory;
        Session session(sink);
        session.enterUpdateMode();
        assert(session.begin(parsed(beginPacket(image))) == Error::NoMemory);
        assert(session.state() == State::Failed && !send(session, image, 0, 100));
    }
    {
        FakeSink sink;
        sink.failInstall = Error::InvalidImage;
        Session session(sink);
        session.enterUpdateMode();
        assert(session.begin(parsed(beginPacket(image))) == Error::None);
        assert(send(session, image, 0, 500));
        assert(session.finish() == Error::InvalidImage);
        assert(session.state() == State::Failed && session.error() == Error::InvalidImage);
    }
}

void testCancel() {
    FakeSink sink;
    Session session(sink);
    session.enterUpdateMode();
    const auto image = testImage(400, 8);
    assert(session.begin(parsed(beginPacket(image))) == Error::None);
    assert(send(session, image, 0, 100));
    session.cancel();
    assert(session.state() == State::Ready && session.received() == 0 && sink.aborts == 1);
    assert(!send(session, image, 100, 100));
}

int main() {
    testBeginValidation();
    testNormalModeRefusesImages();
    testInOrderTransferInstalls();
    testLostDuplicateAndReorderedChunks();
    testResumeAndRestart();
    testFailuresDiscardData();
    testCancel();
    std::cout << "OTA session tests passed\n";
}

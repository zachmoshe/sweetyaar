#include "OtaSession.h"

#include <string.h>

namespace Ota {
namespace {

uint32_t readU32(const uint8_t* bytes) {
    return uint32_t(bytes[0]) | (uint32_t(bytes[1]) << 8) |
           (uint32_t(bytes[2]) << 16) | (uint32_t(bytes[3]) << 24);
}

void writeU32(uint8_t* out, uint32_t value) {
    for (int i = 0; i < 4; ++i) out[i] = static_cast<uint8_t>(value >> (8 * i));
}

bool sameImage(const Image& left, const Image& right) {
    return left.encoding == right.encoding && left.encodedSize == right.encodedSize &&
           left.imageSize == right.imageSize && memcmp(left.sha256, right.sha256, 32) == 0;
}

}  // namespace

bool parseBegin(const uint8_t* data, size_t length, Image& image) {
    if (length != BEGIN_SIZE || data[0] != CommandBegin) return false;
    if (data[1] != EncodingRaw && data[1] != EncodingZlib) return false;
    image.encoding = data[1];
    image.encodedSize = readU32(data + 2);
    image.imageSize = readU32(data + 6);
    memcpy(image.sha256, data + 10, 32);
    if (image.encodedSize == 0 || image.imageSize == 0) return false;
    return image.encoding != EncodingRaw || image.encodedSize == image.imageSize;
}

void Session::enterUpdateMode() {
    _state = State::Ready;
    _error = Error::None;
    _received = 0;
}

Error Session::begin(const Image& image) {
    if (_state == State::Idle || _state == State::Verifying || _state == State::Installing) {
        return Error::WrongMode;
    }
    if (_state == State::Receiving && sameImage(_image, image)) {
        _error = Error::None;
        return Error::None;
    }
    if (_state == State::Receiving) _sink.abort();
    _received = 0;
    _image = image;
    const Error opened = _sink.open(image);
    if (opened != Error::None) {
        _state = State::Failed;
        _error = opened;
        return opened;
    }
    _error = Error::None;
    _state = State::Receiving;
    return Error::None;
}

bool Session::data(const uint8_t* packet, size_t length) {
    if (_state != State::Receiving || length <= DATA_HEADER_SIZE) return false;
    // Anything but the next expected chunk is a duplicate or arrived after a
    // lost one; the app resends from the reported offset.
    if (readU32(packet) != _received) return false;
    const size_t payload = length - DATA_HEADER_SIZE;
    if (payload > _image.encodedSize - _received) {
        fail(Error::Size);
        return false;
    }
    const Error written = _sink.write(packet + DATA_HEADER_SIZE, payload);
    if (written != Error::None) {
        fail(written);
        return false;
    }
    _received += payload;
    return true;
}

Error Session::finish() {
    if (_state != State::Receiving) return Error::WrongMode;
    // Missing chunks are not fatal: the app resends from the reported offset.
    if (_received != _image.encodedSize) return Error::Size;
    _state = State::Verifying;
    if (!_sink.complete() || _sink.written() != _image.imageSize) {
        fail(Error::Size);
        return Error::Size;
    }
    uint8_t digest[32];
    _sink.digest(digest);
    if (memcmp(digest, _image.sha256, sizeof(digest)) != 0) {
        fail(Error::Checksum);
        return Error::Checksum;
    }
    const Error installed = _sink.install();
    if (installed != Error::None) {
        _state = State::Failed;
        _error = installed;
        return installed;
    }
    _state = State::Installing;
    return Error::None;
}

void Session::cancel() {
    if (_state == State::Receiving) _sink.abort();
    if (_state != State::Idle) _state = State::Ready;
    _received = 0;
    _error = Error::None;
}

void Session::fail(Error error) {
    if (_state == State::Receiving || _state == State::Verifying) _sink.abort();
    _state = State::Failed;
    _error = error;
    _received = 0;
}

void Session::encodeStatus(uint8_t out[STATUS_SIZE], uint16_t mtu) const {
    memset(out, 0, STATUS_SIZE);
    out[0] = STATUS_FORMAT;
    out[1] = static_cast<uint8_t>(_state);
    out[2] = static_cast<uint8_t>(_error);
    writeU32(out + 4, _received);
    writeU32(out + 8, _state == State::Idle ? 0 : _image.encodedSize);
    if (_state != State::Idle) memcpy(out + 12, _image.sha256, 4);
    out[16] = static_cast<uint8_t>(mtu);
    out[17] = static_cast<uint8_t>(mtu >> 8);
}

}  // namespace Ota

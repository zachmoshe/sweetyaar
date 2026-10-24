#pragma once

#include <stddef.h>
#include <stdint.h>

// ---------------------------------------------------------------------------
// OtaSession — firmware-update protocol state, independent of the ESP32 APIs.
//
// The app sends one image as numbered chunks. The device accepts only the
// chunk at the next expected offset and reports that offset in its status, so
// a dropped, duplicated or reordered packet is resent from there. Decoding,
// hashing and flash writes belong to the Sink. See "Firmware updates" in
// docs/engineering/firmware.md for the BLE encoding.
// ---------------------------------------------------------------------------

namespace Ota {

enum class State : uint8_t {
    Idle = 0,        // normal firmware; no update in progress
    Ready = 1,       // update mode, waiting for an image
    Receiving = 2,
    Verifying = 3,
    Installing = 4,  // image selected for the next boot; restart follows
    Failed = 5,
};

enum class Error : uint8_t {
    None = 0,
    BatteryLow = 1,    // update mode refused: battery low and not charging
    NotReady = 2,      // Bluetooth access is not ready (for example a bond reset)
    BadRequest = 3,
    NoMemory = 4,
    Flash = 5,
    Decompress = 6,
    InvalidImage = 7,  // the ESP-IDF image check failed
    Checksum = 8,      // decoded image does not match the announced SHA-256
    Size = 9,
    WrongMode = 10,    // command not valid in the current mode or state
};

enum Command : uint8_t {
    CommandEnterUpdateMode = 1,
    CommandBegin = 2,
    CommandFinish = 3,
    CommandCancel = 4,
};

enum Encoding : uint8_t {
    EncodingRaw = 0,
    EncodingZlib = 1,
};

// Status: format, state, error, reserved, received (u32), total (u32),
// first four SHA-256 bytes of the image (session tag), ATT MTU (u16).
// Little endian; fits one notification at the minimum ATT MTU.
constexpr size_t STATUS_SIZE = 18;
constexpr uint8_t STATUS_FORMAT = 1;
// Begin: command, encoding, encoded size (u32), image size (u32), SHA-256.
constexpr size_t BEGIN_SIZE = 42;
// Data: offset of the chunk in the encoded stream (u32), then its bytes.
constexpr size_t DATA_HEADER_SIZE = 4;

struct Image {
    uint8_t encoding = EncodingRaw;
    uint32_t encodedSize = 0;
    uint32_t imageSize = 0;
    uint8_t sha256[32] = {};
};

bool parseBegin(const uint8_t* data, size_t length, Image& image);

// Decodes, hashes and writes one image into the inactive app slot.
class Sink {
public:
    virtual ~Sink() = default;
    virtual Error open(const Image& image) = 0;
    virtual Error write(const uint8_t* encoded, size_t length) = 0;
    virtual uint32_t written() const = 0;     // decoded bytes written
    virtual bool complete() const = 0;        // the decoder reached the stream end
    virtual void digest(uint8_t out[32]) = 0; // SHA-256 of the decoded bytes
    virtual Error install() = 0;              // validate and select for next boot
    virtual void abort() = 0;
};

// Begin, data, finish and cancel arrive serialized on the Bluetooth task; the
// status getters may be read from the loop task.
class Session {
public:
    explicit Session(Sink& sink) : _sink(sink) {}

    // Update-mode firmware accepts images; normal firmware stays Idle.
    void enterUpdateMode();
    // Starts an image, or keeps the received prefix when the same image is
    // announced again (the app reconnected after a pause).
    Error begin(const Image& image);
    // Returns true when the chunk was accepted at the expected offset.
    bool data(const uint8_t* packet, size_t length);
    // Verifies size and checksum, then installs. A short image stays
    // resumable; any other failure discards the received data.
    Error finish();
    void cancel();
    // Report an error without changing the transfer (normal-mode refusals).
    void reportError(Error error) { _error = error; }

    State state() const { return _state; }
    Error error() const { return _error; }
    uint32_t received() const { return _received; }
    void encodeStatus(uint8_t out[STATUS_SIZE], uint16_t mtu) const;

private:
    void fail(Error error);

    Sink& _sink;
    Image _image;
    volatile State _state = State::Idle;
    volatile Error _error = Error::None;
    volatile uint32_t _received = 0;
};

}  // namespace Ota

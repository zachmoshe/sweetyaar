#pragma once

#include <Arduino.h>

#include "BLEParentService.h"

// ---------------------------------------------------------------------------
// OtaUpdate — firmware updates over the parent BLE service.
//
// Normal firmware accepts only "enter update mode": it sets a flag that
// survives a software restart and reboots. Update mode starts the Bluetooth
// controller in BLE-only mode (no Classic audio, ~65 KB free heap), keeps the
// same GATT table and bonds, receives an image into the inactive app slot and
// restarts into it. The old firmware stays bootable until the final switch,
// and the new one rolls back unless it confirms itself at startup.
//
// The diagnostic log (DevLogTransfer.h) streams in both modes: in update mode
// entered for it (fast, used by the Mac), and in normal mode while the toy is
// idle (used by the parent app). The firmware info value tells the app where
// the log stands and whether parents share it automatically.
// ---------------------------------------------------------------------------

namespace OtaUpdate {

// setup(): returns true once, after a restart requested by "enter update mode".
bool consumeUpdateModeRequest();
bool updateMode();
// Update mode entered only to send the log: no firmware image is accepted.
bool logReadOnly();

// Update mode only, before BLEParentService::begin(): Classic memory is
// released and the controller runs BLE-only until the next restart.
bool startBleOnlyController();

// Call after BLEParentService::begin(). Normal mode only: |updateAllowed|
// decides whether the battery permits entering update mode, and
// |logReadAllowed| whether the toy is idle enough to send its log.
void attach(BLEParentService& ble, bool updateModeActive, bool (*updateAllowed)(),
            bool (*logReadAllowed)());

// Published in the firmware info value for the app.
void setLogSharing(bool enabled, uint32_t from);

// A log read is in progress: it postpones sleep but is not activity, so an
// app that reads the log now and then does not keep the toy awake.
bool logReadActive();

// Loop: publishes status, performs requested restarts and the idle timeout.
void poll(uint32_t nowMs);

// End of normal setup(): confirm a freshly installed image, or roll back when
// a required service failed to start.
void confirmRunningImage(bool healthy);

}  // namespace OtaUpdate

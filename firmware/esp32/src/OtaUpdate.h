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
// ---------------------------------------------------------------------------

namespace OtaUpdate {

// setup(): returns true once, after a restart requested by "enter update mode".
bool consumeUpdateModeRequest();
bool updateMode();

// Update mode only, before BLEParentService::begin(): Classic memory is
// released and the controller runs BLE-only until the next restart.
bool startBleOnlyController();

// Call after BLEParentService::begin(). |updateAllowed| decides whether the
// battery permits entering update mode (normal mode only).
void attach(BLEParentService& ble, bool updateModeActive, bool (*updateAllowed)());

// Loop: publishes status, performs requested restarts and the idle timeout.
void poll(uint32_t nowMs);

// End of normal setup(): confirm a freshly installed image, or roll back when
// a required service failed to start.
void confirmRunningImage(bool healthy);

}  // namespace OtaUpdate

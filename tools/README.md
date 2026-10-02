# Project tools

Add standalone development or maintenance utilities here when they are needed.
Common user-facing commands should be exposed through the root `Makefile`.

`device_test.py` is the opt-in Mac/ESP32 Bluetooth runner. It captures real
serial events and uses Bleak, blueutil, SwitchAudioSource and the AVAudioPlayer
helper `device_tone.swift` for radio and audio checks. Tone output is selected
per player; it does not reroute other Mac applications. Run from Terminal.app
with Bluetooth permission. It requires
approval for the current session, the correct board environment and exclusive
access to USB serial; close the normal monitor first.

See [the two test layers](../tests/README.md#two-test-layers). Reports and raw
logs go under the ignored `tools/bt_smoke_logs/` directory. Passing one scenario
does not mean every other flow passed. There is no test bypass in the firmware.

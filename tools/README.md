# Project tools

Standalone development and maintenance utilities live here (the device test
runner, `convert_wavs_to_mono.py`) and the animal-sound pipeline in `animals/`
(`build_animals.py`; see
[content/animal-sounds](../content/animal-sounds/README.md)).
Common user-facing commands should be exposed through the root `Makefile`.

`reset_mac_bluetooth.py` (`make reset-mac-bluetooth`) makes a development Mac
forget nearby SweetYaar toys, found by BLE service UUID rather than by name
(or `ADDRESS=` from the boot log): keychain bond, Classic records and device
rows, then restarts `bluetoothd`. It needs Bluetooth permission, `sudo` and Full
Disk Access, and asks before deleting. `--inspect` prints a read-only report
without key material.

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

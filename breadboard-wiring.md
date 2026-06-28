# SweetYaar — Phase 1 Breadboard Wiring Guide

## Parts Required

| # | Component | Notes |
|---|---|---|
| 1 | ESP32-WROOM-32 DevKit board | Any standard 38-pin DevKitC |
| 2 | MAX98357A breakout | Adafruit #3006 or equivalent |
| 3 | Micro SD SPI breakout | Generic "SD card module" with 3.3V LDO + level shifter |
| 4 | Speaker, 4Ω or 8Ω, ≤3W | Any small speaker; mono |
| 5 | 2× tactile push button | 4-pin, fits breadboard |
| 6 | Breadboard (830-point) | The DevKit spans ~26 columns; you need the full width |
| 7 | Jumper wires | Male-to-male assortment |
| 8 | USB-C cable + 5V power bank or PC USB | Powers the DevKit |
| 9 | Passive vibration switch | Optional for sleep-mode wake testing |
| 10 | High-side load switch | AP2281-3WG-7 or another active-HIGH high-side switch for SD + amp power gating |

> **Note:** No battery/charging/LDO circuit needed for breadboard testing. Use the DevKit USB/5V input or a stable external 5V supply, keep the ESP32 directly powered, and power the SD module plus MAX98357A only from the load-switch output. Keep every ground common.

---

## Power Rails

| From | To |
|---|---|
| DevKit USB/5V input or stable external **5V** | ESP32 DevKit power input |
| Same **5V** source | Load-switch `IN` |
| Load-switch `OUT` | Switched peripheral rail for SD module `VCC` and MAX98357A `VIN` |
| DevKit **GND** pin | Breadboard **−** rail |

The intended SweetYaar wiring keeps only the ESP32 powered directly. Every
powered peripheral on this prototype rail goes behind the load switch.

---

## MAX98357A (I2S Amplifier)

| MAX98357A Pin | Connects To | Notes |
|---|---|---|
| **VIN** | Switched peripheral rail from load-switch `OUT` | MAX98357A accepts 2.5-5.5V |
| **GND** | GND rail | |
| **BCLK** | ESP32 **GPIO26** | Bit clock |
| **LRC** (LRCLK / WS) | ESP32 **GPIO25** | Word select |
| **DIN** | ESP32 **GPIO22** | Data in |
| **SD** (SD_MODE) | ESP32 **GPIO21** | LOW = mute, HIGH = active |
| **GAIN** | Leave floating | 9 dB default (Adafruit); tie to 3.3V for 12 dB |
| **OUT+** | Speaker + terminal | |
| **OUT−** | Speaker − terminal | |

---

## SD Card Module (SPI)

| SD Module Pin | Connects To |
|---|---|
| **VCC** | Switched peripheral rail from load-switch `OUT` |
| **GND** | GND rail |
| **SCK** | ESP32 **GPIO18** |
| **MISO** | ESP32 **GPIO19** |
| **MOSI** | ESP32 **GPIO23** |
| **CS** | ESP32 **GPIO5** |

> Use a breakout that already includes a 3.3V LDO and logic-level shifters (the common blue "SD card module" boards do). If using a bare SPI SD socket, add a 10kΩ pull-up on MISO.

---

## Buttons (active LOW)

No external resistors needed — firmware enables internal pull-ups.

| Button | Pin A | Pin B |
|---|---|---|
| **Button 1** (Songs) | ESP32 **GPIO32** | GND rail |
| **Button 2** (Animals) | ESP32 **GPIO33** | GND rail |

---

## Sleep-Mode Wake Sensor

The sleep firmware wakes from a passive vibration switch on GPIO27.

| Sensor Side | Connects To |
|---|---|
| One switch lead | ESP32 **GPIO27** |
| Other switch lead | GND rail |

No external resistor is needed for the tested wiring; firmware enables the ESP32
pull-up and wakes from deep sleep when GPIO27 is pulled LOW.

---

## Load-Switch Wiring

Issue #2 validates the real sleep design: the SD card module and audio amp are
powered together through a GPIO-controlled high-side load switch. ESP32 power
stays direct; SD module `VCC` and MAX98357A `VIN` are connected only to the
load-switch output.

| Load Switch Pin | Connects To |
|---|---|
| **VIN / IN** | 5V source rail |
| **VOUT / OUT** | SD module `VCC` and MAX98357A `VIN` |
| **EN / ON** | ESP32 **GPIO13** |
| **GND** | GND rail |

The firmware assumes the load-switch enable is active HIGH: GPIO13 HIGH powers
the SD card and amp, and GPIO13 LOW turns them off. Before deep sleep, firmware
switches GPIO13 to RTC output-low mode and holds it there so `EN` stays low
while the ESP32 is asleep.

For the AP2281-3WG-7 SOT26/SOT23-6 part:

| AP2281 Pin | Connects To |
|---|---|
| `1 OUT` | Switched SD module `VCC` and MAX98357A `VIN` rail |
| `2 GND`, `5 GND` | Common ground |
| `3 EN` | ESP32 GPIO13, plus a recommended 100kΩ pulldown to GND |
| `4 IN`, `6 IN` | 5V source rail |

Place a 1µF capacitor from `IN` to GND and a 0.1µF capacitor from `OUT` to GND
close to the switch. The `AP2281-3` variant includes output discharge when
disabled, so the switched rail should fall near 0V after GPIO13 goes LOW and is
RTC-held during sleep.

The firmware hold covers normal deep sleep. Keep the physical `EN` pulldown as
a hardware fail-safe for reset, bootloader, flashing, and crash windows before
firmware has configured GPIO13.

If your load-switch module is active LOW, invert it in hardware or do not use
that module for the sleep-current test.

Backfeed check for Issue #2: after the firmware prints that it is entering deep
sleep, measure GPIO13/`EN` and the switched rail. GPIO13/`EN` should be near 0V,
and the switched rail should also be near 0V. If the rail remains partly powered,
check for backfeeding through SD SPI, I2S, amp mute/control wiring, module LEDs,
or pull-ups on the switched side.

---

## Status LED

GPIO2 is the **on-board LED** on most DevKit boards — no external LED needed. The firmware uses it for boot status.

---

## ASCII Connection Diagram

```
                       ESP32 DevKitC
                   ┌─────────────────┐
              3.3V ┤ 3V3         GND ├── GND rail
               GND ┤ GND         5V  ├
          GPIO22 ──┤ 22          23  ├── SD MOSI
  GPIO21(MUTE) ───┤ 21          19  ├── SD MISO
          GPIO18 ──┤ 18          18  ├  (SCK — same row)
           GPIO5 ──┤ 5            5  ├  (CS — same row)
          GPIO25 ──┤ 25          26  ├── I2S BCLK
          GPIO27 ──┤ 27          13  ├── Load switch EN
          GPIO33 ──┤ 33          32  ├── BTN1 (→ GND)
      (BTN2 → GND)─┘            (2) ├── onboard LED
                   └─────────────────┘

MAX98357A:                    SD Module:
  VIN  → switched rail          VCC  → switched rail
  GND  → GND rail               GND  → GND rail
  BCLK → GPIO26                 SCK  → GPIO18
  LRC  → GPIO25                 MISO → GPIO19
  DIN  → GPIO22                 MOSI → GPIO23
  SD   → GPIO21                 CS   → GPIO5
  OUT+ → Speaker+
  OUT- → Speaker-

Buttons:
  BTN1: GPIO32 ─── [button] ─── GND
  BTN2: GPIO33 ─── [button] ─── GND

Sleep / load-switch test:
  VIB:  GPIO27 ─── [passive vibration switch] ─── GND
  LOAD: GPIO13 ─── EN on active-HIGH load switch
        recommended 100kΩ from EN to GND
        5V source → load switch IN; load switch OUT → SD VCC + MAX98357A VIN
```

---

## Pre-Power Checklist

1. **SD card inserted** with at least one WAV file in `/songs/lullabies/` and one in `/animals/`
2. **Speaker connected** to MAX98357A OUT+ / OUT−
3. **GPIO21 starts LOW** — firmware mutes amp on boot; amp activates on first play
4. **Load-switch `OUT` → MAX98357A VIN and SD VCC**
5. **GPIO27 vibration switch to GND** if testing sleep wake
6. **GPIO13 load-switch EN**, with a recommended 100kΩ pulldown to GND, if measuring final-style peripheral sleep current
7. No external pull-up/pull-down resistors required on buttons or vibration wake

---

## Expected First Boot (Serial monitor at 115200 baud)

```
=== SweetYaar Boot ===
[Device] btName=SweetYaar
[Power] Peripherals enabled on GPIO13
[I2S] Initialized
[Config] defaultVolume=75 defaultTheme=lullabies disabledThemes=0 sleep=1 normal=600s vibWake=120s ble=120s
[BT] A2DP sink started as "SweetYaar"
[Boot] Ready.
```

- LED goes **solid ON** during init, then **OFF** when ready
- GPIO13 goes HIGH during boot to power the SD card and amp through the load switch
- "SweetYaar" appears in your phone's Bluetooth device list
- **BTN1** → plays first WAV from `/songs/lullabies/`
- **BTN2** → plays random WAV from `/animals/`
- Connect phone to "SweetYaar" via BT → enters BT_STREAMING; buttons disabled until disconnect
- After the configured idle timeout, serial prints `[Sleep] Entering deep sleep...`; GPIO13 is RTC-held LOW
- Moving the vibration switch wakes the ESP32 and causes a normal reboot

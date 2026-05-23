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

> **Note:** No battery/charging/LDO circuit needed for breadboard testing. The DevKit's on-board 3.3V regulator feeds everything from USB.

---

## Power Rails

| From | To |
|---|---|
| DevKit **3.3V** pin | Breadboard **+** rail |
| DevKit **GND** pin | Breadboard **−** rail |

---

## MAX98357A (I2S Amplifier)

| MAX98357A Pin | Connects To | Notes |
|---|---|---|
| **VIN** | 3.3V rail | |
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
| **VCC** | 3.3V rail |
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
          GPIO33 ──┤ 33          32  ├── BTN1 (→ GND)
      (BTN2 → GND)─┘            (2) ├── onboard LED
                   └─────────────────┘

MAX98357A:                    SD Module:
  VIN  → 3.3V rail              VCC  → 3.3V rail
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
```

---

## Pre-Power Checklist

1. **SD card inserted** with at least one WAV file in `/songs/lullabies/` and one in `/animals/`
2. **Speaker connected** to MAX98357A OUT+ / OUT−
3. **GPIO21 starts LOW** — firmware mutes amp on boot; amp activates on first play
4. **3.3V → MAX98357A VIN** — chip accepts 2.5–5.5V; 3.3V from DevKit is fine
5. No external pull-up/pull-down resistors required on any signal

---

## Expected First Boot (Serial monitor at 115200 baud)

```
=== SweetYaar Boot ===
[Device] btName=SweetYaar
[I2S] Initialized
[Config] defaultVolume=75 defaultTheme=lullabies
[BT] A2DP sink started as "SweetYaar"
[Boot] Ready.
```

- LED goes **solid ON** during init, then **OFF** when ready
- "SweetYaar" appears in your phone's Bluetooth device list
- **BTN1** → plays first WAV from `/songs/lullabies/`
- **BTN2** → plays random WAV from `/animals/`
- Connect phone to "SweetYaar" via BT → enters BT_STREAMING; buttons disabled until disconnect

# Schematic Pass 1 Plan

This is the order to draw the first real schematic. The goal is to get a complete
electrical design before worrying about exact PCB routing.

## 1. Power Entry

- USB-C connector.
- External 5V screw terminal.
- Source-select SPDT slide switch. USB 5V and external 5V must not be tied together.
- `5V_SYS` rail.
- `5V_SYS` test point.
- CC1/CC2 5.1k pull-down resistors for USB-C sink mode.

## 2. 3.3V Rail

- AP2112K-3.3 / SOT-23-5 3.3V regulator for Rev A.
- Input/output capacitors from regulator datasheet.
- `3V3` test point.
- No dedicated `3V3` LED in the generated Rev A schematic; verify with the test point.
- Optional current-measurement jumper for debugging.

## 3. ESP32 Core

- ESP32-WROOM-32E module.
- EN pull-up and reset button.
- GPIO0 pull-up and boot button.
- Required decoupling near module power pins.
- UART0 TX/RX.
- Antenna keepout notes in PCB layout.

## 4. USB-UART Programming

- CH340C USB-UART bridge in SOIC-16.
- USB D+/D- from USB-C.
- UART TX/RX to ESP32.
- DTR/RTS auto-reset transistor circuit.
- Optional TX/RX LEDs if they do not add complexity.

## 5. microSD Socket

- SD socket in SPI mode.
- `SD_SCK`, `SD_MOSI`, `SD_MISO`, `SD_CS`.
- Pull-ups on `CMD`, `D0`, `D1`, `D2`, `D3`.
- Local 100nF plus bulk capacitor.
- Optional series resistors on `SCK`, `MOSI`, and `CS`.
- Optional card-detect signal to GPIO34.

## 6. I2S Audio

- MAX98357A breakout/module footprint for Rev A.
- `I2S_BCLK`, `I2S_WS`, `I2S_DOUT`, `AMP_MUTE_CTL`.
- `SD/MODE` default mono-average module bias, with transistor mute control.
- Transistor mute path so firmware can shut down the amp without forcing the mode voltage.
- 5V power to amp if using speaker power.
- Local bulk capacitor near amp.
- Optional 470uF DNP footprint near amp 5V input.
- Speaker connection directly on the MAX98357A module.
- `GAIN` pin intentionally left unconnected for default gain.

## 7. Expansion

- SPI expansion header with spare CS pins.
- I2C header.
- User GPIO header.
- 3V3/5V/GND rails near headers.
- Clearly label strap pins and input-only pins.

## 8. Test Points

Minimum useful test points:

- `5V_SYS`
- `3V3`
- `GND`
- `EN`
- `GPIO0`
- `UART0_TX`
- `UART0_RX`
- `SD_SCK`
- `SD_MOSI`
- `SD_MISO`
- `SD_CS`
- `I2S_BCLK`
- `I2S_WS`
- `I2S_DOUT`
- `AMP_MUTE_CTL`
- `AMP_SD_MODE`

## Pass 1 Done Means

- Every major block has symbols.
- All nets are named.
- ERC has no serious unexpected errors.
- The pin map still matches firmware unless we intentionally change it.
- Open BOM decisions are documented instead of hidden.

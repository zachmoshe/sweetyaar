# Rev A Schematic Status

The Rev A schematic is now generated into `esp32_prototype_board.kicad_sch` on an
A1 sheet so the grouped sections are readable without component overlap.
It uses the local symbol library `sweetyaar_rev_a.kicad_sym`, which is registered
through `sym-lib-table`. The project-local `fp-lib-table` points KiCad at the
installed KiCad 10 footprint libraries, so ERC can resolve the selected footprints.

## Included Blocks

- USB-C 5V sink with CC pull-downs.
- External 5V input.
- Manual 5V source select slide switch.
- AP2112K-3.3 regulator with EN tied to `5V_SYS` and local decoupling.
- CH340C USB-UART.
- ESP32 auto-program/reset network using DTR/RTS and two NPN transistors.
- EN and BOOT buttons.
- ESP32-WROOM-32E module with stable SD, I2S, USB-serial, EN, and BOOT wiring.
- microSD SPI socket with pull-ups, series resistors, and local decoupling.
- MAX98357A blue module 1x7 header, direct module speaker connection, and transistor mute control.
- GPIO32/GPIO33 exposed for project buttons or other external controls.
- Status LED with GPIO2 disconnect slide switch.
- SPI, I2C, GPIO expansion headers.
- Test pads for major power, serial, SD, and I2S nets.

## Verification

KiCad ERC passes with zero warnings and zero errors:

```text
ERC messages: 0 Errors 0 Warnings 0
```

The exported netlist was also spot-checked for the important nets:

| Net | Expected Key Connections |
|---|---|
| `SD_SCK` | microSD CLK, SPI header, series resistor from GPIO18 |
| `SD_MOSI` | microSD CMD, SPI header, series resistor from GPIO23 |
| `SD_MISO` | microSD DAT0, GPIO19, SPI header, pull-up |
| `SD_CS` | microSD DAT3/CS, pull-up, series resistor from GPIO5 |
| `I2S_BCLK` | GPIO26 to MAX98357A module |
| `I2S_WS` | GPIO25 to MAX98357A module |
| `I2S_DOUT` | GPIO22 to MAX98357A module |
| `AMP_MUTE_CTL` | GPIO21 to mute transistor base network |
| `AMP_SD_MODE` | MAX98357A SD/MODE pin, module onboard mono-average bias, mute transistor, and test point |
| `UART0_RX` | CH340C TXD to ESP32 GPIO3/RXD0 |
| `UART0_TX` | ESP32 GPIO1/TXD0 to CH340C RXD |

## Known Non-Final Items

This is a complete functional schematic, but not yet a manufacturing-locked design.
The part/footprint lock pass is recorded in `footprint-lock.md`. The MAX98357A
module is locked to the blue 7-pin module header, the microSD socket is locked to
Molex `104031-0811`, and the remaining CH340C, external terminal, transistor,
LED/button, resistor, and capacitor order codes are now selected. Before ordering,
still run the normal JLC quote preview to confirm live stock, rotation, and
footprint alignment.

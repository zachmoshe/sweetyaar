# Rev A Connectors Explained

The dashed blue boxes in the schematic are only visual grouping boxes. They are not
physical parts. A dashed box can contain one connector, many connectors, chips,
resistors, capacitors, or test pads.

## Connector-Like Items

| Reference | What It Is | Physical Meaning |
|---|---|---|
| `J1` | USB-C receptacle | One physical USB-C socket for power and serial data. |
| `J2` | External 5V input | One 2-pin screw terminal or similar connector for bench PSU `+5V` and `GND`. |
| `JP1` | 5V source select | One DPDT top-actuated slide switch chooses USB 5V or external 5V. |
| `J4` | microSD socket | One physical microSD card socket. |
| `J6` | SPI expansion | One 8-pin 2.54mm header. Pins can be used individually with jumper wires. |
| `J7` | I2C expansion | One 4-pin 2.54mm header for `GND`, `3V3`, `SDA`, and `SCL`. |
| `J8` | GPIO expansion | One 12-pin 2.54mm header exposing spare GPIO, including GPIO32/GPIO33, and rails. |
| `U4` | MAX98357A module footprint | One 7-pin 2.54mm header row for the blue module's I2S, mute, ground, and power pins. The speaker connects directly to the module. |
| `TP1`-`TP18` | Test points | Single copper pads for a multimeter, oscilloscope, or logic analyzer probe. Not normal cable connectors. |

## What A Multi-Pin Connector Means

When pins are grouped into one yellow rectangle, that usually means one physical
part with multiple contacts. For example, `J6` is one 8-pin header strip, not eight
separate connectors. You can still connect individual jumper wires to individual
pins, but mechanically it is one row of pins soldered to the PCB.

## What The Single Items On The Right Are

The single small `TP` blocks on the right side of the expansion section are test
points. They are intentionally one-net-only pads. They exist so you can touch a
probe to `3V3`, `SD_MISO`, `I2S_BCLK`, etc. while debugging. They are not meant to
hold a wire permanently.

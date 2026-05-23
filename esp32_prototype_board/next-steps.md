# Next Steps

This is the practical path from the current Rev A package to orderable boards.

## 1. Open The Project

Open `esp32_prototype_board.kicad_pro` in KiCad. You should see:

- A schematic scaffold with the major electrical blocks.
- A PCB starter outline, antenna keepout, and placement zones.
- Design notes in the Markdown files in this folder.

## 2. Review The Real Schematic

The first full Rev A schematic is now in place. Review it in this order:

1. Power entry: USB-C, external 5V, source selector, `5V_SYS`.
2. 3.3V rail: AP2112K-3.3, caps, `3V3`, test pads.
3. ESP32 core: ESP32-WROOM-32E, EN, BOOT, UART0, decoupling.
4. USB-UART: CH340C, USB D+/D-, TX/RX, DTR/RTS auto-reset.
5. microSD: socket, SPI nets, pull-ups, series resistors, decoupling.
6. I2S amp module 1x7 header, GPIO mute transistor, DNP bulk cap, and direct speaker connection on the blue module.
7. Expansion headers and test pads.

## 3. Confirm Part Lock Before Layout

The part-lock pass lives in `footprint-lock.md`. The formerly open rows are now
selected: CH340C uses the healthier `C7464026` SKU, J2 uses `C5188434`, the NPNs
use `C20526`, and the 1uF/10uF/22uF capacitor C-codes are fixed.

The most important rule is simple: the datasheet mechanical drawing must match the
KiCad footprint. This is especially important for USB-C, microSD, J2, and the
tactile switches. Reconfirm live stock and rotations in the final JLC quote
preview before ordering.

## 4. Layout Rules

Keep the ESP32 antenna at the edge and keep copper/wires away from its keepout. Put
the SD socket close to the ESP32. Keep `SD_SCK` short and direct. Put the amp
module and its speaker wires away from the ESP32 antenna and SD lines. Use the
inner layers as solid GND and power planes unless there is a clear reason not to.

## 5. Generate Quote Files

After schematic and layout pass:

- Run ERC.
- Run DRC.
- Generate Gerbers.
- Generate BOM.
- Generate CPL / position file.
- Upload to JLCPCB and inspect every preview.

Do not order until the USB-C connector, microSD socket, and ESP32 orientation are
visually checked in the manufacturer preview.

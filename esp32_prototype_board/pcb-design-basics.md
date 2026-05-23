# PCB Design Basics For This Project

This is the beginner map for how we get from idea to physical boards.

## Vocabulary

**Schematic**: The logical circuit. It says which pins connect to which nets.

**Symbol**: The drawing of a part in the schematic.

**Footprint**: The physical copper pads and outline that go on the PCB.

**Net**: A named electrical connection, such as `3V3`, `GND`, or `SD_SCK`.

**PCB layout**: The physical board: component placement, traces, copper zones,
vias, mounting holes, labels, and board outline.

**Gerbers**: Manufacturing files for the bare PCB.

**BOM**: Bill of materials. The list of parts to buy/place.

**CPL / Pick-and-place file**: Tells the assembly factory where each SMT part goes.

## Normal Workflow

1. Define requirements and pin map.
2. Draw schematic in KiCad.
3. Assign footprints.
4. Run electrical rules check.
5. Place components on the PCB.
6. Route traces and copper pours.
7. Run design rules check.
8. Generate Gerbers.
9. Generate BOM and CPL for assembly.
10. Upload to JLCPCB/PCBWay/etc. for quote.
11. Review the manufacturer preview carefully.
12. Order a small first batch.
13. Bring up the board slowly with a multimeter and simple firmware.

## Why One-Sided SMT

The assembly house can place all small components on the top side in one pass.
That is cheaper and easier to inspect. Through-hole headers and terminals can be
hand-soldered later.

## Why 4 Layers For Rev A

Two-layer boards are cheaper, but this board is meant to make SPI, Bluetooth, and
audio experiments less fragile. A 4-layer stack gives us a continuous ground plane
and a quiet power plane, which reduces weird signal and power behavior. For a small
handful of boards, the extra PCB cost is usually worth the saved debugging time.

## Why Use An ESP32 Module

The ESP32-WROOM module already includes the ESP32 chip, flash, crystal, RF matching,
and antenna. We only need to place the module correctly and respect the antenna
keepout. This avoids hard RF design and hidden tiny parts.

## Why Antenna Placement Matters

The built-in antenna needs free space around it. If copper, ground plane, wires,
speaker leads, or metal are too close, Bluetooth/Wi-Fi performance can suffer.
For Rev A, the ESP32 antenna goes on the board edge and points outward.

## Why SD Cards Are Sensitive

SD over SPI is much faster than buttons or LEDs. Breadboards and long jumper wires
add resistance, capacitance, bad contacts, and signal reflections. On our PCB, the
socket will be close to the ESP32, with pull-ups, decoupling, and short traces.

## Manufacturing Strategy

For Rev A, use the factory for:

- PCB fabrication.
- Top-side SMT parts that are easy and stocked.

Hand-solder after delivery:

- Pin headers.
- Screw terminals.
- Maybe the audio amp module if we use a breakout footprint.

This keeps the first order cheaper and easier to repair.

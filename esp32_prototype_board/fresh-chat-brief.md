# Fresh Chat Brief

This file is the handoff summary for continuing the ESP32 prototype board work in
a new chat. It captures the current design state, the important decisions from the
conversation, and the next work item.

## Project Goal

Build a reusable ESP32 prototype carrier board for audio/storage experiments, not
a final tiny product PCB. The board should remove breadboard pain for common ESP32
projects that need Bluetooth, microSD, I2S audio, USB serial programming, external
5V power, and spare GPIO.

The first real use case is SweetYaar, but the board must stay generic. Project
specific controls, such as SweetYaar buttons, should connect through expansion
headers rather than being permanently built into the carrier.

## Current Files

The design lives in:

```text
/Users/zmoshe/proj/sweetyaar/esp32_prototype_board
```

Important files:

```text
tools/generate_schematic.py        source of truth for generated schematic
esp32_prototype_board.kicad_sch    generated KiCad schematic
sweetyaar_rev_a.kicad_sym          generated local symbol library
esp32_prototype_board.kicad_pcb    starter PCB file
esp32_prototype_board-rev-a-schematic.pdf
rev-a-requirements.md
rev-a-decisions.md
pin-map.md
component-defaults.md
connectors-explained.md
schematic-status.md
next-steps.md
```

Do not manually edit `esp32_prototype_board.kicad_sch` for schematic structure.
Edit `tools/generate_schematic.py`, regenerate, then run ERC.

## Useful Commands

Run these from `/Users/zmoshe/proj/sweetyaar` unless noted otherwise:

```bash
python3 esp32_prototype_board/tools/generate_schematic.py
```

Run these from `/Users/zmoshe/proj/sweetyaar/esp32_prototype_board`:

```bash
/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli sch erc --exit-code-violations esp32_prototype_board.kicad_sch
/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli sch export pdf esp32_prototype_board.kicad_sch -o esp32_prototype_board-rev-a-schematic.pdf
```

The latest verified state has KiCad ERC clean:

```text
0 violations
```

## Current Schematic Decisions

Power:

- `J1` is USB-C USB2 sink, 5V only, no USB Power Delivery.
- `CC1` and `CC2` each have 5.1k pulldowns to GND.
- `J2` is external 5V input.
- `JP1` is an DPDT top-actuated slide switch. It chooses USB 5V or external 5V.
- `5V_SYS` is the selected 5V system rail.
- Grounds are common between USB, bench PSU, ESP32, SD, and amp.
- `U2` is AP2112K-3.3 in SOT-23-5/SOT25. Pinout used:

```text
1 VIN  -> 5V_SYS
2 GND  -> GND
3 EN   -> 5V_SYS
4 NC   -> no connect
5 VOUT -> 3V3
```

USB/UART and boot:

- USB serial bridge is CH340C in SOIC-16.
- UART0 is used for upload/monitor: ESP32 GPIO1/GPIO3.
- EN/RST and BOOT buttons are onboard board-management controls.
- Auto reset/program uses DTR/RTS and two NPN transistors, DevKitC style.

ESP32:

- Module target is ESP32-WROOM-32E with PCB antenna.
- Antenna must be at the board edge with keepout and no copper/wires/speaker leads
  near it.
- GPIO32 and GPIO33 are not onboard buttons. They are free expansion GPIO on `J8`.
- GPIO12 is intentionally unused because it can affect ESP32 flash boot voltage.
- GPIO34-39 are input-only; they have no internal pullups/pulldowns.

microSD:

- Native 3.3V microSD socket, SPI mode.
- Pin map:

```text
GPIO18 -> SD_SCK
GPIO19 -> SD_MISO / DAT0
GPIO23 -> SD_MOSI / CMD
GPIO5  -> SD_CS / DAT3
```

- SD `CMD`, `DAT0`, `DAT1`, `DAT2`, and `DAT3` get 10k pullups to `3V3`.
- `SCK`, `MOSI`, and `CS` have 22R series resistors near ESP32.
- Local SD decoupling is 10uF + 100nF.
- `SD_CD` / GPIO34 is currently exposed on `J8`; it is not wired to the current
  microSD socket symbol.

I2S audio:

- Rev A uses a MAX98357A breakout/module footprint, not the bare tiny IC.
- Module is powered from `5V_SYS`, not `3V3`.
- I2S pins:

```text
GPIO26 -> I2S_BCLK
GPIO25 -> I2S_WS
GPIO22 -> I2S_DOUT
GPIO21 -> AMP_MUTE_CTL
```

- MAX98357A `SD/MODE` is not directly driven by GPIO21.
- `U4` is locked to the blue 7-pin MAX98357A module shown in the 2026-05-17
  bring-up photos. With the component side up and the 7-pin header along the
  bottom edge, the module pin order is:

```text
LRC, BCLK, DIN, GAIN, SD, GND, VIN
```

- The module's top speaker pads are `SPK-` on the left and `SPK+` on the right.
- The module itself provides default stereo-average / mono mix behavior, so Rev A
  no longer adds an AVG jumper or right/left override jumpers.
- The carrier PCB only provides the module's bottom 1x7 header. Solder the
  speaker or a small speaker terminal directly to the module's top `+`/`-` pads.

- `AMP_MUTE_CTL` drives an NPN transistor:

```text
GPIO21 HIGH -> transistor on -> SD/MODE pulled to GND -> amp muted/shutdown
GPIO21 LOW or unconfigured -> transistor off -> module default controls amp
```

- `R24` is the 10k base resistor; `R25` is the 100k pulldown keeping the
  transistor off while GPIO21 floats at boot.
- `GAIN` on the MAX98357A module is intentionally no-connect, using default
  hardware gain. Software volume still controls the I2S sample level.
- `C11` is `470uF DNP`: the footprint/pads are on the PCB but it is not assembled
  by default. It can be hand-soldered later near the amp 5V input.

Expansion:

- `J6` is SPI expansion, 1x8 2.54mm header.
- `J7` is I2C expansion, 1x4 2.54mm header with 4.7k pullups on SDA/SCL.
- `J8` is GPIO expansion, 1x12 2.54mm header:

```text
1   3V3
2   5V_SYS
3   GND
4   GPIO32
5   GPIO33
6   GPIO4
7   GPIO13  (SweetYaar sleep firmware: peripheral load-switch enable)
8   GPIO15
9   GPIO35
10  GPIO36
11  GPIO39
12  SD_CD / GPIO34
```

- Test pads `TP1`-`TP18` cover major rails/signals.
- SweetYaar sleep firmware repurposes GPIO27 (`SPI_CS1` on `J6`) as the passive
  vibration wake input and GPIO13 (`J8` pin 7) as active-HIGH peripheral
  load-switch enable. Rev A exposes these as headers; the vibration switch and
  load switch are external add-ons for this carrier and should become real
  components on the final toy PCB.

## Documentation Alignment Status

The docs were checked and updated to match the final schematic:

- Old regulator wording was replaced with AP2112K-3.3.
- Old onboard-user-button wording was removed; GPIO32/GPIO33 are expansion pins.
- Docs now describe `AMP_MUTE_CTL` with HIGH = mute.
- Docs now describe `GPIO2_LED` through the `JP2` slide switch.
- Docs now describe the MAX98357A module as 5V-powered.
- Docs now describe `JP1` as an DPDT top-actuated slide switch.

## Hardware Lessons From Bring-Up

These drove the PCB design:

- Breadboard/jumper wiring was unreliable for SD SPI and I2S audio.
- Long or power-only USB cables caused voltage and USB monitor problems.
- The ESP32 and audio amp need solid 5V/3.3V rails and common ground.
- Blue SD modules with level shifter/regulator chips can be flaky; a native 3.3V
  socket on the PCB is preferred.
- SPI SD needs short traces, pullups, local decoupling, and optionally small series
  resistors.
- MAX98357A audio should avoid long breadboard connections and should have local
  decoupling plus optional bulk capacitance.
- Sleep-current testing needs the SD card and amp behind a load switch; direct
  power wiring is fine for functional bring-up but not for final current numbers.

## Next Task: Part/Footprint Lock Pass

The next requested task is to choose actual orderable parts that JLCPCB or another
cheap well-known manufacturer can source without us shipping custom parts.

Goal:

- Create a `footprint-lock.md` table.
- Fill obvious parts such as 0805 passives, AP2112K, CH340C, ESP32 module, common
  transistor, LEDs, test pads, headers, and terminals.
- Research high-risk parts carefully: USB-C connector, microSD socket, and
  MAX98357A module/footprint strategy.
- Prefer JLCPCB/LCSC stocked parts. Avoid parts that require customer consignment.
- For each part, compare the datasheet/mechanical drawing against the KiCad
  footprint before locking.

Suggested lock table columns:

```text
Ref(s)
Function
Chosen part / LCSC or manufacturer number
JLC status: Basic / Extended / Hand-solder / Needs quote
KiCad footprint
Risk
Decision / notes
```

Important caution:

- USB-C and microSD footprints are easy to get wrong. Do not rely only on a part
  name. Compare pad pitch, shell tabs, insertion direction, and pin numbering.
- MAX98357A breakout modules are not standardized. If we keep a module footprint,
  the module dimensions/pin order must be chosen before PCB layout.

## Current Open Decisions

- Exact USB-C connector part and footprint.
- microSD is locked to Molex `104031-0811` and the matching KiCad footprint.
- Caliper-check the selected blue MAX98357A breakout/module dimensions before
  final placement.
- Exact screw terminal part for external 5V.
- Exact tactile switch part for EN/BOOT.
- Whether to keep all headers hand-soldered or have some assembled.
- Final board dimensions after physical connector/module placement.

# ESP32 Prototype Board Rev A

This folder tracks the first reusable PCB concept for ESP32 audio/storage experiments.
The goal is not to make the smallest possible product board. The goal is to make a
stable lab board that removes breadboard pain for projects using Bluetooth, SD cards,
I2S audio, USB serial programming, external 5V power, and spare GPIO.

## What To Install

Start with these tools:

1. **KiCad** for schematic and PCB layout.
   Download from <https://www.kicad.org/download/>.

2. **Espressif KiCad libraries** are optional for this Rev A. KiCad 10 already
   includes `RF_Module:ESP32-WROOM-32E`, which is enough to start.

3. **JLCPCB KiCad tools** later, after the schematic and PCB are real.
   Plugin repository: <https://github.com/Bouni/kicad-jlcpcb-tools>.

You do not need to install manufacturing tools yet. First we will design and review
the board in KiCad. After that, we will generate Gerbers, BOM, and CPL/position files.

## Rev A Philosophy

- Use one-sided SMT assembly on the top side only.
- Prefer JLCPCB Basic parts where practical.
- Avoid BGA packages entirely.
- Avoid QFN packages unless there is no reasonable alternative.
- Use an ESP32-WROOM-32E module instead of a bare ESP32 chip.
- Place the ESP32 module antenna at the edge of the board with the required keepout.
- Keep the board comfortable and labeled, not tiny.
- Hand-solder bulky connectors and headers if that reduces assembly cost.

## Current Rev A Defaults

The current decisions are recorded in [rev-a-decisions.md](rev-a-decisions.md).
The component starting points are recorded in
[component-defaults.md](component-defaults.md). The rough small-run cost estimate is
in [cost-estimate.md](cost-estimate.md). The work plan from here is in
[next-steps.md](next-steps.md).

The current schematic status and verification notes are in
[schematic-status.md](schematic-status.md).
Connector/header meanings are explained in
[connectors-explained.md](connectors-explained.md).
For continuing this work in a fresh chat, start with
[fresh-chat-brief.md](fresh-chat-brief.md).

## Major Blocks

- ESP32-WROOM-32E module with built-in PCB antenna.
- USB-C connector for 5V power and USB serial data.
- USB-UART bridge for programming and serial monitor.
- External 5V input terminal for bench PSU power.
- Simple power-source selection so external 5V cannot backfeed USB.
- 3.3V regulator for ESP32, SD card, and logic.
- Soldered microSD socket wired in SPI mode.
- Soldered MAX98357A breakout header with mute control.
- Speaker connection directly on the MAX98357A module.
- I2C expansion header.
- SPI expansion header sharing the SD SPI bus.
- Spare GPIO headers with power and ground nearby.
- Test pads for important rails and buses.

## Open Rev A Decisions

- Resolve the conditional and not-locked rows in `footprint-lock.md`.
- Final board dimensions after connector placement.

## Useful References

- KiCad downloads: <https://www.kicad.org/download/>
- Espressif KiCad libraries: <https://github.com/espressif/kicad-libraries>
- ESP32-WROOM-32E/32UE datasheet: <https://documentation.espressif.com/esp32-wroom-32e_esp32-wroom-32ue_datasheet_en.html>
- ESP32 PCB layout guidelines: <https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32/pcb-layout-design.html>
- ESP-IDF SD pull-up requirements: <https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-reference/peripherals/sd_pullup_requirements.html>

# Rev A Requirements

## Purpose

Build a reusable ESP32 prototype board for audio/storage projects. It should make
experiments feel like firmware work again, not jumper-wire debugging.

## Must Have

- ESP32 module with Classic Bluetooth support.
- Built-in PCB antenna module placed correctly at board edge.
- USB-C connector for power and serial data.
- USB-UART programming and serial monitor.
- EN and BOOT buttons.
- Auto-program/reset circuit from USB-UART DTR/RTS.
- External 5V power input for bench PSU.
- Safe power selection between USB 5V and external 5V.
- On-board 3.3V regulator.
- microSD socket wired for SPI at 3.3V.
- SD pull-ups and local decoupling.
- I2S audio amp path for speaker testing.
- Amp mode default for stereo-average / mono output using the blue module's onboard bias.
- Firmware-controllable amp mute/shutdown.
- Speaker connection on the blue MAX98357A module.
- Spare GPIO headers.
- I2C header.
- External SPI header.
- Clearly labeled test pads.
- Exposed GPIO27 and GPIO13 so SweetYaar sleep-mode firmware can test vibration
  wake and peripheral load-switch enable with external add-on modules.

## Should Have

- One-sided SMT assembly.
- JLCPCB Basic parts where possible.
- Through-hole headers/connectors for easy hand soldering.
- Mounting holes.
- Power LED for `5V_SYS`.
- Optional status LED controlled by ESP32.
- Solder jumpers for optional features that touch boot strap pins.

## Nice To Have

- Card-detect line for SD.
- Amp gain selection pads.
- Amp mute LED or test point.
- Current-measurement jumper for ESP32 3.3V rail.
- Optional `3V3` power LED if we decide the extra rail current is worth it.
- Separate analog/audio ground labeling where useful, while keeping one common GND.
- Silk-screen pin labels on both sides of each header.

## Not Rev A

- Battery charging.
- On-board vibration wake switch.
- On-board SD/amp peripheral load switch.
- Tiny final-product size.
- USB Power Delivery negotiation.
- Native USB ESP32-S3/C3 style support.
- Multiple speaker channels.
- Integrated microphone.
- Display connector.
- Full SDIO 4-bit mode.

## Candidate Parts Strategy

This is intentionally a strategy, not a final BOM.

| Block | Rev A Preference |
|---|---|
| ESP32 | ESP32-WROOM-32E module with PCB antenna |
| USB-UART | CH340C-style visible-lead package if stocked; CP210x if needed |
| USB-C | USB 2.0 Type-C receptacle, sink-only 5V |
| 3.3V regulator | AP2112K-3.3TRG1, 600mA SOT-23-5/SOT25 LDO |
| microSD | Push-push or push-pull socket, SMT top-side |
| I2S amp | Blue 7-pin MAX98357A breakout/module header, 5V powered, default mono average, and GPIO mute |
| External power | 2-pin screw terminal or JST-VH style terminal |
| Speaker | Connect directly to the blue MAX98357A module `+`/`-` holes |
| Headers | 2.54mm through-hole |

## SweetYaar Sleep-Mode Prototype Add-Ons

Rev A is a reusable lab carrier, not the final battery toy PCB. For the sleep-mode
firmware branch, connect the sleep parts externally:

| Sleep Function | Rev A Connection |
|---|---|
| Passive vibration wake switch | `GPIO27` on the SPI header to GND |
| SD + amp load-switch enable | `GPIO13` on the GPIO header to an active-HIGH load-switch EN pin |

The final SweetYaar toy PCB should turn those external add-ons into real board
components: a vibration switch mounted where toy movement is detectable, and a
load switch or switched peripheral rail that powers the SD card and MAX98357A amp
together.

## First Bring-Up Checklist

1. Inspect for shorts before power.
2. Power from USB only, no ESP32 fitted if possible during early rail test.
3. Verify `5V_SYS`.
4. Verify `3V3`.
5. Verify USB-UART enumerates.
6. Verify EN/BOOT and flashing.
7. Flash a serial hello-world.
8. Test SD raw probe.
9. Test SD mount at 400 kHz and 4 MHz.
10. Test I2S sine tone.
11. Test Bluetooth A2DP from phone.
12. Test spare GPIO headers with an external button or jumper wire.
13. Test SweetYaar sleep add-ons: GPIO27 vibration wake and GPIO13 load-switch enable.

## Expected First-Spin Risk

Rev A may still need fixes. The most likely first-spin risks are:

- USB-UART auto-reset transistor logic reversed or timing-sensitive.
- USB-C footprint/mechanical mismatch.
- JLC part substitution or unavailable part.
- ESP32 antenna keepout or placement not good enough.
- SD socket footprint orientation/pin numbering mistake.
- Audio amp module footprint mismatch.
- Header labels needing improvement.

The board should include enough test pads and jumpers that these are repairable.

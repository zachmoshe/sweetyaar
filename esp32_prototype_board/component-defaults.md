# Component Defaults

This file maps each board block to a concrete KiCad symbol/footprint direction.
The manufacturing-facing part-code lock now lives in `footprint-lock.md`. The
final quote pass is still where we recheck live stock, price, package, and whether
each footprint matches the manufacturer preview.

## KiCad Parts To Start With

| Block | KiCad Symbol | KiCad Footprint | Rev A Status |
|---|---|---|---|
| ESP32 module | `RF_Module:ESP32-WROOM-32E` | `RF_Module:ESP32-WROOM-32E` | Use this. |
| USB-C receptacle | `Connector:USB_C_Receptacle_USB2.0_14P` | `Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12` | Candidate; verify exact connector before order. |
| USB-UART | `Interface_USB:CH340C` | `Package_SO:SOIC-16_3.9x9.9mm_P1.27mm` | Use this unless JLC stock says otherwise. |
| 3.3V regulator | AP2112K-3.3 compatible LDO | `Package_TO_SOT_SMD:SOT-23-5` | Use AP2112K-3.3TRG1 / LCSC C51118 unless quote pass says otherwise. |
| microSD socket | `Connector:Micro_SD_Card` or `Connector:Micro_SD_Card_Det1` | `Connector_Card:microSD_HC_Molex_104031-0811` | Locked to Molex 104031-0811. |
| I2S amp | Local `SweetYaar:MAX98357A_MODULE` | `Connector_PinHeader_2.54mm:PinHeader_1x07_P2.54mm_Vertical` | Locked to the blue 7-pin module's bottom header row. |
| External 5V input | `Connector_Generic:Conn_01x02` | Screw terminal or JST-style 2-pin | Hand-solder. |
| Speaker output | On the blue MAX98357A module | Not on the carrier PCB | Solder speaker or speaker terminal directly to the module's top `+`/`-` holes. |
| SPI header | `Connector_Generic:Conn_01x08` | `Connector_PinHeader_2.54mm:PinHeader_1x08_P2.54mm_Vertical` | Hand-solder. |
| I2C header | `Connector_Generic:Conn_01x04` | `Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical` | Hand-solder. |
| GPIO headers | Generic pin headers | 2.54mm vertical headers | Hand-solder. |
| Project buttons/controls | External wiring to GPIO headers | Hand-soldered per project | Do not permanently consume GPIO32/GPIO33 on the carrier. |
| Test pads | `Connector:TestPoint` | `TestPoint:TestPoint_Pad_D1.5mm` | Scatter generously. |
| Passives | `Device:R`, `Device:C` | 0805 preferred | Bigger than 0603, easier to inspect/rework. |

## Important Supporting Parts

| Function | Value | Placement Note |
|---|---:|---|
| USB-C CC pull-downs | 5.1k | One from CC1 to GND, one from CC2 to GND. |
| EN pull-up | 10k | `EN` to `3V3`, button pulls `EN` to GND. |
| BOOT pull-up | 10k | `GPIO0` to `3V3`, button pulls `GPIO0` to GND. |
| SD pull-ups | 10k | On CMD, D0, D1, D2, D3 near the socket. |
| SD series resistors | 22R-33R | On SCK, MOSI, CS near ESP32. Start with 22R. |
| ESP32 bulk cap | 10uF or 22uF | Close to ESP32 `3V3` pins. |
| ESP32 decoupling | 100nF | Close to ESP32 power pins. |
| SD decoupling | 100nF + 10uF | Close to SD socket `VDD`. |
| Amp bulk cap | 470uF optional | Near amp/module 5V input for speaker bursts. |
| Amp decoupling | 100nF + 10uF | Near amp/module power pins. |
| Amp mode selector | On the blue module | Module defaults to mono average from its onboard 1M SD-to-VIN resistor. |
| Amp mute transistor | MMBT3904/SS8050 class NPN | GPIO21 HIGH pulls `SD/MODE` low for shutdown/mute. |

## Notes On The 3.3V Regulator

Rev A uses AP2112K-3.3TRG1 in SOT-23-5/SOT25. The SOT25 pinout from the Diodes
datasheet is:

```text
1 VIN
2 GND
3 EN
4 NC
5 VOUT
```

`EN` is tied to `5V_SYS`, so the 3.3V rail turns on whenever the selected 5V
source is present. The datasheet typical circuit uses 1uF input and output
capacitors; our 22uF bulk capacitors plus local 100nF decoupling are compatible
and give more reservoir for ESP32 radio bursts.

## Notes On The Audio Amp

The KiCad library has a `MAX98357A` symbol, but using the bare chip may force us
into a tiny package. For Rev A the safer move is to solder a MAX98357A breakout
module onto the board with short pins. That still fixes the breadboard problem,
while keeping the first PCB easy to inspect and repair.

Rev A is now locked to the blue 7-pin MAX98357A module already on hand. With the
component side facing up and the 7-pin row along the bottom edge, the header order
from left to right is:

```text
LRC / WS
BCLK
DIN
GAIN
SD / MODE
GND
VIN / 5V
```

The module also has two speaker pads near the top edge. The photo labels show
left pad as speaker minus and right pad as speaker plus. Rev A does not route
those speaker pads through the carrier PCB; solder the speaker or a small speaker
terminal directly to the blue module.

In the generated Rev A schematic, the module `GAIN` pin is intentionally left
unconnected, so the selected module uses its printed default 9 dB hardware gain.
Software volume still controls the I2S sample level before the amplifier;
hardware gain is a later board-level option if the default is not enough.

The `SD/MODE` pin is analog-ish: low shuts the amp down, and intermediate
voltages choose stereo-average, right, or left output. This module already has
onboard bias for its printed default `(L+R)/2` mono average mode, so Rev A does
not add mode-selection resistors or jumpers.

```text
Default: no mode shunt installed; module onboard bias gives mono average
```

GPIO21 does not drive `SD/MODE` directly. Instead it drives an NPN transistor.
When `AMP_MUTE_CTL` is HIGH, the transistor pulls `SD/MODE` to GND and mutes the
amp. When `AMP_MUTE_CTL` is LOW, the transistor is off and the module default
controls the amp.

The large 470uF capacitor footprint near the amp is marked DNP, meaning the pads
exist on the PCB but the capacitor is not assembled by default. It can be
hand-soldered later if speaker current bursts cause supply dips, clicks, or weak
bass.

## Notes On The microSD Socket

The microSD footprint is locked to Molex `104031-0811`. Sockets are annoying:
their pin numbering, shell tabs, and card-detect switches vary, which is why Rev A
uses the exact Molex footprint instead of a lookalike generic socket.

For SPI mode, the socket nets are:

| microSD Pin | Name | Board Net |
|---:|---|---|
| 1 | DAT2 | Pull-up only, optional future use |
| 2 | DAT3 / CD | `SD_CS` |
| 3 | CMD | `SD_MOSI` |
| 4 | VDD | `3V3` |
| 5 | CLK | `SD_SCK` |
| 6 | VSS | `GND` |
| 7 | DAT0 | `SD_MISO` |
| 8 | DAT1 | Pull-up only, optional future use |

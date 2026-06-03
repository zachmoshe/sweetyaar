# Rev A Part / Footprint Lock

Checked on 2026-05-18. This is the manufacturing-facing lock pass for the
generated Rev A schematic. The schematic source of truth is still
`tools/generate_schematic.py`; this file records which exact parts are safe to
use with the footprints already assigned there.

Status meanings:

- `Locked`: use this part/footprint unless JLC stock changes at quote time.
- `Conditional`: usable, but run one more quote or datasheet check before order.
- `Not locked`: do not release the PCB until this row is resolved.
- `Hand-solder`: buy separately or place after board delivery.

## Main Parts

| Ref(s) | Function | Chosen part / LCSC or manufacturer number | JLC status | KiCad footprint | Risk | Decision / notes |
|---|---|---|---|---|---|---|
| `J1` | USB-C USB2 sink receptacle | Korean Hroparts `TYPE-C-31-M-12`, LCSC `C165948` | Extended / verify in JLC quote | `Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12` | Medium | Locked to current footprint. LCSC lists `TYPE-C-31-M-12` as a 16-position USB-C receptacle with SMD packaging and high stock. The local KiCad footprint is explicitly named for this part and includes the 16 top-side signal pads, two locating holes, and four through-hole shield tabs. Check JLC preview for shield-slot plating and orientation before ordering. |
| `U1` | USB-UART bridge | WCH `CH340C`, JLC/LCSC `C7464026`; fallback legacy SKU `C84681` | Extended, economic/standard | `Package_SO:SOIC-16_3.9x9.9mm_P1.27mm` | Low | Locked to `C7464026`. JLC's warning on `C84681` points to another `CH340C` SOP-16 SKU, not to a different chip family. `C7464026` keeps the same schematic, internal oscillator assumption, and SOIC/SOP-16 footprint. 2026-05-18 LCSC reference price: `C7464026` from about `$0.3470`; old `C84681` from about `$0.3557`. If both CH340C SKUs become unavailable, do not silently swap to `CH340G`, `CH340N`, `CH343`, or `CP2102N`; those require schematic/footprint review. |
| `U2` | 3.3 V LDO | Diodes `AP2112K-3.3TRG1`, JLC/LCSC `C51118` | Extended, economic/standard | `Package_TO_SOT_SMD:SOT-23-5` | Low | Locked. JLC lists SOT-25-5 and 600 mA fixed 3.3 V output. Schematic pinout is `1 VIN`, `2 GND`, `3 EN`, `4 NC`, `5 VOUT`, matching the AP2112K SOT25 package used by the footprint. |
| `U3` | ESP32 module | Espressif `ESP32-WROOM-32E-N4`, JLC/LCSC `C701341` | Extended, standard-only | `RF_Module:ESP32-WROOM-32E` | Medium | Locked with assembly caveat. JLC lists the module as `SMD,25.5x18mm` with PCB antenna. Use standard PCBA or hand assembly, place the antenna at the board edge, and keep copper/wiring/speaker leads out of the antenna keepout. |
| `J4` | microSD socket | Molex `104031-0811` | Locked / distributor source or assembly quote | `Connector_Card:microSD_HC_Molex_104031-0811` | Medium | Locked. Use the Molex socket instead of searching for a JLC-only substitute. The footprint is specifically Molex `104031-0811`, with eight card contacts on 1.10 mm pitch plus detect pads `9`/`10` and SMD shell tabs. The schematic currently ignores detect pads and exposes `SD_CD` on `J8`; that is OK for Rev A. |
| `U4` | I2S amp module | User-owned blue MAX98357A I2S mono amp module | Hand-solder | `Connector_PinHeader_2.54mm:PinHeader_1x07_P2.54mm_Vertical` | Low | Locked to the photographed module's bottom 7-pin row. Left-to-right with component side up: `LRC`, `BCLK`, `DIN`, `GAIN`, `SD`, `GND`, `VIN`. Speaker output is not routed through the carrier; solder the speaker or terminal directly to the module's top `SPK-`/`SPK+` holes. |
| `J2` | External 5 V terminal | MAX/MaiXu `MX126-5.0-02P-GN01-Cu-S-A`, LCSC `C5188434` | Hand-solder / loose LCSC buy | `TerminalBlock:TerminalBlock_MaiXu_MX126-5.0-02P_1x02_P5.00mm` | Low | Locked. This is the exact MX126-family 2-pin, 5.00 mm pitch through-hole terminal matching the selected footprint family. 2026-05-18 LCSC reference price: from about `$0.0300`. Viable fallback: KANGNEX `WJ126V-5.0-02P-14-00A`, LCSC `C8404`, from about `$0.0414`; use only if the MX126 part is unavailable, because the body/silkscreen may differ even though the 5.00 mm pin pitch is compatible. |
| `SW1`, `SW2` | EN/RST and BOOT tactile switches | E-Switch `TL3342AF160QG`, LCSC `C4364807` | Exact footprint / source or hand-solder | `Button_Switch_SMD:SW_SPST_TL3342` | Low | Locked to the exact TL3342 footprint family. 2026-05-18 LCSC reference price: from about `$0.2677`; JLC assembly stock may be zero, so plan to source/hand-solder these if needed. Cheap assembly fallback: XKB `TS-1187A-B-A-B`, LCSC `C318884`, from about `$0.0113`, but use it only with a deliberate footprint/preview check because it is a 5.1 mm class lookalike, not the named TL3342 footprint. |
| `Q1`, `Q2`, `Q3` | NPN auto-program and amp mute transistors | JSCJ `MMBT3904(RANGE:100-300)`, LCSC `C20526` | Basic / high-stock class | `Package_TO_SOT_SMD:SOT-23` | Low | Locked. The local symbol maps pad `1` to base, `2` to emitter, and `3` to collector; standard MMBT3904 SOT-23 top-view pinout is `1=B`, `2=E`, `3=C`, matching the footprint. 2026-05-18 LCSC reference price: from about `$0.0051`. |
| `D1`, `D2` | 5 V power and status LEDs | `D1`: Hubei KENTO `KT-0805G`, LCSC `C2297`; `D2`: yellow 0805 LED, LCSC `C2296` | Basic / current library candidate | `LED_SMD:LED_0805_2012Metric` | Low | Locked. `D1` green keeps power conventional; `D2` yellow gives visual distinction without adding footprint risk. 2026-05-18 LCSC reference prices: `C2297` from about `$0.0080`; `C2296` from about `$0.0066`. |
| `JP1` | 5 V source select | G-Switch `MS-22D28-G020`, LCSC/JLC `C963205` | JLC assembly / hand-solder | `SweetYaar:SW-SMD_MS-22D28-G020` | Low | Top-actuated DPDT slide switch. Only pole 1 is used: pad `2` is common `5V_SYS`, pad `1` selects `USB_VBUS`, pad `3` selects `EXT_5V`; pads `4`-`6` are intentionally unused. Rated 1 A at 6 V. |
| `J6`, `J7`, `J8` | SPI, I2C, GPIO expansion | 2.54 mm vertical pin headers | Hand-solder | `Connector_PinHeader_2.54mm:PinHeader_1x08_P2.54mm_Vertical`, `...1x04...`, `...1x12...` | Low | Locked as hand-soldered. Standard breakaway male headers are fine for Rev A. |
| `TP1`-`TP18` | Test pads | Bare PCB pads | PCB only | `TestPoint:TestPoint_Pad_D1.5mm` | Low | Locked. No BOM part. |
| `JP2` | GPIO2 status LED enable | G-Switch `MS-22D28-G020`, LCSC/JLC `C963205` | JLC assembly / hand-solder | `SweetYaar:SW-SMD_MS-22D28-G020` | Low | Top-actuated DPDT slide switch. Only pole 1 is used as on/off: pad `2` is `LED_STATUS_IN`, pad `1` is `GPIO2_LED`, pad `3` is off/unconnected, and pads `4`-`6` are intentionally unused. |

## Passives

Use 0805 passives for Rev A. That keeps the board easy to inspect and rework, and
it matches the generated schematic footprints.

| Ref(s) | Function | Chosen part / LCSC or manufacturer number | JLC status | KiCad footprint | Risk | Decision / notes |
|---|---|---|---|---|---|---|
| `R1`, `R2` | USB-C CC pull-downs | UNI-ROYAL `0805W8F5101T5E`, LCSC `C27834`, 5.1k 1% 0805 | Basic/verify quote | `Resistor_SMD:R_0805_2012Metric` | Low | Locked. 1% is fine; exact tolerance is not critical. |
| `R3` | 5 V LED resistor | UNI-ROYAL `0805W8F2201T5E`, LCSC `C17520`, 2.2k 1% 0805 | Basic/verify quote | `Resistor_SMD:R_0805_2012Metric` | Low | Locked. Gives a modest power LED current on 5 V. |
| `R4`, `R5`, `R6`, `R7`, `R14`-`R18`, `R24` | Pullups/base resistors | UNI-ROYAL `0805W8F1002T5E`, LCSC `C17414`, 10k 1% 0805 | Basic/verify quote | `Resistor_SMD:R_0805_2012Metric` | Low | Locked. High-stock 0805 10k class part; use the same reel for all 10k positions. |
| `R10` | Status LED resistor | UNI-ROYAL `0805W8F1001T5E`, LCSC `C17513`, 1k 1% 0805 | Basic | `Resistor_SMD:R_0805_2012Metric` | Low | Locked. |
| `R11`, `R12`, `R13` | SD SPI series resistors | UNI-ROYAL `0805W8F220JT5E`, LCSC `C17561`, 22R 1% 0805 | Basic/verify quote | `Resistor_SMD:R_0805_2012Metric` | Low | Locked. Place near ESP32 during layout. |
| `R19`, `R20` | I2C pullups | UNI-ROYAL `0805W8F4701T5E`, LCSC `C17673`, 4.7k 1% 0805 | Basic | `Resistor_SMD:R_0805_2012Metric` | Low | Locked. |
| `R25` | Amp mute-base pulldown | UNI-ROYAL `0805W8F1003T5E`, LCSC `C17407`, 100k 1% 0805 | Basic/verify quote | `Resistor_SMD:R_0805_2012Metric` | Low | Locked. Same 0805 resistor family as the other UNI-ROYAL passives. 2026-05-18 LCSC reference price: from about `$0.0013`. |
| `C3`, `C4`, `C5`, `C8`, `C10`, `C13`, `C14` | 100 nF decoupling | Yageo `CC0805KRX7R9BB104`, JLC/LCSC `C49678`, 100nF 50V X7R 0805 | Basic | `Capacitor_SMD:C_0805_2012Metric` | Low | Locked. Use this one 100 nF part everywhere. |
| `C6` | EN delay cap | Samsung `CL21B105KBFNNNE`, LCSC `C28323`, 1uF 50V X7R 0805 | Basic/verify quote | `Capacitor_SMD:C_0805_2012Metric` | Low | Locked. Much more voltage headroom than needed for the EN RC node and a stable X7R dielectric. 2026-05-18 LCSC reference price: from about `$0.0080`. |
| `C9`, `C12` | SD and amp local bulk | CCTC `TCC0805X5R106K250FT`, LCSC `C5448891`, 10uF 25V X5R 0805 | Extended/verify quote | `Capacitor_SMD:C_0805_2012Metric` | Low | Locked. 25 V rating gives comfortable headroom on the 5 V amp rail while staying in 0805. 2026-05-18 LCSC reference price: from about `$0.0098`. |
| `C1`, `C2`, `C7` | 5 V / 3.3 V local bulk | Samsung `CL21A226MAQNNNE`, JLC/LCSC `C45783`, 22uF 25V X5R 0805 | Basic/verify quote | `Capacitor_SMD:C_0805_2012Metric` | Medium | Locked. 22uF in 0805 still loses capacitance under DC bias, but the 25 V rating and large local count are good enough for Rev A reservoir caps. 2026-05-18 JLC/LCSC reference price: from about `$0.0228` on LCSC / about `$0.0319` at JLC 1+. |
| `C11` | Optional amp bulk capacitor | 470uF radial electrolytic, 6.3 V or higher | DNP / hand-solder if needed | `Capacitor_THT:CP_Radial_D6.3mm_P2.50mm` | Low | Locked as DNP. Do not include in the assembled BOM by default. |

## Footprint Checks Already Done

The local KiCad USB-C footprint description points at the HRO `TYPE-C-31-M-12`
datasheet and its pad pattern matches the expected HRO-style 16-position USB-C
receptacle: 0.3/0.6 mm signal/power pads, two non-plated locating holes, and
four mechanical shield tabs.

The local KiCad microSD footprint is explicitly `microSD_HC_Molex_104031-0811`.
Its main contacts are numbered `1` through `8`, with separate `9`/`10` detect
pads. Because Rev A does not wire card detect at the socket, the detect pads can
remain unused as long as they do not get accidentally tied to `SD_CD`.

The TL3342 switch footprint and MX126 terminal footprint are now tied to exact
parts. They still need the same final quote-preview inspection as every connector:
look for pad-center alignment, insertion direction, and silkscreen orientation
before buying boards.

## Blockers Before Layout Release

The MAX98357A module blocker is resolved by locking to the blue 7-pin module's
bottom header row. Because Rev A does not mate to the top speaker holes, there is
no special module-body footprint to verify before layout.

The microSD decision is locked to Molex `104031-0811`. Buy this exact socket from
a normal distributor or use an assembler who can source it; do not substitute a
random JLC/LCSC microSD socket unless the footprint is deliberately replaced.

The CH340C lifecycle warning is resolved for Rev A by using JLC/LCSC `C7464026`,
which is also `CH340C` in SOP-16. The old `C84681` SKU is only a fallback.

## Sources

- [LCSC `TYPE-C-31-M-12` / `C165948`](https://www.lcsc.com/product-detail/C165948.html)
- [JLCPCB `CH340C` / `C84681`](https://jlcpcb.com/partdetail/wch_jiangsu_Qin_heng-CH340C/C84681)
- [JLCPCB `CH340C` / `C7464026`](https://jlcpcb.com/partdetail/WCH_Jiangsu_Qin_Heng-CH340C/C7464026)
- [JLCPCB `AP2112K-3.3TRG1` / `C51118`](https://jlcpcb.com/partdetail/DiodesIncorporated-AP2112K_33TRG1/C51118)
- [JLCPCB `ESP32-WROOM-32E-N4` / `C701341`](https://jlcpcb.com/partdetail/EspressifSystems-ESP32_WROOM_32EN4/C701341)
- [Molex `104031-0811`](https://www.molex.com/en-us/products/part-detail/1040310811)
- [Adafruit MAX98357A breakout pinouts](https://learn.adafruit.com/adafruit-max98357-i2s-class-d-mono-amp/pinouts)
- [SparkFun MAX98357A breakout product page](https://www.sparkfun.com/products/14809)
- [Techexpress MAX98357A module listing with 19 x 18 mm size](https://www.techexpress.co.nz/products/max98357a-i2s-audio-amplifier-pcb-module)
- [JLCPCB `CC0805KRX7R9BB104` / `C49678`](https://jlcpcb.com/partdetail/YAGEO-CC0805KRX7R9BB104/C49678)
- [JLCPCB `0805W8F1001T5E` / `C17513`](https://jlcpcb.com/partdetail/18201-0805W8F1001T5E/C17513)
- [JLCPCB `0805W8F4701T5E` / `C17673`](https://jlcpcb.com/partdetail/C17673)
- [LCSC `0805W8F1003T5E` / `C17407`](https://www.lcsc.com/product-detail/C17407.html)
- [LCSC `0805W8F3903T5E` / `C17656`](https://www.lcsc.com/product-detail/C17656.html)
- [LCSC `MX126-5.0-02P-GN01-Cu-S-A` / `C5188434`](https://www.lcsc.com/product-detail/C5188434.html)
- [LCSC `WJ126V-5.0-02P-14-00A` / `C8404`](https://www.lcsc.com/product-detail/C8404.html)
- [LCSC `TL3342AF160QG` / `C4364807`](https://www.lcsc.com/product-detail/C4364807.html)
- [LCSC `TS-1187A-B-A-B` / `C318884`](https://www.lcsc.com/product-detail/C318884.html)
- [LCSC `MMBT3904(RANGE:100-300)` / `C20526`](https://www.lcsc.com/product-detail/C20526.html)
- [Diodes `MMBT3904` datasheet](https://www.diodes.com/datasheet/download/MMBT3904.pdf)
- [LCSC `CL21B105KBFNNNE` / `C28323`](https://www.lcsc.com/product-detail/C28323.html)
- [LCSC `TCC0805X5R106K250FT` / `C5448891`](https://www.lcsc.com/product-detail/C5448891.html)
- [JLCPCB `CL21A226MAQNNNE` / `C45783`](https://jlcpcb.com/partdetail/46786-CL21A226MAQNNNE/C45783)
- [LCSC `KT-0805G` / `C2297`](https://www.lcsc.com/product-detail/C2297.html)
- [LCSC yellow 0805 LED / `C2296`](https://www.lcsc.com/product-detail/C2296.html)
- Local KiCad footprint files under `/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints`.

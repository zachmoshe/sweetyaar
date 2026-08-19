# SweetYaar Hardware

SweetYaar is built around an original ESP32-WROOM-32, a microSD card, and a
MAX98357A I2S amplifier driving a single speaker. Two push buttons provide the
child's controls, while a passive vibration switch wakes the toy from deep
sleep. The parent app and Bluetooth speaker connection use the ESP32's built-in
radio and do not require additional wireless hardware.

This document is the hardware source of truth. The pin definitions in
`src/Config.h` remain authoritative when hardware and firmware disagree. See
[Firmware](firmware.md) for device behavior and [Mobile App](mobile-app.md) for
parent controls. Unresolved production choices are called out in highlighted
**TBD** blocks so they are not lost inside otherwise authoritative prose.

## System overview

The ESP32 owns every digital interface. It reads content from the SD card over
SPI, sends decoded or Bluetooth audio to the amplifier over I2S, reads the two
buttons, and controls peripheral power before deep sleep.

```text
                          +----------------------+
buttons -------- GPIO --->|                      |---- SPI ----> microSD card
vibration -- RTC GPIO --->|   ESP32-WROOM-32     |---- I2S ----> MAX98357A ----> speaker
parent app ------ BLE --->|                      |
audio source - BT A2DP -->|                      |
                          +----------------------+
```

The production power system adds three rails:

```text
single-cell LiPo / charger SYS
              |
              +---- TPS63802 set to 3.3 V ------- 3V3_AON ---- ESP32
              |                                      |
              |                                      +---- load switch ---- 3V3_PERIPH_SW
              |
              +---- TPS63802 set to 5 V, switched ------------ 5V_PERIPH_SW
```

The ESP32 remains powered from `3V3_AON` during deep sleep. The SD card and
amplifier use switched rails so they do not dominate standby current.

The target must be the original ESP32-WROOM-32. ESP32-S3, C3, and C6 devices do
not provide the Classic Bluetooth A2DP support used by SweetYaar. All GPIO uses
3.3 V logic, and the ESP32, SD card, amplifier, external supply, and test
equipment must share a common ground.

## Signal map

The same signal assignments are used by the DevKit prototype and the planned
PCB.

| GPIO | Firmware name | Direction | Hardware connection | Behavior |
|---:|---|---|---|---|
| 26 | `HW_I2S_BCLK` | Output | MAX98357A `BCLK` | I2S bit clock. |
| 25 | `HW_I2S_WS` | Output | MAX98357A `LRCLK` / `LRC` / `WS` | I2S word-select clock. |
| 22 | `HW_I2S_DOUT` | Output | MAX98357A `DIN` | I2S audio data. |
| 21 | `PIN_AMP_MUTE` | Output | `AMP_MUTE_CTL` low-side transistor | Active HIGH mute control; the transistor pulls `SD_MODE` LOW. |
| 18 | `PIN_SD_SCK` | Output | microSD `SCK` / `CLK` | SPI clock, 20 MHz after initialization. |
| 19 | `PIN_SD_MISO` | Input | microSD `MISO` / `DO` | Card-to-ESP32 data. |
| 23 | `PIN_SD_MOSI` | Output | microSD `MOSI` / `DI` / `CMD` | ESP32-to-card data. |
| 5 | `PIN_SD_CS` | Output | microSD `CS` | SPI chip select, active LOW. |
| 32 | `PIN_BTN1` | Input with internal pull-up | Song button to GND | Active LOW. |
| 33 | `PIN_BTN2` | Input with internal pull-up | Animal button to GND | Active LOW. |
| 27 | `PIN_VIB_WAKE` | Externally biased RTC input | Normally-closed vibration switch to GND | Resting LOW; movement opens the switch and wakes EXT0 on HIGH. |
| 13 | `PIN_PERIPH_PWR_EN` | Output | `PERIPH_PWR_EN`: SD load-switch `EN` and 5 V converter `EN` | HIGH while awake; RTC-held LOW during deep sleep. |
| 2 | `PIN_LED` | Output | DevKit LED or production status LED and resistor | Firmware assumes active HIGH. |

No GPIO is currently assigned to I2C, battery-voltage measurement, charger
status or control, an encoder, or additional sensors. Those functions are
outside the current design; adding one would require a corresponding pin
assignment in both the schematic and firmware.

## Hardware development and debugging

For firmware development, use an ESP32-WROOM-32 38-pin DevKitC with separate,
replaceable modules: a MAX98357A breakout, a 4 Ω or 8 Ω speaker, and a 5 V-ready
microSD SPI breakout. Connect the two push buttons directly between their GPIOs
and ground. Add the normally-closed vibration switch and its external pull-up
when testing sleep and wake behavior.

Bring the system up in stages. Start with the ESP32 connected over a data-capable
USB cable so flashing and serial logs remain available. Add and verify the SD
module first, then the amplifier at low volume, then the buttons, and finally
the vibration circuit. Keeping each subsystem modular makes it possible to
replace a suspect SD or amplifier board without disturbing the rest of the
setup.

For ordinary firmware work, power the SD and amplifier directly from a stable,
current-capable 5 V bench supply and share ground with the ESP32. Do not rely on
a long USB power path: it has previously sagged enough to cause brownouts and
misleading resets. Add the production load switch, boost converter, and battery
path only when those circuits themselves are under test.

This modular setup proves signals and firmware, not battery life. On the current
prototype board GPIO13 drives only an indicator LED; it does not disconnect
either peripheral. Deep sleep can therefore be tested functionally, but its
measured current includes the powered SD and amplifier modules and is not a
production result.

### Audio wiring

| MAX98357A breakout pin | Connect to |
|---|---|
| `VIN` | Stable 5 V. |
| `GND` | Common GND. |
| `BCLK` | GPIO26. |
| `LRC`, `LRCLK`, or `WS` | GPIO25. |
| `DIN` | GPIO22. |
| `SD` or `SD_MODE` | Output of the active-HIGH mute transistor described below. |
| `OUT+`, `OUT-` | The two speaker terminals. Neither terminal is ground. |

The firmware sends 44.1 kHz, 16-bit stereo I2S. The MAX98357A produces one
speaker channel, so the breakout's `SD_MODE` bias determines whether it uses the
left channel, right channel, or a mix of both. Verify the breakout configuration
rather than assuming every module uses the same default.

The planned mute circuit is inverted relative to the ESP32 output:

```text
GPIO21 HIGH ---- mute transistor ON  ---- SD_MODE pulled LOW ---- amplifier off
GPIO21 LOW  ---- mute transistor OFF ---- SD_MODE bias active --- amplifier on
```

GPIO21 should drive the transistor input, not a production `SD_MODE` net
directly. The normal `SD_MODE` bias must still select the desired audio channel
when the transistor is off. This control provides deterministic mute and
click/pop sequencing; removing 5 V power remains the production deep-sleep
isolation mechanism.

### SD-card wiring

| microSD breakout pin | Connect to |
|---|---|
| `VCC` | 5 V only for a breakout explicitly designed for 5 V input. |
| `GND` | Common GND. |
| `SCK` or `CLK` | GPIO18. |
| `MISO` or `DO` | GPIO19. |
| `MOSI`, `DI`, or `CMD` | GPIO23. |
| `CS` | GPIO5. |

A 5 V-ready module usually includes its own regulator and level shifting. A
bare card socket does not: it requires a 3.3 V supply, 3.3 V signals, local
decoupling, and the pull-ups required by the card interface.

### Buttons and vibration wake

```text
GPIO32 ---- song button ------ GND
GPIO33 ---- animal button ---- GND

3V3_AON ---- 470 kΩ ----+---- GPIO27
                            |
                            +---- normally-closed vibration switch ---- GND
```

The button inputs use the ESP32's internal pull-ups. The vibration input does
not: firmware disables the internal and RTC pulls on GPIO27 and expects the
external 470 kΩ bias shown above. At rest, the closed switch holds GPIO27 LOW.
Movement opens it, the resistor raises GPIO27 HIGH, and the ESP32 wakes through
EXT0. This normally-closed, wake-HIGH circuit replaces the earlier
normally-open, wake-LOW prototype assumption.

## Planned production PCB

The production design must solve two problems that the DevKit prototype does
not: safe single-cell charging and low standby current. The power tree is
therefore split into one always-on ESP32 rail and two peripheral rails that are
disabled during deep sleep.

### Power rails and deep sleep

| Rail | Source | Loads | State during deep sleep |
|---|---|---|---|
| `SYS` | Battery/charger power path | Both TPS63802 regulator inputs | Available while the main power switch is on. |
| `3V3_AON` | TPS63802 set to 3.3 V | ESP32, wake pull-up, and control logic | On. |
| `3V3_PERIPH_SW` | AP2281-3WG-7 load switch | Bare microSD card and every SD pull-up | Off. |
| `5V_PERIPH_SW` | TPS63802 set to 5 V, with true shutdown | MAX98357A amplifier | Off. |

GPIO13, named `PERIPH_PWR_EN`, is the shared active-HIGH enable for the AP2281
and the 5 V TPS63802. The firmware drives it HIGH during boot. Before sleeping,
firmware stops playback, mutes the amplifier, closes SD/SPI/I2S, changes
peripheral signal pins to high-impedance inputs, drives `PERIPH_PWR_EN` LOW, and
enables RTC hold so the pin stays LOW while the main CPU sleeps.

A 100 kΩ physical pulldown from GPIO13/`PERIPH_PWR_EN` to GND is required even
though firmware controls and RTC-holds the pin. It keeps both switched branches
off during reset, bootloader entry, flashing, and failures before firmware has
configured the GPIO. Do not add an enable pull-up that would defeat this safe
default.

The wake switch remains connected to `3V3_AON`. Its 470 kΩ pull-up draws
about 7 µA while the normally-closed switch holds the input LOW. On movement,
GPIO27 wakes the ESP32; wake is a normal reboot, after which GPIO13 powers the
peripherals again. If the switch is still open when the toy wants to sleep,
firmware waits for it to close before arming the HIGH-level wake source; this
prevents an immediate wake loop.

#### Deep-sleep quiescent-current budget

Target: **less than 50 µA at the battery**, with the main switch on and USB
disconnected. These are selection targets until the production PCB is measured.

| Component | Deep-sleep state | Reference current | Sleep budget |
|---|---|---:|---:|
| BQ25185 charger/power path | Battery-only; system asleep | 4 µA typical, 5 µA maximum | **4–5 µA** |
| Battery-pack protection | Always on | TBD | **1–2 µA** |
| TPS63802 3.3 V buck-boost | Always on | 11 µA typical | **11–14 µA** |
| ESP32-WROOM-32 + EXT0 | Deep sleep | 10–15 µA | **10–15 µA** |
| 470 kΩ vibration pull-up | Always on | 7 µA | **7 µA** |
| AP2281 SD load switch | Disabled; input powered | 0.01 µA typical | **≤1 µA** |
| microSD + SD pull-ups | **Off on peripheral rail** | 0.1–1 mA card standby; 70–330 µA per 10–47 kΩ pull-up held LOW | **≈0 µA** |
| TPS63802 5 V buck-boost | `EN` LOW; input powered | 0.045 µA typical, 0.6 µA maximum | **≤1 µA** |
| Separate amplifier load switch | Not required with the disconnecting 5 V TPS63802 | 0 µA | **0 µA** |
| MAX98357A | `SD_MODE` LOW, then **off on peripheral rail** | 0.6 µA typical / 2 µA maximum in `SD_MODE` shutdown | **≈0 µA** |
| Leakages | Mute transistor, GPIO, PCB, capacitors, and backfeed | TBD | **2–3 µA** |
| **Expected total** | — | — | **35–48 µA** |

The SD rail is switched because card standby current alone exceeds the complete
sleep budget. SD bias uses pull-ups, not pull-downs.

Firmware asserts the MAX98357A's `SD_MODE` shutdown before disabling the 5 V
converter. The converter is still disabled because its enabled no-load current
would be additional. Its true shutdown means no separate amplifier load switch
is required.

References:
[BQ25185 datasheet](https://www.ti.com/lit/ds/symlink/bq25185.pdf),
[TPS63802 datasheet](https://www.ti.com/lit/ds/symlink/tps63802.pdf),
[TPS631000 datasheet](https://www.ti.com/lit/ds/symlink/tps631000.pdf),
[AP2281 product data](https://www.diodes.com/part/view/AP2281),
[MAX98357A datasheet](https://www.analog.com/media/en/technical-documentation/data-sheets/MAX98357A-MAX98357B.pdf),
[Kingston industrial microSD specification](https://www.kingston.com/datasheets/SDCIT-specsheet-64gb_th.pdf).

### Switched SD rail

The AP2281-3WG-7 switches 3.3 V only for the bare SD card. It does not power the
amplifier. The following SOT26 pinout is a top/marking-side view; the PCB pad
view is mirrored.

```text
                    AP2281-3WG-7
                        _______
3V3_PERIPH_SW ------ 1 --|     |-- 6 ------- 3V3_AON
common GND --------- 2 --|     |-- 5 ------- common GND
PERIPH_PWR_EN ------- 3 --|_____|-- 4 ------- 3V3_AON
```

| Pin | Name | Connection |
|---:|---|---|
| 1 | `OUT` | `3V3_PERIPH_SW`, feeding the card and every SD pull-up. |
| 2, 5 | `GND` | Common ground. |
| 3 | `EN` | GPIO13 / `PERIPH_PWR_EN`, with the 100 kΩ pulldown. |
| 4, 6 | `IN` | `3V3_AON`. |

Connect both `IN` pins and both `GND` pins. Place the datasheet-recommended
1 µF capacitor from `IN` to GND and 0.1 µF from `OUT` to GND close to the
device. These switch capacitors do not replace the local and bulk decoupling
required by the microSD card. The `-3` variant includes an output-discharge path
when disabled, but the AP2281 does not provide reverse-current blocking. SD
signal pins and pull-ups must therefore be arranged so they cannot back-power
`3V3_PERIPH_SW` while it is off. See the
[AP2281 datasheet](https://www.diodes.com/datasheet/download/AP2281.pdf) before
creating the symbol, footprint, or layout.

### Amplifier rail and mute circuit

The MAX98357A is powered from `5V_PERIPH_SW`. The boost converter may provide the
amplifier's sleep isolation only if its datasheet guarantees **true load
disconnect** with `EN` LOW. Some boost topologies still pass battery or `SYS`
voltage to the output through a diode or internal switch when disabled; those
parts require a separate amplifier load switch.

GPIO21 and the mute transistor are retained even with a disconnecting boost.
They allow firmware to mute before clocks or power disappear and to unmute only
after the rail and I2S interface are stable.

The custom PCB cannot assume the pinout or passive components of a breakout.
The production PCB will use `MAX98357AETE+T` in the 16-pin, 3 × 3 mm TQFN
package with 0.5 mm pitch and an exposed pad, matching the generic prototype
board `prod/v1.0`. Do not use the WLP or an SOP-8 footprint. Connect the exposed
pad to a solid ground plane for thermal dissipation.

The channel mode is **mixed mono** (`left/2 + right/2`), so both channels of a
stereo source reach the single speaker. The chosen amplifier gain is **9 dB**;
leave `GAIN_SLOT` unconnected to select that MAX98357A default. Place 0.1 µF and
10 µF VDD bypass capacitors close to the IC and follow the required ground and
thermal layout described in the
[MAX98357A datasheet](https://www.analog.com/media/en/technical-documentation/data-sheets/MAX98357A-MAX98357B.pdf).

GPIO21 (`PIN_AMP_MUTE`, driving `AMP_MUTE_CTL`) is the active-HIGH `SD_MODE`
mute control. It must drive a low-side transistor rather than `SD_MODE`
directly:

```text
GPIO21 HIGH ---- transistor ON  ---- SD_MODE pulled LOW ---- shutdown
GPIO21 LOW  ---- transistor OFF ---- mixed-mono bias active - amplifier on
```

The transistor must behave as an open-drain pull-down: it must never drive
`SD_MODE` HIGH, must tolerate 5 V on its switched side, must turn on reliably
from 3.3 V GPIO logic, and must not add material always-on or deep-sleep current.
Power the mixed-mono bias network from `5V_PERIPH_SW` so it cannot back-power the
amplifier while the rail is off. The exact transistor part is not constrained.

The speaker connects only between `OUTP` and `OUTN`; neither Class-D output may
be tied to ground.

#### Speaker impedance and enclosure

| Speaker | Advantages | Tradeoffs |
|---|---|---|
| 4 Ω | Higher available electrical power and maximum-volume headroom. | About twice the current and power of 8 Ω at the same output voltage; more battery drain, boost stress, amplifier heating, and distortion risk. This is the power-path worst case. |
| 8 Ω | Lower current and heat, easier power-path design, and potentially longer runtime. | About half the electrical power of 4 Ω at the same output voltage, so maximum volume may be lower. |

Speaker sensitivity and enclosure design can matter more to perceived loudness
than impedance alone. Compare candidates using their sensitivity rating and
test both at the fixed 9 dB amplifier gain. Final electrical validation must
still include a 4 Ω speaker at maximum requested volume.

The top three enclosure considerations are:

1. **Acoustic volume and sealing:** Size the air chamber for the selected
   speaker and keep the front and rear sound paths separated. Air leaks or an
   unsuitable chamber volume can remove bass and reduce output more than the
   4 Ω versus 8 Ω choice.
2. **Sound opening and grille:** Give the cone a clear sound path with enough
   open area. Test the real grille, doll fabric, padding, and decorative layers;
   they must protect the cone without muffling it or touching its excursion.
3. **Mounting and vibration:** Mount the speaker rigidly with a gasket or other
   controlled seal, provide wire strain relief, and keep loose PCB, battery,
   fastener, and enclosure parts away from it. Validate at maximum volume for
   buzzes, rattles, and movement while preserving child-safe retention.

> [!WARNING]
> **TBD — Speaker and enclosure:** Select the production speaker impedance and
> power rating together with the enclosure volume, then validate it at the
> fixed 9 dB amplifier gain.

### Battery, charging, and regulation

The production design assumes a protected, single-cell LiPo. The current test
battery is 3400 mAh; approximately 2000 mAh is probably sufficient if runtime
and enclosure tests confirm it. A LiFePO4 cell is possible, but requires a
different BQ25185 charge-voltage setting and revised battery-level thresholds;
the voltage divider, regulator limits, and firmware state-of-charge mapping
must all be revalidated.

| Item | Decision or requirement |
|---|---|
| Battery chemistry | 1S LiPo baseline: 3.7 V nominal, 4.2 V charge termination. |
| Capacity | 3400 mAh tested; approximately 2000 mAh likely usable, pending runtime and fit tests. |
| Battery protection | Required: protected pack/cell with overcharge, over-discharge, over-current, and short-circuit protection. Add a correctly rated fuse or resettable polyfuse in the product power path. |
| Charger | [BQ25185DLHR](https://www.ti.com/product/BQ25185), 1-cell charger with power path, input-current management, thermal regulation, and selectable LiPo/LiFePO4 charge voltage. |
| Use while charging | Supported. Power the device from `SYS`; the BQ25185 reduces charge current when the input or thermal limit is reached and allows the battery to supplement load peaks. |
| Charge current | 1 A in the current setup; final value is TBD and must follow the selected battery's charge-rate limit and enclosure thermal test. |
| Battery thermistor | TBD. The BQ25185 `TS/MR` input supports battery-temperature monitoring; reserve the required thermistor/passive footprints and do not leave the input undefined. |

The BQ25185's charger fault handling does not replace battery-pack protection.
Its 1 A charge setting is also separate from operating current: system load gets
priority, and only the remaining input current is available for charging.

#### 3.3 V and 5 V buck-boost regulators

The current selection is **two TPS63802DLARs**: one always-on 3.3 V regulator
and one switched 5 V regulator. Both options below cover both output voltages
and provide true-shutdown load disconnect. Price and stock are JLCPCB/LCSC
snapshots from 2026-08-18.

| Option | Electrical and thermal | JLCPCB/LCSC | Pros | Cons |
|---|---|---|---|---|
| **[TPS63802DLAR](https://www.ti.com/lit/ds/symlink/tps63802.pdf) — selected** | 2 A class, 4 A minimum boost-current limit; 11 µA enabled, 0.045 µA shutdown; 81°C/W | [C2845237](https://jlcpcb.com/partdetail/TexasInstruments-TPS63802DLAR/C2845237), Extended; 3.2k stock; $0.97 | Better 5 V current and thermal margin; lower shutdown current; `PGOOD` available. | About 3 µA more sleep current on the always-on rail; larger and about $0.44 more. |
| [TPS631000DRLR](https://www.ti.com/lit/ds/symlink/tps631000.pdf) | 2 A at 3.3 V; 5 V/1 A requires validation; 2.6 A minimum peak limit; 8 µA enabled, 0.5 µA shutdown; 132.7°C/W | [C5219190](https://jlcpcb.com/partdetail/TexasInstruments-TPS631000DRLR/C5219190), Extended; 46.4k stock; $0.53 | Lower cost, lower always-on Iq, smaller package, and much higher stock. | Less 5 V current and thermal margin; no `PGOOD`. |

The TPS63802's 3 × 2 mm VSON-HR package has no separate central thermal-pad
pin. Follow TI's GND-pad and copper layout; its specified board-level thermal
resistance is still substantially lower than the TPS631000's.

Output voltage is set by `VOUT -> Rtop -> FB -> Rbottom -> GND`, using
`VOUT = 0.5 V × (1 + Rtop/Rbottom)`. Use 1% resistors:

| Rail | Rtop | Rbottom | Calculated nominal output |
|---|---:|---:|---:|
| `3V3_AON` | 510 kΩ | 91 kΩ | 3.302 V |
| `5V_PERIPH_SW` | 820 kΩ | 91 kΩ | 5.005 V |

The 3.3 V instance is always enabled. GPIO13 enables the 5 V instance and its
100 kΩ pulldown keeps it disabled during reset and sleep. Start with `MODE` LOW
(PFM) on both instances; use forced PWM on the 5 V instance only if audio tests
show objectionable PFM noise. Leave both open-drain `PGOOD` pins unconnected.

The expected amplifier load is a few hundred milliamps with approximately
500 mA bursts; the design target remains 1 A at 5 V. At 90% efficiency, the
converter dissipates about 0.17 W at 300 mA, 0.28 W at 500 mA, and 0.56 W at
1 A. Validate output droop and temperature at minimum `SYS` voltage inside the
enclosure.

> [!WARNING]
> **TBD — Battery capacity and charging:** Select the production protected LiPo,
> confirm whether approximately 2000 mAh meets runtime, choose the final charge
> current (currently 1 A), and decide whether to fit a battery thermistor.

The regulator-IC selection is complete. PCB implementation still requires exact
inductor, capacitor, and power-path fuse part numbers plus transient,
efficiency, and thermal validation.

This is a child product. The enclosure must prevent crushing or puncturing the
cell, isolate sharp edges, and provide strain relief and keyed connectors for
battery and speaker wiring. Early battery prototypes should be charged only
under supervision. The charging and protection circuit requires an electronics
safety review before a PCB is manufactured or installed in a doll.

### Power budget

The current prototype draws approximately 200–250 mA from its 5 V supply during
normal playback. This is a measured whole-device value for the DevKit setup,
with the SD breakout and amplifier continuously powered. It is not a per-rail
measurement and does not represent maximum-volume playback or deep sleep.

The normally-closed vibration circuit draws approximately 7 µA from
`3V3_AON` while at rest, calculated from its 3.3 V supply and 470 kΩ pull-up.
The charger module now under test is configured by default for 1 A charging;
that is a charging value and must not be confused with the toy's operating
current.

> [!WARNING]
> **TBD — Production power measurements:** On the production power tree,
> measure battery-side current during maximum-volume Bluetooth playback with a
> 4 Ω speaker, startup and radio transients, charging while loaded if supported,
> and total deep-sleep current. Do not claim a final operating or sleep-current
> budget until those measurements exist.

### PCB and programming requirements

The current mechanical target is an approximately 60 × 40 mm, two-layer board
for a small JLCPCB run. The microSD slot must sit on an enclosure edge so the
card remains replaceable. The board also needs robust connectors for the
battery, speaker, and both external buttons, plus a physical power switch.

The USB-C connector is for charging only, not firmware data. The production PCB
must therefore expose a safe programming interface for UART, `EN`, boot mode,
power, and ground.

> [!WARNING]
> **TBD — Programming interface:** Select a header, pogo-pad layout, or onboard
> USB-to-UART circuit before the schematic and board layout are finalized.

> [!WARNING]
> **TBD — Mechanical details:** Validate the approximately 60 × 40 mm outline
> against the doll enclosure, then finalize connector types, SD-card access,
> power-switch placement, and the vibration switch part, footprint, and
> orientation.

## Bring-up and validation

### DevKit functional bring-up

Before applying power, verify the supply voltage printed on each module, common
ground, SPI and I2S signal placement, button-to-ground wiring, and speaker
connection. In particular, neither speaker output goes to ground, and GPIO21
must drive the mute circuit with the polarity expected by the firmware.

After flashing, a normal serial boot includes:

```text
=== SweetYaar Boot ===
[Power] Peripherals enabled on GPIO13
[WavPlayer] SD OK
[BT] A2DP sink started as "SweetYaar"
[Boot] Ready.
```

Validate local song and animal playback, both-button stop, BLE controls, A2DP
audio, and vibration wake before treating the pinout as proven. If SD reads are
intermittent or MISO remains LOW, check the card module and physical connection
before changing firmware; defective microSD breakouts have caused this symptom
on the prototype.

### Production power bring-up

Bring up the production power tree with a current-limited bench supply before
connecting a LiPo or speaker. A practical order is:

1. Verify the charger/protection and `SYS` behavior by themselves.
2. Verify `3V3_AON` across the intended battery range and during ESP32 radio
   bursts.
3. Toggle `PERIPH_PWR_EN` and confirm that `3V3_PERIPH_SW` and
   `5V_PERIPH_SW` start and stop cleanly.
4. With the switched rails off, check every SPI, I2S, and control pin for
   backfeeding.
5. Validate SD initialization and low-volume audio before increasing speaker
   load.
6. Measure full-volume Bluetooth playback with the selected 4 Ω speaker,
   including converter temperature and battery-side transient current.
7. Enter deep sleep and measure total battery current, not only an individual
   rail.
8. Move the vibration switch and confirm that the rails return only after the
   ESP32 reboots.

During deep sleep, `PERIPH_PWR_EN`, `3V3_PERIPH_SW`, and `5V_PERIPH_SW` should
all measure LOW or off. A partly powered rail usually means backfeeding through
SPI, I2S, a control signal, an always-on pull-up, an indicator LED, or a boost
converter that lacks true load disconnect.

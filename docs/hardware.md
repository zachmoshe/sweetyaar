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
              +---- low-Iq 3.3 V buck-boost ---- 3V3_AON ---- ESP32
              |                                      |
              |                                      +---- load switch ---- 3V3_PERIPH_SW
              |
              +---- 5 V boost with load disconnect ------------ 5V_PERIPH_SW
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
| 13 | `PIN_PERIPH_PWR_EN` | Output | `PERIPH_PWR_EN`: SD load-switch `EN` and 5 V boost `EN` | HIGH while awake; RTC-held LOW during deep sleep. |
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
| `SYS` | Battery/charger power path | 3.3 V regulator and 5 V boost input | Available while the main power switch is on. |
| `3V3_AON` | Low-quiescent-current buck-boost | ESP32, wake pull-up, and control logic | On. |
| `3V3_PERIPH_SW` | AP2281-3WG-7 load switch | Bare microSD card and every SD pull-up | Off. |
| `5V_PERIPH_SW` | Boost converter with true load disconnect | MAX98357A amplifier | Off. |

GPIO13, named `PERIPH_PWR_EN`, is the shared active-HIGH enable for the AP2281
and the 5 V boost. The firmware drives it HIGH during boot. Before sleeping,
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
The bare MAX98357A is offered in TQFN and WLP packages, not SOP-8. Its
`SD_MODE` network must deliberately select left, right, or mixed-mono audio,
and `GAIN_SLOT` must deliberately select the amplifier gain. The layout must
use the manufacturer footprint and include the required VDD decoupling and
thermal layout described in the
[MAX98357A datasheet](https://www.analog.com/media/en/technical-documentation/data-sheets/MAX98357A-MAX98357B.pdf).

> [!WARNING]
> **TBD — Amplifier implementation:** Select the exact orderable MAX98357A
> package, channel mode, and gain-setting network before creating the
> production symbol, footprint, and layout.

The speaker connects only between `OUTP` and `OUTN`; neither Class-D output may
be tied to ground. Final validation must include a 4 Ω speaker at maximum
requested volume because that is the highest-current case currently planned.

> [!WARNING]
> **TBD — Speaker and enclosure:** Select the production speaker impedance and
> power rating together with the enclosure volume and amplifier gain.

### Battery, charging, and regulation

The current test setup uses a 3400 mAh single-cell LiPo and a charger module
whose default charge current is 1 A. That combination has performed well in
testing so far.

The production power system has the following requirements:

| Function | Requirement |
|---|---|
| Battery | Protected single-cell LiPo from a reputable supplier. |
| Charger | Single-cell charger with thermal regulation, charge termination, status, and appropriate input/battery protection. |
| Charge current | The selected cell must explicitly support the configured current, and charging must remain thermally safe inside the enclosure. |
| 3.3 V regulator | Low-Iq buck-boost, at least 500 mA output, with acceptable ESP32 radio transient response across the battery range. |
| 5 V boost | Active-HIGH enable, true load disconnect, and at least 1 A output capability at the low-battery limit. |
| Protection | Pack protection plus a correctly rated fuse or resettable polyfuse; use temperature sensing where possible. |

> [!WARNING]
> **TBD — Battery and power components:** Evaluate whether an approximately
> 2000 mAh pack provides sufficient runtime, then select the production battery,
> charger or power-path IC, `3V3_AON` buck-boost, `5V_PERIPH_SW` boost, and
> protection components. Confirm the exact battery voltage limits and permitted
> charge current from the selected cell's datasheet.

The tested 1 A charging current is separate from the toy's operating-current
requirement. A power-path design must safely support the system load and the
remaining battery-charge current at the same time. Moving to a 2000 mAh pack
does not automatically make 1 A safe; the permitted charge rate comes from the
specific cell datasheet and must be checked thermally in the enclosure.

> [!WARNING]
> **TBD — Operation while charging:** Confirm whether the toy may operate while
> connected to USB power. If it may, the charger must provide a real power path
> that prioritizes the system load, reduces charging under input or thermal
> limits, and lets the battery supplement load peaks. A simpler charger is
> acceptable only if the toy is intentionally off while charging.

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

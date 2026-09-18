# SweetYaar Hardware

SweetYaar is built around an original ESP32-WROOM-32, a microSD card, and a
MAX98357A I2S amplifier driving a single speaker. Two push buttons provide the
child's controls, while a passive vibration switch wakes the toy from deep
sleep. The parent app and Bluetooth speaker connection use the ESP32's built-in
radio and do not require additional wireless hardware.

This document is the hardware source of truth. The pin definitions in
`firmware/esp32/src/Config.h` remain authoritative when hardware and firmware disagree. See
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

The production power system keeps onboard USB charging permanently available,
adds an optional auxiliary charging input from an off-board source located
elsewhere inside the device, and generates three system rails. The TPS2116
provides reverse-current isolation between the two positive supply paths; this
is not galvanic isolation, and both sources share the mainboard ground.

```text
USB_VBUS ---------------- TPS2116 VIN1 (priority) --+
                                                     +---- TPS2116 VOUT ---- 5V_INPUT ---- BQ25185 IN
off-board regulated 5 V -- AUX_5V_IN -- VIN2 -------+

protected 18650 Li-ion ------------------------------ BQ25185 BAT
           |
           +---- AP2281 switched divider -------------------------- GPIO36 ADC1

BQ25185 SYS ---- hard-off SPST switch ----+---- TPS63802 3.3 V ---- 3V3_AON ---- ESP32
                                          |                                  |
                                          |                                  +---- load switch ---- 3V3_PERIPH_SW
                                          |
                                          +---- TPS63802 5 V, switched -------------------- 5V_PERIPH_SW
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
| 21 | `PIN_AMP_MUTE` | Output | Production: 634 kΩ directly to MAX98357A `SD_MODE`; generic board: Q3 mute transistor | Production is active LOW; the generic board is active HIGH. Select the matching firmware environment. |
| 18 | `PIN_SD_SCK` | Output | microSD `SCK` / `CLK` | SPI clock, 20 MHz after initialization. |
| 19 | `PIN_SD_MISO` | Input | microSD `MISO` / `DO` | Card-to-ESP32 data. |
| 23 | `PIN_SD_MOSI` | Output | microSD `MOSI` / `DI` / `CMD` | ESP32-to-card data. |
| 5 | `PIN_SD_CS` | Output | microSD `CS` | SPI chip select, active LOW. |
| 32 | `PIN_BTN1` | Input with internal pull-up | Song button to GND | Active LOW. |
| 33 | `PIN_BTN2` | Input with internal pull-up | Animal button to GND | Active LOW. |
| 27 | `PIN_VIB_WAKE` | Externally biased RTC input | Normally-closed vibration switch to GND | Resting LOW; movement opens the switch and wakes EXT0 on HIGH. |
| 13 | `PIN_PERIPH_PWR_EN` | Output | `PERIPH_PWR_EN`: SD load-switch `EN`, battery-sense load-switch `EN`, and 5 V converter `EN` | HIGH while awake; RTC-held LOW during deep sleep. |
| 34 | `PIN_CHARGER_STAT1` | Input with external pull-up | BQ25185 `STAT1` | First charger-status bit; 10 kΩ pull-up to `3V3_AON`. |
| 35 | `PIN_CHARGER_STAT2` | Input with external pull-up | BQ25185 `STAT2` | Second charger-status bit; 10 kΩ pull-up to `3V3_AON`. |
| 36 | `PIN_BATTERY_ADC` | ADC1 input | Midpoint of the switched 634 kΩ / 200 kΩ `BAT` divider; the 200 kΩ lower leg is two series 100 kΩ resistors | Calibrated coarse battery-state measurement on ADC1_CH0. |
| 2 | `PIN_STATUS_LED_DATA` | RMT output | 10 kΩ to the base of the status-LED MMBT3904 level shifter | Firmware waveform is inverted by default; the NPN restores normal addressable-LED polarity at `LED_DIN`. |

GPIO16 and GPIO17 were released by the addressable status LED and are currently
unassigned. No GPIO is currently assigned to I2C, charger control, an encoder,
or additional sensors. Charger status and coarse battery level use the three
input-only pins GPIO34, GPIO35, and GPIO36 as listed above.

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
| `SD` or `SD_MODE` | Production wiring: GPIO21 through 634 kΩ. The generic board instead uses its onboard active-HIGH Q3 circuit. |
| `OUT+`, `OUT-` | The two speaker terminals. Neither terminal is ground. |

The firmware sends 44.1 kHz, 16-bit stereo I2S. The MAX98357A produces one
speaker channel, so the breakout's `SD_MODE` bias determines whether it uses the
left channel, right channel, or a mix of both. Verify the breakout configuration
rather than assuming every module uses the same default.

The two supported boards use opposite GPIO21 polarity:

```text
Production board — direct push-pull control:
  GPIO21 LOW  ---- SD_MODE LOW ------------------------------- amplifier off
  GPIO21 HIGH ---- 634 kΩ plus internal 100 kΩ pull-down ---- mixed mono

Generic board — MMBT3904 low-side control:
  GPIO21 HIGH ---- transistor ON  ---- SD_MODE LOW ---------- amplifier off
  GPIO21 LOW  ---- transistor OFF ---- mixed-mono bias ------ amplifier on
```

Flash PlatformIO environment `sweetyaar` on the production board and
`sweetyaar-generic` on the generic board. Both targets use the same
`setAmpMuted()` behavior in source code; only the compile-time electrical
polarity differs. Removing 5 V power remains the production deep-sleep
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
normally-open, wake-LOW prototype assumption. On the production board, the
vibration switch is a PCB-mounted component soldered directly to the board; it
does not use an external cable or connector.

The production PCB uses one four-pin connector for both child buttons, arranged
as two adjacent pairs: `BTN_SONG`, GND, `BTN_ANIMAL`, GND. Both GND pins join the
same PCB ground, but duplicating the contact lets every physical button wire be
crimped into its own terminal; the harness needs no splice or double-wire crimp.
Each pair runs to a physically separate normally-open button. Pressing a button
closes its signal to GND; pressing both at once safely pulls both GPIOs LOW. The
exact connector family remains a schematic/BOM selection.

## Planned production PCB

The production design must solve two problems that the DevKit prototype does
not: safe single-cell charging and low standby current. The power tree is
therefore split into one always-on ESP32 rail and two peripheral rails that are
disabled during deep sleep.

### Power rails and deep sleep

| Rail | Source | Loads | State during deep sleep |
|---|---|---|---|
| `SYS` | BQ25185 `SYS` output through the single hard-off switch | BQ25185 `SYS` bypass capacitor on the charger side of the switch; both TPS63802 regulator inputs and their 10 µF input capacitors on the disconnected side | Available from the battery or charging input while the hard-off switch is closed. Opening the switch disconnects the regulator feed even if USB or AUX is attached, while the battery remains connected to the charger and may still charge. |
| `3V3_AON` | TPS63802 set to 3.3 V | TPS63802 22 µF output capacitor, ESP32 and its decoupling, 470 kΩ GPIO27 wake pull-up, 510 kΩ/91 kΩ regulator-feedback divider, and the disabled AP2281 input with its 1 µF capacitor | On. GPIO2 is released only after the switched 5 V rail is off. |
| `3V3_PERIPH_SW` | AP2281-3WG-7 load switch | Bare microSD card and every SD pull-up | Off. |
| `5V_PERIPH_SW` | TPS63802 set to 5 V, with true shutdown | MAX98357A, one addressable 5 mm status LED and its 1 kΩ data pull-up, plus future switchable 5 V peripherals that fit the validated power budget | Off. |

`5V_PERIPH_SW` is the general switched 5 V peripheral rail, not an
amplifier-only net. Future loads may use it if the regulator's steady-state and
transient limits are revalidated and every new signal crossing from an
always-powered domain obeys the unpowered-domain rules below.

GPIO13, named `PERIPH_PWR_EN`, is the shared active-HIGH enable for both AP2281
instances and the 5 V TPS63802. The firmware drives it HIGH during boot. Before
sleeping, firmware stops playback, mutes the amplifier, closes SD/SPI/I2S, changes
peripheral signal pins to high-impedance inputs, drives `PERIPH_PWR_EN` LOW, and
enables RTC hold so the pin stays LOW while the main CPU sleeps.

A 100 kΩ physical pulldown from GPIO13/`PERIPH_PWR_EN` to GND is required even
though firmware controls and RTC-holds the pin. It keeps all switched branches
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

Target: **at most 75 µA at the battery**, with the main switch on and USB, AUX,
and the debugger disconnected. This is a design target until the production PCB
is measured, not a measured consumption figure.

For a **3400 mAh** battery, continuous sleep at 75 µA gives an ideal
`3400 mAh / 0.075 mA = 45,333 hours`, or **1,889 days / 5.17 years**.
The electronics consume 1.8 mAh per day at that current. This is a capacity-only
estimate, not a shelf-life guarantee: battery self-discharge, aging, temperature,
unusable capacity below cutoff, and every wake/playback interval shorten it.

The budget assumes that both buttons are released, the addressable status LED
and its data pull-up are unpowered, GPIO2 is high-impedance,
`PERIPH_PWR_EN` is RTC-held LOW, and no unlisted
indicator, test-point pull-up, or other circuit is connected to `SYS` or
`3V3_AON`. The `STAT1` and `STAT2` external pull-ups and BQ25185 output leakage
must be included in the final
audit. Both TPS63802 `PGOOD` pins are left unconnected. The budget treats
currents specified at `3V3_AON` as approximately battery-side currents; the
exact battery current depends on battery voltage and the 3.3 V converter's
efficiency at very light load.

| Component | Deep-sleep state | Reference current | Sleep budget |
|---|---|---:|---:|
| BQ25185 charger/power path | Battery-only; system asleep | 4 µA typical, 5 µA maximum at 3.6 V and 0–85°C | **4–5 µA** |
| 18650 protection circuit | Always on | ARB-L18-3500 reference cell; verify a substitute does not exceed the reference design allocation | **1–2 µA provisional** |
| TPS63802 3.3 V buck-boost | Always on | 11 µA typical | **11–14 µA** |
| ESP32-WROOM-32 + EXT0 | Deep sleep | 10–15 µA | **10–15 µA** |
| 3.3 V feedback divider | 510 kΩ from `3V3_AON` to `FB`, 91 kΩ from `FB` to GND | 3.302 V / 601 kΩ = 5.49 µA at `3V3_AON` | **5–7 µA battery-side** |
| 470 kΩ vibration pull-up | Always on | 7 µA | **7 µA** |
| GPIO13 100 kΩ pulldown | GPIO13 and all three controlled enable inputs held LOW | 0 V across the resistor; EN leakage is included in the two AP2281 rows and the 5 V TPS63802 row | **≈0 µA** |
| Buttons and addressable indicator | Buttons released; `5V_PERIPH_SW` off; GPIO2 high-impedance after the rail is removed | The LED, 1 kΩ pull-up, and MMBT3904 collector are unpowered; the 10 kΩ base resistor has no driven voltage | **≈0 µA** |
| `STAT1` / `STAT2` inputs | Battery-only state is HIGH/HIGH through the two 10 kΩ pull-ups | BQ25185 high-level output leakage is 1 µA maximum per pin; include ESP32 input leakage | **≤2 µA, provisional** |
| Always-powered ceramic capacitors | BQ25185 `BAT` 1 µF and `SYS` ≥10 µF; two TPS63802 10 µF input capacitors; 3.3 V TPS63802 22 µF output capacitor; SD-switch AP2281 `IN` 1 µF; battery-sense AP2281 `IN` 1 µF; ESP32 local decoupling | Dielectric insulation leakage; exact capacitor part numbers not selected | **≤2 µA combined, provisional** |
| AP2281 SD load switch | Disabled; input powered | 0.01 µA typical | **≤1 µA** |
| AP2281 battery-sense load switch | `PERIPH_PWR_EN` LOW; `BAT` input powered, divider output discharged | 0.01 µA typical, 1 µA maximum shutdown current | **≤1 µA** |
| Battery-sense divider | Disconnected from `BAT` by its AP2281; the series 200 kΩ lower leg holds GPIO36 at GND | No voltage across the 634 kΩ / 200 kΩ path | **≈0 µA** |
| microSD + SD pull-ups | **Off on peripheral rail** | 0.1–1 mA card standby; 70–330 µA per 10–47 kΩ pull-up held LOW | **≈0 µA** |
| TPS63802 5 V buck-boost | `EN` LOW; input powered | 0.045 µA typical, 0.6 µA maximum | **≤1 µA** |
| Separate amplifier load switch | Not required with the disconnecting 5 V TPS63802 | 0 µA | **0 µA** |
| MAX98357A | `SD_MODE` LOW, then **off on peripheral rail** | 0.6 µA typical / 2 µA maximum in `SD_MODE` shutdown | **≈0 µA** |
| Production GPIO21-to-`SD_MODE` control | GPIO21 is driven LOW before `5V_PERIPH_SW` is disabled and may remain LOW or become high-impedance in deep sleep; the 634 kΩ series resistor has no powered DC path | No intended current path | **≈0 µA** |
| PCB surface leakage | Clean, dry PCB | Not predictable from the schematic alone | **≤1 µA provisional** |
| **Planning total** | — | — | **approximately 38–59 µA** |

The capacitor allocation covers only capacitors that retain DC voltage in
battery-only sleep. The BQ25185 `IN` capacitor and capacitors on
`3V3_PERIPH_SW` and `5V_PERIPH_SW` are unpowered and have approximately zero DC
leakage in this state. The final BOM must sum the maximum specified insulation
leakage of every always-powered capacitor; the **≤2 µA** value is an allocation,
not a measured or guaranteed result.

The resistor paths intentionally excluded from the total have zero voltage
across them in the defined sleep state: the GPIO13 100 kΩ pulldown, the 5 V
feedback divider on its discharged output, and the amplifier's 634 kΩ
GPIO21-to-`SD_MODE` connection while GPIO21 is LOW or high-impedance. The open
button pull-ups also have no intended DC path, but a button held to GND during
sleep can add pull-up current and is not covered by this budget.
Charger-programming resistors are treated as part of
the BQ25185's specified battery-only quiescent current. The selected Semitec
103AT-2 thermistor connects between `TS/MR` and battery ground. The charger
biases `TS/MR` while an input source is present; there is no intended thermistor
current path in battery-only sleep, but final-board leakage at this pin remains
part of the sleep-current audit. If the thermistor is omitted, fit a fixed
10 kΩ resistor from `BAT_TEMP`/`TS/MR` to GND instead. Never leave `BAT_TEMP`
open: an open input is interpreted as a temperature fault and prevents normal
charging. The fixed-resistor option deliberately disables real battery-temperature
protection and must be recorded as an assembly choice.

> [!WARNING]
> **TBD — Close the deep-sleep design budget:** Obtain or measure the
> ARB-L18-3500 protection circuit's maximum standby current and require any
> substitute cell not to exceed that allocation. Select the exact
> always-powered ceramic capacitors, charger-status input leakage, and the
> second AP2281's maximum shutdown leakage,
> then add their worst-case leakage rather than relying on the provisional
> allocations above. Recalculate battery-side current across the intended
> battery-voltage and temperature range and audit every final-schematic
> connection to `SYS` and `3V3_AON`. The resulting worst-case design budget must
> stay within 75 µA with documented margin. If it does not, reduce fixed current—
> starting with the 3.3 V feedback divider—subject to the TPS63802's
> feedback-network requirements and noise validation.

Production-PCB current measurement remains a separate validation item under
**Production power measurements** and will be performed after the current-shunt
test fixture is available. It validates the completed schematic and BOM; it
does not replace the design-budget calculation required to close this TBD.

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
when disabled. Supply every SD pull-up from `3V3_PERIPH_SW` so the card and its
passive network switch off together. See the
[AP2281 datasheet](https://www.diodes.com/datasheet/download/AP2281.pdf) before
creating the symbol, footprint, or layout.

### Switched battery-sense divider

Use a second **AP2281-3WG-7** as a high-side switch between `BAT` and the
battery divider. This repeats an existing IC rather than adding a new unique
assembly part. Keep this switch primarily to prevent `BAT` from biasing GPIO36
and the unpowered ESP32 when hard-off disconnects `SYS`; removing the divider's
sleep current is a secondary benefit. Its approximately 80 mΩ typical
on-resistance drops less than 1 µV at the divider's microampere current, so it
does not materially affect the battery measurement. Sharing `PERIPH_PWR_EN`
disconnects the divider during deep sleep as well as hard-off.

```text
BAT+ ---- AP2281 IN
              OUT ---- 634 kΩ ----+---- GPIO36 / ADC1_CH0
                                  |
                                100 kΩ
                                  |
                                100 kΩ
                                  |
                                 GND

GPIO36 / ADC1_CH0 ---- 100 nF ---- GND
AP2281 EN ------------ PERIPH_PWR_EN
AP2281 GND ----------- GND
```

GPIO36 is the divider midpoint, not a connection after both resistors. With the
switch enabled, the nominal ADC voltage is
`VBAT × 200 kΩ / (634 kΩ + 200 kΩ)`: 1.007 V at 4.2 V, 0.815 V at 3.4 V,
and 0.743 V at 3.1 V. The divider draws 5.04 µA at 4.2 V while awake. Implement
the documented 200 kΩ lower leg as two ordinary 1% 100 kΩ resistors in series;
634 kΩ and 100 kΩ already occur elsewhere on the PCB. Averaging and hysteresis
handle short-term ADC noise, while the deliberately coarse states do not require
precision 0.1% resistors. Divider tolerance creates a fixed unit-to-unit threshold
offset rather than zero-centered sample noise, so verify the thresholds on
production boards.

Connect the AP2281 as in the SD-switch pin table, except `IN` is `BAT`, `OUT` is
the switched divider supply, and `EN` remains `PERIPH_PWR_EN`. Fit the
datasheet-recommended 1 µF input and 0.1 µF output capacitors, plus the 100 nF
ADC-node capacitor shown above. The `-3` variant actively discharges its output
when disabled; the series 200 kΩ lower leg holds the ADC node at GND. Firmware
enables 2.5 dB ADC attenuation (`ADC_2_5db`) and uses calibrated millivolt readings.
The critical battery-warning transitions (3.1–3.4 V) map to 743–815 mV through
the divider. Exact accuracy at the upper end of the battery range is not
required: the ADC provides coarse battery-state thresholds, while charging
state is detected from the BQ25185 `STAT1`/`STAT2` pins.

### Amplifier rail and mute circuit

The MAX98357A is powered from `5V_PERIPH_SW`. The boost converter may provide the
amplifier's sleep isolation only if its datasheet guarantees **true load
disconnect** with `EN` LOW. Some boost topologies still pass battery or `SYS`
voltage to the output through a diode or internal switch when disabled; those
parts require a separate amplifier load switch.

GPIO21 remains under firmware control even with a disconnecting boost. It lets
firmware place the amplifier in shutdown before clocks or power disappear and
enable it only after the rail and I2S interface are stable.

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

`C_AMP3` is a 470 µF polarized bulk capacitor from `5V_PERIPH_SW` to GND.
It is intentionally marked DNP for automated PCBA and will be soldered manually
after assembly; **it is populated in the completed Rev A board**. Its polarity
must be observed. This capacitor is retained because the prototype showed
resets during loud playback without local bulk capacitance. The DNP flag is an
assembly-method marker, not a decision to omit the capacitor from final use.

On the production board, connect GPIO21 to `SD_MODE` through one **634 kΩ, 1%**
series resistor. Do not fit an external transistor, pull-up, or pull-down on
this path. The MAX98357A includes an internal 100 kΩ ±8% pull-down:

```text
GPIO21 ---------------- 634 kΩ ---------------- SD_MODE
                                                   |
                                      internal 100 kΩ ±8%
                                                   |
                                                  GND
```

This is the push-pull-driver connection in Figure 5 of the MAX98357A datasheet.
With 3.3 V GPIO logic, the datasheet specifies `RLARGE = 634 kΩ`; together with
the internal pull-down it produces approximately 0.45 V at `SD_MODE`, safely
selecting mixed mono. GPIO21 LOW selects shutdown. A reset/high-impedance GPIO
also lets the internal pull-down default the amplifier to shutdown.

Firmware must drive GPIO21 LOW before enabling `5V_PERIPH_SW`, keep it LOW while
the rail and I2S clocks initialize, and drive it HIGH only when ready to play.
Before power-off, firmware must drive GPIO21 LOW before stopping I2S and
disabling `5V_PERIPH_SW`. It must never drive GPIO21 HIGH while the amplifier
rail is off. The production `sweetyaar` build therefore defaults to active-LOW
mute. The generic board retains its active-HIGH MMBT3904 circuit and uses the
`sweetyaar-generic` firmware environment.

For comparison, the generic board implements GPIO21 control as follows:

```text
                                  +---- 100 kΩ ---- GND
                                  |
GPIO21 -------- 10 kΩ -------- Q3 base
                              Q3 emitter --------- GND
                              Q3 collector ------- SD_MODE

3V3 ----------- 634 kΩ --------------------------- SD_MODE
```

On that board GPIO21 HIGH turns Q3 on and mutes the amplifier; GPIO21 LOW turns
Q3 off and lets the 634 kΩ resistor select mixed mono. This inversion is why it
must use the `sweetyaar-generic` build rather than the default production build.

The speaker connects only between `OUTP` and `OUTN`; neither Class-D output may
be tied to ground.

#### Speaker electrical interface

| Speaker | Advantages | Tradeoffs |
|---|---|---|
| 4 Ω | Higher available electrical power and maximum-volume headroom. | About twice the current and power of 8 Ω at the same output voltage; more battery drain, boost stress, amplifier heating, and distortion risk. This is the power-path worst case. |
| 8 Ω | Lower current and heat, easier power-path design, and potentially longer runtime. | About half the electrical power of 4 Ω at the same output voltage, so maximum volume may be lower. |

The PCB and amplifier path must support both 4 Ω and 8 Ω speakers. Speaker
impedance is selected per doll installation rather than globally: 8 Ω reduces
load current, while 4 Ω provides more electrical output. The difference in
whole-device current is expected to be modest in normal use. Electrical checks
use the speaker selected for the doll installation; no acoustic comparison or
sound-pressure-level measurement between the two impedances is required. Use
one keyed two-pin speaker connector with a short stranded harness; it must not
be interchangeable with the battery connector.

### Battery, charging, and regulation

The production reference cell is the removable, protected **Fenix
ARB-L18-3500 18650 Li-ion battery**. The
[ARB-L18-3500](https://www.fenixlighting.com/products/fenix-arb-l18-3500-rechargeable-18650-battery/1000)
specifies 1 A recommended charging and is the mechanical and electrical baseline
for the holder and power path; its published size is approximately 69 mm long by
18.6 mm diameter. An alternative cell is acceptable only as a compatible
substitute: protected button-top 18650, 1S Li-ion, approximately 3.6–3.7 V
nominal and 4.2 V maximum, at least 1 A charging capability, and more than 2 A
continuous discharge capability. It must fit the same holder and enclosure;
capacity may vary without changing the PCB design.

| Item | Decision or requirement |
|---|---|
| Battery format and chemistry | Fenix ARB-L18-3500 reference cell, or an electrically and mechanically compatible protected, removable button-top 1S 18650 Li-ion substitute: approximately 3.6–3.7 V nominal and 4.2 V maximum. |
| Required current capability | At least 1 A charging and more than 2 A continuous discharge. These are minimum substitute-cell requirements, not open product choices. |
| Capacity | May vary without changing the PCB, provided the substitute still meets the fixed electrical, protection, and mechanical requirements. |
| Battery protection | The cell must include overcharge, over-discharge, over-current, and short-circuit protection. **Fit no additional fuse or resettable PTC in the current design.** Verify the complete holder, harness, connector, switch, and PCB under expected and fault-current conditions. |
| Charger | [BQ25185DLHR](https://www.ti.com/product/BQ25185), 1-cell charger with power path, input-current management, thermal regulation, and selectable LiPo/LiFePO4 charge voltage. |
| External-source mux | [TPS2116DRLR](https://www.ti.com/product/TPS2116), with USB `VBUS` on priority input `VIN1`, `AUX_5V_IN` on backup input `VIN2`, and `VOUT` feeding BQ25185 `IN`. It provides automatic priority selection, reverse-current blocking, and a 2.5 A path. |
| Auxiliary-source requirement | `AUX_5V_IN` comes from a complete off-board power module mounted elsewhere inside the device, such as a regulated wireless-charging receiver. Require 5.0 V nominal and never more than 5.5 V at the mainboard input. For the default 1.1 A input-current limit, the source and harness must have a continuous-current rating above 1.1 A with suitable margin; otherwise configure `JP_ILIM` for approximately 0.5 A and validate the complete device under load. Connect only a regulated DC output, never a raw wireless-power coil or unregulated rectifier output. |
| Use while charging | Supported. Power the device from `SYS`; the BQ25185 reduces charge current when the input or thermal limit is reached and allows the battery to supplement load peaks. |
| Charge current | **1 A production default, switchable to approximately 0.5 A with one solder jumper.** Connect two 301 Ω resistors in series from `ISET` to GND and place the jumper across the resistor nearest GND. Jumper open gives 602 Ω and approximately 0.5 A; bridged bypasses that resistor, leaving 301 Ω and approximately 1 A. Ship with the jumper bridged. |
| Charger input-current limit | **1.1 A production default, manually switchable to approximately 0.5 A with `JP_ILIM`.** Bridged bypasses the 5.1 kΩ series resistor and leaves 13 kΩ from `ILIM/VSET` to GND; open gives 18.1 kΩ. Both settings select 4.2 V Li-ion charging. This is an assembly/configuration choice, not an automatic response to the connected source. |
| USB charger requirement | Require a 5 V USB-C charger that advertises at least 1.5 A on CC. The supported 1.1 A configuration stays below that advertised capability. The first revision has two 5.1 kΩ CC pull-downs but does not decode the source's CC current advertisement and does not automatically change `JP_ILIM`. |
| Battery connector | Connect the 18650 holder's short harness through a three-position connector from the larger 2.5 mm-pitch JST-XH family. Carry `BAT+`, `BAT−`/GND, and `BAT_TEMP`; choose the physical pin order during schematic/layout review and mark it unambiguously on the PCB and harness. |
| Battery thermistor | Preferred configuration: fit a **Semitec 103AT-2** 10 kΩ NTC (10 kΩ at 25°C, B25/85 = 3435 K) in the battery-holder harness. Connect BQ25185 `TS/MR` to `BAT_TEMP`; connect the thermistor between `BAT_TEMP` and `BAT−`/GND at the holder. If the thermistor is omitted, fit a fixed 10 kΩ resistor from `BAT_TEMP`/`TS/MR` to GND instead; never leave the input open. The fixed resistor permits charging but removes actual cell-temperature protection. Electrically insulate a fitted sensor and press or tape it against the cell wrapper. Do not solder to, scrape, or use the bare 18650 can as a connection. |

The BQ25185 uses `I_CHG = 300 AΩ / R_ISET`; 301 Ω gives approximately 0.997 A
and 602 Ω gives approximately 0.498 A. The two-resistor arrangement is
electrically valid and reduces the resistor BOM to one value; label the jumper
clearly so it cannot accidentally short `ISET` directly to GND. Its charger
fault handling does not replace cell protection. The 1 A charge setting is also
separate from operating current: system load gets priority, and only the
remaining input current is available for charging.

This is a deliberate source-compatibility tradeoff. The two 5.1 kΩ `CC1` and
`CC2` pull-downs identify the board as a USB-C sink, but they do not decode or
verify the source's advertised current. For the supported USB configuration,
the product relies on a 5 V source that advertises at least 1.5 A; the board's
1.1 A input limit then remains within the source-advertised capability. This
charger requirement must appear in the user-facing product documentation.

If a weaker source holds its current limit by allowing VBUS to sag, BQ25185
VINDPM reduces input current to try to maintain the input-voltage threshold.
That is only a fallback: some weak or protected sources may instead shut down,
cycle, or behave unpredictably. VINDPM does not make unrestricted use with an
arbitrary USB source compliant and does not replace the 1.5 A charger
requirement.

The PCB also provides `JP_ILIM` as a manual 1.1 A/0.5 A total-input-limit
selector. Bridged is the 13 kΩ, 1.1 A production default; open inserts the
additional 5.1 kΩ for 18.1 kΩ total and approximately 0.5 A. The selection is
not automatic and must be made before use with a known lower-current source.
This is separate from `JP_ISET`, which changes only the battery fast-charge
target between approximately 1 A and 0.5 A. Opening `JP_ISET` alone does not
guarantee a 500 mA total USB input limit while the system is running.

The 103AT-2 matches the BQ25185's native 10 kΩ, B25/85 = 3435 K temperature
profile, so no external hot/cold compensation network is planned. This direct
connection gives nominal suspend thresholds near **0°C and 60°C**, not a
guaranteed 0–60°C charging window after tolerances. For example, the nominal hot
threshold is `115 mV / 38 µA = 3.03 kΩ`, close to the thermistor's 3.02 kΩ at
60°C. Combining the charger's 105 mV minimum threshold and 39.5 µA maximum bias
gives 2.66 kΩ, approximately 64°C before thermistor tolerance and thermal-contact
error. The cold cutoff also has tolerance; nominal 0°C is not a guaranteed
no-charge-below-0°C limit.

SweetYaar has **no separate product-specific temperature target**. The requirement
is to remain within the selected battery manufacturer's permitted charging
conditions and the charger's operating limits, with margin for electrical
tolerance and sensor placement. The reference ARB-L18-3500's permitted charging
temperature range has not yet been verified from an authoritative battery
specification, so temperature-safety compatibility is **not yet closed**. If a
selected cell permits charging only up to 45°C, this circuit does not enforce
that limit; the temperature-control design must then change. Charger junction
thermal regulation and a cell's general protection circuit are not substitutes
for a verified cell-temperature charging limit. Validate actual suspend and
recovery thresholds against the selected cell's limits on the production
assembly. See the [BQ25185 datasheet](https://www.ti.com/lit/ds/symlink/bq25185.pdf)
and [Semitec 103AT family data](https://www.semitec-global.com/products/thermistor_at/).
When a fixed 10 kΩ substitute is fitted instead, these temperature limits are
not being measured; validation and operating restrictions must account for the
loss of charger-controlled cell-temperature protection.

The PCB must accept charging power from either the onboard USB-C receptacle or
an unpopulated, two-wire connection to a complete off-board power module located
elsewhere inside the device:

```text
USB_VBUS ---------------- TPS2116 VIN1 (priority) --+
                                                     +---- TPS2116 VOUT ---- 5V_INPUT ---- BQ25185 IN
off-board regulated 5 V -- AUX_5V_IN -- VIN2 -------+

DEBUGGER_USB_VBUS ---- external debugger CP2102N ---- J_PROG1 ---- ESP32 UART0/EN/BOOT
```

`AUX_5V_IN` is a power-only input from a separate module mounted inside the
device but outside the main PCB. A complete regulated wireless-charging receiver
is one intended source. The source must provide 5.0 V nominal and must never
exceed 5.5 V at the mainboard input. A lower regulated voltage is acceptable
only after verifying that the BQ25185 starts and charges at an acceptable rate
across source tolerance, system load, and the battery-voltage range; merely
being below 5 V does not prove compatibility.
Never connect a raw battery, wireless-power coil, or unregulated rectifier
output.

Provide clearly labeled 5 V and GND through-hole pads or an unpopulated two-pin
connector footprint with mechanical strain-relief provisions. The PCBA vendor
does not fit this connector; the selected connector or cable is soldered during
device assembly. Place `D2`, an
[ESD441](https://www.ti.com/lit/ds/symlink/esd441.pdf), close to this connection
with its cathode on `AUX_5V_IN` and its anode on GND. `D2` suppresses fast ESD
and connection transients; it is not a regulator, sustained-overvoltage clamp,
reverse-polarity protector, or substitute for the source-voltage requirement.
A TPS2116 power mux prevents reverse current between the USB and auxiliary
sources and gives USB explicit priority. The onboard USB-C charging path
remains fully functional whether or not an auxiliary module is installed.

`5V_INPUT` means the selected external 5 V supply at the BQ25185 `IN` pin. It is
not the battery-charging output, it is not BQ25185 `SYS`, and it is not the
boosted `5V_PERIPH_SW` rail.

#### Power-source selection and reverse-current isolation

All grounds are common. Source isolation is applied to the positive 5 V paths;
do not put a diode or switch in the common-ground connection.

| Boundary | Required schematic behavior |
|---|---|
| USB `VBUS` ↔ `AUX_5V_IN` | Never connect the two sources directly. Route them through the TPS2116 so USB-only, AUX-only, and simultaneous connection are all safe. USB must take precedence whenever both inputs are valid; do not combine or share their current. |
| USB `VBUS` → `5V_INPUT` | This permanent path always remains available for charging. Isolation must prevent an auxiliary source from driving voltage out of the USB-C receptacle. |
| `AUX_5V_IN` → `5V_INPUT` | This optional, power-only path receives regulated DC from an off-board module inside the device. It must prevent USB `VBUS` from driving backward into an absent or unpowered source module. The isolation circuit and mainboard ESD diode are required even though the connector is not populated by the PCBA vendor. |
| `5V_INPUT` ↔ battery/`SYS` | Reach `BAT` and `SYS` only through the BQ25185 power path; do not add an external bypass around its input/battery reverse-current management. |

Use a [TI TPS2116](https://www.ti.com/product/TPS2116), orderable as
`TPS2116DRLR`, for this source selection. It accepts two 1.6–5.5 V inputs,
carries up to 2.5 A, provides priority switching and reverse-current blocking,
and has approximately 37 mΩ typical on-resistance at 5 V. Its 8-pin DRL
SOT-5X3 package is 2.1 mm × 1.6 mm and is intended for assembly with solder
paste and reflow rather than routine hand soldering.

Wire the mux as follows:

| TPS2116 pin | Connection and purpose |
|---|---|
| 1 `GND` | Common PCB ground. Do not isolate the source grounds. |
| 2, 7 `VOUT` | Join both pins and connect them to `5V_INPUT`, then to BQ25185 `IN`. |
| 3 `VIN1` | Protected mainboard USB `VBUS`; this is the priority source. The external debugger has its own USB supply and does not connect to this rail. |
| 4 `PR1` | USB-valid detector: 300 kΩ from USB `VBUS` to `PR1` and 100 kΩ from `PR1` to GND, both 1%. The nominal switchover threshold is 4.0 V; including the TPS2116 reference and resistor tolerances it is approximately 3.6–4.4 V, so a valid 5 V USB source is always selected. |
| 5 `MODE` | Connect directly to `VIN1`/USB `VBUS` to enable automatic priority mode. |
| 6 `VIN2` | `AUX_5V_IN` after the local `D2` ESD shunt; this is selected only when USB is absent or below the `PR1` threshold. The off-board source must remain at or below 5.5 V. |
| 8 `ST` | Optional open-drain source-status output. Leave unconnected in the first revision or expose only as a test pad; no ESP32 GPIO is allocated. |

Place a 1 µF ceramic capacitor from each of `VIN1` and `VIN2` to GND close
to the mux. Place at least 1 µF from `VOUT`/`5V_INPUT` to GND close to the
mux and BQ25185; this capacitor also satisfies the charger's `IN` decoupling
requirement when the two ICs are placed together. Use short, wide copper for
`VIN1`, `VIN2`, `VOUT`, and GND. Normal source voltage must remain inside the
TPS2116's 5.5 V recommended operating maximum. `D1` and `D2` reduce fast
ESD/transient energy but do not make an out-of-range DC source acceptable.

With this wiring, valid USB selects `VIN1`; removing or badly sagging USB
selects `VIN2`; and the break-before-make, reverse-blocking switches prevent the
active source from driving the inactive connector or receiver. No firmware is
involved in source selection.

#### Power-domain separation and sleep-current requirements

The USB/AUX mux isolates independent external power sources. Internal switched
peripherals instead use rail control plus firmware sequencing; the first
revision adds no SPI or I2S signal-isolation components.

| Boundary | Required schematic behavior |
|---|---|
| External USB-powered debugger ↔ ESP32 on `3V3_AON` | Rev A uses direct UART connections and the two-transistor EN/BOOT circuit without power-off isolation. This is accepted only under the operating rule that the debugger and target are both powered whenever the six-pin cable is attached. Disconnect the cable before removing either supply. The debugger never powers the target through `3V3_REF`. |
| `3V3_AON` ↔ `3V3_PERIPH_SW` | Every SD pull-up belongs to the switched rail. Retain GPIO5 as the native VSPI `CS`. Firmware ends SPI, disables internal pulls, and makes the SPI pins inputs before driving `PERIPH_PWR_EN` LOW; on wake it enables the rail, waits for it to settle, and then reconfigures SPI. No SPI isolation buffer is planned. |
| `3V3_AON` ↔ `5V_PERIPH_SW` | Production GPIO21 connects to `SD_MODE` only through 634 kΩ. The GPIO2 status-data crossing uses a 10 kΩ base resistor and MMBT3904 whose collector is pulled up to switched 5 V through 1 kΩ; the 5 V net never reaches GPIO2. Firmware establishes both inactive GPIO levels before enabling the rail. Before power-off it sends an LED-off frame, mutes the amplifier, ends I2S, disables the rail, and only then releases GPIO2. No I2S or LED isolation buffer is planned. |
| `5V_INPUT` ↔ `5V_PERIPH_SW` | These are different 5 V domains and must never be tied together. The switched peripheral boost output must provide true load disconnect and must not feed the external-input or charger path. |
| Charge-status signals | Connect `STAT1` and `STAT2` only to ESP32 GPIO34 and GPIO35, using external pull-ups to `3V3_AON`. Include their leakage in the sleep audit. Do not add direct status LEDs to the BQ25185 outputs. |
| `BAT` ↔ GPIO36 battery measurement | Feed the 634 kΩ / 200 kΩ divider through a second AP2281-3WG-7 whose `EN` is `PERIPH_PWR_EN`; implement the 200 kΩ lower leg as two series 100 kΩ resistors. This prevents `BAT` from driving the ADC while the ESP32 is unpowered and disconnects the divider in deep sleep. Do not measure `SYS` as a substitute. |
| Programming fixture ↔ board supplies | `3V3_REF` is a target-voltage reference/sense output only. The external debugger uses it for its indicator LED and must not drive it. A future fixture must not back-power USB, `AUX_5V_IN`, `SYS`, or the battery. |

The schematic review must trace every power pin, pull-up, protection diode,
indicator, test pad, and external connector against this table. Production
bring-up must test USB and AUX separately and together and measure reverse
current at each inactive external input. The internal peripheral approach is
fixed as rail switching plus firmware sequencing, without SPI or I2S isolation
ICs.

#### Charger-status indication

Route the BQ25185 open-drain `STAT1` and `STAT2` outputs to ESP32 input-only
GPIO34 and GPIO35, with approximately 10 kΩ external pull-ups to `3V3_AON`.
GPIO34 and GPIO35 have no internal pull-ups, so the external resistors are
required. Firmware will log charging and fault states, report them through the
parent app. The current status-LED policy deliberately has no charging or
low-battery pattern; those can be added later as semantic signals without
changing the LED driver. The BQ25185 has no direct charger-status LEDs; this
accepts that no changing indication is available while the ESP32 is in deep
sleep or unavailable. Firmware may remain awake while external charging power
is present if continuous indication is required.

#### Battery-level measurement

The BQ25185 status outputs report charger state and faults, not remaining
battery capacity. Measure `BAT` directly with the switched divider documented
above. Do **not** substitute a `SYS` measurement: the BQ25185 regulates `SYS` to
4.5 V while valid input power is present, and only says that `SYS` automatically
switches to battery power after the input is removed. Its datasheet does not
define `SYS` as a battery-voltage monitor; in battery-only operation it also
includes the BATFET/load-dependent drop. Direct `BAT` measurement therefore
works consistently while charging, externally powered, or battery-only.

This is deliberately a coarse warning, not a percentage or displayed voltage.
Firmware publishes only `UNKNOWN`, `GOOD`, `MEDIUM`, `LOW`, or `CHARGING`.
After boot initialization settles, it averages five readings spaced 100 ms
apart into one seed sample. It then adds one reading every 30 seconds to a
rolling ten-sample window. The voltage-state hysteresis is:

| Transition | Averaged `BAT` threshold |
|---|---:|
| `GOOD` → `MEDIUM` | ≤3.40 V |
| `MEDIUM` → `GOOD` | ≥3.50 V |
| `MEDIUM` → `LOW` | ≤3.10 V |
| `LOW` → `MEDIUM` | ≥3.20 V |

`STAT1=HIGH` and `STAT2=LOW` overrides the voltage state as `CHARGING`
immediately. The averaged voltage state continues updating underneath and is
restored when charging ends. Li-ion terminal voltage still varies with load,
temperature, cell model, and recent charging; a dedicated fuel gauge remains a
future option only if a reliable percentage or runtime estimate becomes useful.

#### Addressable status LED

The currently selected production indicator is the **WS2812D-F5-12mA-C1
(LCSC C4154875)**, a 5 mm through-hole, 24-bit RGB LED on `5V_PERIPH_SW`.
Its lead order is 1=`DOUT`, 2=`VDD`, 3=GND, 4=`DIN`, and its serial channel
order is RGB. Verify the delivered batch against the
[manufacturer's datasheet](https://www.ecsimple.com/files/0f/ws2812d-f5-12ma-c1.pdf)
before assembly; through-hole addressable LEDs are not interchangeable by
appearance alone. Firmware defaults match this 24-bit RGB selection;
`SWEETYAAR_STATUS_LED_RGBW=1` instead selects a 32-bit
SK6812-style RGBW device, and `SWEETYAAR_STATUS_LED_COLOR_ORDER_GRB=1` selects
GRB or GRBW order. `DOUT` may be left unconnected or routed to a labeled test pad;
it is the input for an optional second indicator later and needs no second
ESP32 GPIO.

Use the same MMBT3904 already stocked for the debugger's transistor stages:

```text
GPIO2 ---- 10 kΩ ---- Q_LED1 base
                         emitter ---- GND

5V_PERIPH_SW ---- 1 kΩ ------+---- LED1 DIN
                              |
                         Q_LED1 collector

5V_PERIPH_SW ---------------------- LED1 VDD
GND ------------------------------- LED1 GND
LED1 VDD -------- 100 nF --------- LED1 GND
LED1 DOUT ------------------------- no-connect (current one-LED build)
```

This open-collector stage both translates the data HIGH level to switched 5 V
and inverts it. NeoPixelBus uses the ESP32 RMT peripheral with a configurable
inverted waveform, so the two inversions cancel at `DIN`. `R_LED_PULLUP1`
is **1 kΩ, UNI-ROYAL 0603WAF1001T5E (LCSC C21190), 0603, 1%, 100 mW**,
from the same series as the former 4.7 kΩ part. The lower resistance reduces
the collector's RC rise delay; transistor storage delay still needs measurement.
The transistor sinks approximately 5 mA for a data LOW, including the normal
powered idle state; the pull-up dissipates approximately 25 mW at 5 V.
The unchanged 10 kΩ base resistor draws about 0.26 mA while GPIO2 is HIGH.
Both paths are inactive in normal deep sleep. Do not connect the collector
pull-up directly to GPIO2. Place the 100 nF ceramic capacitor at the LED leads.

The production timing defaults are **T0H = 300 ns, T0L = 950 ns,
T1H = 900 ns, T1L = 350 ns, reset LOW = 300 µs**. These target the
WS2812D-F5-12mA-C1 timing specification; they do not establish compatibility
with every WS2812/SK6812 variant. Build flags independently configure T0H, T1H,
the bit period, and reset time; see the firmware guide. The generic bench build
retains its previous 400/850 ns zero, 800/450 ns one, and 80 µs reset.
These are RMT-generated durations, not measured pulse widths after the NPN:
the collector's RC rise and transistor storage time still require scope
verification at `DIN`. The subsequent 1 kΩ pull-up selection does not change
these firmware defaults or the selected LED. After PCBA, plan on firmware
timing/frame adjustments and hand-soldered LED replacement only, not SMD rework.

The controller applies a global linear brightness cap to every RGB or RGBW
channel, currently 50%. This is an appearance and normal-current limit, not a
power-supply rating: validate the selected LED's full-white maximum and rail
transient on real parts. Tune `SWEETYAAR_STATUS_LED_MAX_BRIGHTNESS_PCT` after
the enclosure and diffuser are available. The current patterns are solid yellow
during initialization, green 1 s on/1 s off when ready, green 0.5 s on/0.5 s off
during local playback, blue 1 s on/1 s off while Classic Bluetooth is connected
but idle, blue 0.5 s on/0.5 s off while A2DP reports audio `STARTED`, fast red
for a latched error, and a 1 s purple/0.25 s dark Quiet-time cadence.
Firmware prints the complete mode legend and exact on/off durations to the serial
log at every boot; the canonical table and example output are in the firmware
engineering guide.

GPIO2 is an ESP32 boot-strapping pin, but the 5 V pull-up is isolated from it by
the transistor and `5V_PERIPH_SW` remains off during reset. Firmware drives
GPIO2 HIGH before enabling the switched rail, keeping physical `DIN` LOW until
RMT owns the pin. Before sleep it sends a black frame while the LED is powered,
disables the 5 V regulator, and then makes GPIO2 an input so the base resistor
adds no intended sleep current. The rail's output capacitors discharge through
the remaining load; firmware does not wait for or measure a zero-volt rail.
The amplifier is muted before regulator disable. GPIO16 and GPIO17 are now free.

The original DevKit's discrete GPIO2 LED is not a functional substitute for
this circuit. For the current direct GPIO2-to-`DIN` RGBW bench wiring, use
`sweetyaar-generic`; it records the non-inverted waveform and 32-bit RGBW frame
along with the board's other required overrides. Its tested channel order is
GRBW. Validate the 3.3 V logic-HIGH margin against the externally powered LED.
The production build continues to require the NPN and inverted RMT waveform.
If a different LED is selected later, record its overrides in the `sweetyaar`
environment. Validate frame
type, color order, inversion, and sleep sequencing before relying on the visual
states.

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
> **Battery-temperature validation:** Temperature sensing and the three-wire
> connector are fixed decisions for the ARB-L18-3500 reference design. Verify
> charge suspend and recovery on the assembled holder. The insulated sensor must
> remain in firm thermal contact with the removable cell without compromising its
> wrapper or requiring soldering to the cell. Any substitute cell must be
> compatible with the same charging and temperature-control design.

The regulator-IC selection is complete; selecting its surrounding passives is a
schematic/BOM engineering task rather than a product-feature decision. The TI
starting point for **each** TPS63802 is one 0.47 µH power inductor and one 10 µF
input ceramic capacitor. The 3.3 V output uses at least one 22 µF output
capacitor; because 5 V is above 3.6 V, TI recommends two 22 µF output capacitors
for the 5 V instance. Select the inductor's saturation and RMS current, DC
resistance, package, and temperature rating from TI's design limits. Select each
capacitor by its **effective** capacitance after DC-bias derating, voltage
rating, temperature rating, ESR, package, and worst-case insulation leakage.

The BQ25185 needs at least 1 µF effective capacitance at `IN`, nominal 10 µF at
`SYS` with at least 1 µF remaining after DC bias, and at least 1 µF at `BAT`.
TI recommends 25 V-rated ceramic parts for `IN` and `SYS` to preserve effective
capacitance after derating. Exact manufacturer part numbers remain open until
the schematic and layout are reviewed, and must be validated for startup,
radio/audio transients, efficiency, heating, and sleep leakage.

The current design relies on the mandatory protected 18650 and therefore adds
no board-level or inline fuse/PTC. This is a fixed architecture decision, not a
claim that the battery's marketing description alone proves product safety.
The complete battery path must still be checked for abnormal operation, short
circuits, temperature, and mechanical damage using the ARB-L18-3500 reference
cell or a substitute meeting the fixed requirements above.

Early battery prototypes should be charged only under supervision. Review the
charging and protection circuit before a PCB is manufactured or installed in a
doll.

### Power budget

The current prototype draws approximately 200–250 mA from its 5 V supply during
normal playback. This is a measured whole-device value for the DevKit setup,
with the SD breakout and amplifier continuously powered. It is not a per-rail
measurement and does not represent every playback condition or deep sleep.

The normally-closed vibration circuit draws approximately 7 µA from
`3V3_AON` while at rest, calculated from its 3.3 V supply and 470 kΩ pull-up.
The production charge current is 1 A; that is a charging value and must not be
confused with the toy's operating current.

> [!WARNING]
> **TBD — Production power measurements:** On the production power tree,
> measure battery-side current during representative playback, startup and radio
> transients, charging while loaded if supported, and total deep-sleep current.
> These are electrical-current measurements; no acoustic dB or 4 Ω-versus-8 Ω
> volume measurement is required. Do not claim a final operating or
> sleep-current budget until those measurements exist.

### PCB electrical interfaces and programming

The production PCB is **four layers**. A two-layer implementation is not being
pursued. Its outline and component placement are intentionally deferred until
the electronics enclosure is designed. Electrically, the PCB must include:

| Interface | Current requirement or decision |
|---|---|
| USB and auxiliary charging | The mainboard USB-C connector is power-only and is required for charging. Also provide unpopulated two-wire 5 V and GND auxiliary-input pads/footprint for a complete off-board source mounted elsewhere inside the device, such as a regulated wireless-charging receiver or power-only USB-C daughterboard. The PCBA vendor fits neither an auxiliary connector nor cable; it is added during device assembly when that option is used. `D2` remains populated on the mainboard. Firmware download and live serial logs use the separate USB-powered debugger through `J_PROG1`. |
| Storage | Fit a replaceable bare microSD socket on `3V3_PERIPH_SW`, entirely inside the electronics enclosure. Changing the card requires opening the enclosure. Place the socket with insertion/removal clearance on the opened PCB, not at an enclosure edge or external opening. |
| Battery | Use a protected removable 18650 in a holder. Connect its short harness through a three-position 2.5 mm-pitch JST-XH carrying `BAT+`, `BAT−`/GND, and `BAT_TEMP`. The preferred holder harness contains the Semitec 103AT-2 from `BAT_TEMP` to `BAT−`/GND. If it is omitted, fit a fixed 10 kΩ substitute from `BAT_TEMP` to GND and record that temperature monitoring is disabled. |
| Speaker | Use one keyed two-pin connector and a short stranded-wire harness. It must support either 4 Ω or 8 Ω speakers and must not be interchangeable with the battery connector. |
| Song and animal buttons | Use one four-pin PCB connector arranged as `BTN_SONG`, GND, `BTN_ANIMAL`, GND. The two ground contacts join on the PCB, allowing four ordinary single-wire crimps and two independent two-wire button branches without a harness splice. |
| Main power | Fit a physical latching **SPST pushbutton switch** on the enclosure as an exceptional safety/service control; deep sleep is normal. The complete switch body—not merely a remote actuator—mounts on the enclosure. Place it in series between BQ25185 `SYS` and the regulator inputs; leave `BAT+` permanently connected to BQ25185 `BAT`. Connect the switch to the PCB with two conductors and a two-pin connector. The switch and every harness contact must carry the validated current with margin. |
| Vibration wake | The normally-closed vibration switch is soldered directly onto the PCB. Exact part and footprint remain schematic/BOM selections; its physical orientation follows enclosure design. |
| Indicators | Route BQ25185 `STAT1`/`STAT2` only to ESP32 GPIO34/GPIO35. Fit one 5 mm through-hole addressable RGB or RGBW status LED on `5V_PERIPH_SW`, with 100 nF local decoupling and the GPIO2/10 kΩ/MMBT3904/1 kΩ open-collector level shifter. Verify the selected part's frame type, lead order, and color order; preserve or test-pad `DOUT` for a future daisy-chained indicator. |
| Programming/test | Use six exposed surface contact pads on 2.54 mm centers (`SweetYaar:DebuggerPad_1x06_P2.54mm`), without holes or solder-paste apertures. Nothing is soldered onto the mainboard here: header pins or pogo pins on the debugger/fixture temporarily touch the pads. Contacts 1–6 are `3V3_REF`, GND, GPIO1/`UART_TXD`, GPIO3/`UART_RXD`, `ESP_EN`, and GPIO0/BOOT. The external debugger supplies CP2102N USB-to-UART and automatic-download control. |

The auxiliary source is physically separate from the main PCB but remains
inside the device enclosure. If the source is a power-only USB-C daughterboard
near the doll surface, that daughterboard must implement the required USB-C sink
configuration and connector-side protection locally, then send only regulated
5 V and GND to `AUX_5V_IN`; two wires cannot carry firmware data or serial logs.

Wireless charging uses the same two-wire interface: connect the regulated 5 V
and GND output of a complete receiver assembly to `AUX_5V_IN`, not its raw
resonant coil or unregulated rectifier output. In a Qi system, the receiver asks
the transmitter for a supported wireless-power level and the transmitter
delivers the negotiated level. The
receiver module then enforces its own output rating, while the BQ25185 separately
limits input current to 1.1 A and battery charge current to 1 A. Transmitter
capability, coupling/alignment, receiver rating, BQ25185 input limit, system
load, battery charge setting, and thermal regulation all apply; the lowest
available limit determines the actual charge rate. Select a receiver with a
regulated 5 V output and enough margin for the 1.1 A charger-input setting, or
include a lower AUX-specific current limit.
[Qi-certified](https://www.wirelesspowerconsortium.com/knowledge-base/testing-and-certification/qi-certified-products/)
transmitter/receiver pairs are designed to negotiate a mutually supported
level, but maximum power is not guaranteed and arbitrary uncertified modules
must not be assumed interoperable. Temperature, alignment, and voltage stability
must be tested in the real doll. USB charging remains permanently available on
the main board, along with firmware service and live logs; wireless charging is
only an optional additional input.

Deep sleep, not the physical switch, is the normal way to stop using the toy.
The enclosure-mounted latching SPST switch is a deliberate hard-off
safety/service control. It opens the `SYS` feed between the BQ25185 and both
system regulators, preventing the battery, USB, or AUX input from powering the
ESP32 or switched peripherals while off. `BAT+` remains permanently connected
to BQ25185 `BAT`, so an attached USB or AUX source may still charge the battery
while the system is hard-off. The switch uses two terminals, two harness
conductors, and a two-pin PCB connector. This is a direct mechanical disconnect
rather than an electronic shutdown commanded through load-switch inputs.

The mainboard USB-C connector is power-only. Its `VBUS` pins feed the charging
path, while its USB data pins are intentionally unconnected. Firmware download
and live serial logs use a separate debugger board containing the CP2102N and
its own USB-C connector. The debugger does not connect its USB `VBUS` or its
CP2102N `VDD` to the target.

The six programming contacts are **bare surface pads on 2.54 mm centers**,
using `SweetYaar:DebuggerPad_1x06_P2.54mm`. There are no through-holes and no
mainboard connector to solder. Standard male header pins or pogo pins on the
debugger/fixture temporarily touch these pads; the fixture must hold all six
contacts reliably throughout flashing. The pads expose copper through the
solder mask but have no `F.Paste` apertures, so the assembly stencil does not
deposit solder paste on them. Contacts 1–6 are
`3V3_REF`, GND, target GPIO1/`UART_TXD`, target GPIO3/`UART_RXD`, `ESP_EN`, and
GPIO0/BOOT. `3V3_REF` is sense-only: on the debugger it powers only the
2.2 kΩ series indicator LED and must never be driven back into the target.
The UART directions cross normally: CP2102N `RXD` receives target `UART_TXD`,
and CP2102N `TXD` drives target `UART_RXD`.

The debugger routes CP2102N `DTR` and `RTS` through Espressif's two-transistor
automatic-download circuit to target `EN` and BOOT. Its DPST serial-only switch
disconnects those two automatic-reset controls when desired; UART TX/RX remain
connected. The target retains the recommended 10 kΩ/1 µF `ESP_EN` network and
10 kΩ GPIO0 pull-up. Reserve GPIO0 for automatic download control and do not
attach another production peripheral to it.

Rev A deliberately omits Espressif's optional 499 Ω series resistor on target
`U0TXD`. The direct UART connection is accepted for the first revision to avoid
another component; the omitted resistor is primarily an emissions/harmonic
suppression recommendation, not a requirement for UART function. Revisit it
only if EMC testing or signal measurements justify the change. It would not by
itself provide power-off isolation.

Rev A also deliberately omits UART power-off isolation. Whenever the six-pin
cable is attached, **power both the target and debugger continuously**. Power
both boards before attaching the cable, and disconnect the cable before
removing either supply. With both devices powered, static UART input current is
only leakage-scale; the CP2102N specifies at most 1.1 µA for an in-range input,
while the CP2102N itself typically consumes about 9.5 mA from debugger USB
during normal operation. The target-reference LED additionally draws roughly
`(3.3 V - LED_VF) / 2.2 kΩ`, typically well below 1 mA.

If this operating rule is broken, the direct output-to-unpowered-input current
is not bounded to a small, guaranteed value by either datasheet. A powered
target can drive 3.3 V into an unpowered CP2102N `RXD`; with `VIO = 0`, that
exceeds the CP2102N's `VIO + 2.5 V` absolute-maximum input voltage. A powered
debugger can similarly inject current from CP2102N `TXD` into an unpowered
ESP32 and partially back-power its 3.3 V domain. Actual current depends on
internal protection structures and other rail loads and may be several
milliamps or more; do not treat the datasheet's normal input-leakage number as a
fault-current limit. A brief mistake may merely cause phantom powering or bad
reset behavior, but it is outside the supported operating condition and is not
guaranteed harmless.

Add USB ESD protection on the debugger and route its `D+` and `D-` as a short
controlled differential pair. Keep the debugger disconnected during
battery-sleep measurements. USB serial provides live logs; retrieving logs
produced before connection or reset requires a separate firmware-managed
persistent log buffer.

Programming-interface references: [ESP32 UART hardware guidance](https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32/schematic-checklist.html#uart),
[ESP32 boot-mode and automatic-download behavior](https://docs.espressif.com/projects/esptool/en/latest/esp32/advanced-topics/boot-mode-selection.html),
[ESP32-DevKitC reference schematic](https://dl.espressif.com/dl/schematics/esp32_devkitc_v4_sch.pdf),
and [CP2102N datasheet](https://www.silabs.com/documents/public/data-sheets/cp2102n-datasheet.pdf).

The TPS2116 closes the USB-priority source-mux selection. During schematic and
layout review, verify the divider threshold, both 1 µF input capacitors, the
shared mux-output/BQ25185-input capacitor, 2.5 A current paths, connector-side
protection, and the required absence of reverse current at both inactive
inputs.

#### Remaining electrical decisions and verification

The battery-warning architecture is closed: direct `BAT` measurement through
the AP2281-switched 634 kΩ / 200 kΩ divider on GPIO36, with the 200 kΩ lower
leg implemented as two series 100 kΩ resistors.

Exact connector models and regulator passives are schematic/BOM selections
that must satisfy the fixed behavior above. The selected WS2812D-F5-12mA-C1
remains a batch-verification item: confirm its pinout, 24-bit RGB frame,
RGB channel order, logic timing, and full-white current on the
purchased batch. The indicator
architecture and its MMBT3904, 10 kOhm base resistor, 4.7 kOhm pull-up, and
100 nF decoupling are fixed. The deep-sleep calculation and production current
measurements are verification work. They can force a component change if a
limit is missed, but they are not additional product-feature decisions.

#### Future electrical revision ideas

- Reconsider an independent one-time fuse or resettable PTC in `BAT+` if a
  future cell, harness, safety review, or abnormal-operation test shows
  that the protected cell's cutoff does not adequately protect the external
  battery path. An inline device close to the holder's positive contact would
  protect more of the harness than a PCB-mounted device. Its normal-current
  rating would have to exceed the 1 A charging current and tolerate measured
  playback and startup transients.

## Enclosure design

Mechanical layout is a separate design phase. The PCB outline, dimensions,
mounting holes, connector edge positions, and component placement must wait for
the electronics enclosure; only the four-layer stackup and electrical
interfaces are fixed now.

Current enclosure requirements and open mechanical work are:

- The mainboard USB-C receptacle must be reachable for charging. Firmware
  flashing and logs use the internal six-pad programming contact row and separate
  debugger, so they require opening the doll zipper and electronics enclosure.
  A future power-only daughterboard may move a charging connector to the doll
  surface without replacing the mainboard charging path.
- The replaceable microSD socket is inside the electronics enclosure and is not
  accessible externally. Do not place it at the enclosure edge; instead provide
  enough internal finger and card-travel clearance to replace the card after the
  enclosure has been opened.
- The protected 18650 holder must fit the ARB-L18-3500 reference envelope of
  approximately 69 mm length and 18.6 mm diameter,
  prevent reverse insertion where practical, retain and electrically insulate
  the cell, and protect it from crushing, puncture, sharp edges, and tool-free
  child access. Retain the insulated 103AT-2 sensor against the cell wrapper so
  it follows cell temperature without obstructing removal. Protect and
  strain-relieve both thermistor leads; join its low side to `BAT−` in the
  holder harness, never by soldering to or exposing the bare cell can.
- Speaker impedance may be 4 Ω or 8 Ω per doll. Select its power rating and
  acoustic chamber for that installation; separate the front and rear sound
  paths, provide sufficient grille opening through the real fabric/padding, and
  validate the mount, seal, buzz, rattle, and cone clearance across the intended
  operating range. No calibrated sound-pressure measurement is required.
- The two child buttons remain physically separate and may be approximately
  20–30 cm from the PCB. Their four-wire harness splits into two ordinary
  signal/GND pairs and needs secure routing and strain relief.
- The complete latching SPST hard-off pushbutton switch is mounted on the
  enclosure and connects to the PCB through a two-wire harness; it is not a
  separate remote actuator for a PCB-mounted switch. Design its opening, child
  access, retention, cable routing, strain relief, and service access. The
  switch and both harness contacts must satisfy their electrical and mechanical
  ratings.
- The 5 mm through-hole addressable RGB or RGBW status LED must be visible from outside. Its
  position, diffuser or light pipe, brightness limit, and color/flash-state
  legend must be designed at the same time.
- The optional wireless receiver—complete coil, ferrite shielding, rectifier,
  and regulated output—may be secured near the bottom of the doll so sitting it
  on the charger provides usable coupling. Its short 5 V/GND cable routes back
  to `AUX_5V_IN`; alignment, temperature, insulation, and retention require
  testing in the real doll.
- The PCB-mounted normally-closed vibration switch must be oriented and located
  so doll motion actuates it reliably without false wakes from normal handling.
- Use one shared, rounded or grommeted harness opening for cables leaving the
  electronics enclosure when routing permits. Provide a clamp, tie-down, or
  molded strain relief inside the enclosure so no solder joint or connector
  contact carries pull force. USB-C and microSD panel openings are separate from
  this cable exit. Use additional cable openings only when component placement
  requires them, and strain-relieve each one. Keep the speaker pair together
  (preferably twisted) and validate that bundling it with the button and power
  harnesses does not cause audible or input noise.

> [!WARNING]
> **TBD — Enclosure and final PCB layout:** Complete the enclosure concept, then
> finalize the board outline and mounts, USB-C access and internal microSD
> service clearance, cell holder,
> speaker acoustics, hard-off actuator, LEDs/light pipes, harness exit and strain
> relief, vibration-switch orientation, and programming-fixture registration.

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
connecting an 18650 cell or speaker. A practical order is:

1. Verify USB-only charging through `5V_INPUT`, with no voltage or measurable
   reverse current appearing at `AUX_5V_IN`.
2. Apply a current-limited 5 V bench supply to `AUX_5V_IN`; verify charging, the
   expected input current, and no voltage at the mainboard USB-C receptacle.
   Repeat with the intended off-board module and its production cable, confirming
   that the mainboard input remains at or below 5.5 V during startup and normal
   operation. The external debugger and its CP2102N supply remain electrically
   separate from this power-path test.
3. Connect USB and AUX together, verify that USB takes priority,
   and measure reverse current into both sources. Do not rely only on voltage.
4. Verify the charger/protection and `SYS` behavior by themselves.
5. With the Semitec 103AT-2 installed against the cell wrapper, verify the
   BQ25185 suspends and resumes charging at the intended hot and cold limits.
   Use a controlled-temperature or resistor-substitution fixture; do not heat,
   chill, short, or probe a live cell unsafely.
6. Verify `3V3_AON` across the intended battery range and during ESP32 radio
   bursts.
7. Toggle `PERIPH_PWR_EN` and confirm that `3V3_PERIPH_SW` and
   `5V_PERIPH_SW` start and stop cleanly, and that the battery-sense AP2281
   follows the same enable.
8. Apply known safe battery-simulator voltages at `BAT` and verify GPIO36 sees
   the expected divider values and firmware state thresholds. With
   `PERIPH_PWR_EN` LOW or the hard-off switch open, confirm the ADC node is held
   near GND and `BAT` cannot back-power the ESP32.
9. With the switched rails off, confirm both peripheral rails turn fully off;
   then turn them back on and verify reliable SD and amplifier initialization.
10. Validate SD initialization and low-volume audio before increasing speaker
   load.
11. During representative Bluetooth playback with the speaker selected for that
   doll, measure converter temperature and battery-side transient current. This
   is an electrical/thermal check, not an acoustic volume measurement.
12. Enter deep sleep and measure total battery current, not only an individual
   rail.
13. Open the hard-off switch and verify that neither the battery, USB, nor AUX
    can power the system regulators while off. With USB or AUX attached, verify
    that the battery can still charge through the BQ25185 while the regulator
    side of the switch remains unpowered.
14. Move the vibration switch and confirm that the rails return only after the
    ESP32 reboots.

During deep sleep, `PERIPH_PWR_EN`, `3V3_PERIPH_SW`, and `5V_PERIPH_SW` should
all measure LOW or off. If a peripheral rail remains active, check its enable
wiring, output-discharge path, and the 5 V converter's required true-load-
disconnect behavior.

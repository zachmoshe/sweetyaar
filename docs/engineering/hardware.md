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

Review the current KiCad schematic and PCB for the electrical implementation.
Files under `hardware/mainboard/production/` are older manufacturing exports;
they do not supersede the editable design and must be regenerated for a new
fabrication run.

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

The production power system keeps the onboard USB charging input permanently connected,
adds an optional auxiliary charging input from an off-board source located
elsewhere inside the device, and generates three system rails. The TPS2121
provides reverse-current isolation between the two positive supply paths; this
is not galvanic isolation, and both sources share the mainboard ground.

```text
USB_VBUS ---------------- TPS2121 IN1 (priority) --+
                                                   +---- OUT ---- 5V_INPUT ---- BQ25186 IN
off-board regulated 5 V -- AUX_5V_IN -- IN2 -------+                              |
                                                                                  +-- I2C, /PG, /INT --> ESP32

protected 18650 Li-ion ------------------------------ BQ25186 BAT
           |
           +---- AP2281 switched divider -------------------------- GPIO36 ADC1

BQ25186 SYS ---- hard-off SPST switch ----+---- TPS63802 3.3 V ---- 3V3_AON ---- ESP32
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
| 4 | `PIN_CHARGER_ENABLE` | Output | Base resistor of the MMBT3904 that pulls BQ25186 `/CE` LOW | HIGH enables charging. GPIO4 defaults to an internal pulldown during and after reset; the external base pulldown and `/CE` bias divider keep charging disabled through boot and hard-off. |
| 16 | `PIN_CHARGER_SDA` | Bidirectional open-drain | BQ25186 `SDA` | 100 kHz I2C data; 10 kΩ pull-up to `3V3_AON`. |
| 17 | `PIN_CHARGER_SCL` | Bidirectional open-drain | BQ25186 `SCL` | 100 kHz I2C clock; 10 kΩ pull-up to `3V3_AON`. |
| 34 | `PIN_CHARGER_PG` | Input with external pull-up | BQ25186 `/PG/GPO` | LOW means valid external input; 10 kΩ pull-up to `3V3_AON`. Also wakes the ESP32 if charging power is attached during deep sleep. |
| 35 | `PIN_CHARGER_INT` | Input with external pull-up | BQ25186 `/INT` | Active-LOW event pulse; 10 kΩ pull-up to `3V3_AON`. |
| 36 | `PIN_BATTERY_ADC` | ADC1 input | Midpoint of the switched 634 kΩ / 200 kΩ `BAT` divider; the 200 kΩ lower leg is two series 100 kΩ resistors | Calibrated coarse battery-state measurement on ADC1_CH0. |
| 2 | `PIN_STATUS_LED_DATA` | RMT output | WS2812B-V6 `DIN` through a series data resistor | Non-inverted 24-bit GRB; no NPN or pull-up to 5 V. Validate direct-drive logic margin. |

GPIO16 and GPIO17, released by the addressable status LED, now form the charger
I2C bus. GPIO34 and GPIO35 are input-only and therefore suit the charger's two
open-drain outputs. GPIO36 remains the coarse battery-voltage ADC input.

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
| `SYS` | BQ25186 `SYS` output through the single hard-off switch | BQ25186 `SYS` bypass capacitor on the charger side of the switch; both TPS63802 regulator inputs and their 10 µF input capacitors on the disconnected side | Available from the battery or charging input while the hard-off switch is closed. Opening the switch disconnects the regulator feed even if USB or AUX is attached. The unpowered ESP32 also releases the external `/CE` pull-down, so charging is disabled while hard-off. |
| `3V3_AON` | TPS63802 set to 3.3 V | TPS63802 22 µF output capacitor, ESP32 and its decoupling, 470 kΩ GPIO27 wake pull-up, 510 kΩ/91 kΩ regulator-feedback divider, and the disabled AP2281 input with its 1 µF capacitor | On. GPIO2 is released only after the switched 5 V rail is off. |
| `3V3_PERIPH_SW` | AP2281-3WG-7 load switch | Bare microSD card and every SD pull-up | Off. |
| `5V_PERIPH_SW` | TPS63802 set to 5 V, with true shutdown | MAX98357A, one WS2812B-V6 addressable status LED, plus future switchable 5 V peripherals that fit the validated power budget | Off. |

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

Battery-only deep sleep also drives the charger-enable transistor off and
disables the BQ25186 host watchdog. This removes NPN base current from the sleep
budget. GPIO34 `/PG` is armed as a second wake source: attaching valid USB or
AUX power pulls `/PG` LOW, reboots the ESP32, and allows firmware to verify the
charger configuration before asserting `/CE`. While external input remains
valid, firmware stays awake to supervise charging.

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
`3V3_AON`. The I2C, `/PG`, and `/INT` pull-ups and BQ25186 pin leakage must be
included in the final
audit. Both TPS63802 `PGOOD` pins are left unconnected. The budget treats
currents specified at `3V3_AON` as approximately battery-side currents; the
exact battery current depends on battery voltage and the 3.3 V converter's
efficiency at very light load.

| Component | Deep-sleep state | Reference current | Sleep budget |
|---|---|---:|---:|
| BQ25186 charger/power path | Battery-only; system asleep | 4 µA typical, 5 µA maximum at 3.6 V and 0–85°C | **4–5 µA** |
| 18650 protection circuit | Always on | ARB-L18-3500 reference cell; verify a substitute does not exceed the reference design allocation | **1–2 µA provisional** |
| TPS63802 3.3 V buck-boost | Always on | 11 µA typical | **11–14 µA** |
| ESP32-WROOM-32 + EXT0/EXT1 | Deep sleep | 10–15 µA | **10–15 µA** |
| 3.3 V feedback divider | 510 kΩ from `3V3_AON` to `FB`, 91 kΩ from `FB` to GND | 3.302 V / 601 kΩ = 5.49 µA at `3V3_AON` | **5–7 µA battery-side** |
| 470 kΩ vibration pull-up | Always on | 7 µA | **7 µA** |
| GPIO13 100 kΩ pulldown | GPIO13 and all three controlled enable inputs held LOW | 0 V across the resistor; EN leakage is included in the two AP2281 rows and the 5 V TPS63802 row | **≈0 µA** |
| Buttons and addressable indicator | Buttons released; `5V_PERIPH_SW` off; GPIO2 high-impedance after the rail is disabled | The LED is unpowered; no driven HIGH on DIN and no pull-up to an always-on rail | **≈0 µA** |
| Charger digital signals | `/PG`, `/INT`, `SDA`, and `SCL` are HIGH through four 10 kΩ pull-ups when idle; no DC path exists through an ideal high-impedance input | Include BQ25186 and ESP32 leakage for all four pins | **≤4 µA, provisional** |
| Always-powered ceramic capacitors | BQ25186 `BAT` 1 µF and `SYS` ≥10 µF; two TPS63802 10 µF input capacitors; 3.3 V TPS63802 22 µF output capacitor; SD-switch AP2281 `IN` 1 µF; battery-sense AP2281 `IN` 1 µF; ESP32 local decoupling | Dielectric insulation leakage; exact capacitor part numbers not selected | **≤2 µA combined, provisional** |
| AP2281 SD load switch | Disabled; input powered | 0.01 µA typical | **≤1 µA** |
| AP2281 battery-sense load switch | `PERIPH_PWR_EN` LOW; `BAT` input powered, divider output discharged | 0.01 µA typical, 1 µA maximum shutdown current | **≤1 µA** |
| Battery-sense divider | Disconnected from `BAT` by its AP2281; the series 200 kΩ lower leg holds GPIO36 at GND | No voltage across the 634 kΩ / 200 kΩ path | **≈0 µA** |
| microSD + SD pull-ups | **Off on peripheral rail** | 0.1–1 mA card standby; 70–330 µA per 10–47 kΩ pull-up held LOW | **≈0 µA** |
| TPS63802 5 V buck-boost | `EN` LOW; input powered | 0.045 µA typical, 0.6 µA maximum | **≤1 µA** |
| Separate amplifier load switch | Not required with the disconnecting 5 V TPS63802 | 0 µA | **0 µA** |
| MAX98357A | `SD_MODE` LOW, then **off on peripheral rail** | 0.6 µA typical / 2 µA maximum in `SD_MODE` shutdown | **≈0 µA** |
| Production GPIO21-to-`SD_MODE` control | GPIO21 is driven LOW before `5V_PERIPH_SW` is disabled and may remain LOW or become high-impedance in deep sleep; the 634 kΩ series resistor has no powered DC path | No intended current path | **≈0 µA** |
| PCB surface leakage | Clean, dry PCB | Not predictable from the schematic alone | **≤1 µA provisional** |
| **Planning total** | — | — | **approximately 40–61 µA** |

The capacitor allocation covers only capacitors that retain DC voltage in
battery-only sleep. The BQ25186 `IN` capacitor and capacitors on
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
There are no analog charger-programming resistor ladders: charge parameters are
held in BQ25186 registers and checked by firmware. The selected Semitec
103AT-2 thermistor connects between `TS/MR` and the dedicated `TS_RETURN`
conductor. The charger
biases `TS/MR` while an input source is present; there is no intended thermistor
current path in battery-only sleep, but final-board leakage at this pin remains
part of the sleep-current audit. In normal use, never leave `BAT_TEMP` open: an
open input is interpreted as a temperature fault and prevents normal charging.
The board also retains a deliberate 10 kΩ debug bypass through `JP3` and
`R_TH1`; leave `JP3` open for normal use with the cell-mounted thermistor. See
the battery section for the bypass wiring and exceptional-use policy.

> [!WARNING]
> **TBD — Close the deep-sleep design budget:** Obtain or measure the
> ARB-L18-3500 protection circuit's maximum standby current and require any
> substitute cell not to exceed that allocation. Select the exact
> always-powered ceramic capacitors, charger-interface leakage, and the
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
[BQ25186 datasheet](https://www.ti.com/lit/ds/symlink/bq25186.pdf),
[BQ25186 thermistor selection](https://www.ti.com/lit/an/spva059/spva059.pdf),
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
state is detected from the BQ25186 `STAT0.CHG_STAT` field over I2C.

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
| Charger | [BQ25186DLHR](https://www.ti.com/product/BQ25186), I2C-controlled 1-cell Li-ion charger with power path. It was selected because firmware can set and verify the battery-temperature limits required by the cell rather than accepting the BQ25185's fixed 60°C HOT threshold. |
| External-source mux | [TPS2121RUXR](https://www.ti.com/product/TPS2121), with USB `VBUS` on priority input `IN1`, `AUX_5V_IN` on backup input `IN2`, and `OUT` feeding BQ25186 `IN`. The circuit sets USB priority at approximately 4.24 V, input overvoltage rejection at approximately 6.04 V, and a nominal 2.25 A mux current limit. |
| Auxiliary-source requirement | `AUX_5V_IN` comes from a complete off-board power module mounted elsewhere inside the device, such as a regulated wireless-charging receiver. Require 5.0 V nominal and never more than 5.5 V at the mainboard input. The source and harness must continuously support the firmware-configured 1.05 A input limit with suitable margin. Connect only a regulated DC output, never a raw wireless-power coil or unregulated rectifier output. |
| Use while charging | Supported. Power the device from `SYS`; the BQ25186 reduces charge current when the input or thermal limit is reached and allows the battery to supplement load peaks. |
| Charge current | **1 A production default**, programmed and read back over I2C. There is no `ISET` resistor or current-selection jumper. |
| Charger input-current limit | **1.05 A production default**, programmed and read back over I2C. There is no `ILIM/VSET` resistor ladder or `JP_ILIM`. |
| USB charger requirement | Require a 5 V USB-C charger that advertises at least 1.5 A on CC. The 1.05 A programmed limit stays below that advertised capability. The two 5.1 kΩ CC pull-downs identify the board as a sink but do not decode the source's current advertisement. |
| Battery connector | Use a **five-position** 2.5 mm-pitch JST-XH-family connector (`J_BATT1`, `JST_XH_B5B-XH-A_1x05_P2.50mm_Vertical`). Pin order is **1: GND / `BAT−`, 2: `BAT+`, 3: `TS_RETURN`, 4: `BAT_TEMP`, 5: unused / unconnected**. The harness has four conductors in a five-position housing; leave cavity 5 empty. The distinct position count reduces confusion with the four-position button connector while retaining the same connector family for ordering. |
| Battery thermistor | Fit an insulated **Semitec 103AT-2** 10 kΩ NTC (10 kΩ at 25°C, B25/85 = 3435 K) firmly against the cell wrapper. Give it **two dedicated wires**, one to `BAT_TEMP` and one to `TS_RETURN`. `BAT_TEMP` reaches BQ25186 `TS/MR`; `TS_RETURN` returns independently to charger GND beside the IC. This Kelvin return avoids current-carrying `BAT−` harness voltage drop and noise at the small TS threshold voltage. Do not join either thermistor lead to `BAT−` at the holder or in the harness. In normal use, connect the thermistor and leave bypass `JP3` open. |
| Thermistor debug bypass | Retain the existing normally-open `JP3` and 10 kΩ `R_TH1` on the board so debugging or a deliberate exceptional override can substitute a fixed resistance without reprinting the PCB. This disables real battery-temperature measurement; it is **not the normal-use configuration**. |
| Cell-temperature policy | Program **0°C COLD and 45°C HOT hard charging cutoffs** to match the Fenix range, and disable the intermediate COOL/WARM derating zones. The cell PCM does not enforce this normal charging-temperature range; the external charger must do it. |
| Hard-off policy | The SPST switch disconnects `SYS` from both regulators. `/CE` is also pulled HIGH when the ESP32 is unpowered, so USB/AUX cannot charge the battery while the device is hard-off. |

The two USB-C `CC1` and `CC2` pull-downs identify the board as a sink but do not
decode the source's advertised current. Product documentation must therefore
require a 5 V source advertising at least 1.5 A. VINDPM can reduce current when
VBUS sags, but it does not make an arbitrary weak source compliant. System load
still has priority over battery charging, so the actual charge current may be
less than the 1 A target.

The battery uses five positions because accidentally interchanging its harness
with the button harness can short the battery or apply cell voltage to ESP32
signals. Keeping JST-XH throughout simplifies component and crimp ordering;
the extra, electrically unused battery position distinguishes this connection.
Use the matching five-position header and housing, and verify the numbered pin
order before connecting the cell. The current PCB already has this footprint
and an unconnected pad 5; the saved schematic still has the earlier four-pin
symbol/footprint and needs to be synchronized, including its ordering entry.

#### BQ25186 pin migration and control

The BQ25186 uses the same ten-pin DLH package and preserves the power pins, but
it is not a schematic drop-in replacement for the analog-programmed BQ25185:

| Pin | BQ25185 function | BQ25186 connection |
|---:|---|---|
| 1 | `SYS` | `SYS`, unchanged. |
| 2 | `BAT` | `BAT`, unchanged. |
| 3 | `STAT2` | `/PG/GPO` to GPIO34 with a 10 kΩ pull-up to `3V3_AON`. |
| 4 | `/CE` | `/CE`, now driven by the fail-closed transistor circuit. |
| 5 | GND | GND, unchanged. |
| 6 | `TS/MR` | `BAT_TEMP`, with the thermistor returning through `TS_RETURN`. Push-button actions are disabled. |
| 7 | `ILIM/VSET` | `SDA` to GPIO16 with a 10 kΩ pull-up to `3V3_AON`; remove the old programming ladder and jumper. |
| 8 | `ISET` | `SCL` to GPIO17 with a 10 kΩ pull-up to `3V3_AON`; remove the old programming resistors and jumper. |
| 9 | `STAT1` | `/INT` to GPIO35 with a 10 kΩ pull-up to `3V3_AON`. |
| 10 | `IN` | `5V_INPUT`, unchanged. |
| Exposed pad | GND | Solder to the local solid GND/thermal plane. |

The `/CE` bias is a divider: `R_CHARGER_CE_DIV1` is 100 kΩ from `5V_INPUT`
to `CHARGER_CE_N`, and `R_CHARGER_CE_DIV2` is 91 kΩ from that node to GND.
At 5 V input it holds `/CE` at approximately 2.38 V, above the BQ25186's
1.0 V HIGH threshold, while reducing the voltage reaching this 5.5 V
absolute-maximum pin during an input transient. This divider scales voltage;
it is not a clamp. It draws no battery-only current when external power is
absent. `Q1`, an MMBT3904, has collector at `/CE`, emitter directly at GND,
and base driven by GPIO4 through the 10 kΩ `R_CHARGER_CE_BASE1`, with the
100 kΩ `R_CHARGER_CE_PD1` from base to GND. GPIO4 HIGH enables charging.
Its reset-default internal pulldown and the external base pulldown keep
charging disabled through reset and boot; the
external pulldown also keeps it disabled when the ESP32 is unpowered or the
hard-off switch is open. Firmware drives GPIO4 LOW at the start of `setup()`
and asserts it only after every safety register has been written and read back
successfully, and only while valid input power is present.

`/PG` is a hardware indication that valid external input exists. `/INT` gives a
short active-LOW pulse when an enabled event changes. Neither signal is required
to configure the charger or read its state—the I2C status registers are
authoritative—but both are wired because suitable GPIOs are available. `/PG`
also wakes the ESP32 when power is attached during battery-only deep sleep;
`/INT` avoids waiting for the periodic status poll while awake.

#### I2C configuration and status

The BQ25186 uses 7-bit address `0x6A`; firmware runs the bus at 100 kHz. It can
set charge voltage/current, input-current limit, termination/precharge behavior,
VINDPM, junction thermal regulation, battery UVLO/OCP, SYS mode/voltage, TS
cutoffs, safety timer, watchdog behavior, interrupt masks, and ship/reset
behavior. It can read the charging phase, input-good state, TS zone/open state,
input/DPPM/thermal limiting, VIN overvoltage, battery UVLO/OCP, safety-timer
fault, event flags, and device ID.

The production register policy is 4.20 V, 1.00 A charge current, 1.05 A input
limit, 10% termination, 4.5 V VINDPM, 4.5 V normal `SYS`, 3.0 V battery UVLO,
3 A battery OCP, a six-hour safety timer, 0°C/45°C TS cutoffs, COOL/WARM zones
disabled, and `TS/MR` push-button actions disabled. The 40-second charger host
watchdog is enabled while awake and disabled immediately before deliberate
deep sleep. These settings do not turn `SYS` into a boost converter: the 3.3 V
and 5 V regulators remain required.

The read-and-verify path has no configuration cache. At boot firmware writes
one register and immediately reads the physical register back before advancing.
It then rereads every configured register every 10 seconds and on `/INT`. Any
I2C failure, unexpected device ID, or mismatch immediately releases `/CE`;
firmware attempts one complete rewrite/read-back cycle and re-enables charging
only after successful verification. The ESP32 CPU1 loop task also uses the
configured five-second task watchdog, while the BQ25186 provides the independent 40-second
no-I2C power-cycle watchdog.

The 103AT-2 is the 10 kΩ/B25/85=3435 K profile used by TI's BQ25186 temperature
thresholds. Firmware selects the hard 0°C and 45°C thresholds recommended for
the reference Fenix battery and disables the optional intermediate zones.
Validate actual suspend and recovery temperatures on the complete holder,
including thermistor tolerance, sensor contact, and thermal lag. Normal use
always includes the thermistor attached to the cell, with `JP3` open.

The existing board intentionally retains `JP3` and `R_TH1` rather than requiring
a PCB reprint to remove the bypass. For debugging, or a deliberate exceptional
decision to disable temperature measurement, closing `JP3` connects the fixed
10 kΩ `R_TH1` between `BAT_TEMP` and `TS_RETURN`. With the thermistor disconnected,
this represents approximately 25°C regardless of actual cell temperature, so
the charger cannot enforce the cell's real hot/cold limits. Leaving the
thermistor connected would put it in parallel with `R_TH1` and produce an
incorrect reading, rather than a fixed-temperature substitute. Restore the
cell-mounted thermistor and open `JP3` for normal use. The bypass is a retained
debug/override facility, not a planned normal operating mode.
See the [BQ25186 datasheet](https://www.ti.com/lit/ds/symlink/bq25186.pdf),
[TI thermistor-selection note](https://www.ti.com/lit/an/spva059/spva059.pdf),
and [Semitec 103AT family data](https://www.semitec-global.com/products/thermistor_at/).

The charger spreads heat through its soldered exposed pad, two 0.2 mm-drill
thermal vias in that pad, three 0.4 mm-drill GND vias at the pad's ends and
beside GND pin 5, nearby GND stitching, and both large 0.5 oz (about 18 µm)
inner GND planes. This is the intended thermal path. At 5 V input, 3 V battery voltage,
and 1 A charge current, charger dissipation is approximately 2 W before current
limiting. Copper area alone does not determine the temperature rise: heat must
also leave the enclosed board. Confirm sustained charging current, thermal
regulation, and cell/enclosure temperatures in the assembled doll; the configured
100°C regulation threshold is an IC-junction threshold, not a cell-temperature
limit.

The PCB must accept charging power from either the onboard USB-C receptacle or
an unpopulated, two-wire connection to a complete off-board power module located
elsewhere inside the device:

```text
USB_VBUS ---------------- TPS2121 IN1 (priority) --+
                                                   +---- OUT ---- 5V_INPUT ---- BQ25186 IN
off-board regulated 5 V -- AUX_5V_IN -- IN2 -------+

DEBUGGER_USB_VBUS ---- external debugger CH340C ---- J_PROG1 ---- ESP32 UART0/EN/BOOT
```

`AUX_5V_IN` is a power-only input from a separate module mounted inside the
device but outside the main PCB. A complete regulated wireless-charging receiver
is one intended source. The source must provide 5.0 V nominal and must never
exceed 5.5 V at the mainboard input. A lower regulated voltage is acceptable
only after verifying that the BQ25186 starts and charges at an acceptable rate
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
A TPS2121 power mux prevents reverse current between the USB and auxiliary
sources and gives USB explicit priority. The onboard USB-C charging path
remains fully functional whether or not an auxiliary module is installed.

`5V_INPUT` means the selected external 5 V supply at the BQ25186 `IN` pin. It is
not the battery-charging output, it is not BQ25186 `SYS`, and it is not the
boosted `5V_PERIPH_SW` rail.

#### Power-source selection and reverse-current isolation

All grounds are common. Source isolation is applied to the positive 5 V paths;
do not put a diode or switch in the common-ground connection.

| Boundary | Required schematic behavior |
|---|---|
| USB `VBUS` ↔ `AUX_5V_IN` | Never connect the two sources directly. Route them through the TPS2121 for USB-only, AUX-only, and simultaneous connection. USB takes precedence when above its priority threshold and below its overvoltage threshold; do not combine or share source current. |
| USB `VBUS` → `5V_INPUT` | This permanently wired mux input reaches the charger when selected and within the mux's voltage limits; actual charging additionally requires the switch-on, firmware-verified `/CE` permission. Isolation must prevent an auxiliary source from driving voltage out of the USB-C receptacle. |
| `AUX_5V_IN` → `5V_INPUT` | This optional, power-only path receives regulated DC from an off-board module inside the device. It must prevent USB `VBUS` from driving backward into an absent or unpowered source module. The isolation circuit and mainboard ESD diode are required even though the connector is not populated by the PCBA vendor. |
| `5V_INPUT` ↔ battery/`SYS` | Reach `BAT` and `SYS` only through the BQ25186 power path; do not add an external bypass around its input/battery reverse-current management. |

`U_MUX1` is a [TI TPS2121](https://www.ti.com/product/TPS2121), orderable as
`TPS2121RUXR` (LCSC `C485916`). Its power inputs operate from 2.8–22 V,
with a 24 V absolute maximum, providing headroom for hot-plug transients on
the nominal 5 V sources. The device supports up to 4.5 A; this board programs
a lower mux limit and keeps the BQ25186 input limit at 1.05 A. The RUX package
is a 12-pin, 2.0 mm × 2.5 mm VQFN-HR, using KiCad footprint
`Package_DFN_QFN:Texas_VQFN-HR-12_2x2.5mm_P0.5mm`.

Wire the mux as follows:

| TPS2121 pin | Connection and purpose |
|---|---|
| 1, 8 `OUT` | Both connect to `5V_INPUT`, feeding BQ25186 `IN`. |
| 2 `IN2` | `AUX_5V_IN`, with connector-side `D2` ESD protection. |
| 3 `CP2` | GND. This circuit uses the internal-reference/input-voltage comparison modes. |
| 4 `OV2` | AUX overvoltage divider: `R_MUX_OV_DIV3` = 470 kΩ from `AUX_5V_IN`, and `R_MUX_OV_DIV4` = 100 kΩ to GND. |
| 5 `OV1` | USB overvoltage divider: `R_MUX_OV_DIV1` = 470 kΩ from `USB_VBUS`, and `R_MUX_OV_DIV2` = 100 kΩ to GND. |
| 6 `PR1` | USB priority divider: `R_PR1_TOP1` = 300 kΩ from `USB_VBUS`, and `R_PR1_BOT1` = 100 kΩ to GND. |
| 7 `IN1` | `USB_VBUS`, with connector-side `D1` ESD protection. The external debugger's USB supply remains separate. |
| 9 `ST` | GND; source-status reporting is unused. TI permits grounding this output when unused. |
| 10 `ILIM` / `ILM` | `R_MUX_ILIM1` and `R_MUX_ILIM2`, both 100 kΩ, in parallel to GND: 50 kΩ effective. |
| 11 `SS` | `C_MUX_SS1`, 100 nF, 50 V, X7R to GND, sets soft start and input settling. |
| 12 `GND` | Common PCB ground. |

With the 1.06 V nominal reference, the fitted 1% divider resistors give a
4.24 V rising USB-priority threshold (approximately 3.98–4.47 V including
reference and resistor tolerances) and 6.04 V rising overvoltage thresholds
on both inputs (approximately 5.66–6.37 V including tolerances). The 50 kΩ
current-limit resistance gives approximately 2.25 A nominal using
`I_LIMIT = 65.2 / R_kΩ^0.861`; it is not a precision 2.25 A ceiling or a
replacement for the charger's 1.05 A input limit.

When USB priority is asserted and USB is not overvoltage, it supplies the
output. Priority releases at approximately 4.16 V falling, due to hysteresis.
With priority released, `CP2` grounded, and both inputs valid, the mux compares
input voltages; releasing priority does not unconditionally force AUX selection.
If only one input is valid, that input supplies the
output; if neither is valid, the output is high impedance. Source selection
and reverse-current blocking require no firmware. This wiring uses the
100 µs typical switchover mode, rather than the 5 µs fast mode. Verify the
voltage dip and BQ25186 battery handover under load.

The fitted power bypass capacitors are all X7R, ±10%:

| Reference | Connection | Value and placement |
|---|---|---|
| `C_MUX1` | `USB_VBUS` to GND | 1 µF, 25 V, 0603, beside mux `IN1`. |
| `C_MUX2` | `AUX_5V_IN` to GND | 1 µF, 25 V, 0603, beside mux `IN2`. |
| `C_MUX4` | `5V_INPUT` to GND | 1 µF, 25 V, 0603, beside mux `OUT`. |
| `C_MUX3` | `5V_INPUT` to GND | 2.2 µF, 25 V, 0805, beside BQ25186 `IN`. |

Keep both output-net capacitors: each provides local bypassing at its own IC.
Use short, wide copper between the mux's power pins and their local capacitors,
with nearby GND returns. The AUX feed crosses on the bottom layer through
0.4 mm-drill vias; the capacitor-to-`IN2` connection remains on the top layer.
At 1.05 A and 56 mΩ typical on-resistance, calculated mux conduction loss is
approximately 62 mW. Power-pin copper also spreads heat; any added thermal
vias at pins 1/8, 2, or 7 must connect to `5V_INPUT`, `AUX_5V_IN`, or
`USB_VBUS`, respectively, not GND.

The higher mux voltage rating and the OV dividers do not make the complete
board a high-voltage input design. Keep both sources regulated to 5 V nominal
and no more than 5.5 V in normal operation. `D1` and `D2` reduce fast ESD and
connection transients; the mux rejects an overvoltage source but is not an
instantaneous voltage clamp. Check hot-plug waveforms at the input, `5V_INPUT`,
and the divided `/CE` node with the intended supplies and cables.
See the [TPS2121 datasheet](https://www.ti.com/lit/ds/symlink/tps2121.pdf),
especially the source-selection table, electrical limits, and layout guidance.

#### Power-domain separation and sleep-current requirements

The USB/AUX mux isolates independent external power sources. Internal switched
peripherals instead use rail control plus firmware sequencing; the first
revision adds no SPI or I2S signal-isolation components.

| Boundary | Required schematic behavior |
|---|---|
| External USB-powered debugger ↔ ESP32 on `3V3_AON` | Rev A uses direct UART connections and the two-transistor EN/BOOT circuit without power-off isolation. This is accepted only under the operating rule that the debugger and target are both powered whenever the six-pin cable is attached. Disconnect the cable before removing either supply. The debugger never powers the target through `3V3_REF`. |
| `3V3_AON` ↔ `3V3_PERIPH_SW` | Every SD pull-up belongs to the switched rail. Retain GPIO5 as the native VSPI `CS`. Firmware ends SPI, disables internal pulls, and makes the SPI pins inputs before driving `PERIPH_PWR_EN` LOW; on wake it enables the rail, waits for it to settle, and then reconfigures SPI. No SPI isolation buffer is planned. |
| `3V3_AON` ↔ `5V_PERIPH_SW` | Production GPIO21 connects to `SD_MODE` only through 634 kΩ. GPIO2 drives WS2812B-V6 DIN through the 330 Ω `R_LED_DIN1`, without an NPN or 5 V pull-up; validate direct-drive logic-HIGH margin. Firmware establishes both inactive GPIO levels before enabling the rail. Before power-off it sends an LED-off frame, mutes the amplifier, ends I2S, disables the rail, and only then releases GPIO2. No I2S or LED isolation buffer is planned. |
| `5V_INPUT` ↔ `5V_PERIPH_SW` | These are different 5 V domains and must never be tied together. The switched peripheral boost output must provide true load disconnect and must not feed the external-input or charger path. |
| Charger control and status | Connect `SDA`/`SCL` to GPIO16/GPIO17 and `/PG`/`/INT` to GPIO34/GPIO35, each with a 10 kΩ pull-up to `3V3_AON`. Connect GPIO4 through the NPN stage to `/CE`. Include leakage in the sleep audit; do not add direct charger-status LEDs. |
| `BAT` ↔ GPIO36 battery measurement | Feed the 634 kΩ / 200 kΩ divider through a second AP2281-3WG-7 whose `EN` is `PERIPH_PWR_EN`; implement the 200 kΩ lower leg as two series 100 kΩ resistors. This prevents `BAT` from driving the ADC while the ESP32 is unpowered and disconnects the divider in deep sleep. Do not measure `SYS` as a substitute. |
| Programming fixture ↔ board supplies | `3V3_REF` is a target-voltage reference/sense output only. The external debugger uses it for its indicator LED and must not drive it. A future fixture must not back-power USB, `AUX_5V_IN`, `SYS`, or the battery. |

The schematic review must trace every power pin, pull-up, protection diode,
indicator, test pad, and external connector against this table. Production
bring-up must test USB and AUX separately and together and measure reverse
current at each inactive external input. The internal peripheral approach is
fixed as rail switching plus firmware sequencing, without SPI or I2S isolation
ICs.

#### Charger-status indication

Firmware reads charging and fault state from the BQ25186 registers. `/PG` on
GPIO34 is a redundant external-input indication and deep-sleep wake source;
`/INT` on GPIO35 prompts an immediate I2C read after enabled events. Both are
open-drain and require their external 10 kΩ pull-ups because GPIO34/GPIO35 have
no internal pull-ups. The current status-LED policy deliberately has no
charging or low-battery pattern; those can be added later as semantic signals
without changing the electrical interface.

#### Battery-level measurement

The BQ25186 status registers report charger state and faults, not remaining
battery capacity. Measure `BAT` directly with the switched divider documented
above. Do **not** substitute a `SYS` measurement: the BQ25186 regulates `SYS` to
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

I2C `STAT0.CHG_STAT` values for constant-current or constant-voltage charging
override the voltage state as `CHARGING`. The averaged voltage state continues updating underneath and is
restored when charging ends. Li-ion terminal voltage still varies with load,
temperature, cell model, and recent charging; a dedicated fuel gauge remains a
future option only if a reliable percentage or runtime estimate becomes useful.

#### Addressable status LED

The production indicator is **WS2812B-V6 (LCSC C52917433)**,
a 5050 SMD, 24-bit RGB LED on `5V_PERIPH_SW`. Its pin order is 1=`VDD`,
2=`DOUT`, 3=GND, 4=`DIN`, and its serial channel order is GRB. Verify the
footprint and delivered batch against the
[manufacturer's datasheet](https://datasheet.lcsc.com/datasheet/pdf/0689d8fd6dabfc7959e82552d4ffad8b.pdf?productCode=C52917433).
This replaces the old WS2812D-F5-12mA-C1 through-hole LED and its inverting
MMBT3904 stage; it is not a footprint-compatible swap. The schematic and
production firmware now use the direct-data circuit below. Do not use the new
non-inverted production firmware with an older NPN-based board.

Firmware explicitly selects `SWEETYAAR_STATUS_LED_RGBW=0`,
`SWEETYAAR_STATUS_LED_COLOR_ORDER_GRB=1` and
`SWEETYAAR_STATUS_LED_DATA_INVERTED=0` in the `sweetyaar` environment.
`DOUT` is routed to `J_LED_EXT1` pin 2 for a future daisy-chained indicator;
pin 1 supplies `5V_PERIPH_SW` and pin 3 is GND. The connector is DNP for
assembly. Do not connect its 5 V data output to an ESP32 input. Firmware currently
drives only the onboard pixel; enabling another status indicator requires code
changes, not just increasing the pixel count (additional pixels are kept black).

Current direct-data connection (`R_LED_DIN1`: 330 Ω, 0603, LCSC C23138):

```text
GPIO2 ----------- 330 Ω ----------- LED1 DIN

5V_PERIPH_SW ---------------------- LED1 VDD
GND ------------------------------- LED1 GND
LED1 VDD -------- 100 nF --------- LED1 GND
LED1 DOUT ------------------------- J_LED_EXT1 pin 2 (optional extension)
```

The LED's MMBT3904, 10 kΩ base resistor and 1 kΩ pull-up to 5 V are removed;
the debugger's transistors are unrelated and remain unchanged. This eliminates
the former approximately 5 mA powered-idle pull-up current and NPN storage delay.
Keep 100 nF local decoupling. No external DIN pulldown is currently fitted;
a weak 47–100 kΩ pulldown is an optional refinement to hold the input LOW while
GPIO2 is high-impedance. Never pull GPIO2 up to 5 V.

Direct-drive qualification remains required: V6 specifies `VIH = 0.55 × VDD`
(2.75 V at 5 V), but the ESP32-WROOM-32E's minimum specified output HIGH is
`0.8 × VDD` (2.64 V at 3.3 V). Thus a nominal 3.3 V signal meets the LED's
threshold, but the two datasheets alone do not guarantee worst-case system
margin. Validate supply tolerances, DIN levels and timing on the intended
short connection; if adequate margin cannot be established, revisit the
interface before production. Firmware timing changes do not fix voltage margin.
See the [ESP32 module DC characteristics](https://www.espressif.com/sites/default/files/documentation/esp32-wroom-32e_esp32-wroom-32ue_datasheet_en.pdf).

The production timing defaults are **T0H = 300 ns, T0L = 950 ns,
T1H = 650 ns, T1L = 600 ns, reset LOW = 300 µs**. These target the
WS2812B-V6 timing specification; they do not establish compatibility
with every WS2812/SK6812 variant. Build flags independently configure T0H, T1H,
the bit period, and reset time; see the firmware guide. The generic bench build
retains its previous 400/850 ns zero, 800/450 ns one, and 80 µs reset.
These are RMT-generated durations, not measured pulse widths at the LED:
verify them at `DIN` after assembly. V6 requires T0H = 220–380 ns and
T1H/T0L/T1L = 580–1000 ns; the previous 900/350 ns one-bit pulse violates
its minimum LOW duration. The user cannot rework SMD components, so validate
the new package, interface and enclosure optics before committing to assembly.

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

GPIO2 is an ESP32 boot-strapping pin; do not add a pull-up to 5 V, and keep
`5V_PERIPH_SW` off during reset. Firmware drives
GPIO2 LOW before enabling the switched rail, keeping physical `DIN` LOW until
RMT owns the pin. Before sleep it sends a black frame while the LED is powered,
disables the 5 V regulator, and then makes GPIO2 an input to avoid driving HIGH
into the unpowered LED. The rail's output capacitors discharge through
the remaining load; firmware does not wait for or measure a zero-volt rail.
The amplifier is muted before regulator disable. GPIO16 and GPIO17 carry the
BQ25186 charger's I2C SDA and SCL signals, respectively.

The original DevKit's discrete GPIO2 LED is not a functional substitute for
this circuit. For the current direct GPIO2-to-`DIN` RGBW bench wiring, use
`sweetyaar-generic`; it records the non-inverted waveform and 32-bit RGBW frame
along with the board's other required overrides. Its tested channel order is
GRBW. Validate the 3.3 V logic-HIGH margin against the externally powered LED.
The production build uses non-inverted WS2812B-V6 data with a 24-bit GRB frame.
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
> **Battery-temperature validation:** Normal operation uses the cell-mounted
> thermistor and a four-wire harness in the five-position battery connector,
> with `JP3` open. These are fixed decisions for the reference design. Verify
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

The BQ25186 needs at least 1 µF effective capacitance at `IN`, nominal 10 µF at
`SYS` with at least 1 µF remaining after DC bias, and at least 1 µF at `BAT`.
The `IN`, `SYS`, and `BAT` capacitors are placement-critical: put each directly
beside its IC pin and the local GND/thermal plane. Select voltage ratings and
package sizes that preserve the required effective capacitance after DC-bias
derating. Exact manufacturer part numbers remain open until the schematic and
layout are reviewed, and must be validated for startup, radio/audio transients,
efficiency, heating, and sleep leakage.

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

The production PCB is **four layers**, 1.6 mm, with 1 oz outer copper and
JLCPCB's default 0.5 oz inner copper. Both inner layers are GND planes. A
two-layer implementation is not being pursued. The current KiCad PCB contains its outline, placement, and routing;
mechanical fit is checked against the enclosure design.

Use **2.5 mm-pitch JST-XH-family connectors for all removable off-board wire
harnesses** to simplify component ordering and use a common crimp/contact
family. The project owner will assemble the final unit, so this intentionally
accepts shared connector types for the two-pin speaker, hard-off switch, and
optional auxiliary-power connections. Label these connections and check the
pinout during assembly. The battery is the specific exception in position
count: five positions with the last unused, versus four for the buttons,
because a battery/button mix-up has much greater electrical consequences.
USB, the microSD socket, and the programming contact pads retain their own
interfaces.

Electrically, the PCB must include:

| Interface | Current requirement or decision |
|---|---|
| USB and auxiliary charging | The mainboard USB-C connector is power-only and is required for charging. Also provide unpopulated two-wire 5 V and GND auxiliary-input pads/footprint for a complete off-board source mounted elsewhere inside the device, such as a regulated wireless-charging receiver or power-only USB-C daughterboard. The PCBA vendor fits neither an auxiliary connector nor cable; it is added during device assembly when that option is used. `D2` remains populated on the mainboard. Firmware download and live serial logs use the separate USB-powered debugger through `J_PROG1`. |
| Storage | Fit a replaceable bare microSD socket on `3V3_PERIPH_SW`, entirely inside the electronics enclosure. Changing the card requires opening the enclosure. Place the socket with insertion/removal clearance on the opened PCB, not at an enclosure edge or external opening. |
| Battery | Use a protected removable 18650 in a holder and a five-position JST-XH connector: 1 GND / `BAT−`, 2 `BAT+`, 3 `TS_RETURN`, 4 `BAT_TEMP`, 5 unused. Fit the insulated Semitec 103AT-2 against the cell with two dedicated wires to `BAT_TEMP` and `TS_RETURN`; do not join its return to the current-carrying `BAT−` conductor at the holder. Leave debug bypass `JP3` open in normal use. |
| Speaker | Use one keyed two-pin JST-XH connector and a short stranded-wire harness. It must support either 4 Ω or 8 Ω speakers; the battery uses a distinct five-position connector. |
| Song and animal buttons | Use one four-pin JST-XH PCB connector arranged as `BTN_SONG`, GND, `BTN_ANIMAL`, GND. The two ground contacts join on the PCB, allowing four ordinary single-wire crimps and two independent two-wire button branches without a harness splice. |
| Main power | Fit a physical latching **SPST pushbutton switch** on the enclosure as an exceptional safety/service control; deep sleep is normal. The complete switch body—not merely a remote actuator—mounts on the enclosure. Place it in series between BQ25186 `SYS` and the regulator inputs; leave `BAT+` permanently connected to BQ25186 `BAT`. Connect the switch to the PCB with two conductors and a two-pin connector. The switch and every harness contact must carry the validated current with margin. |
| Vibration wake | The normally-closed vibration switch is soldered directly onto the PCB. Exact part and footprint remain schematic/BOM selections; its physical orientation follows enclosure design. |
| Indicators | Route BQ25186 `/PG` and `/INT` to ESP32 GPIO34/GPIO35; charger configuration and detailed status use I2C on GPIO16/GPIO17. Target one WS2812B-V6 (C52917433, 5050 SMD) on `5V_PERIPH_SW`, with 100 nF local decoupling and GPIO2 driving DIN through a series data resistor, without the old NPN/5 V pull-up. Verify direct-drive voltage margin, footprint, 24-bit GRB order and timing; preserve or test-pad `DOUT` for a future daisy-chained indicator. |
| Programming/test | Use six exposed surface contact pads on 2.54 mm centers (`SweetYaar:DebuggerPad_1x06_P2.54mm`), without holes or solder-paste apertures. Nothing is soldered onto the mainboard here: header pins or pogo pins on the debugger/fixture temporarily touch the pads. Contacts 1–6 are `3V3_REF`, GND, GPIO1/`UART_TXD`, GPIO3/`UART_RXD`, `ESP_EN`, and GPIO0/BOOT. The external debugger supplies CH340C USB-to-UART and automatic-download control. |

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
receiver module then enforces its own output rating, while the BQ25186 separately
limits input current to 1.05 A and battery charge current to 1 A. Transmitter
capability, coupling/alignment, receiver rating, BQ25186 input limit, system
load, battery charge setting, and thermal regulation all apply; the lowest
available limit determines the actual charge rate. Select a receiver with a
regulated 5 V output and enough margin for the 1.05 A charger-input setting, or
include a lower AUX-specific current limit.
[Qi-certified](https://www.wirelesspowerconsortium.com/knowledge-base/testing-and-certification/qi-certified-products/)
transmitter/receiver pairs are designed to negotiate a mutually supported
level, but maximum power is not guaranteed and arbitrary uncertified modules
must not be assumed interoperable. Temperature, alignment, and voltage stability
must be tested in the real doll. A USB charging input remains permanently fitted
on the main board, along with firmware service and live logs; wireless charging is
only an optional additional input.

Deep sleep, not the physical switch, is the normal way to stop using the toy.
The enclosure-mounted latching SPST switch is a deliberate hard-off
safety/service control. It opens the `SYS` feed between the BQ25186 and both
system regulators, preventing the battery, USB, or AUX input from powering the
ESP32 or switched peripherals while off. `BAT+` remains permanently connected
to BQ25186 `BAT`, but the fail-closed `/CE` circuit disables charging because
the ESP32 is unpowered. The switch uses two terminals, two harness
conductors, and a two-pin PCB connector. This is a direct mechanical disconnect
rather than an electronic shutdown commanded through load-switch inputs.

The mainboard USB-C connector is power-only. Its `VBUS` pins feed the charging
path, while its USB data pins are intentionally unconnected. Firmware download
and live serial logs use a separate debugger board containing a CH340C
(LCSC C7464026, SOP-16), matching the generic board, and its own USB-C connector.
USB `VBUS` feeds an XC6206P332MR-G (C5446, SOT-23-3), which generates the
debugger-only `3V3_DEBUG` supply. Connect both CH340C pin 16 `VCC` and pin 4 `V3`
to this rail; this is the datasheet's external 3.3 V configuration and keeps its
UART outputs at ESP32-compatible levels. Do not power CH340C `VCC` directly
from 5 V in this direct-UART design. The debugger does not connect its USB
`VBUS` or `3V3_DEBUG` supply to the target.

CH340C uses the project symbol `SweetYaar:CH340C_3V3`, based on KiCad's CH340C
symbol with `V3` defined as a power input for this supply configuration.
Its footprint is `Package_SO:SOIC-16_3.9x9.9mm_P1.27mm`. Pin 1 is GND, pin 15
`R232` is tied to GND for normal UART polarity, and unused modem pins and
pin 8 `OUT#` are left unconnected. No external crystal, VBUS-sense divider,
or reset pull-up is needed.

`C4` at the regulator input and `C2` at its output are both 2.2 µF, 25 V X7R
0805, C126591, matching the mainboard; these provide margin over the regulator's
1 µF application-circuit capacitors. `C3` is a local 100 nF capacitor beside
CH340C pins 16/4. `C1` decouples the USB ESD device. Both 100 nF capacitors use
the mainboard's 50 V X7R 0603 C14663. All debugger resistors are 0603, 1%:
`R_CC1/R_CC2` are 5.1 kΩ C23186, `R_DTR1/R_RTS1` are 10 kΩ C25804, and the
green indicator's `R1` is 330 Ω C23138. These are all existing mainboard parts.

The six programming contacts are **bare surface pads on 2.54 mm centers**,
using `SweetYaar:DebuggerPad_1x06_P2.54mm`. There are no through-holes and no
mainboard connector to solder. Standard male header pins or pogo pins on the
debugger/fixture temporarily touch these pads; the fixture must hold all six
contacts reliably throughout flashing. The pads expose copper through the
solder mask but have no `F.Paste` apertures, so the assembly stencil does not
deposit solder paste on them. Contacts 1–6 are
`3V3_REF`, GND, target GPIO1/`UART_TXD`, target GPIO3/`UART_RXD`, `ESP_EN`, and
GPIO0/BOOT. `3V3_REF` is sense-only: on the debugger it powers only the green
KT-0805G indicator LED (C2297, 0805) through 330 Ω and must never be driven
back into the target. The UART directions cross normally: CH340C pin 3 `RXD`
receives target `UART_TXD`, and pin 2 `TXD` drives target `UART_RXD`.

The debugger routes CH340C pin 13 `DTR#` and pin 14 `RTS#` through Espressif's
two-transistor automatic-download circuit to target `EN` and BOOT. **Solder
jumpers are the chosen disconnect mechanism.** `JP1` connects `ESP_EN` to
`TARGET_EN`, and `JP2` connects BOOT to `TARGET_BOOT`. Both use
`Jumper:SolderJumper-2_P1.3mm_Bridged_RoundedPad1.0x1.5mm` and are normally
bridged for automatic firmware download. Open both solder bridges for
serial-only operation without debugger-driven reset/boot control; bridge both
again to restore automatic download. UART TX/RX remain connected in either
configuration. The target retains the recommended 10 kΩ/1 µF `ESP_EN` network and
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
removing either supply. CH340C specifies about 4 mA typical, 12 mA maximum
operating current in its 3.3 V configuration, supplied from debugger USB through
the regulator. Its RXD includes an internal pull-up, so do not describe all
static input current as leakage-only. The target-reference LED additionally
draws roughly `(3.3 V - LED_VF) / 330 Ω` from the target, approximately
0.6–2.1 mA using the LED's listed 2.6–3.1 V forward-voltage range; actual current
and brightness depend on its low-current forward characteristic.

If this operating rule is broken, the direct output-to-unpowered-input current
is not bounded to a small, guaranteed value by either datasheet. A powered
target can drive an unpowered CH340C `RXD`; the general CH340 input limit is
`VCC + 0.5 V`, and this design does not depend on the lot-specific inward-current
protection described for newer CH340C silicon. A powered debugger can similarly
inject current from CH340C `TXD` into an unpowered ESP32 and partially back-power
its 3.3 V domain. Actual current depends on internal protection structures and
other rail loads; normal input-current specifications are not fault-current
limits. Keep both boards powered while connected.

Add USB ESD protection on the debugger and route its `D+` and `D-` as a short
controlled differential pair. Keep the debugger disconnected during
battery-sleep measurements. USB serial provides live logs; retrieving logs
produced before connection or reset requires a separate firmware-managed
persistent log buffer.

Programming-interface references: [ESP32 UART hardware guidance](https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32/schematic-checklist.html#uart),
[ESP32 boot-mode and automatic-download behavior](https://docs.espressif.com/projects/esptool/en/latest/esp32/advanced-topics/boot-mode-selection.html),
[ESP32-DevKitC reference schematic](https://dl.espressif.com/dl/schematics/esp32_devkitc_v4_sch.pdf),
and [CH340 datasheet](https://www.wch-ic.com/downloads/CH340DS1_PDF.html).
Debugger regulator reference: [XC6206 datasheet](https://product.torexsemi.com/system/files/series/xc6206.pdf).

The TPS2121 closes the USB-priority source-mux selection. During schematic and
layout review, verify the priority and OV dividers, the parallel current-limit
resistors, soft-start capacitor, both 1 µF input capacitors, separate local mux
output and charger input capacitors, and the 100 kΩ / 91 kΩ `/CE` divider.
Check power-path widths and vias against normal current and mux current-limit
tolerance, connector-side protection, switchover behavior, and reverse current
at both inactive inputs.

#### Remaining electrical decisions and verification

The battery-warning architecture is closed: direct `BAT` measurement through
the AP2281-switched 634 kΩ / 200 kΩ divider on GPIO36, with the 200 kΩ lower
leg implemented as two series 100 kΩ resistors.

Exact connector models and regulator passives are schematic/BOM selections
that must satisfy the fixed behavior above. The selected WS2812B-V6 remains
a hardware-verification item: confirm its SMD
footprint, 24-bit GRB frame, direct-drive voltage margin, logic timing and
full-white current on the purchased batch. Keep the local 100 nF decoupling;
the old MMBT3904/base-resistor/pull-up interface is no longer the target design.
The deep-sleep calculation and production current
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
  strain-relieve both dedicated thermistor wires, connecting them to `BAT_TEMP`
  and `TS_RETURN` through battery-connector pins 4 and 3 respectively. Do not
  join the thermistor return to battery `BAT−`/GND in the holder or harness;
  its GND connection is at the charger through `TS_RETURN`. Never solder to or
  expose the bare cell can. Leave `JP3` open for normal use.
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
- The WS2812B-V6 SMD addressable RGB status LED must be visible from outside. Its
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
   operation. The external debugger and its CH340C supply remain electrically
   separate from this power-path test.
3. Connect USB and AUX together, verify that nominal 5 V USB takes priority,
   and measure reverse current into both sources. Do not rely only on voltage.
   Capture hot-plug and source-removal waveforms at both inputs, `5V_INPUT`,
   and `/CE`; verify switchover and battery handover under load. Check the
   priority and OV thresholds with current-limited sources and a suitable load,
   accounting for divider/reference tolerances and the input ESD diodes' limits.
4. Verify `/CE` remains HIGH (approximately 2.38 V at 5 V input) through reset
   and hard-off. With the switch on, confirm firmware detects device ID `0x1`,
   reads back every configured
   register, then enables charging only while `/PG` indicates valid input.
5. With the Semitec 103AT-2 installed against the cell wrapper, verify the
   BQ25186 suspends and resumes charging at the intended 45°C and 0°C limits.
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
    can power the system regulators and that `/CE` remains HIGH so the battery
    does not charge even with USB or AUX attached.
14. Move the vibration switch and confirm that the rails return only after the
    ESP32 reboots.

During deep sleep, `PERIPH_PWR_EN`, `3V3_PERIPH_SW`, and `5V_PERIPH_SW` should
all measure LOW or off. If a peripheral rail remains active, check its enable
wiring, output-discharge path, and the 5 V converter's required true-load-
disconnect behavior.

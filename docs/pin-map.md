# ESP32 Production Firmware Pin Map

This map documents only the GPIO connections assumed by the production
`esp32dev` firmware. The source of truth is `src/Config.h`; the diagnostic
PlatformIO environments do not add any production connections.

The target is the original ESP32-WROOM-32. All GPIO signals are 3.3 V logic and
all connected modules must share ground with the ESP32.

## Required connections

| ESP32 GPIO | Firmware name | Direction | Connect to | Firmware assumption |
|---:|---|---|---|---|
| 5 | `PIN_SD_CS` | Output | microSD `CS` | SPI chip select, active LOW. |
| 18 | `PIN_SD_SCK` | Output | microSD `SCK` / `CLK` | SPI clock; the SD bus runs at 20 MHz after initialization. |
| 19 | `PIN_SD_MISO` | Input | microSD `MISO` / `DO` | Data from the SD card to the ESP32. |
| 23 | `PIN_SD_MOSI` | Output | microSD `MOSI` / `DI` / `CMD` | Data from the ESP32 to the SD card. |
| 26 | `HW_I2S_BCLK` | Output | MAX98357A `BCLK` | I2S bit clock. |
| 25 | `HW_I2S_WS` | Output | MAX98357A `LRC` / `WS` | I2S word-select / left-right clock. |
| 22 | `HW_I2S_DOUT` | Output | MAX98357A `DIN` | I2S audio data from the ESP32 to the amplifier. |
| 21 | `PIN_AMP_MUTE` | Output | Rev A `AMP_MUTE_CTL` transistor input | Active HIGH mute control. HIGH must make the transistor pull the MAX98357A `SD/MODE` pin LOW; LOW releases it so the amplifier can run. |
| 32 | `PIN_BTN1` | Input with internal pull-up | Song button to GND | Active LOW. Pressing the button must short GPIO32 to ground; no external pull-up is required. |
| 33 | `PIN_BTN2` | Input with internal pull-up | Animal button to GND | Active LOW. Pressing the button must short GPIO33 to ground; no external pull-up is required. |
| 27 | `PIN_VIB_WAKE` | Input with internal/RTC pull-up | Passive vibration switch to GND | Active LOW. The normally open switch must momentarily short GPIO27 to ground. GPIO27 is also the sole deep-sleep wake source. |
| 13 | `PIN_PERIPH_EN` | Output | Active-HIGH load-switch `EN` | HIGH powers the shared SD-card and amplifier rail while awake. LOW turns that rail off and is RTC-held LOW during deep sleep. |
| 2 | `PIN_LED` | Output | On-board status LED | Assumed active HIGH. It is lit during initialization and used for status indication; no external connection is required on a normal ESP32 dev board. |

## Wiring details the firmware depends on

### Buttons

Each button is a normally open momentary switch:

```text
GPIO32 ---- button 1 ---- GND
GPIO33 ---- button 2 ---- GND
```

The firmware enables the ESP32's internal pull-ups and treats `LOW` as pressed.
Button 1 selects or advances songs, button 2 selects or advances animal sounds,
and a near-simultaneous press is handled as the combined-button action.

### Vibration wake switch

The wake input expects a passive, normally open switch:

```text
GPIO27 ---- vibration switch ---- GND
```

The firmware does not expect a powered vibration-sensor module or an active-HIGH
signal. Before deep sleep it waits for GPIO27 to return HIGH, then configures
EXT0 wake on LOW.

### Peripheral power switch

GPIO13 is not a peripheral power output. It is a logic signal for an
active-HIGH load-switch enable:

```text
GPIO13 ---- load-switch EN
             switched output ---- microSD power
                              `---- MAX98357A power
```

The specified switch is the `AP2281-3WG-7` in its six-pin SOT26 package. Its
physical pinout is shown below from the **top/marking side** of the component:

```text
                     AP2281-3WG-7
                         _______
switched OUT ------- 1 --|     |-- 6 ------- +5V IN
common GND --------- 2 --|     |-- 5 ------- common GND
GPIO13 / EN -------- 3 --|_____|-- 4 ------- +5V IN
```

| AP2281 pin | Name | Connect to |
|---:|---|---|
| 1 | `OUT` | Switched power rail feeding the microSD module `VCC` and MAX98357A `VIN`. |
| 2 | `GND` | Common ground. |
| 3 | `EN` | ESP32 GPIO13, with a 100 kΩ pulldown from this pin to GND. |
| 4 | `IN` | Unswitched +5 V source. |
| 5 | `GND` | Common ground. |
| 6 | `IN` | Unswitched +5 V source. |

Connect **both** input pins and **both** ground pins; the duplicated pins must
not be left floating. Place a 1 µF capacitor between the `IN` rail and GND and
a 0.1 µF capacitor between `OUT` and GND, close to the switch. The drawing is
a top view; the solder-pad/underside view is mirrored.

The firmware assumes the SD card and amplifier are on the same switched rail.
It enables the rail at boot, waits 50 ms before initializing the peripherals,
and disables and RTC-holds the enable LOW for deep sleep. The hardware should
also provide a physical pulldown on `EN` so the rail defaults off during reset,
bootloader operation, or a firmware failure.

### Amplifier mute

GPIO21 follows the Rev A inverted mute circuit:

```text
GPIO21 HIGH ---- transistor on ---- MAX98357A SD/MODE pulled LOW (muted)
GPIO21 LOW  ---- transistor off --- MAX98357A SD/MODE released (enabled)
```

The production polarity constant is `AMP_MUTE_ACTIVE_HIGH = true`. Connecting
GPIO21 directly to `SD/MODE` would invert the behavior expected by the code and
is therefore not the production wiring assumed by the firmware.

## Not used by the production firmware

The production code has no pin assignment for I2C, battery-voltage sensing,
charger control, an external encoder, or additional sensors. UART/USB serial is
used for logs and flashing but is not required for normal toy operation.

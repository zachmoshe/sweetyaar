# Rev A Pin Map

This pin map keeps the reusable board services stable while leaving project-specific
GPIO available on headers. SweetYaar can still use the same firmware pins by wiring
external buttons or controls to the GPIO expansion header.

## Fixed Peripheral Pins

| Function | ESP32 GPIO | Board Net | Notes |
|---|---:|---|---|
| SD SCK / CLK | GPIO18 | `SD_SCK` | Shared with external SPI header. Keep short. |
| SD MISO / DO / D0 | GPIO19 | `SD_MISO` | Add 10k pull-up to 3V3 at socket. |
| SD MOSI / DI / CMD | GPIO23 | `SD_MOSI` | Add 10k pull-up to 3V3 at socket. |
| SD CS / D3 | GPIO5 | `SD_CS` | Add 10k pull-up to 3V3. Boot strap caution, but acceptable if pulled high. |
| SD card detect / spare input | GPIO34 | `SD_CD` | Exposed on `J8`; not wired to the current microSD socket symbol. Input only, needs external pull-up if used. |
| I2S BCLK | GPIO26 | `I2S_BCLK` | To MAX98357A BCLK. |
| I2S LRCK / WS | GPIO25 | `I2S_WS` | To MAX98357A LRC/WS. |
| I2S DOUT | GPIO22 | `I2S_DOUT` | To MAX98357A DIN. |
| Amp mute control | GPIO21 | `AMP_MUTE_CTL` | HIGH mutes via transistor. LOW leaves mode jumper in control. |
| USB serial TX from ESP32 | GPIO1 / U0TXD | `UART0_TX` | To USB-UART RX. Also boot logs. |
| USB serial RX to ESP32 | GPIO3 / U0RXD | `UART0_RX` | To USB-UART TX. |
| Boot button | GPIO0 | `BOOT` | Pulled high, button to GND. |
| Reset button | EN | `EN` | Pulled high, button to GND. |

## Expansion Defaults

| Function | ESP32 GPIO | Board Net | Notes |
|---|---:|---|---|
| I2C SDA | GPIO16 | `I2C_SDA` | Expose on I2C header with 3V3/GND. |
| I2C SCL | GPIO17 | `I2C_SCL` | Expose on I2C header with 3V3/GND. |
| External SPI CS 1 / SweetYaar wake input | GPIO27 | `SPI_CS1` | Reusable default is extra SPI CS. SweetYaar sleep firmware repurposes this header pin as `VIB_WAKE`, active LOW to GND. |
| External SPI CS 2 | GPIO14 | `SPI_CS2` | Boot strap/JTAG-adjacent caution, but usable. |
| Status LED | GPIO2 | `GPIO2_LED` | Goes through the `JP2` slide switch before the LED; GPIO2 is a strap pin. |
| Spare GPIO / project button | GPIO32 | `GPIO32` | Good default for external buttons or controls. |
| Spare GPIO / project button | GPIO33 | `GPIO33` | Good default for external buttons or controls. |
| Spare PWM/GPIO | GPIO4 | `GPIO4` | General purpose. Strap-related; avoid strong boot pull-down/up. |
| Spare GPIO / SweetYaar peripheral enable | GPIO13 | `GPIO13` | Reusable default is spare GPIO. SweetYaar sleep firmware uses this as `PERIPH_EN`, active HIGH. |
| Spare GPIO | GPIO15 | `GPIO15` | Strap pin; expose but label caution. |
| Spare input/ADC | GPIO35 | `GPIO35` | Input only, no internal pull-up/down. |
| Spare input/ADC | GPIO36 | `GPIO36` | Input only, no internal pull-up/down. |
| Spare input/ADC | GPIO39 | `GPIO39` | Input only, no internal pull-up/down. |

## Pins To Treat Carefully

These ESP32 pins affect boot or have limitations:

| Pin | Caution |
|---:|---|
| GPIO0 | Must be low only for flashing; otherwise high for normal boot. |
| GPIO2 | Boot strap pin. Use LED only through the `JP2` enable switch. |
| GPIO5 | Boot strap pin. Used as SD CS with 10k pull-up. |
| GPIO12 | Boot strap pin that can affect flash voltage. Avoid for Rev A expansion default. |
| GPIO15 | Boot strap pin. Expose, but label it. |
| GPIO34-39 | Input only. No internal pull-ups/pull-downs. |
| GPIO1/GPIO3 | UART0 for USB serial and boot logs. Do not use for normal expansion. |

## Header Proposal

### SPI Expansion Header

```text
1  3V3
2  GND
3  SCK    GPIO18
4  MOSI   GPIO23
5  MISO   GPIO19
6  CS1    GPIO27
7  CS2    GPIO14
8  5V
```

For SweetYaar sleep-mode testing, pin 6 is not used as SPI CS1. Wire it to the
passive vibration switch instead:

```text
GPIO27 / SPI CS1 header pin -> passive vibration switch -> GND
```

### I2C Expansion Header

```text
1  GND
2  3V3
3  SDA    GPIO16
4  SCL    GPIO17
```

### User GPIO Header

```text
1   3V3
2   5V
3   GND
4   GPIO32
5   GPIO33
6   GPIO4
7   GPIO13
8   GPIO15
9   GPIO35
10  GPIO36
11  GPIO39
12  SD_CD / GPIO34
```

For SweetYaar sleep-mode testing, GPIO13 drives the active-HIGH enable input on
the SD + amp peripheral load switch.

## SD Socket Pull-Ups

Place these near the microSD socket:

| SD Pin | ESP32 Use | Pull-Up |
|---|---|---|
| CMD / DI | MOSI | 10k to 3V3 |
| D0 / DO | MISO | 10k to 3V3 |
| D1 | unused | 10k to 3V3 |
| D2 | unused | 10k to 3V3 |
| D3 / CS | CS | 10k to 3V3 |

Optional small series resistors near ESP32 for signal cleanup:

| Net | Suggested |
|---|---:|
| `SD_SCK` | 22R-33R |
| `SD_MOSI` | 22R-33R |
| `SD_CS` | 22R-33R |

## Firmware Compatibility

The SweetYaar firmware pin numbers match this map, but Rev A changes the amp mute
polarity because GPIO21 drives a transistor mute control instead of driving the
MAX98357A `SD/MODE` pin directly:

```cpp
PIN_SD_SCK  = 18
PIN_SD_MISO = 19
PIN_SD_MOSI = 23
PIN_SD_CS   = 5

HW_I2S_BCLK = 26
HW_I2S_WS   = 25
HW_I2S_DOUT = 22
PIN_AMP_MUTE = 21  // HIGH = mute on Rev A amp hardware

// Wire project buttons to expansion GPIO, for example:
PIN_BTN1 = 32
PIN_BTN2 = 33

// SweetYaar sleep branch project wiring:
PIN_VIB_WAKE  = 27  // GPIO27/SPI CS1 header pin -> vibration switch -> GND
PIN_PERIPH_EN = 13  // GPIO13 header pin -> active-HIGH load-switch enable
```

The Rev A carrier does not include the SweetYaar vibration switch or load-switch
module on-board. Those parts are external test add-ons for this reusable carrier;
they are expected to become real components on the final SweetYaar toy PCB.

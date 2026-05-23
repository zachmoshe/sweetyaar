# Rev A Design Decisions

These are the current locked-in defaults for the first board spin. They are not
forever decisions. They are the cleanest first version for a reusable lab board.

## Board

| Decision | Rev A Choice | Why |
|---|---|---|
| Board role | Reusable ESP32 prototype carrier | This is a lab tool, not the final toy PCB. |
| Layer count | 4-layer PCB | Gives us solid ground/power planes and calmer SPI/I2S routing. |
| Assembly side | Top-side SMT only | Keeps assembly cheaper and much easier to inspect. |
| Through-hole parts | Hand-soldered after delivery | Headers and terminals are mechanically chunky and easy by hand. |
| Approximate size | 80 mm x 60 mm starter outline | Big enough for labels, headers, and debugging. |
| Board edge | ESP32 antenna on an edge with keepout | Protects Bluetooth/Wi-Fi performance. |

## Core Electronics

| Block | Rev A Choice | Notes |
|---|---|---|
| ESP32 | ESP32-WROOM-32E module with PCB antenna | Classic Bluetooth support, built-in flash/crystal/RF section. |
| USB connector | USB-C, USB 2.0 device, 5V sink only | No USB Power Delivery. CC1/CC2 get 5.1k pull-downs. |
| USB serial | CH340C in SOIC-16 | Visible leads, no crystal, cheap, common. |
| 3.3V regulator | AP2112K-3.3 / SOT-23-5 LDO | Modern low-dropout 600mA regulator; better margin if the 5V rail sags. |
| Power selection | Manual 3-pin jumper and shunt | Prevents USB and bench PSU 5V from being tied together. |
| microSD | Native 3.3V socket wired in SPI mode | No level shifter module, no breadboard contacts. |
| Audio | Blue MAX98357A breakout/module 1x7 header with GPIO mute | Avoids tiny bare amp packages for Rev A; the module defaults to mono average and the speaker attaches directly to the module. |

## Power Model

The board has two possible 5V sources: USB-C VBUS and an external bench PSU input.
Only one source feeds `5V_SYS` at a time. The grounds are always common, because USB
data and serial monitoring need the same reference as the ESP32.

For normal desk work, select USB power. For audio or external testing, select EXT
5V and keep USB connected for serial monitor only.

## Firmware Compatibility

Rev A keeps the reusable board peripherals on stable pins. Project-specific UI,
including SweetYaar buttons, should be wired through the GPIO expansion header
instead of being permanently assigned on the carrier board.

| Peripheral | Nets |
|---|---|
| SD SPI | `SD_SCK=GPIO18`, `SD_MISO=GPIO19`, `SD_MOSI=GPIO23`, `SD_CS=GPIO5` |
| I2S amp | `I2S_BCLK=GPIO26`, `I2S_WS=GPIO25`, `I2S_DOUT=GPIO22`, `AMP_MUTE_CTL=GPIO21`; HIGH mutes |
| Project buttons / controls | Use expansion GPIO such as `GPIO32` and `GPIO33` |
| USB serial | `UART0_TX=GPIO1`, `UART0_RX=GPIO3` |

## Things We Are Avoiding In Rev A

We are not using BGA packages. We are also avoiding QFN and other hidden-pad parts
where practical, because those are harder to inspect and can add X-ray requirements
at assembly. We are not adding battery charging, USB Power Delivery, displays, or
native SDIO mode in this revision.

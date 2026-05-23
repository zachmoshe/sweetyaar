# Rev A Block Diagram

## System Diagram

```mermaid
flowchart LR
    USB["USB-C connector\n5V + USB 2.0 data"] --> PSEL["5V source select\n3-pin jumper"]
    EXT["External 5V input\nscrew terminal"] --> PSEL
    PSEL --> SYS5["5V_SYS rail"]

    SYS5 --> REG33["3.3V regulator\nAP2112K-3.3 LDO"]
    REG33 --> SYS33["3V3 rail"]

    USB --> UART["USB-UART bridge\nCH340C SOIC-16"]
    UART --> ESPUART["ESP32 UART0\nTXD/RXD"]
    UART --> AUTOBOOT["Auto program/reset\nDTR/RTS transistors"]
    AUTOBOOT --> ESPBOOT["ESP32 EN + GPIO0"]

    SYS33 --> ESP["ESP32-WROOM-32E\nbuilt-in antenna at board edge"]
    SYS33 --> SD["microSD socket\n3.3V SPI mode"]
    SYS5 --> AMP["I2S speaker amp\nMAX98357A section/module"]

    ESP --> SD_SPI["SPI bus\nSCK/MOSI/MISO/CS"]
    SD_SPI --> SD
    SD_SPI --> SPIHDR["External SPI header\nextra CS lines"]

    ESP --> I2S["I2S bus\nBCLK/LRCK/DOUT + mute control"]
    I2S --> AMP
    AMP --> SPK["Speaker soldered to\nMAX98357A module"]

    ESP --> I2C["I2C header\nSDA/SCL/3V3/GND"]
    ESP --> GPIO["Spare GPIO headers\nproject buttons/controls connect here"]
    ESP --> LED["Status LED\njumper optional"]
```

## Physical Layout Concept

```text
+------------------------------------------------------------------+
| ESP32-WROOM-32E                                                  |
| [PCB antenna end at board edge / copper keepout]                 |
|                                                                  |
|        GPIO headers                         I2C / SPI headers    |
|                                                                  |
| USB-C  USB-UART   EN/BOOT buttons      microSD socket            |
|                                                                  |
| 5V input  source select  3V3 regulator   I2S amp module header   |
+------------------------------------------------------------------+
```

## Layout Rules We Care About

- Put the ESP32 antenna at the PCB edge, preferably with the antenna portion outside
  the main board outline or at least over a no-copper keepout.
- Keep copper, traces, headers, screws, speaker wires, and power wires away from the
  antenna keepout.
- Keep SD traces short, especially `CLK`.
- Add SD pull-ups at the socket, not somewhere far away on a breadboard.
- Put decoupling capacitors next to the SD socket, ESP32 module, regulator, and amp.
- Keep speaker current loops away from the ESP32 antenna and SD traces.
- Use wide traces or pours for `5V_SYS`, `3V3`, and ground.
- Use many ground vias near power sections and connectors.

## Rev A Power Concept

For the first revision, use a simple source selector:

```text
USB_VBUS ----+
             +-- 3-pin jumper + shunt --> 5V_SYS
EXT_5V  -----+
```

This is intentionally simple. It prevents backfeeding the Mac/USB port from the bench
PSU and makes power debugging obvious. A later revision can use an ideal-diode mux if
automatic source switching becomes important.

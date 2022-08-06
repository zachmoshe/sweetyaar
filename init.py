import os
from machine import Pin, SoftSPI
import uasyncio as asyncio

from src import config
from src import led_indicator
from lib import sdcard
# from lib import wifimanager

cfg = config.get_config()

print(cfg)

LED = led_indicator.LedIndicator(
    cfg["led_indicator"]["GPIO_RED"],
    cfg["led_indicator"]["GPIO_GREEN"], 
    cfg["led_indicator"]["GPIO_BLUE"])


async def _mount_sdcard():
    print("Mounting SDCard... ", end="")
    await asyncio.sleep_ms(100)
    spi = SoftSPI(
        baudrate=40_000_000,
        sck=Pin(cfg["sdcard"]["SPI_SCK"]),
        mosi=Pin(cfg["sdcard"]["SPI_MOSI"]),
        miso=Pin(cfg["sdcard"]["SPI_MISO"]))
    sd = sdcard.SDCard(spi=spi, cs=Pin(cfg["sdcard"]["SPI_CS"]))
    await asyncio.sleep_ms(100)
    os.mount(sd, cfg["sdcard"]["mount_path"])
    await asyncio.sleep_ms(100)
    print("Done!")

# async def _setup_network():
#     # Set network
#     # print("Setting up network... ", end="")
#     # wm = wifimanager.WifiManager(ssid="Sweet Yaar Config", password="sweetyaar")
#     # wm.connect()
#     # print("Done!")
#     pass

async def init():
    blink_task = asyncio.create_task(LED.blink("blue", cycle_ms=200))
    try:
        await _mount_sdcard()
        # await _setup_network()
        blink_task.cancel()
        await LED.blink("green", cycle_ms=2000, times=1)
    except Exception as e:
        print("COULDN'T INIT - ", e)
        blink_task.cancel()
        await LED.blink("red", cycle_ms=1000, times=4)
        raise e


asyncio.run(init())

import gc 
import os
from machine import Pin, SoftSPI, SPI

from src import config
from src import led_indicator
from lib import sdcard
from . import bt_logger

logger = bt_logger.get_logger(__name__)

gc.threshold(gc.mem_free() // 4 + gc.mem_alloc())

cfg = config.get_config()

AUDIO_PLAYER_FILE_BUFFER = bytearray(cfg["audio_player"]["I2S_buffer_length_bytes"])


LED = led_indicator.LedIndicator.from_neo_pixel(
    cfg["led_indicator"]["DI_GPIO"])
LED.set_intensity(-2)


class LedIndicate:
    def __init__(self, led, color):
        self.led = led
        self.color = color
    def __enter__(self):
        self.led.set_color(self.color)
    def __exit__(self, *args):
        self.led.off()


def _mount_sdcard():
    logger.info("Mounting SDCard...")
    if "spi" in cfg["sdcard"]:
        spi = SPI(cfg["sdcard"]["spi"])
    elif "soft_spi" in cfg["sdcard"]:
        spi = SoftSPI(
            sck=Pin(cfg["sdcard"]["soft_spi"]["SPI_SCK"]),
            mosi=Pin(cfg["sdcard"]["soft_spi"]["SPI_MOSI"]),
            miso=Pin(cfg["sdcard"]["soft_spi"]["SPI_MISO"]))
    else:
        raise ValueError("Must provide `spi` or `soft_spi` in sdcard config")
    sd = sdcard.SDCard(spi=spi, cs=Pin(cfg["sdcard"]["SPI_CS"], Pin.OUT))
    os.mount(sd, cfg["sdcard"]["mount_path"])
    return sd

try:
    with LedIndicate(LED, "blue"):
        SDCARD = _mount_sdcard()
    LED.blink_sync("green", cycle_ms=200, times=4)

except Exception as e:
    logger.error(f"COULDN'T INIT BOARD: {repr(e)}")
    LED.blink_sync("red", cycle_ms=400, times=4)
    LED.set_color("red")
    raise e

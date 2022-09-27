import esp32
import gc 
import machine
from machine import Pin, SoftSPI, SPI, Signal
import os
import sys
import time

import uasyncio as asyncio

from src import audio_library
from src import audio_player
from src import bt_logger
from src import config
from src import controller
from src import interfaces 
from src import led_indicator
from lib import sdcard

machine.freq(240_000_000)
gc.threshold(gc.mem_free() // 4 + gc.mem_alloc())
logger = bt_logger.get_logger(__name__)

if machine.wake_reason() == machine.PIN_WAKE:
    logger.info("Woke up due to movement")


class SweetYaarDevice:
    def __init__(self, audio_player_file_buffer):
        loop = asyncio.get_event_loop()
        loop.set_exception_handler(self.asyncio_exception_handler)

        self.config = config.get_config()

        # Bluetooth switch
        bt_gpio = self.config["bluetooth_switch_gpio"]
        self.bluetooth_switch = Signal(Pin(bt_gpio, Pin.IN, Pin.PULL_UP), invert=True)

        # pre-allocate buffer to avoid later fragmented memory..
        self._audio_player_file_buffer = audio_player_file_buffer
        
        self.led = led_indicator.LedIndicator.from_neo_pixel(self.config["led_indicator"]["DI_GPIO"])
        self.led.set_intensity(-2)

        self.sdcard = None
        self.audio_library = None
        self.audio_player = None
        self.controller = None

    def init(self):
        try:
            with self.led.indicate("blue"):
                self._mount_sdcard()
                self._init_components()

            self.led.blink_sync("green", cycle_ms=200, times=4)
            logger.info("Initialization completed.")
            self._play_startup_sound()

        except Exception as e:
            logger.error(f"Couldn't init SweetYaarDevice: {repr(e)}")
            self.led.blink_sync("red", cycle_ms=400, times=4)
            sys.print_exception(e)
            self.shutdown()

        try:
            shutdown_needed = False
            self.controller.take_control()
        
        except KeyboardInterrupt:
            self.cleanup()  # just cleanup, no reset.
            print("Keyboard interrupt. Going back to REPL..")

        except Exception as e:
            shutdown_needed = True
            logger.error(f"Controller caught exception: {repr(e)}")
            sys.print_exception(e)

        finally:
            if shutdown_needed:
                self.shutdown()
        
    def cleanup(self):
        try:
            self._play_shutdown_sound()
        except:
            pass
        with self.led.indicate("red"):
            if self.sdcard is not None:
                self.sdcard.spi.deinit()
            if self.audio_player is not None:
                self.audio_player.audio_out.deinit()

    def shutdown(self):
        try:
            self.cleanup()
        except Exception as e:
            logger.error(f"Couldn't shutdown SweetYaarDevice, forcing boot anyway...")
            sys.print_exception(e)

        finally: 
            machine.reset()

    def sleep(self):
        logger.info("Yaar doesn't want to play 😢 Going to sleep...")
        time.sleep_ms(20)  # Let broadcasting finish
        wakeup_pin = Pin(self.config["movement_sensor_gpio"], mode=Pin.IN, pull=Pin.PULL_DOWN)
        esp32.wake_on_ext0(pin=wakeup_pin, level=esp32.WAKEUP_ALL_LOW)
        machine.lightsleep()

    def reset(self):
        logger.info("Resetting device")
        machine.reset()

    def asyncio_exception_handler(self, loop, context):
        logger.error(f"An exception was caught in a co-routine: {context}")
        sys.print_exception(context["exception"])
        time.sleep_ms(20)
        self.shutdown()

    def _play_startup_sound(self):
        self.audio_player.play_file(self.audio_library.get_sound_filename("startup"))
    
    def _play_shutdown_sound(self):
        self.audio_player.play_file(self.audio_library.get_sound_filename("shutdown"))

    def _mount_sdcard(self):
        logger.info("Mounting SDCard...")
        if "spi" in self.config["sdcard"]:
            spi = SPI(self.config["sdcard"]["spi"])
        elif "soft_spi" in self.config["sdcard"]:
            spi = SoftSPI(
                sck=Pin(self.config["sdcard"]["soft_spi"]["SPI_SCK"]),
                mosi=Pin(self.config["sdcard"]["soft_spi"]["SPI_MOSI"]),
                miso=Pin(self.config["sdcard"]["soft_spi"]["SPI_MISO"]))
        else:
            raise ValueError("Must provide `spi` or `soft_spi` in sdcard config")
        self.sdcard = sdcard.SDCard(spi=spi, cs=Pin(self.config["sdcard"]["SPI_CS"], Pin.OUT))
        os.mount(self.sdcard, self.config["sdcard"]["mount_path"])

    def _init_components(self):
        # Initialize audio components
        self.audio_library = audio_library.AudioLibrary(self.config["audio_library"])
        self.audio_player = audio_player.AudioPlayer(self.config["audio_player"], preallocated_buffer=self._audio_player_file_buffer)

        ifaces = []

        gpio_iface = interfaces.GPIOInterface(cfg=self.config["interfaces"]["gpio"])
        ifaces.append(gpio_iface)

        if self.bluetooth_switch.value() == 1:
            logger.info("Bluetooth is on. Activating interface.")
            bt_iface = interfaces.BluetoothInterface(cfg=self.config["interfaces"]["bluetooth"])
            ifaces.append(bt_iface)
        else:
            logger.info("Bluetooth is off.")

        # Initialize controller and interfaces.
        self.controller = controller.SweetYaarController(self, active_interfaces=ifaces)

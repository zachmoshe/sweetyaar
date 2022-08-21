import init 

import json 
from machine import SoftSPI, SPI, Pin
import uasyncio as asyncio

from src import audio_library
from src import audio_player
from src import config
from src import controller
from src import interfaces 

cfg = config.get_config()

# device7221 = max7221.Max7221Device(cs=20, sck=21, mosi=19)
# pbar = max7221.Max7221RadialProgressBar(device7221, num_active_digits=5)
# wi = max7221.Max7221RadialWorkingIndicator(device7221, 6)

# async def f():
#     task = asyncio.create_task(wi.indicate_working(1))
#     await asyncio.sleep(5)
#     task.cancel()
#     wi.clear()
# asyncio.run(f())

al = audio_library.AudioLibrary(cfg["audio_library"])
ap = audio_player.AudioPlayer(cfg["audio_player"])

# Initialize controller and interfaces
ctl = controller.SweetYaarController(cfg=cfg["controller"], audio_library=al, audio_player=ap)
gpio_iface = interfaces.GPIOInterface(cfg=cfg["interfaces"]["gpio"])
ctl.register_interface(gpio_iface)


print("controller is taking control")
ctl.take_control()
print("controller returned control")

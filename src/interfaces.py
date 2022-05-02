import asyncio
import functools as ft
import logging
import random
import sys
import threading 

import aiohttp.web
import aiohttp_jinja2
import jinja2
from RPi import GPIO

import controller


def _load_actions_mapping(actions_mapping):
    # Checks that all actions are valid. Returns a dictionary from input to Action enum 
    output = {}
    for action_str, input_str in actions_mapping.items():
        output[input_str] = controller.Actions[action_str]  # Will throw a KeyError if no such action_str in Actions.
    return output


class GPIOInterface:
    def __init__(self, config):
        self._gpio_mode = config["gpio_mode"]
        if self._gpio_mode not in ("BCM", "BOARD"):
            raise ValueError(f"Unknown `gpio_mode` in config ({self._gpio_mode}). Must be 'BCM' or 'BOARD'.")
        self._animal_button_gpio_channel = config["animal_button_gpio_channel"]
        self._songs_button_gpio_channel = config["songs_button_gpio_channel"]
        self._button_debounce_ms = config["button_debounce_ms"]

    def listen(self, callback_func, get_stats_func):
        del get_stats_func  # Unused.
        callback_func = ft.partial(callback_func, interface=self)

        async def _listen():
            loop = asyncio.get_event_loop()
            def button_pressed(channel):
                action = self._get_action()
                logging.info(f"GPIO button pressed (channel={channel}). Detected action is {action}.")
                if action is None: 
                    logging.error("Shouldn't be here. No button is marked as pressed although the GPIO callback was called.")
                    return
                loop.call_soon_threadsafe(lambda: callback_func(action))

            # Setup GPIO and input pins
            GPIO.setmode(GPIO.BOARD if self._gpio_mode == "BOARD" else GPIO.BCM)

            GPIO.setup(self._animal_button_gpio_channel, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            GPIO.setup(self._songs_button_gpio_channel, GPIO.IN, pull_up_down=GPIO.PUD_UP)

            GPIO.add_event_detect(self._animal_button_gpio_channel, GPIO.FALLING, button_pressed, bouncetime=self._button_debounce_ms)
            GPIO.add_event_detect(self._songs_button_gpio_channel, GPIO.FALLING, button_pressed, bouncetime=self._button_debounce_ms)
            while True:
                await asyncio.sleep(1)

        asyncio.create_task(_listen())


    def _get_action(self):
        # Since pins are PUD_UP, if input is 0 that means it's pressed.
        animal_pressed = GPIO.input(self._animal_button_gpio_channel) == 0
        songs_pressed = GPIO.input(self._songs_button_gpio_channel) == 0

        if animal_pressed and songs_pressed: 
            return controller.Actions.STOP
        elif animal_pressed:
            return controller.Actions.PLAY_RANDOM_ANIMAL_SOUND
        elif songs_pressed:
            return controller.Actions.PLAY_RANDOM_SONG
        else:
            return None


class WebInterface:
    def __init__(self, config):
        self._host = config["host"]
        self._port = int(config["port"])
        self._actions_mapping = _load_actions_mapping(config["actions_mapping"])
        self._random_backgrounds = config["random_backgrounds"]

    def _get_random_background_wide_narrow(self):
        backgrounds = random.choice(self._random_backgrounds)
        if isinstance(backgrounds, (list, tuple)):
            return backgrounds[:2]  # Should be only 2 elements there...
        else:
            return backgrounds, backgrounds  # Use same image for wide and narrow
        
    def listen(self, callback_func, get_stats_func):
        callback_func = ft.partial(callback_func, interface=self)

        routes = aiohttp.web.RouteTableDef()
        
        @routes.get("/")
        @aiohttp_jinja2.template("index.html")
        async def index(request):
            background_wide, background_narrow = self._get_random_background_wide_narrow()
            return dict(**get_stats_func(), background_wide=background_wide, background_narrow=background_narrow)

        @routes.post("/actions/{action}")
        async def actions(request):
            action = request.match_info["action"]
            if action not in self._actions_mapping:
                logging.warn(f"Unknown HTTP action: {action!r}. Ignoring.")
            else:
                callback_func(self._actions_mapping[action])
            raise aiohttp.web.HTTPFound("/")  # Reload the main page.

        @routes.get("/stats")
        def stats(self):
            return aiohttp.web.json_response(get_stats_func())

        app = aiohttp.web.Application()
        aiohttp_jinja2.setup(app,
            loader=jinja2.FileSystemLoader("src/templates"))

        app.router.add_routes(routes)
        app.router.add_static("/static/",
                          path="src/templates/static",
                          show_index=True)

        async def start_server():
            runner = aiohttp.web.AppRunner(app)
            await runner.setup()
            site = aiohttp.web.TCPSite(runner, self._host, self._port)
            await site.start()

        loop = asyncio.get_event_loop()
        loop.create_task(start_server())
        

class KeyboardInterface:
    def __init__(self, config):
        self._actions_mapping = _load_actions_mapping(config["actions_mapping"])
        
    def listen(self, callback_func, get_stats_func):
        del get_stats_func  # Unused.
        callback_func = ft.partial(callback_func, interface=self)
        
        async def _listen():
            loop = asyncio.get_event_loop()
            reader = asyncio.StreamReader()
            protocol = asyncio.StreamReaderProtocol(reader)
            await loop.connect_read_pipe(lambda: protocol, sys.stdin)
            
            while True:
                line = await reader.readline()
                line = line.strip().decode()

                if not line:
                    break
                elif line not in self._actions_mapping:
                    logging.debug(f"Unknown keyboard input: {line!r}. Ignoring.")
                else:
                    callback_func(self._actions_mapping[line])
        
        asyncio.create_task(_listen())


_INTERFACES = {
    "keyboard": KeyboardInterface,
    "web": WebInterface,
    "gpio": GPIOInterface,
}
def get_interface_class(name):
    return _INTERFACES[name]

import asyncio
import functools as ft
import logging
import sys
import threading 

import aiohttp.web
import aiohttp_jinja2
import jinja2

import controller

def _load_actions_mapping(actions_mapping):
    # Checks that all actions are valid. Returns a dictionary from input to Action enum 
    output = {}
    for action_str, input_str in actions_mapping.items():
        output[input_str] = controller.Actions[action_str]  # Will throw a KeyError if no such action_str in Actions.
    return output


class WebInterface:
    def __init__(self, config):
        self._host = config["host"]
        self._port = int(config["port"])
        self._actions_mapping = _load_actions_mapping(config["actions_mapping"])

    def listen(self, callback):
        callback = ft.partial(callback, interface=self)

        routes = aiohttp.web.RouteTableDef()
        
        @routes.get("/")
        @aiohttp_jinja2.template("index.html")
        async def index(request):
            return {}

        @routes.post("/actions/{action}")
        async def actions(request):
            action = request.match_info["action"]
            if action not in self._actions_mapping:
                logging.warn(f"Unknown HTTP action: {action!r}. Ignoring.")
            else:
                callback(self._actions_mapping[action])
            return aiohttp.web.Response(status=200)

        app = aiohttp.web.Application()
        aiohttp_jinja2.setup(app,
            loader=jinja2.FileSystemLoader("src/templates"))

        app.router.add_routes(routes)
        app.router.add_static("/static/",
                          path="src/templates/static",
                          name="static")

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
        
    def listen(self, callback):
        callback = ft.partial(callback, interface=self)
        
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
                    callback(self._actions_mapping[line])
        
        asyncio.create_task(_listen())


_INTERFACES = {
    "keyboard": KeyboardInterface,
    "web": WebInterface,
}
def get_interface_class(name):
    return _INTERFACES[name]

import asyncio
import enum
import logging
import time 

import audio_library
import interfaces


class Actions(enum.Enum):
    PLAY_RANDOM_ANIMAL_SOUND = enum.auto()
    PLAY_RANDOM_SONG = enum.auto()
    VOLUME_UP = enum.auto()
    VOLUME_DOWN = enum.auto()
    STOP = enum.auto()
    KILL_SWITCH = enum.auto()
    REBOOT = enum.auto()


class SweetYaarController:

    def __init__(self, config):
        self._audio_lib = audio_library.AudioLibrary(config["audio"])
        self.default_starting_volume = config.get("default_starting_volume", 70)
        logging.debug(f"Setting default starting volume to {self.default_starting_volume}")
        self._audio_lib.set_volume(self.default_starting_volume)

        # Start all interfaces 
        self._interfaces = []
        ifaces = config["interfaces"] or {}
        for interface_name, interface_config in ifaces.items():
            i = interfaces.get_interface_class(interface_name)(interface_config)
            self._interfaces.append(i)

        self._should_run = True
        self._kill_switch_inactive_time_secs = config["kill_switch_inactive_time_secs"]
        self._last_kill_switch_time = 0


    def handle_action(self, action: Actions, interface):
        logging.info(f"Received {action} from {interface}")
        if action == Actions.PLAY_RANDOM_ANIMAL_SOUND:
            self.play_random_animal_sound()
        elif action == Actions.PLAY_RANDOM_SONG:
            self.play_random_song()
        elif action == Actions.STOP:
            self.stop_playing()
        elif action == Actions.KILL_SWITCH:
            self.kill_switch()
        elif action == Actions.REBOOT:
            self.stop_control()
        elif action == Actions.VOLUME_UP:
            self.increase_volume()
        elif action == Actions.VOLUME_DOWN:
            self.decrease_volume()
        else:
            raise RuntimeError("can't be here. no other values in enum.")


    async def _main_loop(self):
        logging.info("Starting all interfaces.")
        for iface in self._interfaces:
            iface.listen(self.handle_action)

        while self._should_run:
            await asyncio.sleep(1)


    def take_control(self):
        logging.info("Taking control.")
        asyncio.run(self._main_loop(), debug=False)
        logging.info("Controller exited. Returning control to main().")

    def _is_kill_switch_activated(self):
        return time.time() < self._last_kill_switch_time + self._kill_switch_inactive_time_secs

    def play_random_animal_sound(self):
        logging.info("A random animal sound was requested.")
        if self._is_kill_switch_activated():
            logging.info("Ignoring. Kill switch is active.")
            return
        self._audio_lib.play_random_animal_sound()
    
    def play_random_song(self):
        logging.info("A random song was requested.")
        if self._is_kill_switch_activated():
            logging.info("Ignoring. Kill switch is active.")
            return
        self._audio_lib.play_random_song()

    def stop_playing(self):
        logging.info("Stop playing was requested.")
        self._audio_lib.stop_audio()

    def increase_volume(self):
        logging.info("Increasing volume")
        self._audio_lib.increase_volume()

    def decrease_volume(self):
        logging.info("Decreasing volume")
        self._audio_lib.decrease_volume()

    def kill_switch(self):
        self._audio_lib.stop_audio()
        self._last_kill_switch_time = time.time()

    def stop_control(self):
        logging.info("Controller was requested to stop control.")
        self._should_run = False
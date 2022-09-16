from machine import Pin
import uasyncio as asyncio
import time

from src import audio_player
from . import bt_logger

logger = bt_logger.get_logger(__name__)



class Actions:
    # No enums in micropython...
    PLAY_SONG = 1
    PLAY_ANIMAL_SOUND = 2
    STOP_PLAYING = 3
    KILL_SWITCH = 4
    FORCE_DAYTIME = 10
    FORCE_NIGHTTIME = 11


class DaytimeModeManager:
    def __init__(self, ctl, daytime_range):
        self.ctl = ctl
        # daytime_range is a list of 2 strings representing the start and end of the daytime (HH:MM). e.g. ["06:30", "18:45"]
        self._daytime_range = self._parse_daytime_range(daytime_range)
        self._daytime_override = ()

    @staticmethod
    def _parse_daytime_range(daytime_range):
        if len(daytime_range) != 2 or set(type(x) for x in daytime_range) != {str}:
            raise ValueError(f"Illegal daytime range '{daytime_range}'. Should be two string values (e.g. ['06:00', '18:00']")
        
        daytime_range_ints = [[int(x) for x in hour_str.split(":")] for hour_str in daytime_range]
        return [r[0] * 60 + r[1] for r in daytime_range_ints]
    
    @staticmethod
    def _get_total_minutes():
        _, _, _, hours, minutes, _, _, _ = time.localtime()
        return hours * 60 + minutes

    def get_daytime_mode(self):
        # Check for override.
        localtime = time.localtime()
        current_date = localtime[:3]
        if self._daytime_override and self._daytime_override[0] == current_date:
            return self._daytime_override[1]
        
        # Calculate by daytime_range.
        is_daytime = self._daytime_range[0] <= self._get_total_minutes() < self._daytime_range[1]
        return "daytime" if is_daytime else "nighttime"

    def override_daytime_mode(self, value):
        assert value in ("daytime", "nighttime")
        self._daytime_override = (time.localtime()[:3], value)
        self.publish_daytime_mode()

    def publish_daytime_mode(self):
        self.ctl.update_controller_state({"daytime_mode": self.get_daytime_mode()})

    async def constantly_publish_daytime_mode(self):
        self.publish_daytime_mode()

        while True:
            mins_to_next_switch = (
                (self._daytime_range[1] - self._get_total_minutes()) % (24 * 60)
                if self.get_daytime_mode() == "daytime"
                else (self._daytime_range[0] - self._get_total_minutes()) % (24 * 60)
            )
            await asyncio.sleep(mins_to_next_switch * 60 + 1)
            self.publish_daytime_mode()


class SweetYaarController:
    def __init__(self, cfg, audio_library, audio_player):
        self.audio_library = audio_library
        self.audio_player = audio_player
        self.audio_player.register_activity_callback(self._audio_activity_callback)
        self.currently_playing_desc = ""
        self._kill_switch_inactive_time_secs = cfg["kill_switch_inactive_time_secs"]
        self._last_kill_switch_time = 0
        self.daytime_manager = DaytimeModeManager(self, cfg["daytime_range"])

        self.interfaces = []
        self.controller_state_updates_listeners = []

        asyncio.create_task(self.daytime_manager.constantly_publish_daytime_mode())

    def register_interface(self, iface):
        # Should be called before taking control.
        self.interfaces.append(iface)

    def register_controller_state_update_listener(self, callback_func):
        self.controller_state_updates_listeners.append(callback_func)

    def update_controller_state(self, state_update):
        for l in self.controller_state_updates_listeners:
            l(state_update)

    def _is_kill_switch_activated(self):
        return time.time() < self._last_kill_switch_time + self._kill_switch_inactive_time_secs

    def _audio_activity_callback(self, event, *args):
        if event == audio_player.EVENT_AUDIO_FINISHED:
            self.currently_playing_desc = ""
            self.update_controller_state({"currently_playing": self.currently_playing_desc})
        elif event == audio_player.EVENT_AUDIO_STARTED:
            self.currently_playing_desc = args[0]
            self.update_controller_state({"currently_playing": self.currently_playing_desc})


    async def _publish_kill_switch_counter(self):
        while self._is_kill_switch_activated():
            ctr = self._kill_switch_inactive_time_secs - (time.time() - self._last_kill_switch_time)
            self.update_controller_state({"kill_switch_counter": ctr})
            await asyncio.sleep(1)
        # Make sure we always reset the GUI (sending 0)
        self.update_controller_state({"kill_switch_counter": 0})

    def _play_startup_sound(self):
        self.audio_player.play_file(self.audio_library.get_sound_filename("startup"))
    
    def _play_shutdown_sound(self):
        self.audio_player.play_file(self.audio_library.get_sound_filename("shutdown"))

    async def _main_loop(self):
        try:
            self._play_startup_sound()
            ifaces_tasks = [
                asyncio.create_task(iface.listen(self.handle_action))
                for iface in self.interfaces
            ]
            await asyncio.gather(*ifaces_tasks)
            
        except Exception as e:
            logger.error(f"Controller caught exception: {repr(e)}")
            raise e

        finally:
            self._play_shutdown_sound()
        
    def take_control(self):
        try:
            asyncio.run(self._main_loop())
        except KeyboardInterrupt:
            pass


    def handle_action(self, action):
        if action == Actions.PLAY_SONG:
            self._play_song()
        elif action == Actions.PLAY_ANIMAL_SOUND:
            self._play_animal_sound()
        elif action == Actions.STOP_PLAYING:
            self._stop_playing()
        elif action == Actions.KILL_SWITCH:
            self._activate_kill_switch()
        elif action == Actions.FORCE_DAYTIME:
            self.force_daytime_mode("daytime")
        elif action == Actions.FORCE_NIGHTTIME:
            self.force_daytime_mode("nighttime")
        else:
            logger.error(f"Unknown action {action}")

    def _play_sound_file(self, type, sound_name, sound_path):
        if self._is_kill_switch_activated():
            return
        icon = "♫" if type == "song" else "🐶" if type == "animal" else ""
        desc = f"{icon} {sound_name}"  # Notice that an update will be sent to listeners only when audio is really played.
        self.audio_player.play_file(sound_path, desc)

    def _play_song(self):
        if self._is_kill_switch_activated():
            logger.info("Kill-switch is activated. Ignoring play song request.")
            return
        song_name, song_path = self.audio_library.get_random_song(mode=self.daytime_manager.get_daytime_mode())
        logger.info(f"Playing song: {song_name}")
        self._play_sound_file("song", song_name, song_path)

    def _play_animal_sound(self):
        if self._is_kill_switch_activated():
            logger.info("Kill-switch is activated. Ignoring play animal sound request.")
            return
        animal_name, animal_path = self.audio_library.get_random_animal_sound()
        logger.info(f"Playing animal: {animal_name}")
        self._play_sound_file("animal", animal_name, animal_path)

    def _stop_playing(self):
        logger.info("Stop playing.")
        self.audio_player.stop()

    def _activate_kill_switch(self):
        logger.info("Kill-switch activated.")
        self._stop_playing()
        self._last_kill_switch_time = time.time()
        asyncio.create_task(self._publish_kill_switch_counter())

    def force_daytime_mode(self, value):
        assert value in ("daytime", "nighttime")
        logger.info(f"Forcing {value} mode.")
        self.daytime_manager.override_daytime_mode(value)
from machine import Pin
import uasyncio as asyncio
import time

from src import audio_player


class Actions:
    # No enums in micropython...
    PLAY_SONG = 1
    PLAY_ANIMAL_SOUND = 2
    STOP_PLAYING = 3
    KILL_SWITCH = 4


class SweetYaarController:
    def __init__(self, cfg, audio_library, audio_player):
        self.audio_library = audio_library
        self.audio_player = audio_player
        self.audio_player.register_activity_callback(self._audio_activity_callback)
        self.currently_playing_desc = ""
        self._kill_switch_inactive_time_secs = cfg["kill_switch_inactive_time_secs"]
        self._last_kill_switch_time = 0
        self.interfaces = []

        self.controller_state_updates_listeners = []

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
            print("Controller caught exception: ", e)
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
        else:
            print("[CTL] !!! Unknown action ", action)

    def _play_sound_file(self, type, sound_name, sound_path):
        if self._is_kill_switch_activated():
            return
        icon = "♫" if type == "song" else "🐶" if type == "animal" else ""
        desc = f"{icon} {sound_name}"  # Notice that an update will be sent to listeners only when audio is really played.
        self.audio_player.play_file(sound_path, desc)

    def _play_song(self):
        if self._is_kill_switch_activated():
            return
        song_name, song_path = self.audio_library.get_random_song(mode=None)  # automatically choose mode by time of day.
        self._play_sound_file("song", song_name, song_path)

    def _play_animal_sound(self):
        if self._is_kill_switch_activated():
            return
        animal_name, animal_path = self.audio_library.get_random_animal_sound()
        self._play_sound_file("animal", animal_name, animal_path)

    def _stop_playing(self):
        self.audio_player.stop()

    def _activate_kill_switch(self):
        self._stop_playing()
        self._last_kill_switch_time = time.time()
        asyncio.create_task(self._publish_kill_switch_counter())
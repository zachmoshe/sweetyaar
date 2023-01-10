import machine
from machine import Pin
import time
import uasyncio as asyncio

from src import audio_player
from src import bt_logger

_logger = bt_logger.get_logger(__name__)



class Actions:
    # No enums in micropython...
    PLAY_SONG = 1
    PLAY_ANIMAL_SOUND = 2
    STOP_PLAYING = 3
    KILL_SWITCH = 4

    CHANGE_PLAYLIST = 10
    VOLUME_UP = 12
    VOLUME_DOWN = 13

    RESET_DEVICE = 20
    DEVICE_TIME_CHANGED = 21


class PlaylistsManager:
    def __init__(self, ctl, daytime_range):
        self.ctl = ctl
        # daytime_range is a list of 2 strings representing the start and end of the daytime (HH:MM). e.g. ["06:30", "18:45"]
        self._daytime_range = self._parse_daytime_range(daytime_range)
        self._playlist_override = ()

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

    def get_current_playlist_name(self):
        # Check for override.
        localtime = time.localtime()
        current_date = localtime[:3]
        if self._playlist_override and self._playlist_override[0] == current_date:
            return self._playlist_override[1]
        
        # Calculate by daytime_range.
        is_daytime = self._daytime_range[0] <= self._get_total_minutes() < self._daytime_range[1]
        return "daytime" if is_daytime else "nighttime"

    def change_playlist(self, playlist_name):
        self._playlist_override = (time.localtime()[:3], playlist_name)
        self.publish_current_playlist()
        self.ctl._set_volume_by_playlist()

    def publish_current_playlist(self):
        self.ctl.update_controller_state({"change_playlist": self.get_current_playlist_name()})

    async def constantly_publish_current_playlist(self):
        self.publish_current_playlist()

        while True:
            mins_to_next_switch = min(
                (change_total_minutes - self._get_total_minutes()) % (24 * 60)
                for change_total_minutes in self._daytime_range)
            await asyncio.sleep(mins_to_next_switch * 60 + 1)
            self.publish_current_playlist()


# Empirically calculated. 
# Represnets internal bins boundaries. Anything below first value will be 0 and above last value will be 100.
_VOLTAGE_PERCENTILES = [4.42311955, 4.77237425, 4.82744094, 4.92763572] 
_VOLTAGE_BINS = [0, 25, 50, 75, 100]

class BatteryMonitor:
    def __init__(self, ctl, adc_pin, decay_factor):
        self.ctl = ctl
        self.adc = machine.ADC(machine.Pin(adc_pin))
        self.adc.atten(machine.ADC.ATTN_11DB)
        self.current_decayed_voltage = None
        self.decay_factor = decay_factor

    def _update_decayed_voltage(self):
        read_uv = self.adc.read_uv()
        voltage = 2 * read_uv * 1e-6  # Voltage is divided by 2x10Kohm resistors and measured in microvolts by read_uv().
        if self.current_decayed_voltage is None:
            self.current_decayed_voltage = voltage
        else:
            self.current_decayed_voltage = self.decay_factor * self.current_decayed_voltage + (1 - self.decay_factor) * voltage

    @property
    def voltage_pctl(self):
        value_index = sum(self.current_decayed_voltage >= v for v in _VOLTAGE_PERCENTILES)
        return _VOLTAGE_BINS[value_index]

    async def monitor_battery_voltage(self):
        while True:
            self._update_decayed_voltage()
            self.ctl.update_controller_state({"battery": self.voltage_pctl})
            await asyncio.sleep(60)


class SweetYaarController:

    def __init__(self, device, active_interfaces):
        self.device = device
        self.interfaces = active_interfaces
        self.controller_state_updates_listeners = []

        cfg = device.config["controller"]
        self.device.audio_player.register_activity_callback(self._audio_activity_callback)
        self.update_controller_state({"update_playlists": dict(zip(self.device.audio_library.playlists_names, self.device.audio_library.playlists_repr_names))})
        
        self.currently_playing_desc = ""
        self._kill_switch_inactive_time_secs = cfg["kill_switch_inactive_time_secs"]
        self._sleep_inactivity_threshold_secs = cfg["sleep_inactivity_threshold_secs"]
        self.playlists_manager = PlaylistsManager(self, cfg["daytime_range"])
        self._last_kill_switch_time = None
        self._last_action_ticks_time = time.ticks_ms()
        
        self._max_volume = cfg["volume_max_value"]  # volume is a 0..(_max_volume) integer.
        self._zero_volume = cfg["volume_zero_value"]  # the value that causes no shift in samples.
        self._default_daytime_nighttime_volumes = (cfg["default_daytime_volume"], cfg["default_nighttime_volume"])
        self._current_volume = None  # will track the volume.
        
        self.battery_monitor = BatteryMonitor(self, cfg["battery_adc_gpio"], cfg["battery_decay_factor"])

        self._publish_playlists_task = None
        self._restart_publish_current_playlist_task()
        asyncio.create_task(self.monitor_inactivity_threshold())
        asyncio.create_task(self.battery_monitor.monitor_battery_voltage())
        self._set_volume_by_playlist()

    def _restart_publish_current_playlist_task(self):
        if self._publish_playlists_task is not None:
            self._publish_playlists_task.cancel()
        self._publish_playlists_task = asyncio.create_task(self.playlists_manager.constantly_publish_current_playlist())

    def update_controller_state(self, state_update):
        for iface in self.interfaces:
            if hasattr(iface, "handle_controller_event"):
                iface.handle_controller_event(state_update)

    @property
    def kill_switch_counter_secs(self):
        if self._last_kill_switch_time is None:
            return None
        else:
            diff_from_last_kill_switch = int(time.ticks_diff(time.ticks_ms(), self._last_kill_switch_time) / 1000)
            if diff_from_last_kill_switch > self._kill_switch_inactive_time_secs:
                return None
            else:
                return self._kill_switch_inactive_time_secs - diff_from_last_kill_switch

    @property
    def time_from_last_activity_secs(self):
        return int(time.ticks_diff(time.ticks_ms(), self._last_action_ticks_time) / 1000)

    def update_activity(self):
        self._last_action_ticks_time = time.ticks_ms()

    def _should_sleep(self):
        return self.time_from_last_activity_secs > self._sleep_inactivity_threshold_secs

    def _is_kill_switch_activated(self):
        return self.kill_switch_counter_secs is not None

    def _audio_activity_callback(self, event, *args):
        self.currently_playing_desc = (
            "" if event == audio_player.EVENT_AUDIO_FINISHED
            else args[0])
        self.update_controller_state({"currently_playing": self.currently_playing_desc})

    async def _publish_kill_switch_counter(self):
        while self._is_kill_switch_activated():
            self.update_controller_state({"kill_switch_counter": self.kill_switch_counter_secs})
            await asyncio.sleep(1)
        # Make sure we always reset the GUI (sending 0)
        self.update_controller_state({"kill_switch_counter": 0})

    async def monitor_inactivity_threshold(self):
        while True:
            if self._should_sleep():
                self.device.sleep()
            await asyncio.sleep(60)  # Check again after a minute.

    async def _main_loop(self):
        ifaces_tasks = [
            asyncio.create_task(iface.listen(self.handle_action))
            for iface in self.interfaces
        ]
        await asyncio.gather(*ifaces_tasks)
        
    def take_control(self):
        asyncio.run(self._main_loop())

    def handle_action(self, action, payload=None):
        self.update_activity()
        if action == Actions.PLAY_SONG:
            self._play_song()
        elif action == Actions.PLAY_ANIMAL_SOUND:
            self._play_animal_sound()
        elif action == Actions.STOP_PLAYING:
            self._stop_playing()
        elif action == Actions.KILL_SWITCH:
            self._activate_kill_switch()
        elif action == Actions.CHANGE_PLAYLIST:
            self._change_playlist(payload)
        elif action == Actions.VOLUME_UP:
            self._increase_volume()
        elif action == Actions.VOLUME_DOWN:
            self._decrease_volume()
        elif action == Actions.RESET_DEVICE:
            self.device.reset()
        elif action == Actions.DEVICE_TIME_CHANGED:
            self._restart_publish_current_playlist_task()
        else:
            _logger.error(f"Unknown action {action}")

    def _play_sound_file(self, type, sound_name, sound_path):
        if self._is_kill_switch_activated():
            return
        icon = "♫" if type == "song" else "🐶" if type == "animal" else ""
        desc = f"{icon} {sound_name}"  # Notice that an update will be sent to listeners only when audio is really played.
        self.device.audio_player.play_file(sound_path, desc)

    def _play_song(self):
        if self._is_kill_switch_activated():
            _logger.info("Kill-switch is activated. Ignoring play song request.")
            return
        song_name, song_path = self.device.audio_library.get_random_song(playlist_name=self.playlists_manager.get_current_playlist_name())
        self._play_sound_file("song", song_name, song_path)

    def _play_animal_sound(self):
        if self._is_kill_switch_activated():
            _logger.info("Kill-switch is activated. Ignoring play animal sound request.")
            return
        animal_name, animal_path = self.device.audio_library.get_random_animal_sound()
        _logger.info(f"Playing animal: {animal_name}")
        self._play_sound_file("animal", animal_name, animal_path)

    def _stop_playing(self):
        _logger.info("Stop playing.")
        self.device.audio_player.stop()

    def _activate_kill_switch(self):
        _logger.info("Kill-switch activated.")
        self._stop_playing()
        self._last_kill_switch_time = time.ticks_ms()
        asyncio.create_task(self._publish_kill_switch_counter())

    def _change_playlist(self, playlist_name):
        assert playlist_name in self.device.audio_library.playlists_names
        _logger.info(f"Changing playlist to {playlist_name}.")
        self.playlists_manager.change_playlist(playlist_name)

    def _increase_volume(self):
        _logger.info(f"Increasing volume.")
        self._current_volume = min(self._max_volume, self._current_volume + 1)
        self._update_audio_player_volume()

    def _decrease_volume(self):
        _logger.info(f"Decreasing volume.")
        self._current_volume = max(0, self._current_volume - 1)
        self._update_audio_player_volume()

    def _set_volume_by_playlist(self):
        playlist_name = self.playlists_manager.get_current_playlist_name()
        self._current_volume = self._default_daytime_nighttime_volumes[1 if playlist_name == "nighttime" else 0]
        self._update_audio_player_volume()

    def _update_audio_player_volume(self):
        shift = (self._current_volume - self._zero_volume
                 if self._current_volume > 0  # None will turn off audio playing completely.
                 else None)
        self.device.audio_player.volume = shift
        print("current volume - ", self.volume, shift)
        self.update_controller_state({"volume": self.volume})

    @property
    def volume(self):
        return int(100 * self._current_volume / self._max_volume)
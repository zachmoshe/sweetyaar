import asyncio
import datetime 
import enum
import logging
import pathlib
import random
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
    OVERRIDE_DAYTIME = enum.auto()
    OVERRIDE_NIGHTTIME = enum.auto()


def _parse_glob_expressions(glob_expressions):
    return list(
        song_filename 
        for g in glob_expressions
        for song_filename in pathlib.Path().glob(g))

def _pick_random(audio_list, last_played):
    # pick a random one but not the last one (if len(_songs) > 1)
    valid_songs = [x for x in audio_list if len(audio_list) == 1 or last_played is None or x != last_played]
    random_filename = random.choice(valid_songs)
    return random_filename


class SweetYaarController:

    def __init__(self, config):
        default_starting_volume = config["default_starting_volume"]
        self._time_of_day_cutoff = time.strptime(config["nighttime_cutoff"], "%H:%M")
        self._override_daytime_date = None
        self._override_nighttime_date = None

        self._daytime_songs = _parse_glob_expressions(config["daytime_songs"])
        self._nighttime_songs = _parse_glob_expressions(config["nighttime_songs"])
        self._yaar_callings = _parse_glob_expressions(config["animals"]["yaar_callings"])
        self._animals = _parse_glob_expressions(config["animals"]["animals_sounds"])
        if not self._daytime_songs:
            raise ValueError("parsed daytime songs list is empty.")
        if not self._nighttime_songs:
            raise ValueError("parsed nighttime songs list is empty.")
        if not self._yaar_callings:
            raise ValueError("parsed yaar_callings list is empty.")
        if not self._animals:
            raise ValueError("parsed animal_sounds list is empty.")

        self._last_played_song = None
        self._last_played_animal = None

        self._audio_lib = audio_library.AudioLibrary(config["audio"])
        logging.debug(f"Setting default starting volume to {default_starting_volume}")
        self._audio_lib.set_volume(default_starting_volume)

        # Start all interfaces 
        self._interfaces = []
        ifaces = config["interfaces"] or {}
        for interface_name, interface_config in ifaces.items():
            i = interfaces.get_interface_class(interface_name)(interface_config)
            self._interfaces.append(i)

        self._should_run = True
        self._kill_switch_inactive_time_secs = config["kill_switch_inactive_time_secs"]
        self._last_kill_switch_time = 0

    def get_stats(self):
        currently_playing = self._audio_lib.get_currently_playing_filename()
        currently_playing = pathlib.Path(currently_playing).name if currently_playing is not None else None

        kill_switch_until = (time.strftime('%H:%M:%S', time.localtime(self._last_kill_switch_time + self._kill_switch_inactive_time_secs))
                             if self._is_kill_switch_activated() else None)
        
        return {
            "volume_level": self._audio_lib.get_volume(),
            "battery_level": "N/A",
            "currently_playing": currently_playing,
            "kill_switch_until": kill_switch_until,
            "time_of_day": self._detect_time_of_day(),
        }

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
        elif action == Actions.OVERRIDE_DAYTIME:
            self.override_daytime()
        elif action == Actions.OVERRIDE_NIGHTTIME:
            self.override_nighttime()
        else:
            raise RuntimeError("can't be here. no other values in enum.")


    async def _main_loop(self):
        logging.info("Starting all interfaces.")
        for iface in self._interfaces:
            iface.listen(self.handle_action, self.get_stats)

        self._audio_lib.play_startup_sound()
        try:
            while self._should_run:
                await asyncio.sleep(1)
        except Exception as e:
            logging.warn(f"Caught {e} during main loop. Exiting...")
        finally:
            self._audio_lib.play_shutdown_sound()
            await asyncio.sleep(2)


    def take_control(self):
        logging.info("Taking control.")
        try:
            asyncio.run(self._main_loop(), debug=False)
        except KeyboardInterrupt:
            pass  # Just exit. No need to print the exception.
        logging.info("Controller exited. Returning control to main().")

    def _is_kill_switch_activated(self):
        return time.time() < self._last_kill_switch_time + self._kill_switch_inactive_time_secs

    def _detect_time_of_day(self):
        today = datetime.date.today()
        if self._override_daytime_date == today:
            return "daytime"
        elif self._override_nighttime_date == today:
            return "nighttime"
        else:
            _, _, _, hour, minute, _, _, _, _ = time.localtime()
            _, _, _, cutoff_hour, cutoff_minute, _, _, _, _ = self._time_of_day_cutoff
            return ("daytime" if hour < cutoff_hour or (hour == cutoff_hour and minute <= cutoff_minute)
                    else "nighttime")

    def _get_songs_list(self):
        # Based on daytime/nighttime configuration
        if self._detect_time_of_day() == "daytime":
            return self._daytime_songs
        else:
            return self._nighttime_songs

    def play_random_animal_sound(self):
        logging.info("A random animal sound was requested.")
        if self._is_kill_switch_activated():
            logging.info("Ignoring. Kill switch is active.")
            return
        random_animal_filename = _pick_random(self._animals, self._last_played_animal)
        # last_played is by the animal. The calling will be randomly chosen regardless.
        self._last_played_animal = random_animal_filename
        random_calling_filename = random.choice(self._yaar_callings)
        self._audio_lib.play_random_animal_sound(random_animal_filename, random_calling_filename)
    
    def play_random_song(self):
        logging.info("A random song was requested.")
        if self._is_kill_switch_activated():
            logging.info("Ignoring. Kill switch is active.")
            return
        random_filename = _pick_random(self._get_songs_list(), self._last_played_song)
        self._last_played_song = random_filename
        self._audio_lib.play_random_song(random_filename)

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

    def override_daytime(self):
        self._override_daytime_date = datetime.date.today()
        self._override_nighttime_date = None
    
    def override_nighttime(self):
        self._override_daytime_date = None
        self._override_nighttime_date = datetime.date.today()
    
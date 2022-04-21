import asyncio
from asyncio import subprocess
import logging
import pathlib
import random 

import alsaaudio


APLAY_BINARY = "aplay"

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


class AudioLibrary:
    def __init__(self, config):
        self._songs = _parse_glob_expressions(config["songs"])
        self._last_played_song = None

        self._yaar_callings = _parse_glob_expressions(config["animals"]["yaar_callings"])
        self._animals = _parse_glob_expressions(config["animals"]["animals_sounds"])
        self._last_played_animal = None

        self._currently_playing_task = None
        self._currently_playing_filename = None

        if not self._songs:
            raise ValueError("parsed songs list is empty.")
        if not self._yaar_callings:
            raise ValueError("parsed yaar_callings list is empty.")
        if not self._animals:
            raise ValueError("parsed animal_sounds list is empty.")

        self.mixer = alsaaudio.Mixer(control="Master")
        self.volume_step = config.get("volume_step", 10)

    def get_currently_playing_filename(self):
        return self._currently_playing_filename

    async def _play_sound_file(self, filename):
        logging.debug(f"playing {filename}")
        proc = None
        try:
            self._currently_playing_filename = filename
            proc = await asyncio.create_subprocess_exec(APLAY_BINARY, filename)
            await proc.wait()
            logging.debug(f"finished playing {filename} normally")
        except asyncio.CancelledError as e:
            logging.debug(f"interrupted playing {filename}")
            raise
        except Exception as e:
            logging.error("Unexpected error while playing.")
            logging.exception(e)
            raise
        finally:
            self._currently_playing_filename = None
            if proc is not None:
                proc.kill()

    async def _play_animal(self, animal_sound_filename, calling_filename):
        logging.debug(f"playing {animal_sound_filename} with calling {calling_filename}")
        calling_proc = None
        animal_proc = None
        try:
            self._currently_playing_filename = animal_sound_filename
            calling_proc = await asyncio.create_subprocess_exec(APLAY_BINARY, calling_filename)
            await calling_proc.wait()
            animal_proc = await asyncio.create_subprocess_exec(APLAY_BINARY, animal_sound_filename)
            await animal_proc.wait()
            logging.debug(f"finished playing {animal_sound_filename} normally")
        except asyncio.CancelledError:
            logging.debug(f"interrupted playing {animal_sound_filename}")
            raise
        finally:
            self._currently_playing_filename = None
            if calling_proc is not None:
                calling_proc.kill()
            if animal_proc is not None:
                animal_proc.kill()


    def play_startup_sound(self):
        self.stop_audio()
        self._currently_playing_task = asyncio.create_task(self._play_sound_file("recordings/sounds/startup.wav"))

    def play_shutdown_sound(self):
        self.stop_audio()
        self._currently_playing_task = asyncio.create_task(self._play_sound_file("recordings/sounds/shutdown.wav"))

    def play_random_song(self):
        self.stop_audio()
        random_filename = _pick_random(self._songs, self._last_played_song)
        self._last_played_song = random_filename
        self._currently_playing_task = asyncio.create_task(self._play_sound_file(random_filename))

    def play_random_animal_sound(self):
        self.stop_audio()
        # last_played is by the animal. The calling will be randomly chosen regardless.
        random_animal_filename = _pick_random(self._animals, self._last_played_animal)
        self._last_played_animal = random_animal_filename
        random_calling_filename = random.choice(self._yaar_callings)
        self._currently_playing_task = asyncio.create_task(self._play_animal(random_animal_filename, random_calling_filename))

    def stop_audio(self):
        if self._currently_playing_task is not None:
            self._currently_playing_task.cancel()
        self._currently_playing_task = None

    def increase_volume(self):
        current_volume = self.get_volume()
        new_volume = min(100, round(current_volume + self.volume_step, -1))
        self.set_volume(new_volume)

    def decrease_volume(self):
        current_volume = self.get_volume()
        new_volume = max(0, round(current_volume - self.volume_step, -1))
        self.set_volume(new_volume)

    def set_volume(self, volume):
        self.mixer.setvolume(int(max(0, min(100, volume))))

    def get_volume(self):
        vs = self.mixer.getvolume()
        return sum(vs) / len(vs)  # Averaging on channels.
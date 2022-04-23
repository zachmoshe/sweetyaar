import asyncio
import logging

import alsaaudio


APLAY_BINARY = "aplay"


async def _terminate_or_kill_procs(procs):
    for proc in procs:
        try:
            proc.terminate()
        except ProcessLookupError:
            pass  # process already doesn't exist.
    await asyncio.sleep(0.5)
    for proc in procs:
        if proc.returncode is None:  # didn't finish nicely
            proc.kill()


class AudioLibrary:
    def __init__(self, config):
        self._currently_playing_task = None
        self._currently_playing_filename = None
        self.mixer = alsaaudio.Mixer(control="Master")
        self.volume_step = config["volume_step"]

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
            await _terminate_or_kill_procs([proc])            


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
            await _terminate_or_kill_procs([p for p in (calling_proc, animal_proc) if p is not None])            


    def play_startup_sound(self):
        self.stop_audio()
        self._currently_playing_task = asyncio.create_task(self._play_sound_file("recordings/sounds/startup.wav"))

    def play_shutdown_sound(self):
        self.stop_audio()
        self._currently_playing_task = asyncio.create_task(self._play_sound_file("recordings/sounds/shutdown.wav"))

    def play_random_song(self, filename):
        self.stop_audio()
        self._currently_playing_task = asyncio.create_task(self._play_sound_file(filename))

    def play_random_animal_sound(self, animal_filename, calling_filename):
        self.stop_audio()
        self._currently_playing_task = asyncio.create_task(self._play_animal(animal_filename, calling_filename))

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
from machine import Pin
import uasyncio as asyncio
import time
from src import interfaces

from src import audio_player

# No enums in micropython...
class Actions:
    PLAY_SONG = 1
    PLAY_ANIMAL_SOUND = 2
    STOP_PLAYING = 3


class SweetYaarController:
    def __init__(self, cfg, audio_library, audio_player):
        self.audio_library = audio_library
        self.audio_player = audio_player
        self.audio_player.register_activity_callback(self.audio_activity_callback)
        self.currently_playing_desc = ""

        self.animals_button_gpio = cfg["GPIO_animals_button"]
        self.songs_button_gpio = cfg["GPIO_songs_button"]

    def audio_activity_callback(self, event):
        if event == audio_player.EVENT_AUDIO_STARTED:
            print(f"[CTL] {self.currently_playing_desc}")
        elif event == audio_player.EVENT_AUDIO_FINISHED:
            print("[CTL][AUDIO_EVENT] Audio finished.")
        else:
            print("[CTL][AUDIO_EVENT] Unsupported event.")

    def _play_startup_sound(self):
        self.audio_player.play_file(self.audio_library.get_sound_filename("startup"))
    
    def _play_shutdown_sound(self):
        self.audio_player.play_file(self.audio_library.get_sound_filename("shutdown"))

    async def _main_loop(self):
        try:
            self._play_startup_sound()
            gpio_iface = interfaces.GPIOInterface(animals_button_gpio=self.animals_button_gpio, songs_button_gpio=self.songs_button_gpio)
            await gpio_iface.listen(self.handle_action)

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
            print("[CTL] Playing song")
            self._play_song()
        elif action == Actions.PLAY_ANIMAL_SOUND:
            self._play_animal_sound()
        elif action == Actions.STOP_PLAYING:
            print("[CTL] Stop")
            self._stop_playing()
        else:
            print("[CTL] !!! Unknown action ", action)

    def _play_song(self):
        song_name, song_path = self.audio_library.get_random_song()
        self.currently_playing_desc = f"♫ {song_name}"
        self.audio_player.play_file(song_path)

    def _play_animal_sound(self):
        animal_name, animal_path = self.audio_library.get_random_animal_sound()
        self.currently_playing_desc = f"🐶 {animal_name}"
        self.audio_player.play_file(animal_path)

    def _stop_playing(self):
        self.currently_playing_song_desc = None
        self.audio_player.stop()

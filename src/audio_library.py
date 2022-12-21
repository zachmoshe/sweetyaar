import os
import random 
import re
import time

from src import bt_logger

logger = bt_logger.get_logger(__name__)

_RE_REMOVE_TRAILING_SLASH = re.compile(r"^(.*?)/*$")
_RE_VALID_FILENAME = re.compile(r"^([a-zA-Z0-9.-_]+)[.]([a-zA-Z0-9.-_]+)$")


_DEFAULT_BASE_SD_PATH = "/sd"


def _join(*paths): 
    if not paths: 
        return ""
    return "/".join(_RE_REMOVE_TRAILING_SLASH.match(p).group(1) for p in paths)


def _exists(path):
    try:
        os.stat(path)
        return True
    except OSError:
        return False


def _load_audio_folder(folder, humanize_filenames=True):
    if not _exists(folder):
        return {}
    results = {}
    for path in os.listdir(folder):
        if path[0] == "." or path[0] == "_":
            continue
        
        m = _RE_VALID_FILENAME.match(path)
        if m is None:
            logger.error(f"Illegal audio filename: {folder}/{path}")
            continue
        filename = m.group(1)
        # "humanize" filename if needed
        if humanize_filenames:
            filename = " ".join(w[0].upper() + w[1:]
                                for w in filename.split("_"))
        results[filename] = _join(folder, path)
    return results


_MANDATORY_PLAYLISTS = ("daytime", "nighttime")

class AudioLibrary:
    def __init__(self, config, base_sd_path = _DEFAULT_BASE_SD_PATH):
        if not _exists(base_sd_path):
            raise ValueError(f"Can't find base audio folder '{base_sd_path}'")

        # Load sounds
        self.sounds = _load_audio_folder(_join(base_sd_path, config["sounds_folder"]), humanize_filenames=False)
        self.animal_sounds = _load_audio_folder(_join(base_sd_path, config["animal_sounds_folder"]))
        self.playlists = {
            playlist_name: (repr_name, _load_audio_folder(_join(base_sd_path, playlist_folder)))
            for playlist_name, (repr_name, playlist_folder) in config["playlists"].items()
        }

        if any(x not in self.playlists for x in _MANDATORY_PLAYLISTS):
            raise ValueError(f"playlists must contain at least {_MANDATORY_PLAYLISTS}")
        for playlist_name, (_, playlist_songs) in self.playlists.items():
            if not playlist_songs:
                raise ValueError(f"playlist '{playlist_name}' doesn't contain any songs in folder.")
        self.last_returned_song_item = None
        self.last_returned_animal_item = None

    @property
    def playlists_names(self):
        return self.playlists.keys()
    
    @property
    def playlists_repr_names(self):
        return tuple(repr_name for repr_name, _ in self.playlists.values())

    @staticmethod
    def _choose_random_audio_item_non_repeat(items, last_item):
        valid_items = [i for i in items if i != last_item]
        random_item = random.choice(valid_items) if valid_items else random.choice(items)        
        return random_item

    def get_sound_filename(self, sound_name):
        return self.sounds[sound_name]

    def get_random_song(self, playlist_name):
        if playlist_name not in self.playlists:
            raise ValueError(f"Illegal playlist '{playlist_name}'")
        
        songs_items = list(self.playlists[playlist_name][1].items())
        random_song_item = self._choose_random_audio_item_non_repeat(songs_items, self.last_returned_song_item)
        self.last_returned_song_item = random_song_item
        return random_song_item

    def get_random_animal_sound(self):
        animal_items = list(self.animal_sounds.items())
        random_animal_item = self._choose_random_audio_item_non_repeat(animal_items, self.last_returned_animal_item)
        self.last_returned_animal_item = random_animal_item
        return random_animal_item

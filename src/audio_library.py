import collections
import os
import random 
import re
import time

from micropython import const
from src import bt_logger

_logger = bt_logger.get_logger(__name__)

_DEFAULT_BASE_SD_PATH = const("/sd")


def _join(*paths): 
    _RE_REMOVE_TRAILING_SLASH = re.compile(r"^(.*?)/*$")
    if not paths: 
        return ""
    return "/".join(_RE_REMOVE_TRAILING_SLASH.match(p).group(1) for p in paths)


def _exists(path):
    try:
        os.stat(path)
        return True
    except OSError:
        return False


def _random_shuffle(arr):
    """Fisher-Yates shuffle"""
    arr = list(arr)  # don't change in place.
    for i in range(len(arr)-1, 0, -1):
        j = random.randrange(i+1)
        arr[i], arr[j] = arr[j], arr[i]
    return arr


def _load_audio_folder(folder, humanize_filenames=True, random_shuffle=False):
    _RE_VALID_FILENAME = re.compile(r"^([a-zA-Z0-9.\-_]+)[.]([a-zA-Z0-9.-_]+)$")
    if not _exists(folder):
        return {}
    results = {}
    for path in os.listdir(folder):
        if path[0] == "." or path[0] == "_":
            continue
        
        m = _RE_VALID_FILENAME.match(path)
        if m is None:
            _logger.error(f"Illegal audio filename: {folder}/{path}")
            continue
        filename = m.group(1)
        # "humanize" filename if needed
        if humanize_filenames:
            filename = " ".join(w[0].upper() + w[1:]
                                for w in filename.split("_"))
        results[filename] = _join(folder, path)

    if random_shuffle:
        shuffled_items = _random_shuffle(results.items())
        results = collections.OrderedDict(shuffled_items)
    return results


_MANDATORY_PLAYLISTS = ("daytime", "nighttime")

class AudioLibrary:
    def __init__(self, config, base_sd_path = _DEFAULT_BASE_SD_PATH):
        if not _exists(base_sd_path):
            raise ValueError(f"Can't find base audio folder '{base_sd_path}'")

        # Load sounds
        self.sounds = _load_audio_folder(_join(base_sd_path, config["sounds_folder"]), humanize_filenames=False)
        self.animal_sounds = _load_audio_folder(_join(base_sd_path, config["animal_sounds_folder"]), random_shuffle=True)
        self.playlists = {
            playlist_name: (repr_name, _load_audio_folder(_join(base_sd_path, playlist_folder), random_shuffle=True))
            for playlist_name, (repr_name, playlist_folder) in config["playlists"].items()
        }

        if any(x not in self.playlists for x in _MANDATORY_PLAYLISTS):
            raise ValueError(f"playlists must contain at least {_MANDATORY_PLAYLISTS}")
        for playlist_name, (_, playlist_songs) in self.playlists.items():
            if not playlist_songs:
                raise ValueError(f"playlist '{playlist_name}' doesn't contain any songs in folder.")
        self.returned_song_idx = {playlist_name: 0 for playlist in self.playlists.keys()}
        self.returned_animal_idx = 0

    @property
    def playlists_names(self):
        return self.playlists.keys()
    
    @property
    def playlists_repr_names(self):
        return tuple(repr_name for repr_name, _ in self.playlists.values())

    def get_sound_filename(self, sound_name):
        return self.sounds[sound_name]

    def get_random_song(self, playlist_name):
        """Returns (song_name, song_path)."""
        if playlist_name not in self.playlists:
            raise ValueError(f"Illegal playlist '{playlist_name}'")
        
        curr_song_idx = self.returned_song_idx[playlist_name]
        song_item = self.playlists[playlist_name][1][curr_song_idx]
        self.returned_song_idx[playlist_name] = (self.returned_song_idx[playlist_name] + 1) % len(self.playlists[playlist_name][1])
        return song_item
        
    def get_random_animal_sound(self):
        """Returns (animal_sound_name, animal_sound_path)."""
        animal_item = self.animal_sounds[self.returned_animal_idx]
        self.returned_animal_idx = (self.returned_animal_idx + 1) % len(self.animal_sounds)
        return animal_item

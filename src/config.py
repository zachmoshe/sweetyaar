import json

from micropython import const

_CONFIG_FILENAME = const("etc/sweetyaar.json")
_CONFIG_OBJ = None

def get_config():
    global _CONFIG_OBJ
    # Not exactly thread-safe but will do the job here...
    if _CONFIG_OBJ is None:
        # Load config
        with open(_CONFIG_FILENAME) as f:
            _CONFIG_OBJ = json.load(f)
    return _CONFIG_OBJ

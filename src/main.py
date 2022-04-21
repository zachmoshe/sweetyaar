import asyncio
import atexit
from cgitb import lookup
import logging
import pathlib
import pprint 
import sys

import audio_library
import controller
import yaml


_CONFIG_FILE = "etc/config.yaml"

logging.basicConfig(
     level=logging.DEBUG, 
     format= '[%(asctime)s] {%(pathname)s:%(lineno)d} %(levelname)s - %(message)s',
     datefmt='%Y-%m-%d %H:%M:%S'
 )


def load_config(config_file):
    return yaml.safe_load(open(config_file, "rt").read())["sweetyaar"]


def main() -> int:
    cfg = load_config(_CONFIG_FILE)
    logging.info("Starting sweetyaar control loop with the following config:\n" + pprint.pformat(cfg))
    ctl = controller.SweetYaarController(cfg)
    ctl.take_control()

if __name__ == "__main__":
    main()

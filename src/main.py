from cgitb import lookup
import logging
from logging.handlers import TimedRotatingFileHandler
import pprint 

import controller
import yaml


_CONFIG_FILE = "etc/config.yaml"


def create_timed_rotating_log(path, log_level_str):
    logger = logging.getLogger()
    logger.setLevel(logging.getLevelName(log_level_str))
    
    # Every day. Keep 30 days back.
    handler = TimedRotatingFileHandler(path,
                                       when="D",
                                       interval=1,
                                       backupCount=30)
    handler.setFormatter(logging.Formatter("[%(asctime)s] {%(pathname)s:%(lineno)d} %(levelname)s - %(message)s"))
    logger.addHandler(handler)


def load_config(config_file):
    return yaml.safe_load(open(config_file, "rt").read())["sweetyaar"]


def main() -> int:
    cfg = load_config(_CONFIG_FILE)
    create_timed_rotating_log(cfg["log_path"], cfg["log_level"])
    logging.info("Starting sweetyaar control loop with the following config:\n" + pprint.pformat(cfg))
    ctl = controller.SweetYaarController(cfg)
    ctl.take_control()

if __name__ == "__main__":
    main()

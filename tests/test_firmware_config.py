"""Regression checks for firmware build and SD configuration."""

from __future__ import annotations

import json
import pathlib


ROOT = pathlib.Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "content" / "sd-card-template" / "config.json"
PLATFORMIO_PATH = ROOT / "firmware" / "esp32" / "platformio.ini"
FIRMWARE_CONFIG_PATH = ROOT / "firmware" / "esp32" / "src" / "Config.h"


def platformio_environment(name: str) -> str:
    platformio = PLATFORMIO_PATH.read_text()
    environment = platformio.split(f"[env:{name}]", maxsplit=1)[1]
    return environment.split("\n[", maxsplit=1)[0]


def test_sd_template_has_versioned_sleep_config() -> None:
    config = json.loads(CONFIG_PATH.read_text())
    assert config["schemaVersion"] == 2
    assert config["defaultVolumePct"] == 75
    assert config["defaultTheme"] == "lullabies"
    assert set(config["sleep"]) == {
        "enabled",
        "normalIdleSec",
        "vibrationWakeIdleSec",
        "bleIdleSec",
    }
    assert config["bedtime"] == {
        "enabled": True,
        "startTime": "18:30",
        "endTime": "06:30",
        "theme": "lullabies",
        "volumeCapPct": 45,
    }


def test_generic_board_overrides_hardware_inversions() -> None:
    generic = platformio_environment("sweetyaar-generic")

    assert "-DSWEETYAAR_AMP_MUTE_ACTIVE_HIGH=1" in generic
    assert "-DSWEETYAAR_STATUS_LED_DATA_INVERTED=0" in generic
    assert "-DSWEETYAAR_STATUS_LED_RGBW=1" in generic
    assert "-DSWEETYAAR_STATUS_LED_COLOR_ORDER_GRB=1" in generic


def test_status_led_default_max_brightness_is_50_percent() -> None:
    firmware_config = FIRMWARE_CONFIG_PATH.read_text()
    assert "#define SWEETYAAR_STATUS_LED_MAX_BRIGHTNESS_PCT 50" in firmware_config
    assert "#define SWEETYAAR_STATUS_LED_RGBW 0" in firmware_config

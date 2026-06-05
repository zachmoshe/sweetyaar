"""Regression checks for the BLE config contract and SD config persistence."""

from __future__ import annotations

import json
import pathlib


ROOT = pathlib.Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "sd_card_template" / "config.json"


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

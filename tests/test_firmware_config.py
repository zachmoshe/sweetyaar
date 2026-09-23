"""Regression checks for firmware build and SD configuration."""

from __future__ import annotations

import configparser
import json
import pathlib
import re
import shutil
import subprocess

import pytest


ROOT = pathlib.Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "content" / "sd-card-template" / "config.json"
PLATFORMIO_PATH = ROOT / "firmware" / "esp32" / "platformio.ini"
FIRMWARE_CONFIG_PATH = ROOT / "firmware" / "esp32" / "src" / "Config.h"
BQ25186_SOURCE_PATH = ROOT / "firmware" / "esp32" / "src" / "BQ25186Charger.cpp"
MAINBOARD_SCHEMATIC_PATH = (
    ROOT / "hardware" / "mainboard" / "sweetyaar-mainboard.kicad_sch"
)


def platformio_environment(name: str) -> str:
    platformio = PLATFORMIO_PATH.read_text()
    environment = platformio.split(f"[env:{name}]", maxsplit=1)[1]
    return environment.split("\n[", maxsplit=1)[0]


def platformio_build_flags(name: str) -> list[str]:
    config = configparser.ConfigParser(interpolation=None)
    config.read(PLATFORMIO_PATH)

    def expand(value: str) -> str:
        return re.sub(
            r"\$\{([^}]+)\}",
            lambda match: expand(config[match[1].rsplit(".", 1)[0]][
                match[1].rsplit(".", 1)[1]
            ]),
            value,
        )

    return re.findall(r"-D\S+", expand(config[f"env:{name}"]["build_flags"]))


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
    assert "-DSWEETYAAR_STATUS_LED_T0H_NS=400" in generic
    assert "-DSWEETYAAR_STATUS_LED_T1H_NS=800" in generic
    assert "-DSWEETYAAR_STATUS_LED_BIT_NS=1250" in generic
    assert "-DSWEETYAAR_STATUS_LED_RESET_US=80" in generic
    assert "-DSWEETYAAR_BQ25186_ENABLED=0" in generic


def test_production_board_enables_bq25186() -> None:
    production = platformio_environment("sweetyaar")
    assert "-DSWEETYAAR_BQ25186_ENABLED=1" in production


@pytest.mark.parametrize("environment", ["sweetyaar", "sweetyaar-generic"])
def test_board_build_flags_do_not_redefine_macros(environment: str) -> None:
    flags = platformio_build_flags(environment)
    names = [flag.split("=", 1)[0] for flag in flags]
    assert len(names) == len(set(names))
    assert "-DCORE_DEBUG_LEVEL=1" in flags
    assert "-DAUDIO_TOOLS_PREFER_SD" in flags


def compile_led_config(flags: list[str], assertions: str = "") -> subprocess.CompletedProcess:
    compiler = shutil.which("c++")
    assert compiler is not None, "A C++ compiler is required for firmware config tests"
    return subprocess.run(
        [compiler, "-std=c++17", "-x", "c++", "-fsyntax-only", "-",
         "-I", str(FIRMWARE_CONFIG_PATH.parent), *flags],
        input='#include <cstdint>\n#include <cstddef>\n#include "Config.h"\n' + assertions,
        text=True, capture_output=True, check=False,
    )


@pytest.mark.parametrize("environment", [None, "sweetyaar", "sweetyaar-generic"])
def test_status_led_effective_timing(environment: str | None) -> None:
    flags = platformio_build_flags(environment) if environment else []
    generic = environment == "sweetyaar-generic"
    zero, one, reset = (400, 800, 80) if generic else (300, 650, 300)
    result = compile_led_config(flags, f"""
static_assert(SWEETYAAR_STATUS_LED_T0H_NS == {zero});
static_assert(SWEETYAAR_STATUS_LED_T1H_NS == {one});
static_assert(SWEETYAAR_STATUS_LED_BIT_NS == 1250);
static_assert(SWEETYAAR_STATUS_LED_RESET_US == {reset});
static_assert(SWEETYAAR_STATUS_LED_RGBW == {int(generic)});
static_assert(SWEETYAAR_STATUS_LED_DATA_INVERTED == 0);
static_assert(SWEETYAAR_STATUS_LED_COLOR_ORDER_GRB == 1);
""")
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("environment", [None, "sweetyaar"])
def test_production_led_timing_matches_ws2812b_v6(environment: str | None) -> None:
    # Worldsemi WS2812B-V6 V1.1, page 4: check LOW as well as HIGH durations.
    flags = platformio_build_flags(environment) if environment else []
    result = compile_led_config(flags, """
constexpr auto zeroHigh = SWEETYAAR_STATUS_LED_T0H_NS;
constexpr auto oneHigh = SWEETYAAR_STATUS_LED_T1H_NS;
constexpr auto zeroLow = SWEETYAAR_STATUS_LED_BIT_NS - zeroHigh;
constexpr auto oneLow = SWEETYAAR_STATUS_LED_BIT_NS - oneHigh;
static_assert(zeroHigh >= 220 && zeroHigh <= 380);
static_assert(oneHigh >= 580 && oneHigh <= 1000);
static_assert(zeroLow >= 580 && zeroLow <= 1000);
static_assert(oneLow >= 580 && oneLow <= 1000);
static_assert(SWEETYAAR_STATUS_LED_BIT_NS >= 1250);
static_assert(SWEETYAAR_STATUS_LED_RESET_US > 280);
""")
    assert result.returncode == 0, result.stderr


def test_status_led_timing_can_be_overridden_independently() -> None:
    result = compile_led_config([
        "-DSWEETYAAR_STATUS_LED_T0H_NS=350",
        "-DSWEETYAAR_STATUS_LED_T1H_NS=825",
        "-DSWEETYAAR_STATUS_LED_BIT_NS=1300",
        "-DSWEETYAAR_STATUS_LED_RESET_US=350",
        "-DSWEETYAAR_STATUS_LED_RGBW=1",
        "-DSWEETYAAR_STATUS_LED_COLOR_ORDER_GRB=0",
        "-DSWEETYAAR_STATUS_LED_DATA_INVERTED=1",
    ], """
static_assert(SWEETYAAR_STATUS_LED_T0H_NS == 350);
static_assert(SWEETYAAR_STATUS_LED_T1H_NS == 825);
static_assert(SWEETYAAR_STATUS_LED_BIT_NS == 1300);
static_assert(SWEETYAAR_STATUS_LED_RESET_US == 350);
static_assert(SWEETYAAR_STATUS_LED_DATA_INVERTED == 1);
static_assert(SWEETYAAR_STATUS_LED_COLOR_ORDER_GRB == 0);
""")
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("setting", [
    "T0H_NS=301", "T0H_NS=0", "T0H_NS=-25", "T0H_NS=1250",
    "T1H_NS=0", "T1H_NS=1250", "T1H_NS=801",
    "BIT_NS=1201", "BIT_NS=65550", "RESET_US=0", "RESET_US=820",
])
def test_status_led_rejects_unrepresentable_timing(setting: str) -> None:
    result = compile_led_config([f"-DSWEETYAAR_STATUS_LED_{setting}"])
    assert result.returncode != 0
    assert "Status LED" in result.stderr or "SWEETYAAR_STATUS_LED_RESET_US" in result.stderr


def test_status_led_default_max_brightness_is_50_percent() -> None:
    firmware_config = FIRMWARE_CONFIG_PATH.read_text()
    assert "#define SWEETYAAR_STATUS_LED_MAX_BRIGHTNESS_PCT 50" in firmware_config
    assert "#define SWEETYAAR_STATUS_LED_RGBW 0" in firmware_config


@pytest.mark.parametrize(
    ("environment", "enabled"),
    [(None, 1), ("sweetyaar", 1), ("sweetyaar-generic", 0)],
)
def test_charger_pinout_and_board_selection(
    environment: str | None, enabled: int
) -> None:
    flags = platformio_build_flags(environment) if environment else []
    result = compile_led_config(flags, f"""
static_assert(SWEETYAAR_BQ25186_ENABLED == {enabled});
static_assert(HAS_BQ25186 == {str(bool(enabled)).lower()});
static_assert(PIN_CHARGER_ENABLE == 14);
static_assert(PIN_CHARGER_SDA == 16);
static_assert(PIN_CHARGER_SCL == 17);
static_assert(PIN_CHARGER_PG == 34);
static_assert(PIN_CHARGER_INT == 35);
static_assert(CHARGER_VERIFY_INTERVAL_MS == 10000);
""")
    assert result.returncode == 0, result.stderr


def test_bq25186_safety_policy_is_encoded_and_verified() -> None:
    source = BQ25186_SOURCE_PATH.read_text()
    for setting in (
        "VALUE_VBAT_CTRL = 0x46",
        "VALUE_ICHG_CTRL = 0x7F",
        "VALUE_CHARGECTRL0 = 0x24",
        "VALUE_CHARGECTRL1 = 0xD0",
        "VALUE_IC_CTRL_AWAKE = 0x86",
        "VALUE_IC_CTRL_SLEEP = 0x87",
        "VALUE_TMR_ILIM = 0x4F",
        "VALUE_SHIP_RST = 0x00",
        "VALUE_SYS_REG = 0x40",
        "VALUE_TS_CONTROL = 0xCC",
        "VALUE_MASK_ID = 0x01",
    ):
        assert setting in source

    assert "writeAndVerify(setting.reg, setting.value)" in source
    assert "readRegister(setting.reg, actual)" in source
    assert "setChargeEnabled(false)" in source


def test_battery_divider_matches_production_schematic() -> None:
    firmware_config = FIRMWARE_CONFIG_PATH.read_text()
    schematic = MAINBOARD_SCHEMATIC_PATH.read_text()

    assert "BATTERY_DIVIDER_TOP_OHMS = 634000" in firmware_config
    assert "BATTERY_DIVIDER_BOTTOM_OHMS = 200000" in firmware_config

    for reference, value in (
        ("R_BAT_H1", "634k"),
        ("R_BAT_L1", "100k"),
        ("R_BAT_L2", "100k"),
    ):
        assert re.search(
            rf'\(property "Reference" "{reference}".*?'
            rf'\(property "Value" "{value}"',
            schematic,
            flags=re.DOTALL,
        )

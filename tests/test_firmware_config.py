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

    # PlatformIO unescapes \" in build_flags before calling the compiler.
    flags = re.findall(r"-D\S+", expand(config[f"env:{name}"]["build_flags"]))
    return [flag.replace('\\"', '"') for flag in flags]


def test_sd_template_matches_the_config_schema() -> None:
    """Structure and technical limits only; default themes and volumes are content choices."""
    config = json.loads(CONFIG_PATH.read_text())

    def percent(value) -> bool:
        return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 100

    def theme_id(value) -> bool:
        # Theme IDs must fit the firmware's 63-byte live-theme buffer.
        return isinstance(value, str) and 0 < len(value.encode()) <= 63

    def clock(value) -> bool:
        return isinstance(value, str) and re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", value) is not None

    def seconds(value) -> bool:
        # The app accepts 1 s to one day for each sleep timeout.
        return isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 86400

    assert config["schemaVersion"] == 2
    assert set(config) == {"schemaVersion", "defaultVolumePct", "defaultTheme",
                           "disabledThemes", "bedtime", "sleep"}
    assert percent(config["defaultVolumePct"])
    assert theme_id(config["defaultTheme"])
    assert isinstance(config["disabledThemes"], list)
    assert all(theme_id(theme) for theme in config["disabledThemes"])

    bedtime = config["bedtime"]
    assert set(bedtime) == {"enabled", "startTime", "endTime", "theme", "volumeCapPct"}
    assert isinstance(bedtime["enabled"], bool)
    assert clock(bedtime["startTime"]) and clock(bedtime["endTime"])
    assert theme_id(bedtime["theme"])
    assert percent(bedtime["volumeCapPct"])

    sleep = config["sleep"]
    assert set(sleep) == {"enabled", "normalIdleSec", "vibrationWakeIdleSec", "bleIdleSec"}
    assert isinstance(sleep["enabled"], bool)
    assert all(seconds(sleep[key]) for key in ("normalIdleSec", "vibrationWakeIdleSec", "bleIdleSec"))


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


@pytest.mark.parametrize("environment", ["sweetyaar", "sweetyaar-generic"])
def test_board_id_matches_environment(environment: str) -> None:
    # Release images and the app's update check are keyed by this ID.
    assert f'-DSWEETYAAR_BOARD_ID="{environment}"' in platformio_build_flags(environment)


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
def test_status_led_board_settings(environment: str | None) -> None:
    # Frame type, inversion and channel order decide whether each board's LED
    # shows the right colour. Pulse timings are checked against the
    # WS2812B-V6 datasheet ranges below.
    flags = platformio_build_flags(environment) if environment else []
    generic = environment == "sweetyaar-generic"
    result = compile_led_config(flags, f"""
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


def test_status_led_brightness_cap_is_visible_and_guarded() -> None:
    # The cap is a tuning value; only an invisible LED or an impossible
    # percentage would be wrong.
    result = compile_led_config([], "static_assert(STATUS_LED_MAX_BRIGHTNESS_PCT >= 1);\n")
    assert result.returncode == 0, result.stderr
    for invalid in ("-1", "101"):
        result = compile_led_config([f"-DSWEETYAAR_STATUS_LED_MAX_BRIGHTNESS_PCT={invalid}"])
        assert result.returncode != 0


@pytest.mark.parametrize(
    ("environment", "enabled"),
    [(None, 1), ("sweetyaar", 1), ("sweetyaar-generic", 0)],
)
def test_charger_board_selection(environment: str | None, enabled: int) -> None:
    # Only the production board has a BQ25186.
    flags = platformio_build_flags(environment) if environment else []
    result = compile_led_config(flags, f"""
static_assert(SWEETYAAR_BQ25186_ENABLED == {enabled});
static_assert(HAS_BQ25186 == {str(bool(enabled)).lower()});
""")
    assert result.returncode == 0, result.stderr


def kicad_cli() -> str | None:
    return shutil.which("kicad-cli") or next(
        (path for path in ("/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli",)
         if pathlib.Path(path).exists()), None)


def schematic_nets(tmp_path: pathlib.Path) -> dict[str, list[tuple[str, str]]]:
    """Net name -> [(reference, pin function)] from the exported netlist."""
    cli = kicad_cli()
    if not cli:
        pytest.skip("kicad-cli is required to read the schematic's connections")
    netlist = tmp_path / "mainboard.net"
    subprocess.run([cli, "sch", "export", "netlist", "--format", "kicadsexpr",
                    "-o", str(netlist), str(MAINBOARD_SCHEMATIC_PATH)],
                   check=True, capture_output=True)
    nets = {}
    for block in re.split(r"\n\t\t\(net\n", netlist.read_text())[1:]:
        name = re.search(r'\(name "([^"]*)"\)', block).group(1)
        nets[name] = [(ref, function or pin) for ref, pin, function in re.findall(
            r'\(ref "([^"]+)"\)\s*\(pin "([^"]+)"\)(?:\s*\(pinfunction "([^"]*)"\))?', block)]
    return nets


def test_charger_pins_match_schematic(tmp_path: pathlib.Path) -> None:
    # Each GPIO in Config.h must reach the charger signal it is used for.
    config = FIRMWARE_CONFIG_PATH.read_text()
    nets = schematic_nets(tmp_path)

    def gpio(name: str) -> int:
        return int(re.search(rf"\b{name}\s*=\s*(\d+);", config).group(1))

    def net_of(io: int) -> tuple[str, list[tuple[str, str]]]:
        for net, nodes in nets.items():
            if any(ref == "U_ESP32" and function.startswith(f"IO{io}_") for ref, function in nodes):
                return net, nodes
        raise AssertionError(f"IO{io} is not connected in the schematic")

    for name, charger_pin in (("PIN_CHARGER_SDA", "SDA"), ("PIN_CHARGER_SCL", "SCL"),
                              ("PIN_CHARGER_PG", "PG#"), ("PIN_CHARGER_INT", "INT#")):
        net, nodes = net_of(gpio(name))
        assert any(ref == "U_CHG1" and function.startswith(charger_pin) for ref, function in nodes), \
            f"{name} (IO{gpio(name)}) is on {net}, not the charger's {charger_pin}"
    # /CE is driven through a transistor, so its GPIO reaches the enable net.
    assert net_of(gpio("PIN_CHARGER_ENABLE"))[0] == "/CHARGER_ENABLE"


def test_bq25186_safety_policy_is_encoded_and_verified() -> None:
    source = BQ25186_SOURCE_PATH.read_text()
    for setting in (
        "VALUE_VBAT_CTRL = 0x46",
        "VALUE_ICHG_CTRL = 0x7F",
        "VALUE_CHARGECTRL0 = 0x24",
        "VALUE_CHARGECTRL1 = 0xD7",
        "VALUE_IC_CTRL_AWAKE = 0x86",
        "VALUE_IC_CTRL_SLEEP = 0x87",
        "VALUE_TMR_ILIM = 0x4F",
        "VALUE_SHIP_RST = 0x00",
        "VALUE_SYS_REG = 0x40",
        "VALUE_TS_CONTROL = 0xCC",
        "VALUE_MASK_ID = 0x41",
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

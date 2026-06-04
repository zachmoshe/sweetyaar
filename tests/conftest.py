from __future__ import annotations

import os
import pathlib

import pytest

from helpers import ROOT


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--bt-address",
        default=os.environ.get("SWEETYAAR_BT_ADDRESS", "40-22-D8-3D-8A-22"),
        help="Classic Bluetooth MAC address for real-device smoke tests.",
    )
    parser.addoption(
        "--device-name",
        default=os.environ.get("SWEETYAAR_DEVICE_NAME", "SweetYaar"),
        help="BLE/Classic Bluetooth device name for real-device smoke tests.",
    )


@pytest.fixture(scope="session")
def repo_root() -> pathlib.Path:
    return ROOT

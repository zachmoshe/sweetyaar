from __future__ import annotations

import pytest

from helpers import find_platformio, run_checked


@pytest.mark.firmware
def test_esp32dev_firmware_build(repo_root) -> None:
    pio = find_platformio(repo_root)
    if not pio:
        pytest.skip("PlatformIO not found; expected .venv/bin/pio in this repo or a parent checkout.")

    result = run_checked([pio, "run", "-e", "esp32dev"], cwd=repo_root)
    assert "esp32dev" in result.stdout
    assert "SUCCESS" in result.stdout

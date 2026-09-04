from __future__ import annotations

import pytest

from helpers import find_platformio, run_checked


@pytest.mark.firmware
@pytest.mark.parametrize("environment", ["sweetyaar", "sweetyaar-generic"])
def test_sweetyaar_firmware_build(repo_root, environment: str) -> None:
    pio = find_platformio(repo_root)
    if not pio:
        pytest.skip("PlatformIO not found; expected .venv/bin/pio in this repo or a parent checkout.")

    result = run_checked(
        [pio, "run", "-e", environment],
        cwd=repo_root / "firmware" / "esp32",
    )
    assert environment in result.stdout
    assert "SUCCESS" in result.stdout

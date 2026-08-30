from __future__ import annotations

import pathlib
import shutil
import subprocess


ROOT = pathlib.Path(__file__).resolve().parents[1]


def find_platformio(root: pathlib.Path = ROOT) -> pathlib.Path | None:
    for base in (root, *root.parents):
        candidate = base / ".venv" / "bin" / "pio"
        if candidate.exists():
            return candidate
    found = shutil.which("pio")
    return pathlib.Path(found) if found else None


def run_command(
    cmd: list[str | pathlib.Path],
    *,
    cwd: pathlib.Path = ROOT,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(part) for part in cmd],
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=check,
    )


def run_checked(cmd: list[str | pathlib.Path], *, cwd: pathlib.Path = ROOT) -> subprocess.CompletedProcess[str]:
    return run_command(cmd, cwd=cwd, check=True)

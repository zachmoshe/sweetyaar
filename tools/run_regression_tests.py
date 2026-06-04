#!/usr/bin/env python3
"""Compatibility wrapper for SweetYaar's pytest regression suite."""

from __future__ import annotations

import pathlib
import subprocess
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]


def run(cmd: list[str | pathlib.Path]) -> None:
    printable = " ".join(str(part) for part in cmd)
    print(f"+ {printable}", flush=True)
    subprocess.run([str(part) for part in cmd], cwd=ROOT, check=True)


def main(argv: list[str]) -> int:
    run([sys.executable, "-m", "pytest", *argv])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

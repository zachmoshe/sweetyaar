from __future__ import annotations

import pathlib
import shutil

import pytest

from helpers import run_checked


def test_state_machine_native_transitions(repo_root: pathlib.Path, tmp_path: pathlib.Path) -> None:
    compiler = shutil.which("c++") or shutil.which("g++") or shutil.which("clang++")
    if not compiler:
        pytest.skip("No C++ compiler found for native state-machine regression test.")

    exe = tmp_path / "state_machine_native_test"
    run_checked([
        compiler,
        "-std=c++17",
        "-Wall",
        "-Wextra",
        "-I",
        repo_root / "tests" / "native_stubs",
        "-I",
        repo_root / "src",
        repo_root / "src" / "StateMachine.cpp",
        repo_root / "tests" / "state_machine_native_test.cpp",
        "-o",
        exe,
    ])
    result = run_checked([exe])
    assert "state-machine native test passed" in result.stdout

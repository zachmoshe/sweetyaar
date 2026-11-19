from __future__ import annotations

import shutil

import pytest

from helpers import run_checked


def test_parent_app_save_flow(repo_root) -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is not installed; parent app UI test skipped.")

    result = run_checked([
        node,
        repo_root / "tests" / "parent_app_ui_test.js",
    ])
    assert "parent app UI tests passed" in result.stdout


def test_logs_queue(repo_root) -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is not installed; logs queue test skipped.")
    result = run_checked([node, repo_root / "tests" / "logs_queue_test.js"])
    assert "logs queue tests passed" in result.stdout


def test_studio_device_client(repo_root) -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is not installed; Studio device test skipped.")
    result = run_checked([node, repo_root / "tests" / "studio_device_test.js"])
    assert "studio device tests passed" in result.stdout


def test_studio_audio_helpers(repo_root) -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is not installed; Studio audio test skipped.")
    result = run_checked([node, repo_root / "tests" / "studio_audio_test.js"])
    assert "studio audio tests passed" in result.stdout


def test_studio_parts(repo_root) -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is not installed; Studio parts test skipped.")
    result = run_checked([node, repo_root / "tests" / "studio_parts_test.js"])
    assert "studio parts tests passed" in result.stdout


def test_studio_animal_matching(repo_root) -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is not installed; Studio animals test skipped.")
    result = run_checked([node, repo_root / "tests" / "studio_animals_test.js"])
    assert "studio animals tests passed" in result.stdout


def test_studio_export(repo_root) -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is not installed; Studio export test skipped.")
    result = run_checked([node, repo_root / "tests" / "studio_export_test.js"])
    assert "studio export tests passed" in result.stdout

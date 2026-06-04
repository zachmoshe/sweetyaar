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

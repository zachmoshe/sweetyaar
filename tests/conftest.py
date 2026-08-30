from __future__ import annotations

import pathlib

import pytest

from helpers import ROOT


@pytest.fixture(scope="session")
def repo_root() -> pathlib.Path:
    return ROOT

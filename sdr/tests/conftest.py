"""Shared test fixtures and safety nets for vtms-sdr tests."""

import os
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _no_stray_files(tmp_path, monkeypatch):
    """Prevent tests from creating files in the project directory.

    Automatically changes the working directory to a temporary directory
    before each test and restores it afterward. This ensures any test
    that auto-generates filenames (recordings, transcripts, scan CSVs)
    writes to the temp directory instead of polluting the project root.
    """
    monkeypatch.chdir(tmp_path)

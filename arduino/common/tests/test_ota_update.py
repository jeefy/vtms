"""Tests for OTA update module.

Run on host with CPython/pytest.
"""

import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import patch, MagicMock


class TestFileHelpers:
    """Test file read/write/exists helpers."""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self._orig = os.getcwd()
        os.chdir(self.tmpdir)

    def teardown_method(self):
        os.chdir(self._orig)
        shutil.rmtree(self.tmpdir)

    def test_write_and_read(self):
        from ota_update import write_file, read_file

        write_file("test.txt", "hello world")
        assert read_file("test.txt") == "hello world"

    def test_read_nonexistent(self):
        from ota_update import read_file

        assert read_file("nonexistent.txt") == ""

    def test_read_strips_whitespace(self):
        from ota_update import write_file, read_file

        write_file("test.txt", "  hello  \n")
        assert read_file("test.txt") == "hello"

    def test_file_exists_true(self):
        from ota_update import write_file, file_exists

        write_file("test.txt", "x")
        assert file_exists("test.txt") is True

    def test_file_exists_false(self):
        from ota_update import file_exists

        assert file_exists("nope.txt") is False


class TestIsUpdateAvailable:
    """Test hash comparison logic (pure function)."""

    def test_different_hash(self):
        from ota_update import is_update_available

        assert is_update_available("abc123", "def456") is True

    def test_same_hash(self):
        from ota_update import is_update_available

        assert is_update_available("abc123", "abc123") is False

    def test_empty_server_hash(self):
        from ota_update import is_update_available

        assert is_update_available("", "abc123") is False

    def test_empty_current_hash_means_update(self):
        from ota_update import is_update_available

        assert is_update_available("abc123", "") is True

    def test_skip_hash_matches(self):
        from ota_update import is_update_available

        assert is_update_available("abc123", "", "abc123") is False

    def test_skip_hash_different(self):
        from ota_update import is_update_available

        assert is_update_available("abc123", "", "def456") is True


class TestBootCount:
    """Test boot counter functions."""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self._orig = os.getcwd()
        os.chdir(self.tmpdir)

    def teardown_method(self):
        os.chdir(self._orig)
        shutil.rmtree(self.tmpdir)

    def test_initial_count_zero(self):
        from ota_update import get_boot_count

        assert get_boot_count() == 0

    def test_increment(self):
        from ota_update import increment_boot_count, get_boot_count

        assert increment_boot_count() == 1
        assert get_boot_count() == 1

    def test_multiple_increments(self):
        from ota_update import increment_boot_count

        increment_boot_count()
        increment_boot_count()
        assert increment_boot_count() == 3

    def test_reset(self):
        from ota_update import increment_boot_count, reset_boot_count, get_boot_count

        increment_boot_count()
        increment_boot_count()
        reset_boot_count()
        assert get_boot_count() == 0

    def test_needs_rollback_false(self):
        from ota_update import increment_boot_count, needs_rollback

        increment_boot_count()
        assert needs_rollback() is False

    def test_needs_rollback_at_threshold(self):
        from ota_update import increment_boot_count, needs_rollback

        for _ in range(3):
            increment_boot_count()
        assert needs_rollback() is True

    def test_needs_rollback_custom_threshold(self):
        from ota_update import increment_boot_count, needs_rollback

        increment_boot_count()
        assert needs_rollback(max_boots=1) is True


class TestBackupRestore:
    """Test file backup and restore."""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self._orig = os.getcwd()
        os.chdir(self.tmpdir)

    def teardown_method(self):
        os.chdir(self._orig)
        shutil.rmtree(self.tmpdir)

    def test_backup_and_restore(self):
        from ota_update import write_file, read_file, backup_files, restore_backup

        write_file("main.py", "original code")
        backup_files(["main.py"])
        write_file("main.py", "new code")
        assert read_file("main.py") == "new code"
        restored = restore_backup()
        assert read_file("main.py") == "original code"
        assert "main.py" in restored

    def test_backup_nonexistent_file(self):
        from ota_update import backup_files

        backup_files(["nonexistent.py"])  # should not raise

    def test_restore_no_backup_dir(self):
        from ota_update import restore_backup

        assert restore_backup() == []


class TestPerformRollback:
    """Test full rollback flow."""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self._orig = os.getcwd()
        os.chdir(self.tmpdir)

    def teardown_method(self):
        os.chdir(self._orig)
        shutil.rmtree(self.tmpdir)

    def test_rollback_restores_and_marks_skip(self):
        from ota_update import (
            write_file,
            read_file,
            backup_files,
            perform_rollback,
            HASH_FILE,
            SKIP_FILE,
        )

        write_file("main.py", "old code")
        backup_files(["main.py"])
        write_file("main.py", "broken code")
        write_file(HASH_FILE, "badhash123")

        assert perform_rollback() is True
        assert read_file("main.py") == "old code"
        assert read_file(SKIP_FILE) == "badhash123"
        assert read_file(HASH_FILE) == ""

    def test_rollback_no_backup(self):
        from ota_update import perform_rollback

        assert perform_rollback() is False


class TestFetchManifest:
    """Test manifest fetching with mocked HTTP."""

    def test_success(self):
        from ota_update import fetch_manifest

        manifest = {"hash": "abc123", "files": ["main.py"]}
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = json.dumps(manifest)

        with patch("ota_update.requests") as mock_req:
            mock_req.get.return_value = mock_resp
            result = fetch_manifest("10.42.0.1:8266", "analog_sensors")

        assert result == manifest
        mock_req.get.assert_called_once_with(
            "http://10.42.0.1:8266/manifest/analog_sensors"
        )

    def test_http_error(self):
        from ota_update import fetch_manifest

        mock_resp = MagicMock()
        mock_resp.status_code = 404

        with patch("ota_update.requests") as mock_req:
            mock_req.get.return_value = mock_resp
            result = fetch_manifest("10.42.0.1:8266", "unknown")

        assert result is None

    def test_connection_error(self):
        from ota_update import fetch_manifest

        with patch("ota_update.requests") as mock_req:
            mock_req.get.side_effect = OSError("connection refused")
            result = fetch_manifest("10.42.0.1:8266", "test")

        assert result is None


class TestApplyUpdate:
    """Test update application with mocked downloads."""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self._orig = os.getcwd()
        os.chdir(self.tmpdir)

    def teardown_method(self):
        os.chdir(self._orig)
        shutil.rmtree(self.tmpdir)

    def test_successful_update(self):
        from ota_update import apply_update, read_file, HASH_FILE, write_file

        write_file("main.py", "old code")
        manifest = {"hash": "newhash", "files": ["main.py", "config.py"]}

        with patch("ota_update.download_file") as mock_dl:
            mock_dl.side_effect = ["new main", "new config"]
            result = apply_update("server", "device", manifest)

        assert result is True
        assert read_file("main.py") == "new main"
        assert read_file("config.py") == "new config"
        assert read_file(HASH_FILE) == "newhash"

    def test_download_failure_restores_backup(self):
        from ota_update import apply_update, read_file, write_file

        write_file("main.py", "old code")
        manifest = {"hash": "newhash", "files": ["main.py", "config.py"]}

        with patch("ota_update.download_file") as mock_dl:
            mock_dl.side_effect = ["new main", None]  # second file fails
            result = apply_update("server", "device", manifest)

        assert result is False
        assert read_file("main.py") == "old code"  # restored


class TestCheckAndUpdate:
    """Test full check-and-update orchestration."""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self._orig = os.getcwd()
        os.chdir(self.tmpdir)

    def teardown_method(self):
        os.chdir(self._orig)
        shutil.rmtree(self.tmpdir)

    def test_current(self):
        from ota_update import check_and_update, write_file, HASH_FILE

        write_file(HASH_FILE, "abc123")

        with patch("ota_update.fetch_manifest") as mock_fm:
            mock_fm.return_value = {"hash": "abc123", "files": ["main.py"]}
            result = check_and_update("server", "device")

        assert result == "current"

    def test_updated(self):
        from ota_update import check_and_update

        with patch("ota_update.fetch_manifest") as mock_fm:
            mock_fm.return_value = {"hash": "newhash", "files": ["main.py"]}
            with patch("ota_update.apply_update", return_value=True):
                result = check_and_update("server", "device")

        assert result == "updated"

    def test_manifest_error(self):
        from ota_update import check_and_update

        with patch("ota_update.fetch_manifest", return_value=None):
            result = check_and_update("server", "device")

        assert result == "error"

    def test_skipped_hash(self):
        from ota_update import check_and_update, write_file, SKIP_FILE

        write_file(SKIP_FILE, "badhash")

        with patch("ota_update.fetch_manifest") as mock_fm:
            mock_fm.return_value = {"hash": "badhash", "files": ["main.py"]}
            result = check_and_update("server", "device")

        assert result == "current"

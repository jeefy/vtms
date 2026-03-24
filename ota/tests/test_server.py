"""Tests for OTA server.

Run with: python -m pytest ota/tests/ -v
"""

import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest


class TestGetDeviceFiles:
    """Test device file listing."""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmpdir, "common"))
        os.makedirs(os.path.join(self.tmpdir, "test_device"))

    def teardown_method(self):
        shutil.rmtree(self.tmpdir)

    def test_includes_common_and_device(self):
        from server import get_device_files

        with open(os.path.join(self.tmpdir, "common", "boot.py"), "w") as f:
            f.write("")
        with open(os.path.join(self.tmpdir, "test_device", "main.py"), "w") as f:
            f.write("")
        files = get_device_files(self.tmpdir, "test_device")
        assert "boot.py" in files
        assert "main.py" in files

    def test_only_py_files(self):
        from server import get_device_files

        with open(os.path.join(self.tmpdir, "test_device", "main.py"), "w") as f:
            f.write("")
        with open(os.path.join(self.tmpdir, "test_device", "README.md"), "w") as f:
            f.write("")
        files = get_device_files(self.tmpdir, "test_device")
        assert "main.py" in files
        assert "README.md" not in files

    def test_sorted_output(self):
        from server import get_device_files

        with open(os.path.join(self.tmpdir, "common", "z_boot.py"), "w") as f:
            f.write("")
        with open(os.path.join(self.tmpdir, "test_device", "a_main.py"), "w") as f:
            f.write("")
        files = get_device_files(self.tmpdir, "test_device")
        assert files == sorted(files)

    def test_deduplicates(self):
        from server import get_device_files

        # Same filename in both common and device
        with open(os.path.join(self.tmpdir, "common", "boot.py"), "w") as f:
            f.write("common")
        with open(os.path.join(self.tmpdir, "test_device", "boot.py"), "w") as f:
            f.write("device")
        files = get_device_files(self.tmpdir, "test_device")
        assert files.count("boot.py") == 1


class TestResolveFile:
    """Test file resolution (device dir takes priority over common)."""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmpdir, "common"))
        os.makedirs(os.path.join(self.tmpdir, "test_device"))

    def teardown_method(self):
        shutil.rmtree(self.tmpdir)

    def test_prefers_device_over_common(self):
        from server import resolve_file

        with open(os.path.join(self.tmpdir, "common", "boot.py"), "w") as f:
            f.write("common")
        with open(os.path.join(self.tmpdir, "test_device", "boot.py"), "w") as f:
            f.write("device")
        path = resolve_file(self.tmpdir, "test_device", "boot.py")
        assert "test_device" in path

    def test_falls_back_to_common(self):
        from server import resolve_file

        with open(os.path.join(self.tmpdir, "common", "boot.py"), "w") as f:
            f.write("common")
        path = resolve_file(self.tmpdir, "test_device", "boot.py")
        assert "common" in path


class TestComputeDeviceHash:
    """Test per-device hash computation."""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmpdir, "common"))
        os.makedirs(os.path.join(self.tmpdir, "test_device"))

    def teardown_method(self):
        shutil.rmtree(self.tmpdir)

    def test_deterministic(self):
        from server import compute_device_hash

        with open(os.path.join(self.tmpdir, "common", "boot.py"), "w") as f:
            f.write("boot code")
        with open(os.path.join(self.tmpdir, "test_device", "main.py"), "w") as f:
            f.write("main code")
        h1 = compute_device_hash(self.tmpdir, "test_device")
        h2 = compute_device_hash(self.tmpdir, "test_device")
        assert h1 == h2
        assert len(h1) == 64  # SHA256 hex

    def test_changes_with_content(self):
        from server import compute_device_hash

        with open(os.path.join(self.tmpdir, "test_device", "main.py"), "w") as f:
            f.write("version 1")
        h1 = compute_device_hash(self.tmpdir, "test_device")
        with open(os.path.join(self.tmpdir, "test_device", "main.py"), "w") as f:
            f.write("version 2")
        h2 = compute_device_hash(self.tmpdir, "test_device")
        assert h1 != h2


class TestBuildManifests:
    """Test manifest building for all device types."""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmpdir, "common"))
        os.makedirs(os.path.join(self.tmpdir, "device_a"))
        os.makedirs(os.path.join(self.tmpdir, "device_b"))

    def teardown_method(self):
        shutil.rmtree(self.tmpdir)

    def test_builds_for_all_devices(self):
        from server import build_manifests

        with open(os.path.join(self.tmpdir, "device_a", "main.py"), "w") as f:
            f.write("a")
        with open(os.path.join(self.tmpdir, "device_b", "main.py"), "w") as f:
            f.write("b")
        manifests = build_manifests(self.tmpdir)
        assert "device_a" in manifests
        assert "device_b" in manifests
        assert "common" not in manifests

    def test_manifest_structure(self):
        from server import build_manifests

        with open(os.path.join(self.tmpdir, "device_a", "main.py"), "w") as f:
            f.write("code")
        manifests = build_manifests(self.tmpdir)
        m = manifests["device_a"]
        assert "hash" in m
        assert "files" in m
        assert "device_type" in m
        assert m["device_type"] == "device_a"


class TestPathTraversal:
    """Test that path traversal via device_type and filename is blocked."""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmpdir, "common"))
        os.makedirs(os.path.join(self.tmpdir, "test_device"))
        with open(os.path.join(self.tmpdir, "test_device", "main.py"), "w") as f:
            f.write("ok")

    def teardown_method(self):
        shutil.rmtree(self.tmpdir)

    def test_resolve_file_rejects_dotdot_device_type(self):
        from server import resolve_file

        with pytest.raises(ValueError):
            resolve_file(self.tmpdir, "..", "main.py")

    def test_resolve_file_rejects_slash_device_type(self):
        from server import resolve_file

        with pytest.raises(ValueError):
            resolve_file(self.tmpdir, "foo/bar", "main.py")

    def test_resolve_file_rejects_dotdot_filename(self):
        from server import resolve_file

        with pytest.raises(ValueError):
            resolve_file(self.tmpdir, "test_device", "../etc/passwd")

    def test_get_device_files_rejects_dotdot(self):
        from server import get_device_files

        with pytest.raises(ValueError):
            get_device_files(self.tmpdir, "..")

    def test_get_device_files_rejects_slash(self):
        from server import get_device_files

        with pytest.raises(ValueError):
            get_device_files(self.tmpdir, "../etc")

    def test_handle_manifest_returns_400_for_invalid_device_type(self):
        from server import OTAHandler
        import io
        from http.server import HTTPServer
        from unittest.mock import MagicMock

        handler = object.__new__(OTAHandler)
        handler.wfile = io.BytesIO()
        handler._headers_buffer = []
        handler.request_version = "HTTP/1.1"
        handler.requestline = "GET /manifest/.. HTTP/1.1"
        handler.responses = OTAHandler.responses
        handler.manifests = {}
        handler.firmware_dir = self.tmpdir

        handler._handle_manifest("..")
        handler.wfile.seek(0)
        response = handler.wfile.read().decode()
        assert "400" in response
        assert "invalid device type" in response

    def test_handle_file_returns_400_for_invalid_device_type(self):
        from server import OTAHandler
        import io

        handler = object.__new__(OTAHandler)
        handler.wfile = io.BytesIO()
        handler._headers_buffer = []
        handler.request_version = "HTTP/1.1"
        handler.requestline = "GET /files/../main.py HTTP/1.1"
        handler.responses = OTAHandler.responses
        handler.manifests = {}
        handler.firmware_dir = self.tmpdir

        handler._handle_file("..", "main.py")
        handler.wfile.seek(0)
        response = handler.wfile.read().decode()
        assert "400" in response
        assert "invalid device type" in response

    def test_valid_device_type_accepted(self):
        from server import _validate_device_type

        # Should not raise for valid names
        _validate_device_type("test_device")
        _validate_device_type("esp32-sensor")
        _validate_device_type("DeviceA123")

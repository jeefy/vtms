"""Tests for vtms_sdr.sdr with mocked RTL-SDR hardware."""

import numpy as np
import pytest
from unittest.mock import patch, MagicMock

from vtms_sdr.sdr import SDRDevice, DEFAULT_SAMPLE_RATE, DEFAULT_BLOCK_SIZE


class FakeRtlSdr:
    """Mock RTL-SDR device for testing."""

    def __init__(self, device_index=0):
        self.sample_rate = DEFAULT_SAMPLE_RATE
        self.center_freq = 146_520_000
        self.gain = "auto"
        self.freq_correction = 0
        self._closed = False
        self._read_count = 0

    def read_samples(self, num_samples):
        """Return synthetic IQ samples."""
        self._read_count += 1
        # Generate random complex samples like a real SDR would
        return (
            np.random.randn(num_samples) + 1j * np.random.randn(num_samples)
        ).astype(np.complex64)

    def close(self):
        self._closed = True


@pytest.fixture
def mock_rtlsdr():
    """Patch the RtlSdr import to use our fake."""
    fake_device = FakeRtlSdr()
    with patch("vtms_sdr.sdr.RtlSdr", create=True) as mock_cls:
        # Make the import inside SDRDevice.open() work
        import vtms_sdr.sdr as sdr_module

        original_open = SDRDevice.open

        def patched_open(self):
            self._sdr = FakeRtlSdr(self._device_index)

        with patch.object(SDRDevice, "open", patched_open):
            yield fake_device


class TestSDRDeviceContextManager:
    def test_context_manager_opens_and_closes(self, mock_rtlsdr):
        with SDRDevice() as sdr:
            assert sdr._sdr is not None
        assert sdr._sdr is None

    def test_context_manager_closes_on_exception(self, mock_rtlsdr):
        with pytest.raises(ValueError):
            with SDRDevice() as sdr:
                raise ValueError("test error")
        assert sdr._sdr is None


class TestSDRDeviceConfigure:
    def test_configure_sets_frequency(self, mock_rtlsdr):
        with SDRDevice() as sdr:
            sdr.configure(center_freq=146_520_000)
            assert sdr._sdr.center_freq == 146_520_000

    def test_configure_sets_sample_rate(self, mock_rtlsdr):
        with SDRDevice() as sdr:
            sdr.configure(center_freq=146_520_000, sample_rate=1_000_000)
            assert sdr._sdr.sample_rate == 1_000_000

    def test_configure_auto_gain(self, mock_rtlsdr):
        with SDRDevice() as sdr:
            sdr.configure(center_freq=146_520_000, gain="auto")
            assert sdr._sdr.gain == "auto"

    def test_configure_manual_gain(self, mock_rtlsdr):
        with SDRDevice() as sdr:
            sdr.configure(center_freq=146_520_000, gain=40.0)
            assert sdr._sdr.gain == 40.0

    def test_configure_invalid_frequency_too_low(self, mock_rtlsdr):
        with SDRDevice() as sdr:
            with pytest.raises(ValueError, match="out of RTL-SDR range"):
                sdr.configure(center_freq=1_000_000)

    def test_configure_invalid_frequency_too_high(self, mock_rtlsdr):
        with SDRDevice() as sdr:
            with pytest.raises(ValueError, match="out of RTL-SDR range"):
                sdr.configure(center_freq=2_000_000_000)

    def test_configure_without_open_raises(self):
        sdr = SDRDevice()
        with pytest.raises(RuntimeError, match="not open"):
            sdr.configure(center_freq=146_520_000)


class TestSDRDeviceStream:
    def test_stream_yields_complex_arrays(self, mock_rtlsdr):
        with SDRDevice() as sdr:
            sdr.configure(center_freq=146_520_000)
            count = 0
            for iq_block in sdr.stream():
                assert isinstance(iq_block, np.ndarray)
                assert iq_block.dtype == np.complex64
                assert len(iq_block) == DEFAULT_BLOCK_SIZE
                count += 1
                if count >= 3:
                    break
            assert count == 3

    def test_stream_custom_block_size(self, mock_rtlsdr):
        with SDRDevice() as sdr:
            sdr.configure(center_freq=146_520_000)
            for iq_block in sdr.stream(block_size=1024):
                assert len(iq_block) == 1024
                break

    def test_stream_without_open_raises(self):
        sdr = SDRDevice()
        with pytest.raises(RuntimeError, match="not open"):
            next(sdr.stream())


class TestSDRDeviceReadSamples:
    def test_read_samples_returns_array(self, mock_rtlsdr):
        with SDRDevice() as sdr:
            sdr.configure(center_freq=146_520_000)
            samples = sdr.read_samples(1024)
            assert isinstance(samples, np.ndarray)
            assert samples.dtype == np.complex64
            assert len(samples) == 1024

    def test_read_samples_without_open_raises(self):
        sdr = SDRDevice()
        with pytest.raises(RuntimeError, match="not open"):
            sdr.read_samples()


class TestSDRDeviceProperties:
    def test_center_freq_when_open(self, mock_rtlsdr):
        with SDRDevice() as sdr:
            sdr.configure(center_freq=146_520_000)
            assert sdr.center_freq == 146_520_000

    def test_center_freq_when_closed(self):
        sdr = SDRDevice()
        assert sdr.center_freq == 0

    def test_sample_rate_when_open(self, mock_rtlsdr):
        with SDRDevice() as sdr:
            sdr.configure(center_freq=146_520_000)
            assert sdr.sample_rate == DEFAULT_SAMPLE_RATE

    def test_sample_rate_when_closed(self):
        sdr = SDRDevice()
        assert sdr.sample_rate == 0

    def test_get_info_when_open(self, mock_rtlsdr):
        with SDRDevice() as sdr:
            sdr.configure(center_freq=146_520_000)
            info = sdr.get_info()
            assert info["center_freq"] == 146_520_000
            assert "146.520 MHz" in info["center_freq_str"]
            assert info["sample_rate"] == DEFAULT_SAMPLE_RATE

    def test_get_info_when_closed(self):
        sdr = SDRDevice()
        info = sdr.get_info()
        assert info == {"status": "closed"}


class TestSDRDeviceErrorHandling:
    def test_open_no_device_found(self):
        """Test error when no RTL-SDR device is connected."""
        with patch.dict("sys.modules", {"rtlsdr": MagicMock()}) as _:
            import vtms_sdr.sdr as sdr_module

            with patch.object(SDRDevice, "open") as mock_open:
                mock_open.side_effect = RuntimeError(
                    "No RTL-SDR device found. Is it plugged in?"
                )
                sdr = SDRDevice()
                with pytest.raises(RuntimeError, match="No RTL-SDR device found"):
                    sdr.open()

    def test_close_idempotent(self, mock_rtlsdr):
        """Calling close multiple times should not raise."""
        with SDRDevice() as sdr:
            pass
        # Already closed by context manager, calling again should be safe
        sdr.close()
        sdr.close()

    def test_stream_ioerror_recovery(self, mock_rtlsdr):
        """Test that stream attempts recovery on IOError."""
        with SDRDevice() as sdr:
            sdr.configure(center_freq=146_520_000)

            call_count = 0
            original_read = sdr._sdr.read_samples

            def flaky_read(n):
                nonlocal call_count
                call_count += 1
                if call_count == 2:  # Fail on second read
                    raise IOError("USB transfer error")
                return original_read(n)

            sdr._sdr.read_samples = flaky_read

            blocks = []
            for block in sdr.stream():
                blocks.append(block)
                if len(blocks) >= 3:
                    break

            # Should have gotten blocks despite the IOError
            assert len(blocks) >= 2


class TestSDRDeviceSetGain:
    """Test SDRDevice.set_gain() individual setter."""

    def test_set_gain_numeric(self):
        """set_gain(20.0) sets gain to 20.0 on the underlying device."""
        from vtms_sdr.sdr import SDRDevice

        sdr = SDRDevice(device_index=0)
        sdr._sdr = MagicMock()
        sdr.set_gain(20.0)
        assert sdr._sdr.gain == 20.0

    def test_set_gain_auto(self):
        """set_gain('auto') sets gain to 'auto' on the underlying device."""
        from vtms_sdr.sdr import SDRDevice

        sdr = SDRDevice(device_index=0)
        sdr._sdr = MagicMock()
        sdr.set_gain("auto")
        assert sdr._sdr.gain == "auto"

    def test_set_gain_raises_when_closed(self):
        """set_gain() raises RuntimeError if device not open."""
        from vtms_sdr.sdr import SDRDevice

        sdr = SDRDevice(device_index=0)
        sdr._sdr = None
        with pytest.raises(RuntimeError, match="not open"):
            sdr.set_gain(20.0)


class TestSDRDeviceSetPPM:
    """Test SDRDevice.set_ppm() individual setter."""

    def test_set_ppm(self):
        """set_ppm(5) sets freq_correction to 5."""
        from vtms_sdr.sdr import SDRDevice

        sdr = SDRDevice(device_index=0)
        sdr._sdr = MagicMock()
        sdr.set_ppm(5)
        assert sdr._sdr.freq_correction == 5

    def test_set_ppm_zero(self):
        """set_ppm(0) sets freq_correction to 0."""
        from vtms_sdr.sdr import SDRDevice

        sdr = SDRDevice(device_index=0)
        sdr._sdr = MagicMock()
        sdr.set_ppm(0)
        assert sdr._sdr.freq_correction == 0

    def test_set_ppm_raises_when_closed(self):
        """set_ppm() raises RuntimeError if device not open."""
        from vtms_sdr.sdr import SDRDevice

        sdr = SDRDevice(device_index=0)
        sdr._sdr = None
        with pytest.raises(RuntimeError, match="not open"):
            sdr.set_ppm(5)


class TestDitheringCompat:
    """SDRDevice.open() must work with upstream librtlsdr (no dithering symbol)."""

    def test_open_succeeds_without_dithering_symbol(self):
        """open() works when rtlsdr_set_dithering is missing from librtlsdr."""
        import sys
        import types

        # Simulate what happens when pyrtlsdr's librtlsdr.py hits a missing
        # rtlsdr_set_dithering symbol: `from rtlsdr import RtlSdr` raises
        # AttributeError.  Our open() should handle this and still succeed.

        fake_device = FakeRtlSdr()

        # A constructor that blows up on first call (simulating the unpatched
        # import), then succeeds on retry (after our shim fixes things).
        call_count = 0

        class FakeRtlSdrClass:
            def __init__(self, device_index=0, **kwargs):
                nonlocal call_count
                call_count += 1
                self.__dict__.update(fake_device.__dict__)
                self.close = fake_device.close
                self.read_samples = fake_device.read_samples

        # Patch the import path so SDRDevice.open() finds our fake
        with patch.dict(sys.modules):
            # Remove any cached rtlsdr modules so open() reimports
            for mod_name in list(sys.modules):
                if mod_name.startswith("rtlsdr"):
                    del sys.modules[mod_name]

            # Create fake rtlsdr module with RtlSdr that raises like the
            # real one does when dithering symbol is missing
            fake_rtlsdr = types.ModuleType("rtlsdr")

            first_import = True

            original_import = (
                __builtins__.__import__
                if hasattr(__builtins__, "__import__")
                else __import__
            )

            def fake_import(name, *args, **kwargs):
                nonlocal first_import
                if name == "rtlsdr" or (
                    name == "" and args and args[0] and "rtlsdr" in str(args[0])
                ):
                    if first_import:
                        first_import = False
                        raise AttributeError(
                            "/lib64/librtlsdr.so.2: undefined symbol: rtlsdr_set_dithering"
                        )
                    # Second import succeeds
                    fake_rtlsdr.RtlSdr = FakeRtlSdrClass
                    sys.modules["rtlsdr"] = fake_rtlsdr
                    return fake_rtlsdr
                return original_import(name, *args, **kwargs)

            sdr = SDRDevice(device_index=0)

            with patch("builtins.__import__", side_effect=fake_import):
                sdr.open()

            assert sdr._sdr is not None

    def test_open_still_raises_for_real_import_errors(self):
        """open() still raises RuntimeError for genuine import failures."""
        import sys

        sdr = SDRDevice(device_index=0)

        with patch.dict(sys.modules):
            for mod_name in list(sys.modules):
                if mod_name.startswith("rtlsdr"):
                    del sys.modules[mod_name]

            def fake_import(name, *args, **kwargs):
                if name == "rtlsdr":
                    raise ImportError("No module named 'rtlsdr'")
                return __import__(name, *args, **kwargs)

            with patch("builtins.__import__", side_effect=fake_import):
                with pytest.raises(RuntimeError, match="pyrtlsdr is not installed"):
                    sdr.open()

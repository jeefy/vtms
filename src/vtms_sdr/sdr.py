"""RTL-SDR device management: open, configure, and stream IQ samples."""

from __future__ import annotations

import logging
import sys
from typing import Generator

import numpy as np

from .utils import format_frequency, validate_frequency

logger = logging.getLogger(__name__)


def _patch_librtlsdr_compat() -> None:
    """Patch pyrtlsdr to work with upstream librtlsdr (missing blog-fork symbols).

    The ``pyrtlsdr`` package eagerly binds ``rtlsdr_set_dithering`` (and several
    GPIO helpers) at import time.  These symbols only exist in the *rtl-sdr-blog*
    fork — they are absent from the upstream ``librtlsdr`` shipped by most distros
    (including Fedora).

    This function removes any partially-loaded ``rtlsdr`` sub-modules, monkey-
    patches the ctypes library object so the missing symbol resolves to a no-op,
    and allows a clean re-import.
    """
    import ctypes

    # Remove partially-loaded rtlsdr modules so the next import starts fresh.
    for mod_name in [k for k in sys.modules if k.startswith("rtlsdr")]:
        del sys.modules[mod_name]

    # Load the raw shared library ourselves so we can patch it.
    from ctypes.util import find_library

    lib_path = find_library("rtlsdr")
    if lib_path is None:
        # Let the subsequent import produce the normal "Error loading librtlsdr"
        return

    lib = ctypes.CDLL(lib_path)

    # Symbols added by rtl-sdr-blog that upstream lacks.  pyrtlsdr binds them
    # unconditionally at import time; stub out any that are missing.
    _blog_only_symbols = [
        "rtlsdr_set_dithering",
        "rtlsdr_set_gpio_output",
        "rtlsdr_set_gpio_input",
        "rtlsdr_set_gpio_bit",
        "rtlsdr_get_gpio_bit",
        "rtlsdr_set_gpio_byte",
        "rtlsdr_get_gpio_byte",
        "rtlsdr_set_gpio_status",
    ]

    patched_any = False
    for sym in _blog_only_symbols:
        if not hasattr(lib, sym):
            # ctypes resolves names via __getattr__ → dlsym.  Setting an
            # attribute directly on the CDLL shadows __getattr__, so
            # pyrtlsdr's `f = librtlsdr.<sym>` will find our stub instead
            # of calling dlsym (which would fail).
            stub = ctypes.CFUNCTYPE(ctypes.c_int)(lambda *a: 0)
            setattr(lib, sym, stub)
            patched_any = True

    if patched_any:
        logger.debug(
            "Patched upstream librtlsdr for pyrtlsdr compatibility "
            "(missing blog-fork symbols stubbed out)"
        )


__all__ = [
    "DEFAULT_BLOCK_SIZE",
    "DEFAULT_SAMPLE_RATE",
    "SDRDevice",
]

# Default sample rate suitable for wideband FM and general use
DEFAULT_SAMPLE_RATE = 2_400_000  # 2.4 Msps
DEFAULT_BLOCK_SIZE = 262_144  # ~109ms of samples at 2.4 Msps


class SDRDevice:
    """Context manager wrapping an RTL-SDR dongle via pyrtlsdr.

    Usage:
        with SDRDevice() as sdr:
            sdr.configure(center_freq=146_520_000, gain='auto')
            for iq_block in sdr.stream():
                process(iq_block)
    """

    def __init__(self, device_index: int = 0):
        self._device_index = device_index
        self._sdr = None

    def __enter__(self) -> SDRDevice:
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def open(self) -> None:
        """Open the RTL-SDR device.

        Raises:
            RuntimeError: If no device is found or device can't be opened.
        """
        try:
            from rtlsdr import RtlSdr
        except ImportError:
            raise RuntimeError(
                "pyrtlsdr is not installed. Install with: pip install pyrtlsdr\n"
                "Also ensure librtlsdr is installed on your system."
            )
        except AttributeError as exc:
            if "rtlsdr_set_dithering" not in str(exc):
                raise
            # Upstream librtlsdr lacks blog-fork symbols.  Patch and retry.
            logger.info(
                "Upstream librtlsdr detected (missing dithering symbol). "
                "Applying compatibility shim."
            )
            _patch_librtlsdr_compat()
            from rtlsdr import RtlSdr

        try:
            self._sdr = RtlSdr(self._device_index)
        except Exception as e:
            error_msg = str(e).lower()
            if "no" in error_msg and ("device" in error_msg or "found" in error_msg):
                raise RuntimeError("No RTL-SDR device found. Is it plugged in?") from e
            elif "busy" in error_msg or "claimed" in error_msg:
                raise RuntimeError(
                    "RTL-SDR device is busy. "
                    "Check for other SDR applications (gqrx, rtl_fm, etc)."
                ) from e
            else:
                raise RuntimeError(f"Failed to open RTL-SDR device: {e}") from e

    def close(self) -> None:
        """Close the RTL-SDR device."""
        if self._sdr is not None:
            try:
                self._sdr.close()
            except Exception:
                pass
            self._sdr = None

    def configure(
        self,
        center_freq: int,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        gain: str | float = "auto",
        ppm: int = 0,
    ) -> None:
        """Configure the SDR device parameters.

        Args:
            center_freq: Center frequency in Hz.
            sample_rate: Sample rate in samples/second.
            gain: Gain in dB, or 'auto' for automatic gain.
            ppm: Crystal oscillator frequency correction in parts-per-million.
                 Use ``rtl_test -p`` to measure your dongle's PPM error.

        Raises:
            RuntimeError: If device is not open.
            ValueError: If frequency is out of range.
        """
        if self._sdr is None:
            raise RuntimeError("SDR device is not open")

        validate_frequency(center_freq)

        self._sdr.sample_rate = sample_rate
        self._sdr.center_freq = center_freq

        if ppm:
            self._sdr.freq_correction = int(ppm)

        if gain == "auto":
            self._sdr.gain = "auto"
        else:
            self._sdr.gain = float(gain)

    def set_gain(self, gain: str | float) -> None:
        """Set the SDR gain at runtime.

        Args:
            gain: Gain in dB, or 'auto' for automatic gain.

        Raises:
            RuntimeError: If device is not open.
        """
        if self._sdr is None:
            raise RuntimeError("SDR device is not open")

        if gain == "auto":
            self._sdr.gain = "auto"
        else:
            self._sdr.gain = float(gain)

    def set_ppm(self, ppm: int) -> None:
        """Set the PPM frequency correction at runtime.

        Args:
            ppm: Crystal oscillator frequency correction in parts-per-million.

        Raises:
            RuntimeError: If device is not open.
        """
        if self._sdr is None:
            raise RuntimeError("SDR device is not open")

        self._sdr.freq_correction = int(ppm)

    def stream(
        self,
        block_size: int = DEFAULT_BLOCK_SIZE,
    ) -> Generator[np.ndarray, None, None]:
        """Yield blocks of complex IQ samples from the SDR.

        Each block is a numpy array of complex64 values with shape (block_size,).
        Real part = I (in-phase), Imaginary part = Q (quadrature).

        Args:
            block_size: Number of IQ samples per block.

        Yields:
            numpy.ndarray of complex64 IQ samples.

        Raises:
            RuntimeError: If device is not open.
        """
        if self._sdr is None:
            raise RuntimeError("SDR device is not open")

        while True:
            try:
                samples = self._sdr.read_samples(block_size)
                yield np.array(samples, dtype=np.complex64)
            except KeyboardInterrupt:
                break
            except IOError as e:
                logger.warning("USB read error: %s. Attempting recovery...", e)
                try:
                    # Try to recover by re-reading
                    samples = self._sdr.read_samples(block_size)
                    yield np.array(samples, dtype=np.complex64)
                except Exception:
                    logger.error("Recovery failed. Stopping.")
                    break

    def read_samples(self, num_samples: int = DEFAULT_BLOCK_SIZE) -> np.ndarray:
        """Read a single block of IQ samples (non-streaming).

        Useful for scanner operations that need a single measurement.

        Args:
            num_samples: Number of samples to read.

        Returns:
            numpy.ndarray of complex64 IQ samples.
        """
        if self._sdr is None:
            raise RuntimeError("SDR device is not open")

        samples = self._sdr.read_samples(num_samples)
        return np.array(samples, dtype=np.complex64)

    @property
    def center_freq(self) -> int:
        """Current center frequency in Hz."""
        if self._sdr is None:
            return 0
        return int(self._sdr.center_freq)

    @property
    def sample_rate(self) -> int:
        """Current sample rate in samples/second."""
        if self._sdr is None:
            return 0
        return int(self._sdr.sample_rate)

    def get_info(self) -> dict:
        """Return device info as a dictionary."""
        if self._sdr is None:
            return {"status": "closed"}

        return {
            "center_freq": self.center_freq,
            "center_freq_str": format_frequency(self.center_freq),
            "sample_rate": self.sample_rate,
            "gain": self._sdr.gain,
        }

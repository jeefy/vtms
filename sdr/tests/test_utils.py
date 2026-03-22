"""Tests for vtms_sdr.utils."""

import pytest

from vtms_sdr.utils import (
    parse_frequency,
    validate_frequency,
    format_frequency,
    power_to_db,
    db_to_power,
    generate_frequency_list,
    estimate_scan_time,
    RTL_SDR_MIN_FREQ,
    RTL_SDR_MAX_FREQ,
)


class TestParseFrequency:
    def test_mhz_suffix(self):
        assert parse_frequency("146.52M") == 146_520_000

    def test_mhz_long_suffix(self):
        assert parse_frequency("146.52MHz") == 146_520_000

    def test_khz_suffix(self):
        assert parse_frequency("7200k") == 7_200_000

    def test_khz_long_suffix(self):
        assert parse_frequency("7200kHz") == 7_200_000

    def test_ghz_suffix(self):
        assert parse_frequency("1.42G") == 1_420_000_000

    def test_ghz_long_suffix(self):
        assert parse_frequency("1.42GHz") == 1_420_000_000

    def test_plain_number(self):
        assert parse_frequency("1420000000") == 1_420_000_000

    def test_hz_suffix(self):
        assert parse_frequency("1420000000Hz") == 1_420_000_000

    def test_case_insensitive(self):
        assert parse_frequency("146.52mhz") == 146_520_000
        assert parse_frequency("146.52MHZ") == 146_520_000

    def test_whitespace_stripped(self):
        assert parse_frequency("  146.52M  ") == 146_520_000

    def test_invalid_format(self):
        with pytest.raises(ValueError, match="Invalid frequency"):
            parse_frequency("not_a_freq")

    def test_invalid_suffix(self):
        with pytest.raises(ValueError, match="Invalid frequency"):
            parse_frequency("146.52X")

    def test_empty_string(self):
        with pytest.raises(ValueError, match="Invalid frequency"):
            parse_frequency("")


class TestValidateFrequency:
    def test_valid_vhf(self):
        validate_frequency(146_520_000)  # Should not raise

    def test_valid_uhf(self):
        validate_frequency(462_562_500)  # Should not raise

    def test_too_low(self):
        with pytest.raises(ValueError, match="out of RTL-SDR range"):
            validate_frequency(1_000_000)  # 1 MHz, below 24 MHz

    def test_too_high(self):
        with pytest.raises(ValueError, match="out of RTL-SDR range"):
            validate_frequency(2_000_000_000)  # 2 GHz, above 1.766 GHz

    def test_boundary_low(self):
        validate_frequency(RTL_SDR_MIN_FREQ)  # Should not raise

    def test_boundary_high(self):
        validate_frequency(RTL_SDR_MAX_FREQ)  # Should not raise


class TestFormatFrequency:
    def test_mhz(self):
        assert format_frequency(146_520_000) == "146.520 MHz"

    def test_ghz(self):
        assert format_frequency(1_420_000_000) == "1.420 GHz"

    def test_khz(self):
        assert format_frequency(25_000) == "25.000 kHz"

    def test_hz(self):
        assert format_frequency(500) == "500 Hz"


class TestPowerConversion:
    def test_power_to_db(self):
        assert abs(power_to_db(1.0) - 0.0) < 0.01

    def test_power_to_db_ten(self):
        assert abs(power_to_db(10.0) - 10.0) < 0.01

    def test_power_to_db_hundred(self):
        assert abs(power_to_db(100.0) - 20.0) < 0.01

    def test_power_to_db_zero(self):
        assert power_to_db(0.0) == -100.0

    def test_power_to_db_negative(self):
        assert power_to_db(-1.0) == -100.0

    def test_db_to_power(self):
        assert abs(db_to_power(0.0) - 1.0) < 0.01

    def test_db_to_power_ten(self):
        assert abs(db_to_power(10.0) - 10.0) < 0.01

    def test_roundtrip(self):
        original = 42.0
        assert abs(db_to_power(power_to_db(original)) - original) < 0.01


class TestGenerateFrequencyList:
    def test_basic_range(self):
        freqs = generate_frequency_list(100, 200, 50)
        assert freqs == [100, 150, 200]

    def test_step_larger_than_range(self):
        freqs = generate_frequency_list(100, 120, 50)
        assert freqs == [100]

    def test_start_equals_end_raises(self):
        with pytest.raises(ValueError, match="must be less than"):
            generate_frequency_list(100, 100, 10)

    def test_start_greater_than_end_raises(self):
        with pytest.raises(ValueError, match="must be less than"):
            generate_frequency_list(200, 100, 10)

    def test_zero_step_raises(self):
        with pytest.raises(ValueError, match="positive"):
            generate_frequency_list(100, 200, 0)

    def test_realistic_vhf_range(self):
        freqs = generate_frequency_list(144_000_000, 144_100_000, 25_000)
        assert len(freqs) == 5
        assert freqs[0] == 144_000_000
        assert freqs[-1] == 144_100_000


class TestEstimateScanTime:
    def test_basic(self):
        assert estimate_scan_time(10, 100) == 1.0

    def test_many_channels(self):
        assert estimate_scan_time(100, 100) == 10.0


import numpy as np


class TestIqPowerDb:
    def test_strong_signal(self):
        """Full-scale IQ should be near 0 dB."""
        from vtms_sdr.utils import iq_power_db

        iq = np.ones(1000, dtype=np.complex64) * (0.5 + 0.5j)
        db = iq_power_db(iq)
        assert -5 < db < 5

    def test_weak_signal(self):
        """Very weak IQ should be well below 0 dB."""
        from vtms_sdr.utils import iq_power_db

        iq = np.ones(1000, dtype=np.complex64) * (0.001 + 0.001j)
        db = iq_power_db(iq)
        assert db < -25

    def test_silence(self):
        """Zero IQ should return -100 dB (floor)."""
        from vtms_sdr.utils import iq_power_db

        iq = np.zeros(1000, dtype=np.complex64)
        db = iq_power_db(iq)
        assert db == -100.0

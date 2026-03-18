"""Demodulation engines for FM, AM, and SSB signals.

Each demodulator takes raw IQ samples from the SDR and produces
mono audio samples at 48 kHz suitable for recording.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np
from scipy.signal import decimate, firwin, lfilter, lfilter_zi

__all__ = [
    "AUDIO_SAMPLE_RATE",
    "AMDemodulator",
    "Demodulator",
    "FMDemodulator",
    "SSBDemodulator",
]


# Output audio sample rate
AUDIO_SAMPLE_RATE = 48_000


class Demodulator(ABC):
    """Base class for signal demodulators.

    Factory method:
        demod = Demodulator.create("fm", sample_rate=2_400_000)
    """

    def __init__(self, sample_rate: int):
        """Initialize demodulator.

        Args:
            sample_rate: Input IQ sample rate in samples/second.
        """
        self.sample_rate = sample_rate
        self.audio_rate = AUDIO_SAMPLE_RATE
        self._setup_filters()

    @abstractmethod
    def _setup_filters(self) -> None:
        """Set up DSP filters for this demodulation mode."""

    @abstractmethod
    def demodulate(self, iq_samples: np.ndarray) -> np.ndarray:
        """Demodulate IQ samples into audio samples.

        Args:
            iq_samples: Complex64 numpy array of IQ samples.

        Returns:
            Float32 numpy array of audio samples at 48 kHz.
        """

    @staticmethod
    def create(mode: str, sample_rate: int) -> Demodulator:
        """Factory method to create the appropriate demodulator.

        Args:
            mode: Modulation type ('fm', 'am', or 'ssb').
            sample_rate: Input IQ sample rate.

        Returns:
            Configured Demodulator instance.

        Raises:
            ValueError: If mode is not recognized.
        """
        mode = mode.lower().strip()
        if mode == "fm":
            return FMDemodulator(sample_rate)
        elif mode == "am":
            return AMDemodulator(sample_rate)
        elif mode == "ssb":
            return SSBDemodulator(sample_rate)
        else:
            raise ValueError(f"Unknown modulation '{mode}'. Supported: fm, am, ssb")

    @property
    def name(self) -> str:
        """Human-readable name of this demodulation mode."""
        return self.__class__.__name__.replace("Demodulator", "").upper()

    def _multi_decimate(self, signal: np.ndarray, factor: int) -> np.ndarray:
        """Decimate in multiple stages if factor is large."""
        result = signal
        remaining = factor

        while remaining > 1:
            if remaining > 13:
                stage_factor = 10 if remaining % 10 == 0 else min(remaining, 13)
            else:
                stage_factor = remaining

            if len(result) > stage_factor:
                result = decimate(result, stage_factor, ftype="fir")
            remaining //= stage_factor

            if remaining <= 0:
                break

        return result


class FMDemodulator(Demodulator):
    """Narrowband FM demodulator for two-way radio voice (Baofeng, GMRS, etc.).

    Designed for NBFM signals with ±5 kHz deviation (wide) or ±2.5 kHz
    (narrow). Uses the standard quadrature demodulation approach
    matching GNU Radio's ``analog.nbfm_rx``.

    DSP chain:
        IQ input
        -> DC offset removal (IIR high-pass on I and Q)
        -> decimate to intermediate rate (48 ksps)
        -> channel filter (±12.5 kHz, isolates NBFM signal)
        -> FM discriminator with proper gain scaling
        -> de-emphasis filter (75 µs time constant)
        -> high-pass filter at 300 Hz (removes CTCSS sub-tones)
        -> AGC (automatic gain control)
        -> soft-clip to [-1, 1]
        -> audio output at 48 kHz
    """

    # NBFM parameters
    _MAX_DEVIATION = 5_000  # Hz, ±5 kHz for wide NBFM (Baofeng default)
    _CHANNEL_CUTOFF = 12_500  # Hz, one-sided (half of 25 kHz channel spacing)
    _DEEMPH_TAU = 75e-6  # 75 µs de-emphasis (standard FM, -3dB at 2122 Hz)
    _CTCSS_HP_CUTOFF = 300  # Hz, high-pass to remove CTCSS sub-tones
    # AGC parameters
    _AGC_TARGET_RMS = 0.25  # Target RMS level for voice audio
    _AGC_ATTACK_TIME = 0.05  # Seconds — fast attack to catch voice onset
    _AGC_RELEASE_TIME = 0.4  # Seconds — slow release for natural sound
    _AGC_MAX_GAIN = 10.0  # Maximum amplification
    _AGC_MIN_GAIN = 0.5  # Minimum amplification (don't fully mute)
    _AGC_NOISE_GATE_RMS = 0.02  # Below this RMS, don't increase gain (noise gate)

    def _setup_filters(self) -> None:
        # --- Decimation to 48 ksps ---
        # We decimate the IQ signal down to 48 ksps (= audio rate).
        # scipy.decimate applies an anti-alias filter internally.
        # At 48 ksps Nyquist is 24 kHz, sufficient for ±12.5 kHz NBFM channel.
        self._decimation_factor = self.sample_rate // self.audio_rate
        if self._decimation_factor < 1:
            self._decimation_factor = 1

        # --- DC blocking filter (IIR high-pass at ~10 Hz) ---
        # RTL-SDR dongles have a DC spike at center frequency.
        # Single-pole IIR: y[n] = x[n] - x[n-1] + α·y[n-1]
        # α = (1 - sin(ω₀)) / cos(ω₀) where ω₀ = 2π·f₀/fs
        # At the post-decimation rate of 48 kHz, 10 Hz cutoff:
        w0 = 2.0 * np.pi * 10.0 / self.audio_rate
        self._dc_alpha = (1.0 - np.sin(w0)) / np.cos(w0)
        # lfilter coefficients: y[n] = x[n] - x[n-1] + α·y[n-1]
        self._dc_b = np.array([1.0, -1.0])
        self._dc_a = np.array([1.0, -self._dc_alpha])
        # Stateful filter initial conditions (one zi value per channel)
        self._dc_zi_i = np.zeros(1)
        self._dc_zi_q = np.zeros(1)

        # --- Channel isolation filter at 48 ksps ---
        # Cutoff at 12.5 kHz (one-sided), matching 25 kHz NBFM channel
        # spacing. Carson's rule: BW = 2×(5000+3000) = 16 kHz, so we
        # need at least ±8 kHz, but 12.5 kHz avoids rolloff losses.
        cutoff_norm = self._CHANNEL_CUTOFF / (self.audio_rate / 2)
        cutoff_norm = min(cutoff_norm, 0.99)
        self._channel_filter = firwin(101, cutoff_norm)
        self._channel_zi_i = np.zeros(100)  # filter state for I
        self._channel_zi_q = np.zeros(100)  # filter state for Q

        # --- FM discriminator gain ---
        # atan2 output is in radians [-π, +π] mapping to [-fs/2, +fs/2].
        # For NBFM with ±5 kHz deviation, the signal only occupies a
        # tiny fraction of that range. Scale to get [-1, +1] audio:
        #   gain = fs / (2π × max_deviation)
        # This matches GNU Radio's analog.quadrature_demod_cf gain.
        self._discriminator_gain = self.audio_rate / (2.0 * np.pi * self._MAX_DEVIATION)

        # --- De-emphasis filter (single-pole IIR) ---
        # y[n] = (1-α)·x[n] + α·y[n-1]
        # α = exp(-1 / (fs × τ))
        self._deemph_alpha = np.exp(-1.0 / (self.audio_rate * self._DEEMPH_TAU))
        self._deemph_b = np.array([1.0 - self._deemph_alpha])
        self._deemph_a = np.array([1.0, -self._deemph_alpha])
        self._deemph_zi = np.zeros(1)

        # --- CTCSS removal high-pass filter ---
        # Removes sub-audible CTCSS tones (67–254 Hz) from the audio.
        # Simple FIR high-pass at 300 Hz.
        hp_cutoff = self._CTCSS_HP_CUTOFF / (self.audio_rate / 2)
        hp_cutoff = max(hp_cutoff, 0.001)
        self._hp_filter = firwin(101, hp_cutoff, pass_zero=False)
        self._hp_zi = np.zeros(100)  # filter state (101 taps - 1)

        # --- AGC state ---
        self._agc_gain = 3.0  # Initial gain (same as old fixed gain)

        # State for continuous demodulation across blocks
        self._prev_sample = np.complex64(0)

    def demodulate(self, iq_samples: np.ndarray) -> np.ndarray:
        # Stage 1: Decimate IQ to 48 ksps.
        if self._decimation_factor > 1:
            iq_down = self._multi_decimate_complex(iq_samples, self._decimation_factor)
        else:
            iq_down = iq_samples

        # Stage 2: DC offset removal on I and Q.
        i_data = np.real(iq_down).astype(np.float64)
        q_data = np.imag(iq_down).astype(np.float64)
        i_data, self._dc_zi_i = self._dc_block(i_data, self._dc_zi_i)
        q_data, self._dc_zi_q = self._dc_block(q_data, self._dc_zi_q)
        iq_dc_removed = (i_data + 1j * q_data).astype(np.complex64)

        # Stage 3: Channel filter (lowpass at 8 kHz).
        i_filt, self._channel_zi_i = lfilter(
            self._channel_filter,
            1.0,
            np.real(iq_dc_removed),
            zi=self._channel_zi_i,
        )
        q_filt, self._channel_zi_q = lfilter(
            self._channel_filter,
            1.0,
            np.imag(iq_dc_removed),
            zi=self._channel_zi_q,
        )
        filtered = np.asarray(i_filt + 1j * q_filt, dtype=np.complex64)

        # Stage 4: FM discriminator with proper gain scaling.
        # Conjugate-multiply method: Δφ = angle(s[n] × conj(s[n-1]))
        delayed = np.empty_like(filtered)
        delayed[0] = self._prev_sample
        delayed[1:] = filtered[:-1]
        self._prev_sample = filtered[-1]

        phase_diff = np.angle(filtered * np.conj(delayed))
        audio = phase_diff * self._discriminator_gain

        # Stage 5: De-emphasis filter (75 µs).
        audio = self._apply_deemphasis(audio)

        # Stage 6: High-pass filter to remove CTCSS sub-tones.
        audio, self._hp_zi = lfilter(self._hp_filter, 1.0, audio, zi=self._hp_zi)
        audio = np.asarray(audio)

        # Stage 7: AGC — adjust gain based on signal level.
        audio = self._apply_agc(audio)

        # Stage 8: Soft-clip to [-1, 1] — no per-block normalization.
        # The discriminator gain gives us properly scaled audio;
        # just clip any over-deviated peaks.
        audio = np.clip(audio, -1.0, 1.0)

        return audio.astype(np.float32)

    def _dc_block(
        self,
        data: np.ndarray,
        zi: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Apply DC blocking high-pass IIR filter (vectorized via lfilter).

        y[n] = x[n] - x[n-1] + α·y[n-1]
        """
        out, zi_out = lfilter(self._dc_b, self._dc_a, data, zi=zi)
        return out, zi_out

    def _apply_deemphasis(self, audio: np.ndarray) -> np.ndarray:
        """Apply single-pole de-emphasis IIR filter (vectorized via lfilter).

        y[n] = (1-α)·x[n] + α·y[n-1]
        """
        out, self._deemph_zi = lfilter(
            self._deemph_b, self._deemph_a, audio, zi=self._deemph_zi
        )
        return out

    def _apply_agc(self, audio: np.ndarray) -> np.ndarray:
        """Apply automatic gain control.

        Uses a slow envelope follower to track signal level and adjust
        gain to maintain a consistent output level. Includes a noise
        gate to prevent amplifying silence.
        """
        rms = float(np.sqrt(np.mean(audio**2)))

        if rms < self._AGC_NOISE_GATE_RMS:
            # Below noise gate — apply current gain but don't increase it.
            # This prevents pumping up noise during silence.
            return audio * self._agc_gain

        # Compute desired gain to reach target RMS
        desired_gain = self._AGC_TARGET_RMS / (rms + 1e-10)
        desired_gain = np.clip(desired_gain, self._AGC_MIN_GAIN, self._AGC_MAX_GAIN)

        # Smooth gain change — fast attack, slow release
        block_duration = len(audio) / self.audio_rate
        if desired_gain < self._agc_gain:
            # Attack (signal got louder, reduce gain quickly)
            alpha = 1.0 - np.exp(-block_duration / self._AGC_ATTACK_TIME)
        else:
            # Release (signal got quieter, increase gain slowly)
            alpha = 1.0 - np.exp(-block_duration / self._AGC_RELEASE_TIME)

        self._agc_gain += alpha * (desired_gain - self._agc_gain)
        self._agc_gain = float(
            np.clip(self._agc_gain, self._AGC_MIN_GAIN, self._AGC_MAX_GAIN)
        )

        return audio * self._agc_gain

    def _multi_decimate_complex(self, signal: np.ndarray, factor: int) -> np.ndarray:
        """Decimate complex IQ signal in stages (I and Q independently)."""
        real = np.real(signal).astype(np.float64)
        imag = np.imag(signal).astype(np.float64)
        real = self._multi_decimate(real, factor)
        imag = self._multi_decimate(imag, factor)
        return (real + 1j * imag).astype(np.complex64)


class AMDemodulator(Demodulator):
    """AM envelope demodulator.

    Uses envelope detection (magnitude of analytic signal) to
    recover audio from AM signals. Works for standard AM broadcast
    and aviation band.

    DSP chain: IQ -> bandpass -> envelope (abs) -> DC removal -> decimate -> audio
    """

    def _setup_filters(self) -> None:
        # AM channel bandwidth ~10 kHz
        channel_bw = 10_000
        cutoff = channel_bw / self.sample_rate
        cutoff = min(cutoff, 0.99)
        self._channel_filter = firwin(101, cutoff)
        self._channel_zi = np.zeros(100)  # 101 taps - 1

        # DC removal filter (simple highpass)
        hp_cutoff = 100 / self.sample_rate  # 100 Hz highpass
        hp_cutoff = max(hp_cutoff, 0.001)
        self._dc_filter = firwin(101, hp_cutoff, pass_zero=False)
        self._dc_zi = np.zeros(100)  # 101 taps - 1

        self._decimation_factor = self.sample_rate // self.audio_rate

    def demodulate(self, iq_samples: np.ndarray) -> np.ndarray:
        # Apply channel filter (stateful across blocks)
        filtered, self._channel_zi = lfilter(
            self._channel_filter, 1.0, iq_samples, zi=self._channel_zi
        )
        filtered = np.asarray(filtered)

        # AM envelope detection: magnitude of complex signal
        envelope = np.abs(filtered)

        # Remove DC offset (stateful across blocks)
        audio, self._dc_zi = lfilter(self._dc_filter, 1.0, envelope, zi=self._dc_zi)
        audio = np.asarray(audio)

        # Decimate to audio rate
        if self._decimation_factor > 1:
            audio = self._multi_decimate(audio, self._decimation_factor)

        # Clip to [-1, 1] — no per-block normalization to preserve
        # relative amplitude across blocks.
        audio = np.clip(audio, -1.0, 1.0)

        return audio.astype(np.float32)


class SSBDemodulator(Demodulator):
    """Single Sideband (SSB) demodulator for amateur radio.

    Demodulates upper sideband (USB) by default, which is standard
    for VHF/UHF SSB. Uses frequency shifting and filtering to
    extract the sideband.

    DSP chain: IQ -> freq shift -> lowpass (3kHz) -> take real -> decimate -> audio
    """

    def __init__(self, sample_rate: int, sideband: str = "usb"):
        """Initialize SSB demodulator.

        Args:
            sample_rate: Input IQ sample rate.
            sideband: 'usb' for upper sideband, 'lsb' for lower.
        """
        self.sideband = sideband.lower()
        self._sample_count = 0
        super().__init__(sample_rate)

    def _setup_filters(self) -> None:
        # SSB voice bandwidth: 300 Hz - 3000 Hz
        ssb_bw = 3_000
        cutoff = ssb_bw / self.sample_rate
        cutoff = min(cutoff, 0.99)
        self._ssb_filter = firwin(201, cutoff)
        self._ssb_zi = np.zeros(200)  # 201 taps - 1

        self._decimation_factor = self.sample_rate // self.audio_rate

    def demodulate(self, iq_samples: np.ndarray) -> np.ndarray:
        n_samples = len(iq_samples)

        # For USB: the signal of interest is above the carrier (center freq)
        # For LSB: below the carrier
        # Apply a small frequency shift to center the sideband
        if self.sideband == "lsb":
            shift_freq = -1500  # Center of LSB passband
        else:
            shift_freq = 1500  # Center of USB passband

        # Generate mixing signal
        t = np.arange(self._sample_count, self._sample_count + n_samples)
        self._sample_count += n_samples
        mixer = np.exp(-2j * np.pi * shift_freq / self.sample_rate * t)

        # Shift frequency
        shifted = iq_samples * mixer.astype(np.complex64)

        # Lowpass filter to SSB bandwidth (stateful across blocks)
        filtered, self._ssb_zi = lfilter(
            self._ssb_filter, 1.0, shifted, zi=self._ssb_zi
        )
        filtered = np.asarray(filtered)

        # Take real part (product detector)
        audio = np.real(filtered)

        # Decimate to audio rate
        if self._decimation_factor > 1:
            audio = self._multi_decimate(audio, self._decimation_factor)

        # Clip to [-1, 1] — no per-block normalization to preserve
        # relative amplitude across blocks.
        audio = np.clip(audio, -1.0, 1.0)

        return audio.astype(np.float32)

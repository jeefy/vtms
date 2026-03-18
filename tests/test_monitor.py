"""Tests for the AudioMonitor class (live audio playback)."""

import queue
import threading
import time
from unittest.mock import MagicMock, patch, PropertyMock

import numpy as np
import pytest


class TestAudioMonitorInit:
    """Test AudioMonitor construction."""

    def test_default_volume(self):
        """AudioMonitor defaults to 50% volume."""
        from vtms_sdr.monitor import AudioMonitor

        monitor = AudioMonitor()
        assert monitor.volume == 0.5

    def test_custom_volume(self):
        """AudioMonitor accepts custom initial volume."""
        from vtms_sdr.monitor import AudioMonitor

        monitor = AudioMonitor(volume=0.8)
        assert monitor.volume == 0.8

    def test_default_sample_rate(self):
        """AudioMonitor defaults to 48000 Hz sample rate."""
        from vtms_sdr.monitor import AudioMonitor

        monitor = AudioMonitor()
        assert monitor.sample_rate == 48000

    def test_custom_sample_rate(self):
        """AudioMonitor accepts custom sample rate."""
        from vtms_sdr.monitor import AudioMonitor

        monitor = AudioMonitor(sample_rate=44100)
        assert monitor.sample_rate == 44100


class TestAudioMonitorVolume:
    """Test volume property behavior."""

    def test_set_volume(self):
        """Setting volume updates the value."""
        from vtms_sdr.monitor import AudioMonitor

        monitor = AudioMonitor()
        monitor.volume = 0.75
        assert monitor.volume == 0.75

    def test_volume_clamps_above_one(self):
        """Volume above 1.0 is clamped to 1.0."""
        from vtms_sdr.monitor import AudioMonitor

        monitor = AudioMonitor()
        monitor.volume = 1.5
        assert monitor.volume == 1.0

    def test_volume_clamps_below_zero(self):
        """Volume below 0.0 is clamped to 0.0."""
        from vtms_sdr.monitor import AudioMonitor

        monitor = AudioMonitor()
        monitor.volume = -0.3
        assert monitor.volume == 0.0

    def test_volume_zero(self):
        """Volume can be set to exactly 0."""
        from vtms_sdr.monitor import AudioMonitor

        monitor = AudioMonitor()
        monitor.volume = 0.0
        assert monitor.volume == 0.0

    def test_volume_one(self):
        """Volume can be set to exactly 1.0."""
        from vtms_sdr.monitor import AudioMonitor

        monitor = AudioMonitor()
        monitor.volume = 1.0
        assert monitor.volume == 1.0


class TestAudioMonitorFeed:
    """Test the feed() method that queues audio blocks."""

    def test_feed_enqueues_audio(self):
        """feed() adds audio block to the internal queue."""
        from vtms_sdr.monitor import AudioMonitor

        monitor = AudioMonitor()
        audio = np.zeros(1024, dtype=np.float32)
        monitor.feed(audio)
        assert not monitor._queue.empty()

    def test_feed_copies_audio(self):
        """feed() should copy the audio to avoid mutation issues."""
        from vtms_sdr.monitor import AudioMonitor

        monitor = AudioMonitor()
        audio = np.ones(1024, dtype=np.float32)
        monitor.feed(audio)
        # Mutate original
        audio[:] = 0.0
        # Queued copy should still be ones
        queued = monitor._queue.get_nowait()
        np.testing.assert_array_equal(queued, np.ones(1024, dtype=np.float32))

    def test_feed_drops_when_queue_full(self):
        """feed() drops blocks when queue is at max size (no memory growth)."""
        from vtms_sdr.monitor import AudioMonitor

        monitor = AudioMonitor()
        # Fill queue beyond reasonable size
        for i in range(monitor.MAX_QUEUE_SIZE + 10):
            monitor.feed(np.zeros(1024, dtype=np.float32))
        assert monitor._queue.qsize() <= monitor.MAX_QUEUE_SIZE


class TestAudioMonitorCallback:
    """Test the sounddevice output callback."""

    def test_callback_writes_audio_from_queue(self):
        """Callback pulls audio from queue and writes to output buffer."""
        from vtms_sdr.monitor import AudioMonitor

        monitor = AudioMonitor(volume=1.0)
        audio = np.full(1024, 0.5, dtype=np.float32)
        monitor.feed(audio)

        # Simulate sounddevice callback
        outdata = np.zeros((1024, 1), dtype=np.float32)
        monitor._audio_callback(outdata, 1024, None, None)

        expected = np.full((1024, 1), 0.5, dtype=np.float32)
        np.testing.assert_array_almost_equal(outdata, expected)

    def test_callback_applies_volume(self):
        """Callback scales audio by current volume."""
        from vtms_sdr.monitor import AudioMonitor

        monitor = AudioMonitor(volume=0.5)
        audio = np.full(1024, 0.8, dtype=np.float32)
        monitor.feed(audio)

        outdata = np.zeros((1024, 1), dtype=np.float32)
        monitor._audio_callback(outdata, 1024, None, None)

        expected = np.full((1024, 1), 0.4, dtype=np.float32)
        np.testing.assert_array_almost_equal(outdata, expected)

    def test_callback_writes_silence_when_queue_empty(self):
        """Callback writes zeros when no audio is available."""
        from vtms_sdr.monitor import AudioMonitor

        monitor = AudioMonitor()
        outdata = np.ones((1024, 1), dtype=np.float32)
        monitor._audio_callback(outdata, 1024, None, None)

        np.testing.assert_array_equal(outdata, np.zeros((1024, 1), dtype=np.float32))

    def test_callback_handles_partial_block(self):
        """When queued audio is shorter than requested, pad with silence."""
        from vtms_sdr.monitor import AudioMonitor

        monitor = AudioMonitor(volume=1.0)
        # Feed only 512 samples but callback wants 1024
        audio = np.full(512, 0.7, dtype=np.float32)
        monitor.feed(audio)

        outdata = np.zeros((1024, 1), dtype=np.float32)
        monitor._audio_callback(outdata, 1024, None, None)

        # First 512 should have audio, rest should be silence
        np.testing.assert_array_almost_equal(
            outdata[:512], np.full((512, 1), 0.7, dtype=np.float32)
        )
        np.testing.assert_array_equal(
            outdata[512:], np.zeros((512, 1), dtype=np.float32)
        )

    def test_callback_concatenates_multiple_blocks(self):
        """When multiple small blocks are queued, callback concatenates them."""
        from vtms_sdr.monitor import AudioMonitor

        monitor = AudioMonitor(volume=1.0)
        monitor.feed(np.full(256, 0.3, dtype=np.float32))
        monitor.feed(np.full(256, 0.6, dtype=np.float32))

        outdata = np.zeros((512, 1), dtype=np.float32)
        monitor._audio_callback(outdata, 512, None, None)

        np.testing.assert_array_almost_equal(
            outdata[:256], np.full((256, 1), 0.3, dtype=np.float32)
        )
        np.testing.assert_array_almost_equal(
            outdata[256:], np.full((256, 1), 0.6, dtype=np.float32)
        )


class TestAudioMonitorStartStop:
    """Test start/stop lifecycle with mocked sounddevice."""

    @patch("vtms_sdr.monitor.sd")
    def test_start_opens_output_stream(self, mock_sd):
        """start() creates and starts a sounddevice OutputStream."""
        from vtms_sdr.monitor import AudioMonitor

        monitor = AudioMonitor(sample_rate=48000)
        monitor.start()

        mock_sd.OutputStream.assert_called_once()
        call_kwargs = mock_sd.OutputStream.call_args[1]
        assert call_kwargs["samplerate"] == 48000
        assert call_kwargs["channels"] == 1
        mock_sd.OutputStream.return_value.start.assert_called_once()

    @patch("vtms_sdr.monitor.sd")
    def test_stop_closes_stream(self, mock_sd):
        """stop() stops and closes the sounddevice stream."""
        from vtms_sdr.monitor import AudioMonitor

        monitor = AudioMonitor()
        monitor.start()
        monitor.stop()

        mock_sd.OutputStream.return_value.stop.assert_called_once()
        mock_sd.OutputStream.return_value.close.assert_called_once()

    @patch("vtms_sdr.monitor.sd")
    def test_stop_without_start_is_safe(self, mock_sd):
        """stop() does nothing if start() was never called."""
        from vtms_sdr.monitor import AudioMonitor

        monitor = AudioMonitor()
        monitor.stop()  # Should not raise

    @patch("vtms_sdr.monitor.sd")
    def test_context_manager(self, mock_sd):
        """AudioMonitor works as a context manager."""
        from vtms_sdr.monitor import AudioMonitor

        with AudioMonitor() as monitor:
            assert monitor is not None
            mock_sd.OutputStream.return_value.start.assert_called_once()

        mock_sd.OutputStream.return_value.stop.assert_called_once()
        mock_sd.OutputStream.return_value.close.assert_called_once()

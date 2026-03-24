"""Tests for AudioWSServer WebSocket audio streaming."""

from __future__ import annotations

import asyncio
import struct
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest


class TestAudioWSServerLifecycle:
    """Test start/stop lifecycle of the WebSocket server."""

    def test_start_stop(self):
        """Server should start and stop without error."""
        from vtms_sdr.audio_ws import AudioWSServer

        server = AudioWSServer(host="127.0.0.1", port=0)
        server.start()
        try:
            assert server.port is not None
            assert server.port > 0
        finally:
            server.stop()

    def test_double_start_is_noop(self):
        """Calling start() twice should not raise."""
        from vtms_sdr.audio_ws import AudioWSServer

        server = AudioWSServer(host="127.0.0.1", port=0)
        server.start()
        try:
            port1 = server.port
            server.start()  # Should be a no-op
            assert server.port == port1
        finally:
            server.stop()

    def test_stop_without_start_is_noop(self):
        """Calling stop() without start() should not raise."""
        from vtms_sdr.audio_ws import AudioWSServer

        server = AudioWSServer(host="127.0.0.1", port=0)
        server.stop()  # Should not raise

    def test_port_zero_picks_ephemeral(self):
        """port=0 should bind to an ephemeral port."""
        from vtms_sdr.audio_ws import AudioWSServer

        server = AudioWSServer(host="127.0.0.1", port=0)
        server.start()
        try:
            assert server.port > 1024  # Ephemeral port range
        finally:
            server.stop()


class TestAudioWSServerBroadcast:
    """Test broadcasting audio data to connected clients."""

    def test_client_receives_broadcast(self):
        """A connected client should receive broadcast data."""
        from websockets.sync.client import connect

        from vtms_sdr.audio_ws import AudioWSServer

        server = AudioWSServer(host="127.0.0.1", port=0)
        server.start()
        try:
            with connect(f"ws://127.0.0.1:{server.port}") as ws:
                # Send some audio data
                audio = np.ones(128, dtype=np.float32)
                server.broadcast(audio.tobytes())

                # Client should receive it
                data = ws.recv(timeout=2)
                assert isinstance(data, bytes)
                received = np.frombuffer(data, dtype=np.float32)
                np.testing.assert_array_equal(received, audio)
        finally:
            server.stop()

    def test_multiple_clients_receive_broadcast(self):
        """Multiple connected clients should all receive broadcast data."""
        from websockets.sync.client import connect

        from vtms_sdr.audio_ws import AudioWSServer

        server = AudioWSServer(host="127.0.0.1", port=0)
        server.start()
        try:
            with (
                connect(f"ws://127.0.0.1:{server.port}") as ws1,
                connect(f"ws://127.0.0.1:{server.port}") as ws2,
            ):
                audio = np.ones(64, dtype=np.float32) * 0.5
                server.broadcast(audio.tobytes())

                data1 = ws1.recv(timeout=2)
                data2 = ws2.recv(timeout=2)
                assert data1 == data2
                assert data1 == audio.tobytes()
        finally:
            server.stop()

    def test_broadcast_without_clients_is_noop(self):
        """Broadcasting with no clients should not raise."""
        from vtms_sdr.audio_ws import AudioWSServer

        server = AudioWSServer(host="127.0.0.1", port=0)
        server.start()
        try:
            audio = np.zeros(128, dtype=np.float32)
            server.broadcast(audio.tobytes())  # Should not raise
        finally:
            server.stop()

    def test_broadcast_before_start_is_noop(self):
        """Broadcasting before start() should not raise."""
        from vtms_sdr.audio_ws import AudioWSServer

        server = AudioWSServer(host="127.0.0.1", port=0)
        server.broadcast(b"\x00" * 256)  # Should not raise

    def test_disconnected_client_cleaned_up(self):
        """After a client disconnects, broadcast should still work."""
        from websockets.sync.client import connect

        from vtms_sdr.audio_ws import AudioWSServer

        server = AudioWSServer(host="127.0.0.1", port=0)
        server.start()
        try:
            # Connect and disconnect a client
            ws = connect(f"ws://127.0.0.1:{server.port}")
            ws.close()
            time.sleep(0.1)  # Let the server process the disconnect

            # Broadcast should still work without error
            audio = np.zeros(64, dtype=np.float32)
            server.broadcast(audio.tobytes())

            # New client should still be able to connect and receive
            with connect(f"ws://127.0.0.1:{server.port}") as ws2:
                server.broadcast(audio.tobytes())
                data = ws2.recv(timeout=2)
                assert len(data) == 64 * 4  # float32 = 4 bytes each
        finally:
            server.stop()


class TestSessionAudioWS:
    """Test audio_ws integration in RecordConfig and RecordingSession."""

    def test_record_config_audio_ws_default_none(self):
        """RecordConfig.audio_ws should default to None."""
        from vtms_sdr.session import RecordConfig

        config = RecordConfig(
            freq=146_520_000,
            mod="fm",
            output_path=Path("test.wav"),
            audio_format="wav",
        )
        assert config.audio_ws is None

    def test_record_config_audio_ws_accepts_instance(self):
        """RecordConfig should accept an AudioWSServer instance."""
        from vtms_sdr.audio_ws import AudioWSServer
        from vtms_sdr.session import RecordConfig

        ws = AudioWSServer(host="127.0.0.1", port=0)
        config = RecordConfig(
            freq=146_520_000,
            mod="fm",
            output_path=Path("test.wav"),
            audio_format="wav",
            audio_ws=ws,
        )
        assert config.audio_ws is ws

    @patch("vtms_sdr.sdr.SDRDevice")
    @patch("vtms_sdr.demod.Demodulator")
    @patch("vtms_sdr.recorder.AudioRecorder")
    def test_session_broadcasts_audio(self, MockRecorder, MockDemod, MockSDR):
        """run() should broadcast demodulated audio via AudioWSServer."""
        from vtms_sdr.audio_ws import AudioWSServer
        from vtms_sdr.session import RecordConfig, RecordingSession

        iq_block = np.ones(256, dtype=np.complex64) * 0.5
        audio_chunk = np.zeros(128, dtype=np.float32)

        mock_sdr = MagicMock()
        mock_sdr.sample_rate = 2_048_000
        mock_sdr.center_freq = 146_520_000
        mock_sdr.get_info.return_value = {"gain": "auto"}
        mock_sdr.stream.return_value = iter([iq_block])
        MockSDR.return_value.__enter__ = MagicMock(return_value=mock_sdr)
        MockSDR.return_value.__exit__ = MagicMock(return_value=False)

        mock_demod = MagicMock()
        mock_demod.demodulate.return_value = audio_chunk
        mock_demod.pre_hp_audio = None
        MockDemod.create.return_value = mock_demod

        mock_recorder = MagicMock()
        mock_recorder.record.side_effect = lambda gen, **kw: (
            [_ for _ in gen],
            {"file": "test.wav", "audio_duration_sec": 0.0, "file_size_bytes": 0},
        )[1]
        MockRecorder.return_value = mock_recorder

        mock_ws = MagicMock(spec=AudioWSServer)
        config = RecordConfig(
            freq=146_520_000,
            mod="fm",
            output_path=Path("test.wav"),
            audio_format="wav",
            audio_ws=mock_ws,
        )
        session = RecordingSession(config)
        session.run()

        # broadcast should have been called with the audio bytes
        mock_ws.broadcast.assert_called_once()
        call_args = mock_ws.broadcast.call_args[0]
        received = np.frombuffer(call_args[0], dtype=np.float32)
        np.testing.assert_array_equal(received, audio_chunk)

    @patch("vtms_sdr.sdr.SDRDevice")
    @patch("vtms_sdr.demod.Demodulator")
    @patch("vtms_sdr.recorder.AudioRecorder")
    def test_session_no_audio_ws_still_works(self, MockRecorder, MockDemod, MockSDR):
        """run() should work fine without audio_ws."""
        from vtms_sdr.session import RecordConfig, RecordingSession

        mock_sdr = MagicMock()
        mock_sdr.sample_rate = 2_048_000
        mock_sdr.center_freq = 146_520_000
        mock_sdr.get_info.return_value = {"gain": "auto"}
        mock_sdr.stream.return_value = iter([])
        MockSDR.return_value.__enter__ = MagicMock(return_value=mock_sdr)
        MockSDR.return_value.__exit__ = MagicMock(return_value=False)

        MockDemod.create.return_value = MagicMock()

        mock_recorder = MagicMock()
        mock_recorder.record.return_value = {
            "file": "test.wav",
            "audio_duration_sec": 0.0,
            "file_size_bytes": 0,
        }
        MockRecorder.return_value = mock_recorder

        config = RecordConfig(
            freq=146_520_000,
            mod="fm",
            output_path=Path("test.wav"),
            audio_format="wav",
        )
        session = RecordingSession(config)
        stats = session.run()
        assert stats["file"] == "test.wav"


class TestCLIAudioWSFlag:
    """Test --audio-ws-port CLI option."""

    def test_audio_ws_port_in_help(self):
        """--audio-ws-port should appear in record --help."""
        from click.testing import CliRunner

        from vtms_sdr.cli import record

        runner = CliRunner()
        result = runner.invoke(record, ["--help"])
        assert "--audio-ws-port" in result.output

    @patch("vtms_sdr.session.RecordingSession")
    @patch("vtms_sdr.audio_ws.AudioWSServer")
    def test_audio_ws_port_creates_server(self, MockWSServer, MockSession):
        """--audio-ws-port should create and start an AudioWSServer."""
        from click.testing import CliRunner

        from vtms_sdr.cli import main

        MockSession.return_value.run.return_value = {
            "file": "test.wav",
            "audio_duration_sec": 0.0,
            "file_size_bytes": 0,
        }

        runner = CliRunner()
        result = runner.invoke(
            main,
            ["record", "-f", "146.52M", "--audio-ws-port", "9003"],
        )

        MockWSServer.assert_called_once()
        call_kwargs = MockWSServer.call_args
        assert (
            call_kwargs.kwargs.get("port") == 9003 or call_kwargs[1].get("port") == 9003
        )
        MockWSServer.return_value.start.assert_called_once()
        MockWSServer.return_value.stop.assert_called_once()

    @patch("vtms_sdr.session.RecordingSession")
    def test_no_audio_ws_port_no_server(self, MockSession):
        """Without --audio-ws-port, no AudioWSServer should be created."""
        from click.testing import CliRunner

        from vtms_sdr.cli import main

        MockSession.return_value.run.return_value = {
            "file": "test.wav",
            "audio_duration_sec": 0.0,
            "file_size_bytes": 0,
        }

        runner = CliRunner()
        with patch("vtms_sdr.audio_ws.AudioWSServer") as MockWSServer:
            result = runner.invoke(main, ["record", "-f", "146.52M"])
            MockWSServer.assert_not_called()

"""WebSocket server for streaming live PCM audio from SDR.

Runs an asyncio event loop in a background thread. Broadcasts binary
audio frames (float32 PCM) to all connected WebSocket clients.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any

from websockets.asyncio.server import broadcast, serve, Server

logger = logging.getLogger(__name__)

__all__ = ["AudioWSServer"]


class AudioWSServer:
    """Threaded WebSocket server that broadcasts PCM audio.

    Usage::

        server = AudioWSServer(host="0.0.0.0", port=9003)
        server.start()
        # ... in audio loop:
        server.broadcast(audio_bytes)
        # ... when done:
        server.stop()
    """

    def __init__(self, *, host: str = "0.0.0.0", port: int = 9003) -> None:
        self._host = host
        self._port = port
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._server: Server | None = None
        self._connections: set = set()
        self._started = False
        self._ready = threading.Event()

    @property
    def port(self) -> int | None:
        """The actual port the server is listening on (after start)."""
        if self._server is not None:
            # Get the actual bound port from the server's socket
            for sock in self._server.sockets:
                return sock.getsockname()[1]
        return None

    def start(self) -> None:
        """Start the WebSocket server in a background thread."""
        if self._started:
            return

        self._loop = asyncio.new_event_loop()
        self._ready.clear()

        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="audio-ws"
        )
        self._thread.start()
        self._ready.wait(timeout=5.0)
        self._started = True

    def stop(self) -> None:
        """Stop the server and wait for background thread to exit."""
        if not self._started:
            return

        if self._loop is not None and self._server is not None:
            self._loop.call_soon_threadsafe(self._server.close)

        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None

        self._loop = None
        self._server = None
        self._connections.clear()
        self._started = False

    def broadcast(self, data: bytes) -> None:
        """Broadcast binary audio data to all connected clients.

        Safe to call from any thread. No-op if server is not started
        or no clients are connected.
        """
        if not self._started or not self._connections:
            return

        # broadcast() from websockets is synchronous and thread-safe
        # when called with the connections set
        try:
            broadcast(self._connections, data)
        except Exception:
            logger.debug("Broadcast error (client likely disconnected)", exc_info=True)

    def _run_loop(self) -> None:
        """Run the asyncio event loop in the background thread."""
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._serve())
        except asyncio.CancelledError:
            pass  # Expected when stop() closes the server

    async def _serve(self) -> None:
        """Start the WebSocket server and run until closed."""
        async with serve(self._handler, self._host, self._port) as server:
            self._server = server
            self._ready.set()
            await server.serve_forever()

    async def _handler(self, websocket) -> None:
        """Handle a WebSocket connection."""
        self._connections.add(websocket)
        try:
            await websocket.wait_closed()
        finally:
            self._connections.discard(websocket)

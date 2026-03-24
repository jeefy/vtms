"""Thread-safe shared state bus for SDR session state.

Provides a central state store that the recording session publishes to
and consumers (MQTT bridge, UI) subscribe to for change notifications.
"""

from __future__ import annotations

import copy
import logging
import threading
from typing import Any, Callable

logger = logging.getLogger(__name__)

__all__ = ["StateManager"]

# Type aliases for callbacks
StateCallback = Callable[[str, Any], None]
ControlCallback = Callable[[str, Any], None]


class StateManager:
    """Thread-safe shared state bus.

    - ``update(key, value)`` — session publishes state changes
    - ``subscribe(callback)`` — consumers register for change notifications
    - ``snapshot()`` — returns current state as dict (deep copy)
    - ``dispatch_control(action, value)`` — control commands flow back to session
    - ``on_control(callback)`` — register control handler
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state: dict[str, Any] = {}
        self._subscribers: list[StateCallback] = []
        self._control_handlers: list[ControlCallback] = []

    def update(self, key: str, value: Any) -> None:
        """Update a state key and notify subscribers if the value changed."""
        with self._lock:
            if key in self._state and self._state[key] == value:
                return
            self._state[key] = (
                copy.deepcopy(value) if isinstance(value, (list, dict, set)) else value
            )
            subscribers = list(self._subscribers)

        for cb in subscribers:
            try:
                cb(key, value)
            except Exception:
                logger.warning("State subscriber error for key %r", key, exc_info=True)

    def snapshot(self) -> dict[str, Any]:
        """Return a deep copy of the current state."""
        with self._lock:
            return copy.deepcopy(self._state)

    def subscribe(self, callback: StateCallback) -> Callable[[], None]:
        """Register a callback for state change notifications.

        Returns an unsubscribe function.
        """
        with self._lock:
            self._subscribers.append(callback)

        def unsubscribe() -> None:
            with self._lock:
                try:
                    self._subscribers.remove(callback)
                except ValueError:
                    pass

        return unsubscribe

    def dispatch_control(self, action: str, value: Any) -> None:
        """Dispatch a control command to registered handlers."""
        with self._lock:
            handlers = list(self._control_handlers)

        for cb in handlers:
            try:
                cb(action, value)
            except Exception:
                logger.warning(
                    "Control handler error for action %r", action, exc_info=True
                )

    def on_control(self, callback: ControlCallback) -> None:
        """Register a handler for control commands."""
        with self._lock:
            self._control_handlers.append(callback)

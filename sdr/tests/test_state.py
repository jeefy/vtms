"""Tests for state.py: StateManager thread-safe shared state bus."""

from __future__ import annotations

import threading
import time

import pytest


class TestStateManagerImport:
    """Test StateManager is importable."""

    def test_can_import(self):
        from vtms_sdr.state import StateManager


class TestStateManagerUpdate:
    """Test state update and retrieval."""

    def test_update_stores_value(self):
        from vtms_sdr.state import StateManager

        sm = StateManager()
        sm.update("freq", 146_520_000)
        assert sm.snapshot()["freq"] == 146_520_000

    def test_update_overwrites_previous(self):
        from vtms_sdr.state import StateManager

        sm = StateManager()
        sm.update("freq", 100_000)
        sm.update("freq", 200_000)
        assert sm.snapshot()["freq"] == 200_000

    def test_update_multiple_keys(self):
        from vtms_sdr.state import StateManager

        sm = StateManager()
        sm.update("freq", 146_520_000)
        sm.update("mod", "fm")
        sm.update("signal_power", -45.2)
        snap = sm.snapshot()
        assert snap["freq"] == 146_520_000
        assert snap["mod"] == "fm"
        assert snap["signal_power"] == -45.2


class TestStateManagerSnapshot:
    """Test snapshot returns independent copy."""

    def test_snapshot_empty(self):
        from vtms_sdr.state import StateManager

        sm = StateManager()
        assert sm.snapshot() == {}

    def test_snapshot_returns_copy(self):
        from vtms_sdr.state import StateManager

        sm = StateManager()
        sm.update("freq", 100_000)
        snap = sm.snapshot()
        snap["freq"] = 999
        assert sm.snapshot()["freq"] == 100_000

    def test_snapshot_deep_copies_mutable_values(self):
        from vtms_sdr.state import StateManager

        sm = StateManager()
        sm.update("transcriptions", [{"text": "hello", "ts": 1.0}])
        snap = sm.snapshot()
        snap["transcriptions"].append({"text": "world", "ts": 2.0})
        assert len(sm.snapshot()["transcriptions"]) == 1


class TestStateManagerSubscribe:
    """Test subscribe/notify for state changes."""

    def test_subscriber_called_on_update(self):
        from vtms_sdr.state import StateManager

        sm = StateManager()
        received = []
        sm.subscribe(lambda key, value: received.append((key, value)))
        sm.update("freq", 146_520_000)
        assert received == [("freq", 146_520_000)]

    def test_multiple_subscribers(self):
        from vtms_sdr.state import StateManager

        sm = StateManager()
        r1 = []
        r2 = []
        sm.subscribe(lambda k, v: r1.append((k, v)))
        sm.subscribe(lambda k, v: r2.append((k, v)))
        sm.update("mod", "am")
        assert r1 == [("mod", "am")]
        assert r2 == [("mod", "am")]

    def test_subscriber_not_called_for_same_value(self):
        """Subscribers should not fire when value hasn't changed."""
        from vtms_sdr.state import StateManager

        sm = StateManager()
        received = []
        sm.subscribe(lambda k, v: received.append((k, v)))
        sm.update("mod", "fm")
        sm.update("mod", "fm")
        assert len(received) == 1

    def test_subscriber_error_does_not_break_others(self):
        from vtms_sdr.state import StateManager

        sm = StateManager()
        r = []

        def bad_callback(k, v):
            raise RuntimeError("oops")

        sm.subscribe(bad_callback)
        sm.subscribe(lambda k, v: r.append((k, v)))
        sm.update("freq", 100_000)
        assert r == [("freq", 100_000)]

    def test_unsubscribe(self):
        from vtms_sdr.state import StateManager

        sm = StateManager()
        received = []
        unsub = sm.subscribe(lambda k, v: received.append((k, v)))
        sm.update("freq", 100_000)
        unsub()
        sm.update("freq", 200_000)
        assert len(received) == 1


class TestStateManagerControl:
    """Test control command dispatch."""

    def test_dispatch_control(self):
        from vtms_sdr.state import StateManager

        sm = StateManager()
        received = []
        sm.on_control(lambda action, value: received.append((action, value)))
        sm.dispatch_control("set_freq", 146_520_000)
        assert received == [("set_freq", 146_520_000)]

    def test_multiple_control_handlers(self):
        from vtms_sdr.state import StateManager

        sm = StateManager()
        r1 = []
        r2 = []
        sm.on_control(lambda a, v: r1.append((a, v)))
        sm.on_control(lambda a, v: r2.append((a, v)))
        sm.dispatch_control("set_squelch", -25.0)
        assert r1 == [("set_squelch", -25.0)]
        assert r2 == [("set_squelch", -25.0)]

    def test_control_handler_error_does_not_break_others(self):
        from vtms_sdr.state import StateManager

        sm = StateManager()
        r = []

        def bad_handler(a, v):
            raise RuntimeError("oops")

        sm.on_control(bad_handler)
        sm.on_control(lambda a, v: r.append((a, v)))
        sm.dispatch_control("set_gain", 40.0)
        assert r == [("set_gain", 40.0)]


class TestStateManagerThreadSafety:
    """Test thread safety of StateManager."""

    def test_concurrent_updates(self):
        from vtms_sdr.state import StateManager

        sm = StateManager()
        errors = []

        def writer(prefix, count):
            try:
                for i in range(count):
                    sm.update(f"{prefix}_{i}", i)
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=writer, args=(f"t{n}", 100)) for n in range(5)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        snap = sm.snapshot()
        # Each thread writes 100 keys with distinct prefixes
        assert len(snap) == 500

    def test_concurrent_subscribe_and_update(self):
        from vtms_sdr.state import StateManager

        sm = StateManager()
        received = []
        lock = threading.Lock()

        def collector(k, v):
            with lock:
                received.append((k, v))

        sm.subscribe(collector)

        def writer():
            for i in range(50):
                sm.update(f"key_{i}", i)

        t = threading.Thread(target=writer)
        t.start()
        t.join()

        assert len(received) == 50

"""Tests for LED controller topic-to-pin mapping.

Run on host with CPython/pytest.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest


class TestParseMessage:
    """Test MQTT message parsing for LED control."""

    def test_true_returns_high(self):
        from led_logic import parse_led_value

        assert parse_led_value(b"true") == 1

    def test_false_returns_low(self):
        from led_logic import parse_led_value

        assert parse_led_value(b"false") == 0

    def test_unknown_returns_none(self):
        from led_logic import parse_led_value

        assert parse_led_value(b"maybe") is None

    def test_case_insensitive_true(self):
        from led_logic import parse_led_value

        assert parse_led_value(b"True") == 1

    def test_empty_returns_none(self):
        from led_logic import parse_led_value

        assert parse_led_value(b"") is None

    def test_one_returns_high(self):
        from led_logic import parse_led_value

        assert parse_led_value(b"1") == 1

    def test_zero_returns_low(self):
        from led_logic import parse_led_value

        assert parse_led_value(b"0") == 0

    def test_on_returns_high(self):
        from led_logic import parse_led_value

        assert parse_led_value(b"on") == 1

    def test_off_returns_low(self):
        from led_logic import parse_led_value

        assert parse_led_value(b"off") == 0

    def test_uppercase_true(self):
        from led_logic import parse_led_value

        assert parse_led_value(b"TRUE") == 1

    def test_uppercase_false(self):
        from led_logic import parse_led_value

        assert parse_led_value(b"FALSE") == 0


class TestTopicToPin:
    """Test topic-to-pin mapping lookup."""

    def test_known_topic(self):
        from led_logic import topic_to_pin

        assert topic_to_pin(b"lemons/flag/black") == 14

    def test_red_flag(self):
        from led_logic import topic_to_pin

        assert topic_to_pin(b"lemons/flag/red") == 27

    def test_pit(self):
        from led_logic import topic_to_pin

        assert topic_to_pin(b"lemons/pit") == 26

    def test_box(self):
        from led_logic import topic_to_pin

        assert topic_to_pin(b"lemons/box") == 12

    def test_unknown_topic(self):
        from led_logic import topic_to_pin

        assert topic_to_pin(b"lemons/unknown") is None

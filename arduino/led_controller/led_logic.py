"""LED control logic: topic-to-pin mapping and message parsing.

Pure functions testable on host CPython.
"""

from config import LED_PINS


def parse_led_value(msg):
    """Parse MQTT message payload to pin value.

    Accepts: true/false, 1/0, on/off (case-insensitive).
    Returns 1, 0, or None for unrecognized values.
    """
    lower = msg.lower().strip()
    if lower in (b"true", b"1", b"on"):
        return 1
    elif lower in (b"false", b"0", b"off"):
        return 0
    return None


def topic_to_pin(topic):
    """Look up GPIO pin number for an MQTT topic.

    Returns pin number or None if topic is not mapped.
    """
    topic_str = topic.decode() if isinstance(topic, bytes) else topic
    return LED_PINS.get(topic_str)

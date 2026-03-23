"""LED control logic: topic-to-pin mapping and message parsing.

Pure functions testable on host CPython.
"""

from config import LED_PINS


def parse_led_value(msg):
    """Parse MQTT message payload to pin value.

    Returns 1 for "true", 0 for "false", None for unknown.
    """
    if msg == b"true":
        return 1
    elif msg == b"false":
        return 0
    return None


def topic_to_pin(topic):
    """Look up GPIO pin number for an MQTT topic.

    Returns pin number or None if topic is not mapped.
    """
    topic_str = topic.decode() if isinstance(topic, bytes) else topic
    return LED_PINS.get(topic_str)

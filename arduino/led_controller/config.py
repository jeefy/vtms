"""Configuration for ESP32 LED controller."""

# WiFi networks — loaded from generated secrets module (see .env)
try:
    from secrets import WIFI_NETWORKS
except ImportError:
    print("ERROR: secrets.py missing — run 'make generate-secrets'")
    WIFI_NETWORKS = []

WIFI_CONNECT_TIMEOUT = 15

# MQTT
MQTT_BROKER = "192.168.50.24"
MQTT_PORT = 1883
MQTT_CLIENT_PREFIX = "esp32-led"

# GPIO pin assignments for indicator LEDs
LED_PINS = {
    "lemons/flag/black": 14,
    "lemons/flag/red": 27,
    "lemons/pit": 26,
    "lemons/box": 12,
}

# MQTT subscription (wildcard covers all LED topics)
MQTT_SUBSCRIBE_TOPIC = "lemons/#"

# OTA
DEVICE_TYPE = "led_controller"
OTA_SERVER = "10.42.0.1:8266"

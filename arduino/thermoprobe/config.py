"""Configuration for ESP32 thermoprobe (MAX6675 thermocouple)."""

# WiFi networks (tried in order)
WIFI_NETWORKS = [
    ("vtms", ""),  # car-pi hotspot (OTA updates) -- set password
    ("The Grid", "REDACTED_WIFI_PASSWORD"),
]

WIFI_CONNECT_TIMEOUT = 15

# MQTT
MQTT_BROKER = "192.168.50.24"
MQTT_PORT = 1883
MQTT_CLIENT_PREFIX = "esp32-thermoprobe"

# MAX6675 SPI pins
THERMO_CLK = 14
THERMO_CS = 15
THERMO_DO = 12

# MQTT topic (preserving existing topic)
MQTT_TOPIC = "lemons/temp/oil_F"

# Timing
POLL_INTERVAL_MS = 500  # MAX6675 needs >= 250ms between reads

# OTA
DEVICE_TYPE = "thermoprobe"
OTA_SERVER = "10.42.0.1:8266"

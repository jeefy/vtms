"""Configuration for ESP32 analog temperature sensor."""

# WiFi networks (tried in order)
WIFI_NETWORKS = [
    ("vtms", ""),  # car-pi hotspot (OTA updates) -- set password
    ("The Grid", "REDACTED_WIFI_PASSWORD"),
]

WIFI_CONNECT_TIMEOUT = 15

# MQTT
MQTT_BROKER = "192.168.50.24"
MQTT_PORT = 1883
MQTT_CLIENT_PREFIX = "esp32-temp"

# ADC pin (ADC1 only -- ADC2 unavailable when WiFi active)
TEMP_ADC_PIN = 36  # GPIO36, ADC1_CH0 (equivalent to A0)

# ADC reference
V_REF = 3.3

# MQTT topic (preserving existing topic)
MQTT_TOPIC = "lemons/temp/transmission"

# Timing
POLL_INTERVAL_MS = 500

# OTA
DEVICE_TYPE = "temp_sensor"
OTA_SERVER = "10.42.0.1:8266"

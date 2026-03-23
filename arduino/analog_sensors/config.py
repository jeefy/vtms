"""Configuration for ESP32 analog sensor firmware."""

# WiFi networks — loaded from generated secrets module (see .env)
try:
    from secrets import WIFI_NETWORKS
except ImportError:
    print("ERROR: secrets.py missing — run 'make generate-secrets'")
    WIFI_NETWORKS = []

WIFI_CONNECT_TIMEOUT = 15  # seconds per SSID attempt

# MQTT
MQTT_BROKER = "192.168.50.24"
MQTT_PORT = 1883
MQTT_CLIENT_PREFIX = "esp32-analog"
MQTT_TOPIC_PREFIX = "lemons/analog"

# ADC pins (ADC1 only -- ADC2 unavailable when WiFi active)
FUEL_ADC_PIN = 34  # GPIO34, ADC1_CH6
OIL_ADC_PIN = 35  # GPIO35, ADC1_CH7

# ESP32 ADC reference voltage
V_REF = 3.3

# HiLetgo voltage module divider ratio (30k / 7.5k = 5:1)
# True gauge voltage = module_output * DIVIDER_RATIO
DIVIDER_RATIO = 5.0

# Fuel level calibration (empirical -- update after debug readings)
# These are MODULE OUTPUT voltages (after 5:1 division), not gauge voltages
FUEL_V_FULL = 0.20  # module output voltage at full tank (placeholder)
FUEL_V_EMPTY = 0.80  # module output voltage at empty tank (placeholder)

# Oil pressure calibration (empirical -- update after debug readings)
OIL_V_0PSI = 0.15  # module output voltage at 0 PSI (placeholder)
OIL_V_MAX = 0.70  # module output voltage at max PSI (placeholder)
OIL_MAX_PSI = 150.0  # max pressure rating of Greddy sender

# Smoothing (exponential moving average)
EMA_ALPHA = 0.3  # weight for new readings (0-1, higher = less smoothing)

# Timing
POLL_INTERVAL = 2  # seconds between sensor reads

# Debug mode (publishes raw voltages for calibration)
DEBUG = True

# OTA
DEVICE_TYPE = "analog_sensors"
OTA_SERVER = "10.42.0.1:8266"

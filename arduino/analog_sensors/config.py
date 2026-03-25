"""Configuration for ESP32 analog sensor firmware."""

# WiFi networks — loaded from generated secrets module (see .env)
try:
    from secrets import WIFI_NETWORKS, MQTT_BROKER, MQTT_PORT, OTA_SERVER
except ImportError:
    print("ERROR: secrets.py missing — run 'make generate-secrets'")
    WIFI_NETWORKS = []
    MQTT_BROKER = "192.168.50.24"
    MQTT_PORT = 1883
    OTA_SERVER = "100.84.179.100:8266"

WIFI_CONNECT_TIMEOUT = 15  # seconds per SSID attempt

# MQTT
MQTT_CLIENT_PREFIX = "esp32-analog"
MQTT_TOPIC_PREFIX = "lemons/analog"

# ADC pins (ADC1 only -- ADC2 unavailable when WiFi active)
FUEL_ADC_PIN = 34  # GPIO34, ADC1_CH6
OIL_ADC_PIN = 35  # GPIO35, ADC1_CH7

# Spare voltage sensor pins (raw voltage output for wiring verification)
SPARE_1_ADC_PIN = 32  # GPIO32, ADC1_CH4 (D32)
SPARE_2_ADC_PIN = 33  # GPIO33, ADC1_CH5 (D33)
SPARE_3_ADC_PIN = 36  # GPIO36, ADC1_CH0 (VP)

# Spare pin/topic pairs for iteration in main loop
SPARE_PINS = [
    (SPARE_1_ADC_PIN, "spare_1"),
    (SPARE_2_ADC_PIN, "spare_2"),
    (SPARE_3_ADC_PIN, "spare_3"),
]

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
POLL_INTERVAL = 1  # seconds between sensor reads

# Debug mode (publishes raw voltages for calibration)
DEBUG = False

# OTA
DEVICE_TYPE = "analog_sensors"

// ESP32 sketch to read an MLX90641 thermal camera and compute
// three tire zones: inside, middle, outside.
//
// Depends on the Melexis MLX90641 Arduino library (or compatible API):
// - MLX90641_API.h
// - MLX90641_I2C_Driver.h
// Installable from: https://github.com/Melexis/MLX90641-library (Arduino)
//
// Hardware:
// - Connect sensor VCC to 3.3V (or as required)
// - GND to GND
// - SDA to SDA (ESP32 default: GPIO21)
// - SCL to SCL (ESP32 default: GPIO22)
// - I2C address typically 0x33 for MLX90641
//
// This file is intentionally a .cpp so you can add it to an ESP32 Arduino
// project. If you prefer an .ino, rename accordingly.

#include <Wire.h>
#include "MLX90641_API.h"
#include "MLX90641_I2C_Driver.h"

// MQTT / WiFi (based on examples in repo)
#include <WiFi.h>
#include <PubSubClient.h>

// MAX6675 thermocouple support
#include "max6675.h"

// --- Edit these to match your WiFi / MQTT broker ---
const char *ssid = "The Grid"; // Enter your Wi-Fi name
const char *password = "REDACTED_WIFI_PASSWORD";  // Enter Wi-Fi password

// MQTT Broker
const char *mqtt_broker = "192.168.50.24";
const char *mqtt_base_topic = "vtms"; // base topic, we'll publish vtms/<vehicle>/<side>/<position>/[zone]
const char *mqtt_username = "";
const char *mqtt_password = "";
const int mqtt_port = 1883;

// Per-wheel configuration (customise per device)
const char *mqtt_vehicle = "car1";   // e.g. car1, truck2
const char *mqtt_side = "left";      // left or right
const char *mqtt_position = "front"; // front or rear

WiFiClient espClient;
PubSubClient mqttClient(espClient);

void mqttCallback(char *topic, byte *payload, unsigned int length)
{
    // simple echo debug callback
    char msg[length + 1];
    memcpy(msg, payload, length);
    msg[length] = '\0';
    Serial.printf("MQTT message arrived topic=%s payload=%s\n", topic, msg);
}

// --- MAX6675 configuration ---
// Number of thermocouples attached to this ESP32 (e.g., brake + wheel = 2)
#define NUM_THERMO 2
// SPI pins (shared): CLK and DO (MISO)
const int thermoCLK = 14;
const int thermoDO = 12;
// Chip-select pins per thermocouple (one CS per sensor). Edit to match your wiring.
int thermoCS[NUM_THERMO] = {15, 13};
// Logical names for each thermocouple (used in topic names)
const char *thermo_name[NUM_THERMO] = {"brake", "wheel"};

// MAX6675 objects (created in setup)
MAX6675 *thermos[NUM_THERMO];

// Assumed MLX90641 geometry. MLX90641 can come in different resolutions.
// A common variant is 16x12 (width=16, height=12). If your part differs,
// update WIDTH/HEIGHT appropriately.
#define WIDTH 16
#define HEIGHT 12
#define PIXELS (WIDTH * HEIGHT)

// MLX90641 I2C address (common default)
#define MLX_I2C_ADDR 0x33

// Change emissivity and any per-sensor offset here.
float emissivity = 0.98; // typical rubber/leather; tune as needed
float global_offset_c = 0.0; // global calibration offset in degC

paramsMLX90641 mlx90641;
float frameTo[PIXELS];
uint16_t frameData[PIXELS];
uint8_t eeMLX90641[832]; // size used by library for EEPROM dump (safe large buffer)

// region definitions: split width into three vertical zones (inside, middle, outside)
int col_split1, col_split2;

void setupSensor()
{
    // Initialize I2C
    Wire.begin();

    // Try to dump EEPROM and extract parameters
    int status = MLX90641_DumpEE(MLX_I2C_ADDR, eeMLX90641);
    if (status != 0)
    {
        Serial.print("MLX90641_DumpEE failed: ");
        Serial.println(status);
        return;
    }

    status = MLX90641_ExtractParameters(eeMLX90641, &mlx90641);
    if (status != 0)
    {
        Serial.print("MLX90641_ExtractParameters failed: ");
        Serial.println(status);
        return;
    }

    // Optionally set refresh rate: valid values are 0..8 (see library); choose 2 or 4
    MLX90641_SetRefreshRate(MLX_I2C_ADDR, 0x02); // example: 2 -> ~2Hz (tune as needed)
}

void connectWiFiAndMQTT()
{
    Serial.print("Connecting to WiFi '"); Serial.print(ssid); Serial.println("'...");
    WiFi.begin(ssid, password);
    while (WiFi.status() != WL_CONNECTED)
    {
        delay(500);
        Serial.println("Connecting to WiFi..");
    }
    Serial.println("Connected to the Wi-Fi network");

    mqttClient.setServer(mqtt_broker, mqtt_port);
    mqttClient.setCallback(mqttCallback);
    while (!mqttClient.connected())
    {
        String client_id = "esp32-client-";
        client_id += String(WiFi.macAddress());
        Serial.printf("The client %s connects to MQTT broker %s:%d\n", client_id.c_str(), mqtt_broker, mqtt_port);
        if (mqttClient.connect(client_id.c_str(), mqtt_username, mqtt_password))
        {
            Serial.println("MQTT broker connected");
        }
        else
        {
            Serial.print("failed with state ");
            Serial.print(mqttClient.state());
            delay(2000);
        }
    }

    // Announce
    mqttClient.publish(mqtt_base_topic, "MLX90641 Tire sensor online");
}

void setup()
{
    Serial.begin(115200);
    delay(200);
    Serial.println("MLX90641 Tire Temperature Monitor (ESP32)");

    // WiFi and MQTT
    connectWiFiAndMQTT();

    // Initialize MAX6675 thermocouple objects
    for (int i = 0; i < NUM_THERMO; i++)
    {
        // Ensure CS pin is set as output and high by default
        pinMode(thermoCS[i], OUTPUT);
        digitalWrite(thermoCS[i], HIGH);
        thermos[i] = new MAX6675(thermoCLK, thermoCS[i], thermoDO);
        delay(50); // small settle
    }

    setupSensor();

    col_split1 = WIDTH / 3; // inside: cols [0 .. col_split1-1]
    col_split2 = 2 * (WIDTH / 3); // middle: [col_split1 .. col_split2-1], outside: [col_split2 .. WIDTH-1]

    // Give sensor a moment to stabilise
    delay(500);
}

// Compute mean temperature of a rectangular region given column range
float regionAverage(int colStart, int colEnd)
{
    float sum = 0.0;
    int count = 0;
    for (int r = 0; r < HEIGHT; r++)
    {
        for (int c = colStart; c <= colEnd; c++)
        {
            int idx = r * WIDTH + c; // row-major index
            float t = frameTo[idx];
            if (!isnan(t) && isfinite(t))
            {
                sum += t;
                count++;
            }
        }
    }
    if (count == 0)
        return NAN;
    return sum / count;
}

void publishRegion(const char *zone, float value)
{
    if (!isfinite(value)) return;
    char buf[32];
    // Format with two decimals
    dtostrf(value, 6, 2, buf);
    // topic = mqtt_base_topic/vehicle/side/position/zone
    char topic[128];
    snprintf(topic, sizeof(topic), "%s/%s/%s/%s/%s", mqtt_base_topic, mqtt_vehicle, mqtt_side, mqtt_position, zone);
    mqttClient.publish(topic, buf);
}

void publishCombined(float inside, float middle, float outside)
{
    // publish a compact JSON object to mqtt_base_topic/vehicle/side/position
    char topic[128];
    snprintf(topic, sizeof(topic), "%s/%s/%s/%s", mqtt_base_topic, mqtt_vehicle, mqtt_side, mqtt_position);

    // Prepare string values
    char s_inside[16], s_middle[16], s_outside[16], s_ts[32];
    if (isfinite(inside)) dtostrf(inside, 6, 2, s_inside); else strcpy(s_inside, "null");
    if (isfinite(middle)) dtostrf(middle, 6, 2, s_middle); else strcpy(s_middle, "null");
    if (isfinite(outside)) dtostrf(outside, 6, 2, s_outside); else strcpy(s_outside, "null");

    // timestamp (ms since boot)
    unsigned long ts = millis();
    snprintf(s_ts, sizeof(s_ts), "%lu", ts);

    // Build JSON payload: {"ts":123,"inside":31.12,"middle":30.01,"outside":29.99}
    char payload[256];
    // Use numeric values in JSON; if null we add literal null
    const char *inside_val = (strcmp(s_inside, "null") == 0) ? "null" : s_inside;
    const char *middle_val = (strcmp(s_middle, "null") == 0) ? "null" : s_middle;
    const char *outside_val = (strcmp(s_outside, "null") == 0) ? "null" : s_outside;
    snprintf(payload, sizeof(payload), "{\"ts\":%s,\"inside\":%s,\"middle\":%s,\"outside\":%s}", s_ts, inside_val, middle_val, outside_val);

    mqttClient.publish(topic, payload);
}

void publishThermo(const char *name, float value)
{
    if (!isfinite(value)) return;
    char buf[32];
    dtostrf(value, 6, 2, buf);
    char topic[128];
    snprintf(topic, sizeof(topic), "%s/%s/%s/%s/thermocouple/%s", mqtt_base_topic, mqtt_vehicle, mqtt_side, mqtt_position, name);
    mqttClient.publish(topic, buf);
}

void publishThermoCombined()
{
    // publish JSON with all thermocouple readings at mqtt_base_topic/vehicle/side/position/thermocouples
    char topic[128];
    snprintf(topic, sizeof(topic), "%s/%s/%s/%s/thermocouples", mqtt_base_topic, mqtt_vehicle, mqtt_side, mqtt_position);

    char s_ts[32];
    unsigned long ts = millis();
    snprintf(s_ts, sizeof(s_ts), "%lu", ts);

    // Build payload incrementally
    char payload[512];
    int off = 0;
    off += snprintf(payload + off, sizeof(payload) - off, "{\"ts\":%s", s_ts);
    for (int i = 0; i < NUM_THERMO; i++)
    {
        float t = thermos[i]->readCelsius();
        if (isfinite(t))
        {
            char s[32]; dtostrf(t, 6, 2, s);
            off += snprintf(payload + off, sizeof(payload) - off, ",\"%s\":%s", thermo_name[i], s);
        }
        else
        {
            off += snprintf(payload + off, sizeof(payload) - off, ",\"%s\":null", thermo_name[i]);
        }
    }
    off += snprintf(payload + off, sizeof(payload) - off, "}");

    mqttClient.publish(topic, payload);
}

void loop()
{
    // Keep MQTT client running
    if (!mqttClient.connected())
    {
        // Try reconnecting
        connectWiFiAndMQTT();
    }
    mqttClient.loop();

    // Get raw frame (packed uint16_t values)
    int stat = MLX90641_GetFrameData(MLX_I2C_ADDR, frameData);
    if (stat != 0)
    {
        Serial.print("GetFrameData failed: ");
        Serial.println(stat);
        delay(200);
        return;
    }

    // Convert to temperatures (degC) using library helper
    // last parameter is the ambient temperature placeholder (we pass 0 and library computes internally)
    MLX90641_CalculateTo(frameData, &mlx90641, emissivity, frameTo);

    // Apply global offset
    for (int i = 0; i < PIXELS; i++)
    {
        frameTo[i] += global_offset_c;
    }

    // Compute region averages
    float inside_temp = regionAverage(0, col_split1 - 1);
    float middle_temp = regionAverage(col_split1, col_split2 - 1);
    float outside_temp = regionAverage(col_split2, WIDTH - 1);

    // Print a compact single-line CSV-friendly output with timestamp (millis)
    Serial.print(millis());
    Serial.print(", inside:"); Serial.print(inside_temp, 2);
    Serial.print(", middle:"); Serial.print(middle_temp, 2);
    Serial.print(", outside:"); Serial.println(outside_temp, 2);

    // Publish to MQTT
    publishRegion("inside", inside_temp);
    publishRegion("middle", middle_temp);
    publishRegion("outside", outside_temp);
    publishCombined(inside_temp, middle_temp, outside_temp);

    // Read and publish thermocouples
    for (int i = 0; i < NUM_THERMO; i++)
    {
        float t = thermos[i]->readCelsius();
        if (isfinite(t))
        {
            Serial.printf("thermo %s = %.2f C\n", thermo_name[i], t);
            publishThermo(thermo_name[i], t);
        }
        else
        {
            Serial.printf("thermo %s = (error)\n", thermo_name[i]);
        }
        delay(50); // small gap between CS toggles
    }
    publishThermoCombined();

    // Also print a small heatmap (optional, very simple)
    for (int r = 0; r < HEIGHT; r++)
    {
        for (int c = 0; c < WIDTH; c++)
        {
            float t = frameTo[r * WIDTH + c];
            // Visual map: map temperature to an ASCII char
            char ch;
            if (t < 20) ch = '.';
            else if (t < 30) ch = '-';
            else if (t < 40) ch = '*';
            else if (t < 60) ch = 'o';
            else ch = '#';
            Serial.print(ch);
        }
        Serial.println();
    }

    // Sleep/delay between frames. Refresh rate is set on device; respect that and add a small delay.
    delay(500);
}

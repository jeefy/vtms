#include <WiFi.h>
#include <PubSubClient.h>
#include "max6675.h"
// WiFi
//const char *ssid = "vtms"; // Enter your Wi-Fi name
//const char *password = "dangertomanifold";  // Enter Wi-Fi password
const char *ssid = "The Grid"; // Enter your Wi-Fi name
const char *password = "Get a Clu!";  // Enter Wi-Fi password

// MQTT Broker
const char *mqtt_broker = "192.168.50.24";
const char *topic = "emqx/esp32";
const char *mqtt_username = "";
const char *mqtt_password = "";
const int mqtt_port = 1883;

int thermoDO = 12;
int thermoCS = 15;
int thermoCLK = 14;

long temp_C, temp_F;
char buf[16];

MAX6675 thermocouple(thermoCLK, thermoCS, thermoDO);

WiFiClient espClient;
PubSubClient client(espClient);

void setup() {
    // initialize serial communication at 115200 bits per second:
    Serial.begin(115200);

    // Connecting to a WiFi network
    WiFi.begin(ssid, password);
    while (WiFi.status() != WL_CONNECTED) {
        delay(1000);
        Serial.println("Connecting to WiFi..");
    }
    Serial.println("Connected to the Wi-Fi network");
    //connecting to a mqtt broker
    client.setServer(mqtt_broker, mqtt_port);
    client.setCallback(callback);
    while (!client.connected()) {
        String client_id = "esp32-client-";
        client_id += String(WiFi.macAddress());
        Serial.printf("The client %s connects to the public MQTT broker\n", client_id.c_str());
        if (client.connect(client_id.c_str(), mqtt_username, mqtt_password)) {
            Serial.println("MQTT broker connected to The Grid");
        } else {
            Serial.print("failed with state ");
            Serial.print(client.state());
            delay(3000);
        }
    }
    // Publish and subscribe
    client.publish(topic, "Hi, I'm VTMS MQTT Sensor");
    client.subscribe(topic);
}

void callback(char *topic, byte *payload, unsigned int length) {
    char msg[length + 1];
    memcpy(msg, payload, length);
    msg[length] = '\0';
    Serial.printf("Message arrived in topic: %s\n", topic);
    Serial.printf("Message: %s\n", msg);
    Serial.println("-----------------------");
}

void loop() {
     // For the MAX6675 to update, you must delay AT LEAST 250ms between reads!
    temp_C = thermocouple.readCelsius();    /*Read Temperature on °C*/
    temp_F = thermocouple.readFahrenheit(); 

    // print out the values you read:
    Serial.printf("temp_C = %dC\n", temp_C);
    Serial.printf("temp_F = %dF\n", temp_F);
    ltoa(temp_F,buf,10);
    client.publish("lemons/temp/oil_F", buf);

    delay(500);  // delay in between reads for clear read from serial
}
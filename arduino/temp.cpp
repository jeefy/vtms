#include <WiFi.h>
#include <PubSubClient.h>
// WiFi
const char *ssid = "The Grid"; // Enter your Wi-Fi name
const char *password = "Get a Clu!";  // Enter Wi-Fi password

// MQTT Broker
const char *mqtt_broker = "192.168.50.24";
const char *topic = "emqx/esp32";
const char *mqtt_username = "";
const char *mqtt_password = "";
const int mqtt_port = 1883;

#define REF_VOLTAGE    3.3
#define ADC_RESOLUTION 4096.0

WiFiClient espClient;
PubSubClient client(espClient);

void setup() {
    // Set software serial baud to 9600;
    Serial.begin(9600);
    // Connecting to a WiFi network
    WiFi.begin(ssid, password);
    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
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
            delay(2000);
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
    int sensorValue = analogRead(A0);
    // Convert the analog reading (which goes from 0 - 1023) to a voltage (0 - 5V):
    float voltage = ((float)sensorValue * REF_VOLTAGE) / ADC_RESOLUTION;
    // print out the value you read:
    Serial.println(voltage);
    
    // Convert float to string for MQTT publishing
    char voltageStr[10];
    dtostrf(voltage, 6, 3, voltageStr);
    client.publish("lemons/temp/transmission", voltageStr);
    delay(500);
}
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
const byte led_gpio = 14;

WiFiClient espClient;
PubSubClient client(espClient);

void setup() {
    pinMode(led_gpio, OUTPUT);
    // Set software serial baud to 115200;
    Serial.begin(19200);
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
            Serial.println("Public EMQX MQTT broker connected");
        } else {
            Serial.print("failed with state ");
            Serial.print(client.state());
            delay(2000);
        }
    }
    // Publish and subscribe
    client.publish(topic, "Hi, I'm VTMS LED Controller");
    client.subscribe(topic);
}

void callback(char *topic, byte *payload, unsigned int length) {
    Serial.print("Message arrived in topic: ");
    Serial.println(topic);
    Serial.print("Message:");
    for (int i = 0; i < length; i++) {
        Serial.print((char) payload[i]);
    }
    Serial.println();
    Serial.println("-----------------------");
    if (strcmp(topic, "lemons/flag/black") == 0) {
        // Copy payload to a null-terminated string
        char msg[length + 1];
        memcpy(msg, payload, length);
        msg[length] = '\0';
        if (strcmp(msg, "true") == 0) {
            digitalWrite(led_gpio, HIGH);
        }
        if (strcmp(msg, "false") == 0) {
            digitalWrite(led_gpio, LOW);
        }
    }
}

void loop() {
    client.loop();
}

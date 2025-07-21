#!/usr/bin/env python3

import time, sys, signal
import paho.mqtt.client as mqtt
import sqlite3
from src import config

print('Not Fast Not Furious!')

# The callback for when the client receives a CONNACK response from the server.
def on_connect(client, userdata, flags, reason_code, properties):
    print(f"Connected with result code {reason_code}")
    # Subscribing in on_connect() means that if we lose the connection and
    # reconnect then subscriptions will be renewed.
    client.subscribe("lemons/#")

# The callback for when a PUBLISH message is received from the server.
def on_message(client, userdata, msg):
    print(msg.topic+" "+str(msg.payload)) 
    cur.execute("INSERT INTO telemetry VALUES(?, ?, ?)", (msg.topic, msg.payload, time.time()))

def graceful_shutdown():
    print()
    # the will_set is not sent on graceful shutdown by design
    # we need to wait until the message has been sent, else it will not appear in the broker
    mqttc.disconnect()
    mqttc.loop_stop()
    con.close()
    print("Graceful shutdown complete.")
    sys.exit(0)

# catch ctrl-c
def signal_handler(signum, frame):
    graceful_shutdown()


con = sqlite3.connect('data/logger.db', check_same_thread=False)
cur = con.cursor()
cur.execute("CREATE TABLE IF NOT EXISTS telemetry(metric, value, timestamp)")

mqttc = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
mqttc.on_connect = on_connect
mqttc.on_message = on_message
mqttc.connect(config.mqtt_server, 1883, 60)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

mqttc.loop_forever()

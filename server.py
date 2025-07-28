#!/usr/bin/env python3

import time, sys, signal
import paho.mqtt.client as mqtt
import psycopg2
import psycopg2.extras
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
    try:
        payload_str = str(msg.payload.decode('utf-8'))
        print(f"{msg.topic} {payload_str}")
        
        # Use parameterized query for PostgreSQL
        cur.execute("INSERT INTO telemetry (metric, value, timestamp) VALUES (%s, %s, %s)", 
                   (msg.topic, payload_str, time.time()))
        con.commit()  # Commit each transaction
        
    except Exception as e:
        print(f"Error inserting data: {e}")
        con.rollback()

def graceful_shutdown():
    print()
    # the will_set is not sent on graceful shutdown by design
    # we need to wait until the message has been sent, else it will not appear in the broker
    mqttc.disconnect()
    mqttc.loop_stop()
    if con:
        con.close()
    print("Graceful shutdown complete.")
    sys.exit(0)

# catch ctrl-c
def signal_handler(signum, frame):
    graceful_shutdown()


# PostgreSQL connection
try:
    # Use configuration from config module
    con = psycopg2.connect(
        host=config.config.postgres_host,
        database=config.config.postgres_database,
        user=config.config.postgres_user, 
        password=config.config.postgres_password,
        port=config.config.postgres_port
    )
    con.set_session(autocommit=False)  # Use explicit transactions
    cur = con.cursor()
    
    # Create table with PostgreSQL syntax and appropriate data types
    cur.execute("""
        CREATE TABLE IF NOT EXISTS telemetry (
            id SERIAL PRIMARY KEY,
            metric VARCHAR(255) NOT NULL,
            value TEXT,
            timestamp DOUBLE PRECISION NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Create index for better query performance
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_telemetry_metric_timestamp 
        ON telemetry(metric, timestamp)
    """)
    
    con.commit()
    print("PostgreSQL database connection established")
    
except psycopg2.Error as e:
    print(f"PostgreSQL connection error: {e}")
    sys.exit(1)

mqttc = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
mqttc.on_connect = on_connect
mqttc.on_message = on_message
mqttc.connect(config.mqtt_server, config.config.mqtt_port, config.config.mqtt_keepalive)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

mqttc.loop_forever()

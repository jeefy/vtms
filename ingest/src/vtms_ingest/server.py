#!/usr/bin/env python3
"""
VTMS Ingest Server

Subscribes to MQTT telemetry topics and persists messages to PostgreSQL.
"""

import signal
import sys

import paho.mqtt.client as mqtt
import psycopg2

from vtms_ingest.config import config

TELEMETRY_TOPICS = [
    "lemons/RPM",
    "lemons/SPEED",
    "lemons/COOLANT_TEMP",
    "lemons/OIL_TEMP",
    "lemons/THROTTLE_POS",
    "lemons/ENGINE_LOAD",
    "lemons/gps/#",
    "lemons/DTC/#",
    "lemons/fuel/#",
    "lemons/oil/#",
    "lemons/egt/#",
    "lemons/spare/#",
]


def on_connect(client, userdata, flags, reason_code, properties):
    """Handle MQTT CONNACK — subscribe to telemetry topics only."""
    print(f"Connected with result code {reason_code}")
    for topic in TELEMETRY_TOPICS:
        client.subscribe(topic)


def on_disconnect(client, userdata, flags, reason_code, properties):
    """Handle MQTT disconnect — paho reconnects automatically via loop_forever."""
    print(f"MQTT disconnected (rc={reason_code}), will auto-reconnect...")


def on_message(client, userdata, msg):
    """Handle incoming MQTT messages — insert into PostgreSQL."""
    global con, cur
    try:
        payload_str = str(msg.payload.decode("utf-8"))
        print(f"{msg.topic} {payload_str}")

        cur.execute(
            "INSERT INTO telemetry (metric, value) VALUES (%s, %s)",
            (msg.topic, payload_str),
        )
        con.commit()

    except psycopg2.OperationalError as e:
        print(f"DB connection lost: {e}, reconnecting...")
        try:
            con = psycopg2.connect(
                host=config.postgres_host,
                database=config.postgres_database,
                user=config.postgres_user,
                password=config.postgres_password,
                port=config.postgres_port,
            )
            con.set_session(autocommit=False)
            cur = con.cursor()
            print("DB reconnected")
        except psycopg2.Error as reconnect_err:
            print(f"DB reconnect failed: {reconnect_err}")

    except Exception as e:
        print(f"Error inserting data: {e}")
        try:
            con.rollback()
        except Exception:
            pass


def graceful_shutdown():
    """Disconnect MQTT and close DB connection."""
    print()
    mqttc.disconnect()
    mqttc.loop_stop()
    if con:
        con.close()
    print("Graceful shutdown complete.")
    sys.exit(0)


def signal_handler(signum, frame):
    graceful_shutdown()


def main():
    """Entry point for the ingest server."""
    global con, cur, mqttc

    print("Not Fast Not Furious!")
    config.validate_postgres()

    # PostgreSQL connection
    try:
        con = psycopg2.connect(
            host=config.postgres_host,
            database=config.postgres_database,
            user=config.postgres_user,
            password=config.postgres_password,
            port=config.postgres_port,
        )
        con.set_session(autocommit=False)
        cur = con.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS telemetry (
                id SERIAL PRIMARY KEY,
                metric VARCHAR(255) NOT NULL,
                value TEXT,
                timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

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
    mqttc.on_disconnect = on_disconnect
    mqttc.on_message = on_message
    mqttc.connect(config.mqtt_server, config.mqtt_port, config.mqtt_keepalive)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    mqttc.loop_forever()


if __name__ == "__main__":
    main()

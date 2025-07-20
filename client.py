import obd
from obd import OBDStatus

from src import myobd, config
from functools import partial

import paho.mqtt.client as mqtt

is_pi = config.is_raspberrypi()
if is_pi:
    from src import led

# Need them ol' Debug flags

# The callback for when the client receives a CONNACK response from the server.
def on_connect(client, userdata, flags, reason_code, properties):
    if config.getDebug():
        print(f"Connected with result code {reason_code}")
    # Subscribing in on_connect() means that if we lose the connection and
    # reconnect then subscriptions will be renewed.
    client.subscribe("lemons/#")

# The callback for when a PUBLISH message is received from the server.
def on_message(client, userdata, msg, obd2=None, mqttc=None):
    payload = str(msg.payload.decode("utf-8"))
    
    print(msg.topic+" " + payload)
    
    if is_pi:
        led.handler(msg, mqttc=mqttc)

    if msg.topic == 'lemons/obd2/watch':
        if payload in obd.commands:
            with connection.paused():
                obd2.watch(obd.commands[payload], callback=partial(myobd.new_metric, mqttc=mqttc))
    elif msg.topic == 'lemons/obd2/unwatch':
        if payload in obd.commands:
            with connection.paused():
                obd2.unwatch(obd.commands[payload])
    elif msg.topic == 'lemons/obd2/query':
        if payload in obd.commands:
            r = obd2.query(obd.commands[payload])

            if payload in myobd.metric_commands:
                myobd.new_metric(r, mqttc=mqttc)
            elif payload in myobd.monitor_commands:
                myobd.new_monitor(r, mqttc=mqttc)
            elif payload == 'GET_DTC':
                myobd.new_dtc(r, mqttc=mqttc)
            else:
                if config.getDebug():
                    print('ERR: No proper handler for query type "{}" -- defaulting to Metric'.format(payload))
                    myobd.new_metric(r, mqttc=mqttc)
    elif msg.topic == 'lemons/debug':
        if payload == 'true':
            config.setDebug(True)
            print('OBD2 - Debug mode enabled')
            print('{}'.format(config.getDebug()))
        else:
            print('OBD2 - Debug mode disabled')
            config.setDebug(False)
            print('{}'.format(config.getDebug()))
    elif msg.topic == 'lemons/message':
        # Output to screen
        print('Pit message: {}'.format(payload))
    elif msg.topic == 'lemons/flag/red' and payload == 'true':
        print('Red Flag: {}'.format(payload))
    elif msg.topic == 'lemons/flag/black' and payload == 'true':
        print('Black Flag: {}'.format(payload))
    elif msg.topic == 'lemons/pit' and payload == 'true':
        print('Pit Soon: {}'.format(payload))
    elif msg.topic == 'lemons/box' and payload == 'true':
        print('BOX BOX: {}'.format(payload))

while True:
    # Loop through ports = obd.scan_serial()  to try and connect to OBDII port
    ports = obd.scan_serial()
    print('Possible ports: ')
    print(ports)
    print('----')
    for port in ports:
        connection = obd.Async(port, delay_cmds=0, fast=True)

        if connection.status() is not OBDStatus.CAR_CONNECTED:
            print('OBD2 - No connection to OBDII port from {}'.format(port))
            continue
        else:
            print('OBD2 - Connected to OBDII port on {}'.format(port))
            break
            
    if connection.status() is not OBDStatus.CAR_CONNECTED:
        print('OBD2 - No connection to OBDII port')
        exit(1)

    mqttc = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    mqttc.on_connect = on_connect
    mqttc.on_message = partial(on_message, obd2=connection, mqttc=mqttc)
    mqttc.connect(config.mqtt_server, 1883, 60)
    mqttc.loop_start()

    for command in myobd.metric_commands:
        if connection.supports(obd.commands[command]):
            print('OBD2 - starting metrics watch for ', command)
            connection.watch(obd.commands[command], callback=partial(myobd.new_metric, mqttc=mqttc))
    
    for command in myobd.monitor_commands:
        if connection.supports(obd.commands[command]):
            print('OBD2 - starting monitor watch for ', command)
            connection.watch(obd.commands[command], callback=partial(myobd.new_monitor, mqttc=mqttc))
    
    
    connection.watch(obd.commands.GET_DTC, callback=partial(myobd.new_dtc, mqttc=mqttc))

    connection.start()

    mqttc.loop_forever()
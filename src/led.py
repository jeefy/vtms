import RPi.GPIO as GPIO    # Import Raspberry Pi GPIO library
from time import sleep     # Import the sleep function from the time module

mapping = {
    'box': 8,
    'pit': 10,
    'red': 12,
    'black': 16
}

def __init__():
    GPIO.setwarnings(False)    # Ignore warning for now

    GPIO.setmode(GPIO.BOARD)   # Use physical pin numbering
    for pin in mapping.values():
        GPIO.setup(pin, GPIO.OUT, initial=GPIO.LOW)

def handler(msg, mqttc=None):
    payload = str(msg.payload.decode("utf-8"))
    print(msg.topic+" " + payload)
    if msg.topic == 'lemons/flag/red':
        if payload == 'true':
            GPIO.output(mapping['red'], GPIO.HIGH)
        else:
            GPIO.output(mapping['red'], GPIO.LOW)
    elif msg.topic == 'lemons/flag/black':
        if payload == 'true':
            GPIO.output(mapping['black'], GPIO.HIGH)
        else:
            GPIO.output(mapping['black'], GPIO.LOW)
    elif msg.topic == 'lemons/pit':
        if payload == 'true':
            GPIO.output(mapping['pit'], GPIO.HIGH)
        else:
            GPIO.output(mapping['pit'], GPIO.LOW)
    elif msg.topic == 'lemons/box':
        if payload == 'true':
            GPIO.output(mapping['box'], GPIO.HIGH)
        else:
            GPIO.output(mapping['box'], GPIO.LOW)
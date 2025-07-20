debug = False
mqtt_server = "192.168.50.24"

def setDebug(val):
    global debug
    debug = val

def getDebug():
    return debug

def is_raspberrypi():
    try:
        with io.open('/sys/firmware/devicetree/base/model', 'r') as m:
            if 'raspberry pi' in m.read().lower(): return True
    except Exception: pass
    return False
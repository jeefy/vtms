debug = False
mqtt_server = "192.168.50.24"

def setDebug(val):
    global debug
    debug = val

def getDebug():
    return debug
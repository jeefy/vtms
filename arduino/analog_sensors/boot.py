"""Boot script: connect to WiFi on startup.

MicroPython runs boot.py automatically before main.py.
Tries each configured SSID in order until one connects.
"""

import network
import time

from config import WIFI_NETWORKS, WIFI_CONNECT_TIMEOUT

wlan = network.WLAN(network.STA_IF)
wlan.active(True)


def connect_wifi():
    """Try each configured SSID. Returns True if connected."""
    if wlan.isconnected():
        print("WiFi: already connected -", wlan.ifconfig()[0])
        return True

    for ssid, password in WIFI_NETWORKS:
        print("WiFi: trying", ssid)
        wlan.connect(ssid, password)

        start = time.time()
        while not wlan.isconnected():
            if time.time() - start > WIFI_CONNECT_TIMEOUT:
                print("WiFi: timeout on", ssid)
                wlan.disconnect()
                break
            time.sleep(0.5)

        if wlan.isconnected():
            print("WiFi: connected to", ssid, "-", wlan.ifconfig()[0])
            return True

    print("WiFi: failed to connect to any network")
    return False


# Run on boot
connect_wifi()

"""Boot script: connect to WiFi and check for OTA updates.

MicroPython runs boot.py automatically before main.py.
Tries each configured SSID in order until one connects.
If connected to the car-pi hotspot, checks for OTA updates.
"""

import network
import time

from config import WIFI_NETWORKS, WIFI_CONNECT_TIMEOUT, DEVICE_TYPE, OTA_SERVER

wlan = network.WLAN(network.STA_IF)
wlan.active(True)


def connect_wifi():
    """Try each configured SSID. Returns True if connected."""
    if wlan.isconnected():
        print("WiFi: already connected -", wlan.ifconfig()[0])
        return True

    for ssid, password in WIFI_NETWORKS:
        wlan.disconnect()
        time.sleep(0.5)
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


def _run_ota_check():
    """Run OTA update check and rollback detection."""
    from ota_update import (
        check_and_update,
        increment_boot_count,
        needs_rollback,
        perform_rollback,
    )

    count = increment_boot_count()
    print("Boot count:", count)

    if needs_rollback():
        print("OTA: crash loop detected, rolling back...")
        perform_rollback()
        from machine import reset

        reset()

    result = check_and_update(OTA_SERVER, DEVICE_TYPE)
    if result == "updated":
        print("OTA: update applied, rebooting...")
        from machine import reset

        reset()
    elif result == "current":
        print("OTA: firmware is current")
    else:
        print("OTA: update check failed, continuing with current firmware")


# Run on boot — MicroPython executes boot.py before main.py.
# Module cache prevents re-execution when main.py does 'from boot import connect_wifi'.
connect_wifi()

if wlan.isconnected():
    try:
        _run_ota_check()
    except Exception as e:
        print("OTA: error during check:", e)
        print("OTA: continuing with current firmware")

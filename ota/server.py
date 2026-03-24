"""VTMS OTA Server — serves ESP32 firmware bundles over HTTP.

Computes per-device firmware hashes and serves files + manifests.
Publishes hash announcements over MQTT.
"""

import hashlib
import json
import os
import re
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler

FIRMWARE_DIR = os.environ.get("FIRMWARE_DIR", "/firmware")
MQTT_BROKER = os.environ.get("MQTT_BROKER", "192.168.50.24")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
HTTP_PORT = int(os.environ.get("HTTP_PORT", "8266"))
ANNOUNCE_INTERVAL = int(os.environ.get("ANNOUNCE_INTERVAL", "60"))

COMMON_DIR = "common"
DEVICE_TYPE_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


# ── Pure functions (testable without dependencies) ─────────


def _validate_device_type(device_type):
    """Reject device_type values that could escape the firmware directory."""
    if not DEVICE_TYPE_RE.match(device_type):
        raise ValueError(f"invalid device_type: {device_type!r}")


def get_device_files(firmware_dir, device_type):
    """Get sorted, deduplicated list of .py files for a device type."""
    _validate_device_type(device_type)
    files = set()
    common_path = os.path.join(firmware_dir, COMMON_DIR)
    if os.path.isdir(common_path):
        for f in os.listdir(common_path):
            if f.endswith(".py"):
                files.add(f)
    device_path = os.path.join(firmware_dir, device_type)
    if os.path.isdir(device_path):
        for f in os.listdir(device_path):
            if f.endswith(".py"):
                files.add(f)
    return sorted(files)


def resolve_file(firmware_dir, device_type, filename):
    """Resolve filename to path (device dir first, then common)."""
    _validate_device_type(device_type)
    if ".." in filename or "/" in filename:
        raise ValueError(f"invalid filename: {filename!r}")
    device_path = os.path.join(firmware_dir, device_type, filename)
    if os.path.isfile(device_path):
        return device_path
    return os.path.join(firmware_dir, COMMON_DIR, filename)


def compute_device_hash(firmware_dir, device_type):
    """Compute SHA256 hash of all files for a device type."""
    files = get_device_files(firmware_dir, device_type)
    hasher = hashlib.sha256()
    for filename in files:
        filepath = resolve_file(firmware_dir, device_type, filename)
        with open(filepath, "rb") as f:
            hasher.update(f.read())
    return hasher.hexdigest()


def build_manifests(firmware_dir):
    """Build manifests for all device types found in firmware_dir."""
    manifests = {}
    for entry in sorted(os.listdir(firmware_dir)):
        entry_path = os.path.join(firmware_dir, entry)
        if os.path.isdir(entry_path) and entry != COMMON_DIR:
            files = get_device_files(firmware_dir, entry)
            if files:
                manifests[entry] = {
                    "device_type": entry,
                    "hash": compute_device_hash(firmware_dir, entry),
                    "files": files,
                }
    return manifests


# ── HTTP server ────────────────────────────────────────────


class OTAHandler(BaseHTTPRequestHandler):
    """HTTP handler for OTA manifest and file serving."""

    manifests = {}
    firmware_dir = FIRMWARE_DIR

    def do_GET(self):
        parts = self.path.strip("/").split("/")

        if self.path == "/health":
            self._json_response(200, {"status": "ok"})
        elif len(parts) == 2 and parts[0] == "manifest":
            self._handle_manifest(parts[1])
        elif len(parts) == 3 and parts[0] == "files":
            self._handle_file(parts[1], parts[2])
        else:
            self._json_response(404, {"error": "not found"})

    def _handle_manifest(self, device_type):
        try:
            _validate_device_type(device_type)
        except ValueError:
            self._json_response(400, {"error": "invalid device type"})
            return
        if device_type in self.manifests:
            self._json_response(200, self.manifests[device_type])
        else:
            self._json_response(404, {"error": "unknown device type"})

    def _handle_file(self, device_type, filename):
        try:
            _validate_device_type(device_type)
        except ValueError:
            self._json_response(400, {"error": "invalid device type"})
            return
        if ".." in filename or "/" in filename:
            self._json_response(400, {"error": "invalid filename"})
            return
        filepath = resolve_file(self.firmware_dir, device_type, filename)
        if not os.path.isfile(filepath):
            self._json_response(404, {"error": "file not found"})
            return
        with open(filepath, "rb") as f:
            content = f.read()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _json_response(self, code, data):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        print("[HTTP]", format % args)


# ── MQTT announcements ─────────────────────────────────────


def mqtt_loop(manifests):
    """Background thread: connect to MQTT and periodically announce hashes."""
    import paho.mqtt.client as paho_mqtt

    client = paho_mqtt.Client(
        paho_mqtt.CallbackAPIVersion.VERSION2, client_id="vtms-ota-server"
    )

    while True:
        try:
            client.connect(MQTT_BROKER, MQTT_PORT)
            print("[MQTT] Connected to", MQTT_BROKER)
            break
        except Exception as e:
            print("[MQTT] Connect failed:", e)
            time.sleep(5)

    while True:
        for device_type, manifest in manifests.items():
            topic = "vtms/ota/{}/notify".format(device_type)
            payload = json.dumps({"hash": manifest["hash"]})
            client.publish(topic, payload, retain=True)
        print("[MQTT] Announced hashes for", len(manifests), "devices")
        time.sleep(ANNOUNCE_INTERVAL)


# ── Main ───────────────────────────────────────────────────


def main():
    """Start OTA server."""
    print("VTMS OTA Server starting...")
    print("  Firmware dir:", FIRMWARE_DIR)
    print("  HTTP port:", HTTP_PORT)
    print("  MQTT broker: {}:{}".format(MQTT_BROKER, MQTT_PORT))

    manifests = build_manifests(FIRMWARE_DIR)
    print("  Device types:", list(manifests.keys()))
    for dt, m in manifests.items():
        print("    {}: hash={} files={}".format(dt, m["hash"][:12], len(m["files"])))

    OTAHandler.manifests = manifests
    OTAHandler.firmware_dir = FIRMWARE_DIR

    mqtt_thread = threading.Thread(target=mqtt_loop, args=(manifests,), daemon=True)
    mqtt_thread.start()

    server = HTTPServer(("0.0.0.0", HTTP_PORT), OTAHandler)
    print("[HTTP] Serving on port", HTTP_PORT)
    server.serve_forever()


if __name__ == "__main__":
    main()

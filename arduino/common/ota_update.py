"""OTA update module for ESP32 MicroPython devices.

Handles firmware update checks, downloads, and rollback.
Pure functions testable on host CPython.
"""

import os

try:
    import ujson as json
except ImportError:
    import json

try:
    import urequests as requests
except ImportError:
    try:
        import requests
    except ImportError:
        requests = None

# Marker files on ESP32 flash
HASH_FILE = "_ota_hash"
SKIP_FILE = "_ota_skip"
BOOT_COUNT_FILE = "_boot_count"
BACKUP_DIR = "_backup"


# ── File helpers ───────────────────────────────────────────


def read_file(path):
    """Read a file's contents. Returns empty string if not found."""
    try:
        with open(path, "r") as f:
            return f.read().strip()
    except OSError:
        return ""


def write_file(path, content):
    """Write content to a file."""
    with open(path, "w") as f:
        f.write(content)


def file_exists(path):
    """Check if a file exists."""
    try:
        os.stat(path)
        return True
    except OSError:
        return False


def _ensure_dir(path):
    """Create directory if it doesn't exist."""
    try:
        os.mkdir(path)
    except OSError:
        pass


# ── Hash comparison ────────────────────────────────────────


def is_update_available(server_hash, current_hash, skip_hash=""):
    """Check if an OTA update is needed (pure function)."""
    if not server_hash:
        return False
    if server_hash == skip_hash:
        return False
    return server_hash != current_hash


# ── Boot count / rollback ─────────────────────────────────


def get_boot_count():
    """Read the boot counter from file."""
    s = read_file(BOOT_COUNT_FILE)
    try:
        return int(s) if s else 0
    except ValueError:
        return 0


def increment_boot_count():
    """Increment and save the boot counter. Returns new count."""
    count = get_boot_count() + 1
    write_file(BOOT_COUNT_FILE, str(count))
    return count


def reset_boot_count():
    """Reset the boot counter to 0."""
    write_file(BOOT_COUNT_FILE, "0")


def needs_rollback(max_boots=3):
    """Check if rollback is needed based on boot count."""
    return get_boot_count() >= max_boots


# ── Backup / restore ──────────────────────────────────────


def backup_files(filenames):
    """Backup listed files to _backup/ directory."""
    _ensure_dir(BACKUP_DIR)
    for name in filenames:
        if file_exists(name):
            content = read_file(name)
            write_file("{}/{}".format(BACKUP_DIR, name), content)


def restore_backup():
    """Restore all files from _backup/ directory.

    Returns list of restored filenames (empty if no backup).
    """
    if not file_exists(BACKUP_DIR):
        return []
    try:
        files = os.listdir(BACKUP_DIR)
    except OSError:
        return []

    restored = []
    for name in files:
        content = read_file("{}/{}".format(BACKUP_DIR, name))
        write_file(name, content)
        restored.append(name)
    return restored


def perform_rollback():
    """Full rollback: restore backup, mark hash to skip, reset count.

    Returns True if backup files were restored.
    """
    current_hash = read_file(HASH_FILE)
    if current_hash:
        write_file(SKIP_FILE, current_hash)

    restored = restore_backup()

    if file_exists(HASH_FILE):
        os.remove(HASH_FILE)
    reset_boot_count()

    if restored:
        print("OTA: rollback restored", len(restored), "files")
    else:
        print("OTA: rollback found no backup files")
    return len(restored) > 0


# ── HTTP operations ────────────────────────────────────────


def fetch_manifest(ota_server, device_type):
    """Fetch OTA manifest from the HTTP server.

    Returns dict with 'hash' and 'files' keys, or None on error.
    """
    url = "http://{}/manifest/{}".format(ota_server, device_type)
    try:
        resp = requests.get(url)
        if resp.status_code == 200:
            data = json.loads(resp.text)
            resp.close()
            return data
        resp.close()
    except Exception as e:
        print("OTA: manifest fetch failed:", e)
    return None


def download_file(ota_server, device_type, filename):
    """Download a single file from the OTA server.

    Returns file content as string, or None on error.
    """
    url = "http://{}/files/{}/{}".format(ota_server, device_type, filename)
    try:
        resp = requests.get(url)
        if resp.status_code == 200:
            content = resp.text
            resp.close()
            return content
        resp.close()
    except Exception as e:
        print("OTA: download failed for {}: {}".format(filename, e))
    return None


# ── Update application ─────────────────────────────────────


def apply_update(ota_server, device_type, manifest):
    """Download and apply an OTA update.

    Backs up current files, downloads new ones, saves hash.
    Returns True on success, False on failure (restores backup).
    """
    filenames = manifest["files"]
    new_hash = manifest["hash"]

    backup_files(filenames)

    for filename in filenames:
        content = download_file(ota_server, device_type, filename)
        if content is None:
            print("OTA: download failed, restoring backup")
            restore_backup()
            return False
        write_file(filename, content)

    write_file(HASH_FILE, new_hash)
    if file_exists(SKIP_FILE):
        os.remove(SKIP_FILE)
    reset_boot_count()

    print("OTA: update applied successfully")
    return True


def check_and_update(ota_server, device_type):
    """Full OTA check-and-update flow.

    Returns: "updated", "current", or "error".
    """
    manifest = fetch_manifest(ota_server, device_type)
    if manifest is None:
        return "error"

    server_hash = manifest.get("hash", "")
    current_hash = read_file(HASH_FILE)
    skip_hash = read_file(SKIP_FILE)

    if not is_update_available(server_hash, current_hash, skip_hash):
        return "current"

    print(
        "OTA: update available ({} -> {})".format(
            current_hash[:8] if current_hash else "none",
            server_hash[:8],
        )
    )

    if apply_update(ota_server, device_type, manifest):
        return "updated"
    return "error"


def is_on_hotspot(gateway_ip="10.42.0.1"):
    """Check if connected to the car-pi hotspot by gateway IP."""
    try:
        import network

        wlan = network.WLAN(network.STA_IF)
        if not wlan.isconnected():
            return False
        return wlan.ifconfig()[2] == gateway_ip
    except Exception:
        return False

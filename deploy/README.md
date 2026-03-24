# deploy/

Ansible-driven provisioning for the VTMS field deployment. This directory contains everything needed to set up two Raspberry Pis from scratch: a **car-pi** that rides in the vehicle and a **base-pi** that stays at the operations post. Both Pis get Docker, Tailscale, and Cockpit via a shared common role, then receive their specific workloads via Docker Compose.

## Architecture

```
                    ┌──────────────────────────────┐
  ESP32 devices ──► │  car-pi                      │
   (WiFi "vtms")    │  - vtms-client (GPS/OBD)     │
   10.42.0.0/24     │  - vtms-ota (firmware server) │
                    │  - watchtower                │
                    └──────────┬───────────────────┘
                               │ Tailscale / LAN
                    ┌──────────▼───────────────────┐
                    │  base-pi                     │
                    │  - vtms-web (dashboard :3001) │
                    │  - vtms-sdr (radio ingest)   │
                    │  - watchtower                │
                    │  - Chromium kiosk → :3001    │
                    └──────────────────────────────┘
```

Both Pis communicate with an external MQTT broker at `192.168.50.24:1883`. Container images are pulled from a local registry at `192.168.50.46:5000`.

## Prerequisites

- **Ansible** (tested with core 2.14+). Install with `pip install ansible`.
- **SSH access** to both Pis as the `car` user (key-based auth recommended). The inventory resolves hostnames via Tailscale MagicDNS (`car-pi`, `base-pi`); update `inventory.yml` with IPs if needed.
- **Tailscale auth key** exported as `TAILSCALE_AUTH_KEY`. Generate a reusable key from the Tailscale admin console.

```sh
export TAILSCALE_AUTH_KEY="tskey-auth-..."
```

## Running Provisioning

From the repo root:

```sh
# Provision both Pis
ansible-playbook deploy/playbooks/site.yml

# Provision only car-pi
ansible-playbook deploy/playbooks/car-pi.yml

# Provision only base-pi
ansible-playbook deploy/playbooks/base-pi.yml
```

Ansible picks up `deploy/ansible.cfg` automatically when run from the `deploy/` directory. If running from the repo root, point to it explicitly:

```sh
ANSIBLE_CONFIG=deploy/ansible.cfg ansible-playbook deploy/playbooks/site.yml
```

## Roles

### common

Applied to both Pis. Installs baseline infrastructure:

- apt packages: `curl`, `gnupg`, `apt-transport-https`, `ca-certificates`, `cockpit`
- Enables Cockpit (web admin on port 9090)
- Installs Docker via `get.docker.com`, adds `car` to the docker group, installs the Compose plugin
- Configures Docker to trust the insecure registry at `192.168.50.46:5000`
- Installs Tailscale and brings it up with the provided auth key, using `100.90.165.127` as the exit node
- Creates `/opt/vtms` as the compose project directory

### car_pi

Provisions the in-vehicle Pi:

- Creates a WiFi hotspot (SSID `vtms`, band `bg`, channel 6) via NetworkManager, set to auto-connect on boot
- Enables IPv4 forwarding
- Deploys iptables NAT rules so hotspot clients (10.42.0.0/24) route through Tailscale
- Copies `docker-compose.car-pi.yml` to `/opt/vtms/docker-compose.yml` and starts services

### base_pi

Provisions the operations-post Pi:

- Installs `chromium-browser` and `unclutter`
- Configures auto-login to desktop, disables screen blanking
- Deploys a kiosk autostart entry that launches Chromium in `--kiosk` mode pointed at `http://localhost:3001`
- Hides the mouse cursor with unclutter
- Copies `docker-compose.base-pi.yml` to `/opt/vtms/docker-compose.yml` and starts services

## Docker Compose Services

### car-pi

| Service | Image | Purpose |
|---------|-------|---------|
| `vtms-client` | `192.168.50.46:5000/vtms:latest` | GPS/OBD data collection, publishes to MQTT. Runs privileged with host network and `/dev` access. |
| `vtms-ota` | `192.168.50.46:5000/vtms-ota:latest` | OTA firmware server for ESP32 devices on the hotspot. Listens on port 8266. |
| `watchtower` | `containrrr/watchtower` | Auto-pulls new images every 120s from the registry. |

### base-pi

| Service | Image | Purpose |
|---------|-------|---------|
| `vtms-web` | `192.168.50.46:5000/vtms-web:latest` | Web dashboard and API server on port 3001. |
| `vtms-sdr` | `192.168.50.46:5000/vtms-sdr:latest` | SDR radio recording (default freq 462.5625 MHz). Runs privileged with USB device access. |
| `watchtower` | `containrrr/watchtower` | Auto-pulls new images every 120s from the registry. |

All services use `network_mode: host` (except watchtower) and are tagged for watchtower auto-update.

## Network Topology

- **car-pi hotspot**: NetworkManager creates a WiFi AP on `wlan0` with SSID `vtms`. Clients get addresses in `10.42.0.0/24`. NAT rules masquerade hotspot traffic through the Pi's uplink (typically Tailscale).
- **MQTT broker**: External, at `192.168.50.24:1883`. Both vtms-client and vtms-ota connect here.
- **Tailscale**: Both Pis join the tailnet. Exit node `100.90.165.127` is used for outbound traffic with LAN access allowed.

## Image Registry

Images are hosted on a local Docker registry at `192.168.50.46:5000`. Docker on both Pis is configured to trust this as an insecure registry.

To build and push images from the development machine:

```sh
make deploy-push
```

Watchtower on each Pi polls the registry every 120 seconds and pulls updated images automatically.

## Important Variables

### group_vars/all.yml (apply to both Pis)

| Variable | Value | Description |
|----------|-------|-------------|
| `registry` | `192.168.50.46:5000` | Docker image registry |
| `tailscale_auth_key` | `$TAILSCALE_AUTH_KEY` | Looked up from environment |
| `tailscale_exit_node` | `100.90.165.127` | Tailscale exit node IP |
| `mqtt_server` | `192.168.50.24` | MQTT broker address |
| `mqtt_port` | `1883` | MQTT broker port |
| `compose_dir` | `/opt/vtms` | Docker Compose project path on Pi |

### host_vars/car-pi.yml

| Variable | Value | Description |
|----------|-------|-------------|
| `hotspot_ssid` | `{{ lookup('env', 'HOTSPOT_SSID') }}` | WiFi hotspot SSID (from `.env`) |
| `hotspot_password` | `{{ lookup('env', 'HOTSPOT_PASSWORD') }}` | Hotspot WPA password (from `.env`) |
| `hotspot_band` | `bg` | WiFi band (2.4 GHz) |
| `hotspot_channel` | `6` | WiFi channel |
| `hotspot_subnet` | `10.42.0.0/24` | Hotspot client subnet |

### host_vars/base-pi.yml

| Variable | Value | Description |
|----------|-------|-------------|
| `vtms_sdr_args` | `record --freq 462.5625` | Default SDR recording arguments |
| `kiosk_url` | `http://localhost:3001` | URL opened by Chromium kiosk |

## Directory Structure

```
deploy/
├── ansible.cfg                       # Ansible config (inventory, remote user, roles path)
├── inventory.yml                     # Host inventory: car_pi and base_pi groups
├── group_vars/
│   └── all.yml                       # Variables shared across all hosts
├── host_vars/
│   ├── car-pi.yml                    # Car-pi-specific variables (hotspot config)
│   └── base-pi.yml                   # Base-pi-specific variables (kiosk, SDR)
├── playbooks/
│   ├── site.yml                      # Full deployment (imports car-pi + base-pi)
│   ├── car-pi.yml                    # Car-pi only
│   └── base-pi.yml                   # Base-pi only
├── roles/
│   ├── common/
│   │   ├── tasks/main.yml            # Docker, Tailscale, Cockpit, apt baseline
│   │   ├── handlers/main.yml         # Restart Docker handler
│   │   └── templates/daemon.json.j2  # Docker daemon config (insecure registry)
│   ├── car_pi/
│   │   ├── tasks/main.yml            # Hotspot, NAT, compose deploy
│   │   ├── handlers/main.yml         # Restore iptables handler
│   │   └── templates/iptables-restore.j2  # NAT/filter rules
│   └── base_pi/
│       ├── tasks/main.yml            # Kiosk setup, compose deploy
│       └── templates/vtms-kiosk.desktop.j2  # Chromium kiosk autostart
├── docker-compose.car-pi.yml        # Compose file for car-pi services
└── docker-compose.base-pi.yml       # Compose file for base-pi services
```

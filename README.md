# VTMS (Vehicle Telemetry Monitoring System)

## How to install (from scratch)

```
export TAILSCALE_AUTH_KEY=a-tailscale-auth-key
curl -sf -L https://raw.githubusercontent.com/jeefy/vtms/refs/heads/main/install.sh | sudo -E sh -
```

## How to run

```
# Start this for OTA Updates
docker run --detach \
    --name watchtower \
    --volume /var/run/docker.sock:/var/run/docker.sock \
    containrrr/watchtower

# Start the OBD2 Client
docker run -d --restart=always --privileged -v /dev:/dev ghcr.io/jeefy/vtms:main
```

## TODO
- Handle LTE faults
- LED Alerts https://raspberrypihq.com/making-a-led-blink-using-the-raspberry-pi-and-python/

## Helper Utilities

https://mqtt-explorer.com/
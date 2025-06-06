#!/bin/bash

# Check to see if TAILSCALE_AUTH_KEY is set
if [ -z "${TAILSCALE_AUTH_KEY}" ]; then
    echo "Error: TAILSCALE_AUTH_KEY is not set. Please set it before running this script."
    exit 1
fi

# Prerequisites
echo "Installing pre-requisites..."
apt update

apt install -y docker.io

systemctl start docker
systemctl enable docker

docker info

apt install -y cockpit cockpit-docker
systemctl enable --now cockpit.socket

curl -fsSL https://tailscale.com/install.sh | sh

tailscale up --accept-routes --exit-node archives --exit-node-allow-lan-access=true --auth-key="${TAILSCALE_AUTH_KEY}" 

# Start this for OTA Updates
docker run --detach \
    --name watchtower \
    --volume /var/run/docker.sock:/var/run/docker.sock \
    containrrr/watchtower

# Start the OBD2 Client
docker run -d --restart=always --privileged -v /dev:/dev ghcr.io/jeefy/vtms:main

echo "Installation complete. You can access Cockpit at https://<your-server-ip>:9090"
echo "OBD2 Client is running in the background."
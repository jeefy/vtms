WHOAMI   := $(shell whoami)
REGISTRY ?= 192.168.50.46:5000

# ── Python (client) ────────────────────────────────────
.PHONY: client-install client-test client-lint client-format client-run

client-install:
	cd client && uv sync

client-test:
	cd client && uv run pytest tests/ -v

client-test-cov:
	cd client && uv run pytest tests/ -v --cov=vtms_client --cov-report=term-missing

client-lint:
	cd client && uv run ruff check src/ tests/

client-format:
	cd client && uv run ruff format src/ tests/

client-run:
	cd client && uv run vtms-client

# ── Python (ingest) ────────────────────────────────────
.PHONY: ingest-install ingest-run

ingest-install:
	cd ingest && uv sync

ingest-run:
	cd ingest && uv run vtms-ingest

# ── Python (sdr) ───────────────────────────────────────
.PHONY: sdr-install sdr-test sdr-lint sdr-run

sdr-install:
	cd sdr && uv sync

sdr-test:
	cd sdr && uv run pytest tests/ -v

sdr-lint:
	cd sdr && uv run ruff check src/ tests/

sdr-run:
	cd sdr && uv run vtms-sdr --help

# ── Node (server + web) ───────────────────────────────
.PHONY: node-install server-build server-dev web-build web-dev

node-install:
	pnpm install

server-build: node-install
	pnpm --filter vtms-server build

server-dev:
	pnpm --filter vtms-server dev

web-build: node-install
	pnpm --filter web build

web-dev:
	pnpm --filter web dev

# ── Docker images ──────────────────────────────────────
.PHONY: image-client image-sdr image-web image-client-push image-sdr-push image-web-push

image-client:
	docker buildx build --network=host --platform linux/arm64 -t $(REGISTRY)/vtms:latest --load client/

image-client-push: image-client
	skopeo copy --dest-tls-verify=false docker-daemon:$(REGISTRY)/vtms:latest docker://$(REGISTRY)/vtms:latest

image-sdr:
	docker buildx build --network=host --platform linux/arm64 -t $(REGISTRY)/vtms-sdr:latest --load sdr/

image-sdr-push: image-sdr
	skopeo copy --dest-tls-verify=false docker-daemon:$(REGISTRY)/vtms-sdr:latest docker://$(REGISTRY)/vtms-sdr:latest

image-web:
	docker buildx build --network=host --platform linux/arm64 -f Dockerfile.web -t $(REGISTRY)/vtms-web:latest --load .

image-web-push: image-web
	skopeo copy --dest-tls-verify=false docker-daemon:$(REGISTRY)/vtms-web:latest docker://$(REGISTRY)/vtms-web:latest

image-ota:
	docker buildx build --network=host --platform linux/arm64 -f Dockerfile.ota -t $(REGISTRY)/vtms-ota:latest --load .

image-ota-push: image-ota
	skopeo copy --dest-tls-verify=false docker-daemon:$(REGISTRY)/vtms-ota:latest docker://$(REGISTRY)/vtms-ota:latest

deploy-push: image-client-push image-sdr-push image-web-push image-ota-push
	@echo "All images pushed to $(REGISTRY)"

# ── CI helpers ─────────────────────────────────────────
.PHONY: ci-client ci-sdr ci-node ci test lint

ci-client: client-lint client-test
ci-sdr: sdr-lint sdr-test
ci-node: server-build web-build
ci: ci-client ci-sdr ci-node

test: client-test sdr-test esp32-test ota-test
lint: client-lint sdr-lint

# ── ESP32 MicroPython Devices ──────────────────────────
.PHONY: esp32-test flash-micropython monitor-esp32
.PHONY: flash-analog-sensors flash-thermoprobe flash-temp-sensor flash-led-controller

# ── OTA Server ─────────────────────────────────────────
.PHONY: ota-test

ota-test:
	cd ota && python -m pytest tests/ -v

esp32-test:
	cd arduino/common && python -m pytest tests/ -v
	cd arduino/analog_sensors && python -m pytest tests/ -v
	cd arduino/thermoprobe && python -m pytest tests/ -v
	cd arduino/temp_sensor && python -m pytest tests/ -v
	cd arduino/led_controller && python -m pytest tests/ -v

flash-micropython:
	@echo "1. Download firmware from https://micropython.org/download/ESP32_GENERIC/"
	@echo "2. pip install esptool mpremote"
	@echo "3. esptool.py --chip esp32 erase_flash"
	@echo "4. esptool.py --chip esp32 write_flash -z 0x1000 <firmware.bin>"

generate-secrets: .env ## Generate secrets files for Arduino/MicroPython from .env
	@echo "Generating arduino/common/secrets.py from .env …"
	@. ./.env && printf '"""Device secrets — generated from .env, do NOT commit."""\n\nWIFI_NETWORKS = [\n    ("%s", "%s"),\n    ("%s", "%s"),\n]\n\nMQTT_BROKER = "%s"\nMQTT_PORT = %s\nOTA_SERVER = "%s"\n' \
		"$$WIFI_SSID_1" "$$WIFI_PASSWORD_1" \
		"$$WIFI_SSID_2" "$$WIFI_PASSWORD_2" \
		"$$MQTT_BROKER" "$$MQTT_PORT" "$$OTA_SERVER" \
		> arduino/common/secrets.py
	@echo "Generating arduino/arduino_secrets.h from .env …"
	@. ./.env && printf '#ifndef ARDUINO_SECRETS_H\n#define ARDUINO_SECRETS_H\n#define SECRET_WIFI_SSID "%s"\n#define SECRET_WIFI_PASS "%s"\n#endif\n' \
		"$$WIFI_SSID_2" "$$WIFI_PASSWORD_2" \
		> arduino/arduino_secrets.h
	@echo "Done.  Files are gitignored — do not commit them."

flash-analog-sensors: generate-secrets
	mpremote cp arduino/common/boot.py :boot.py
	mpremote cp arduino/common/mqtt_client.py :mqtt_client.py
	mpremote cp arduino/common/adc_utils.py :adc_utils.py
	mpremote cp arduino/common/ota_update.py :ota_update.py
	mpremote cp arduino/common/secrets.py :secrets.py
	mpremote cp arduino/analog_sensors/config.py :config.py
	mpremote cp arduino/analog_sensors/sensors.py :sensors.py
	mpremote cp arduino/analog_sensors/main.py :main.py
	mpremote reset

flash-thermoprobe: generate-secrets
	mpremote cp arduino/common/boot.py :boot.py
	mpremote cp arduino/common/mqtt_client.py :mqtt_client.py
	mpremote cp arduino/common/ota_update.py :ota_update.py
	mpremote cp arduino/common/secrets.py :secrets.py
	mpremote cp arduino/thermoprobe/config.py :config.py
	mpremote cp arduino/thermoprobe/max6675.py :max6675.py
	mpremote cp arduino/thermoprobe/main.py :main.py
	mpremote reset

flash-temp-sensor: generate-secrets
	mpremote cp arduino/common/boot.py :boot.py
	mpremote cp arduino/common/mqtt_client.py :mqtt_client.py
	mpremote cp arduino/common/adc_utils.py :adc_utils.py
	mpremote cp arduino/common/ota_update.py :ota_update.py
	mpremote cp arduino/common/secrets.py :secrets.py
	mpremote cp arduino/temp_sensor/config.py :config.py
	mpremote cp arduino/temp_sensor/sensors.py :sensors.py
	mpremote cp arduino/temp_sensor/main.py :main.py
	mpremote reset

flash-led-controller: generate-secrets
	mpremote cp arduino/common/boot.py :boot.py
	mpremote cp arduino/common/mqtt_client.py :mqtt_client.py
	mpremote cp arduino/common/ota_update.py :ota_update.py
	mpremote cp arduino/common/secrets.py :secrets.py
	mpremote cp arduino/led_controller/config.py :config.py
	mpremote cp arduino/led_controller/led_logic.py :led_logic.py
	mpremote cp arduino/led_controller/main.py :main.py
	mpremote reset

monitor-esp32:
	mpremote connect auto repl

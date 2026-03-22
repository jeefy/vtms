PYTHON   ?= python3
PIP      ?= pip3
WHOAMI   := $(shell whoami)
IMAGE    := $(WHOAMI)/vtms

# ── Python ──────────────────────────────────────────────
.PHONY: venv requirements requirements-dev pip-compile lint test client server-py

venv:
	$(PYTHON) -m venv .venv
	@echo "Activate with: source .venv/bin/activate"

requirements:
	$(PIP) install -r requirements.txt

requirements-dev: requirements
	$(PIP) install -r requirements-dev.txt

pip-compile:
	$(PIP) install pip-tools
	pip-compile requirements.in -o requirements.txt
	pip-compile requirements-dev.in -o requirements-dev.txt

lint:
	$(PYTHON) -m flake8 client.py server.py src/ tests/
	$(PYTHON) -m black --check client.py server.py src/ tests/
	$(PYTHON) -m isort --check client.py server.py src/ tests/

format:
	$(PYTHON) -m black client.py server.py src/ tests/
	$(PYTHON) -m isort client.py server.py src/ tests/

test:
	$(PYTHON) -m pytest tests/ -v

test-cov:
	$(PYTHON) -m pytest tests/ -v --cov=src --cov-report=term-missing

client:
	$(PYTHON) client.py

server-py:
	$(PYTHON) -m flask --app server run

# ── Node (server + web) ────────────────────────────────
.PHONY: server-install server-build server-dev web-install web-build web-dev

server-install:
	cd server && npm ci

server-build: server-install
	cd server && npm run build

server-dev:
	cd server && npm run dev

web-install:
	cd web && npm ci

web-build: web-install
	cd web && npm run build

web-dev:
	cd web && npm run dev

# ── Docker ──────────────────────────────────────────────
.PHONY: image image-run image-push image-web image-web-run

image:
	docker build -t $(IMAGE):latest .

image-run: image
	docker run -v ./data/:/app/data --privileged --rm --name vtms $(IMAGE):latest

image-push: image
	docker push $(IMAGE):latest

image-web:
	docker build -f Dockerfile.web -t $(IMAGE)-web:latest .

image-web-run: image-web
	docker run --rm -p 3001:3001 --name vtms-web $(IMAGE)-web:latest

# ── CI helpers ──────────────────────────────────────────
.PHONY: ci-python ci-node ci

ci-python: lint test

ci-node: server-build web-build

ci: ci-python ci-node

# ── Local registry (deployment) ─────────────────────────
REGISTRY ?= 192.168.50.46:5000

image-local:
	docker buildx build --platform linux/arm64 -t $(REGISTRY)/vtms:latest --load .

image-local-push: image-local
	docker push $(REGISTRY)/vtms:latest

image-web-local:
	docker buildx build --platform linux/arm64 -f Dockerfile.web -t $(REGISTRY)/vtms-web:latest --load .

image-web-local-push: image-web-local
	docker push $(REGISTRY)/vtms-web:latest

deploy-push: image-local-push image-web-local-push
	@echo "All images pushed to $(REGISTRY)"

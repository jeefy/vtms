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

deploy-push: image-client-push image-sdr-push image-web-push
	@echo "All images pushed to $(REGISTRY)"

# ── CI helpers ─────────────────────────────────────────
.PHONY: ci-client ci-sdr ci-node ci test lint

ci-client: client-lint client-test
ci-sdr: sdr-lint sdr-test
ci-node: server-build web-build
ci: ci-client ci-sdr ci-node

test: client-test sdr-test
lint: client-lint sdr-lint

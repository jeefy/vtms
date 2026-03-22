# Monorepo Consolidation Design

**Date:** 2026-03-22
**Status:** Approved

## Goal

Consolidate `vtms` and `vtms-sdr` into a single monorepo containing everything needed to operate the racing team's vehicle telemetry and communications systems.

## Target Structure

```
vtms/
├── client/                    # Python telemetry client (OBD + GPS → MQTT)
│   ├── pyproject.toml
│   ├── src/vtms_client/
│   ├── tests/
│   └── Dockerfile
├── ingest/                    # Python MQTT → PostgreSQL server
│   ├── pyproject.toml
│   └── src/vtms_ingest/
├── sdr/                       # RTL-SDR recorder/scanner (from vtms-sdr)
│   ├── pyproject.toml
│   ├── src/vtms_sdr/
│   ├── tests/
│   └── Dockerfile
├── server/                    # Node/Express API + GoPro control
│   ├── package.json
│   └── src/
├── web/                       # React/Vite dashboard
│   ├── package.json
│   └── src/
├── arduino/                   # ESP32/CAN gauge firmware
├── deploy/                    # Ansible + Docker Compose
├── docs/
├── .github/workflows/
├── Dockerfile.web             # Multi-stage: server + web
├── Makefile                   # Top-level orchestrator
├── pnpm-workspace.yaml
├── package.json               # Root (pnpm workspaces)
└── uv.lock
```

## Key Decisions

### 1. Git History Preservation

Use `git subtree add --prefix=sdr` to merge vtms-sdr with full commit history.

### 2. Python Packaging: uv + pyproject.toml

- Each Python package (`client`, `ingest`, `sdr`) gets its own `pyproject.toml`
- Root `uv` workspace for shared lockfile and unified dev experience
- Replaces `requirements.txt` / `pip-tools` workflow

### 3. Node Packaging: pnpm Workspaces

- Root `pnpm-workspace.yaml` listing `server/` and `web/`
- Single `pnpm-lock.yaml` replaces per-package `package-lock.json`

### 4. Build Orchestration: Makefile

- No additional monorepo tooling (no Nx, Turborepo)
- Root Makefile delegates to each package

### 5. Docker Images (unchanged names)

| Image | Source | Dockerfile |
|-------|--------|------------|
| `vtms` | client/ | `client/Dockerfile` |
| `vtms-sdr` | sdr/ | `sdr/Dockerfile` |
| `vtms-web` | server/ + web/ | `Dockerfile.web` (root) |

### 6. CI

- Python CI: matrix over `{client, ingest, sdr}` × Python versions
- Node CI: pnpm-based builds for server + web
- Path filters to skip unrelated jobs
- Docker publish builds all 3 images

## File Moves

| Current | New |
|---------|-----|
| `client.py` | `client/src/vtms_client/__main__.py` |
| `src/*.py` | `client/src/vtms_client/` |
| `tests/` | `client/tests/` |
| `requirements.txt` | removed (replaced by `client/pyproject.toml`) |
| `requirements-dev.txt` | removed (dev deps in pyproject.toml) |
| `pytest.ini` | `[tool.pytest]` in `client/pyproject.toml` |
| `server.py` | `ingest/src/vtms_ingest/server.py` |
| `Dockerfile` | `client/Dockerfile` |
| `(vtms-sdr repo)` | `sdr/` (via git subtree) |

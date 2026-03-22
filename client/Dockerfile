FROM python:3.13-slim

RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy project metadata first for layer caching
COPY pyproject.toml ./

# Install dependencies (without dev group)
RUN uv sync --no-dev --no-install-project

# Copy source code
COPY src/ src/

# Install the project itself
RUN uv sync --no-dev

ENTRYPOINT ["uv", "run", "vtms-client"]

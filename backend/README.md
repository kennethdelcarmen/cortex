# Cortex Backend

This directory contains the Python service layer shared by Cortex REST and MCP
interfaces. It targets Python 3.12 and uses `uv` for dependency management.

## Local setup

Run commands from this directory:

```bash
uv sync
uv run uvicorn cortex_backend.app:app --reload
```

The initial service exposes:

- `GET /healthz` for dependency-free liveness.
- `GET /readyz` for storage readiness.
- `GET /api/v1` for versioned API metadata.
- `GET /mcp` as an explicit not-yet-configured MCP transport placeholder.

## Verification

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```

The scaffold uses an in-memory storage adapter. Turso/libSQL, domain models,
authentication, migrations, and MCP domain tools are intentionally deferred
until their first vertical slice is designed.

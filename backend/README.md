# Cortex Backend

This directory contains the Python service layer shared by Cortex REST and MCP
interfaces. It targets Python 3.12 and uses `uv` for dependency management.

## Self-hosting direction

Cortex is being reoriented as a local-first, self-hostable open-source
application. The intended future deployment is a user-managed Docker Compose
stack on Linux, a VPS, or a NAS, with a persistent SQLite-compatible database
stored in an application data volume.

The current backend implements the persistent SQLite foundation, but there is
not yet a Compose configuration, container image, frontend, authentication,
migration system, or domain functionality. Turso/libSQL, hosted services,
mobile synchronization, and semantic vector storage are optional or deferred
rather than current backend requirements.

## Local setup

Run commands from this directory:

```bash
uv sync
uv run uvicorn cortex_backend.app:app --reload
```

The local runtime uses SQLite at `data/cortex.db` by default. Set
`CORTEX_DATABASE_PATH` to use another path, such as
`CORTEX_DATABASE_PATH=/var/lib/cortex/cortex.db`. The parent directory is
created when `/readyz` first checks storage, and the default `data/` directory
is ignored by Git.

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

The backend now has a persistent SQLite storage foundation while domain models,
authentication, migrations, self-hosting packaging, and MCP domain tools remain
deferred until their first vertical slice is designed.

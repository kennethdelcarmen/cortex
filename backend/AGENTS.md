# Backend Engineering Guide

This guide applies to the `backend/` subtree and supplements the repository-level
`AGENTS.md`. The root instructions remain authoritative when a rule is not
backend-specific or when the two documents conflict.

## Purpose and boundaries

The backend is the shared Python service layer for Cortex. It will serve two
equivalent access paths:

- FastAPI REST endpoints for the visual client.
- FastMCP tools and, when implemented, their SSE transport for AI agents.

Domain behavior belongs in async service functions. REST routers and MCP tools
are adapters: they validate and translate protocol input, call the same service
functions, and translate results and errors back to their protocol. Do not
duplicate business rules in a router or tool handler.

The initial scaffold intentionally contains no domain models, migrations,
authentication, persistent database adapter, or self-hosting packaging. It also
does not contain a Turso connection. Add those at the first domain vertical
slice with explicit compatibility and rollout decisions.

## Layout and ownership

```text
backend/
├── AGENTS.md
├── README.md
├── pyproject.toml
├── src/cortex_backend/
│   ├── api/                 # HTTP routers and protocol schemas
│   ├── app.py               # App factory and composition root
│   ├── config.py            # Typed environment-backed settings
│   ├── mcp.py               # FastMCP registry composition
│   └── storage.py           # Persistence protocols and adapters
└── tests/                   # Deterministic externally visible behavior tests
```

Keep the composition root small and explicit. New domain modules should own
their service functions, repository protocols, schemas, and focused tests. A
module may depend inward on service and domain contracts, but transport code
must not become the owner of persistence or business policy.

## API and service conventions

- Version client-facing REST routes under `/api/v1`.
- Keep operational probes outside the versioned API: `/healthz` is liveness and
  `/readyz` checks required dependencies.
- Use typed Pydantic request and response models at protocol boundaries.
- Use async functions through the service and adapter layers so external I/O can
  be introduced without changing public contracts.
- Map expected domain failures to stable error responses. Do not expose raw
  exception messages, credentials, database details, or personal data.
- Keep routers thin and inject dependencies through explicit app-owned seams.

## Persistence and synchronization

Persistence is represented by small async protocols. The in-memory adapter is
for deterministic tests and local bootstrap behavior; it is not a production
store. The planned default is a SQLite-compatible local database file in a
mounted application data volume. A Turso/libSQL adapter may be considered later
as an optional backend, but it is not the current baseline. Any future adapter
must preserve explicit ownership, transaction boundaries, and migration
compatibility.

Schema changes, migrations, backfills, retention, backup/restore behavior, and
any future synchronization behavior must be documented and tested as
compatibility changes. Offline-first mobile synchronization is deferred. Do not
hide database calls inside route handlers or use an unbounded query by default.

## MCP conventions

The FastMCP registry is composed in `mcp.py`. Each future tool must call the
same service function used by the corresponding REST route. Tool input and
output schemas, authorization, error semantics, and side effects must be
documented before exposing a tool. The `/mcp` endpoint remains an explicit
placeholder until a real transport and at least one domain tool are ready.

## Configuration, security, and operations

- Load typed settings through Pydantic Settings with the `CORTEX_` prefix.
- Keep secrets in environment or deployment secret stores; never commit or log
  them. `.env` is local-only and must remain ignored.
- Default CORS behavior to deny-all until the frontend origin is explicitly
  configured.
- Authentication and authorization are required before exposing private task,
  knowledge, or financial data.
- Log lifecycle and failure context without request bodies, tokens, financial
  records, or other unnecessary personal data.
- Keep resource creation and cleanup in application lifespan or adapters, not in
  module import side effects.

## Quality gates

Run these commands from `backend/`:

```bash
uv sync
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```

Tests should describe externally visible behavior and cover normal, error,
permission, migration, and synchronization paths as those features are added.
For shared service changes, include representative REST and MCP parity tests.

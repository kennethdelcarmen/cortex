# Cortex Backend

This directory contains the Python service layer shared by Cortex REST and MCP
interfaces. It targets Python 3.12 and uses `uv` for dependency management.

## Self-hosting direction

Cortex is being reoriented as a local-first, self-hostable open-source
application. The intended future deployment is a user-managed Docker Compose
stack on Linux, a VPS, or a NAS, with a persistent SQLite-compatible database
stored in an application data volume.

The current backend implements a persistent SQLite foundation and a local-owner
authentication slice. There is not yet a Compose configuration, container
image, frontend, or domain functionality. Turso/libSQL, hosted services,
mobile synchronization, external identity providers, password recovery, agent
tokens, and semantic vector storage are optional or deferred rather than
current backend requirements.

## Local setup

Run commands from this directory:

```bash
uv sync
uv run uvicorn cortex_backend.app:app --reload
```

The local runtime uses SQLite at `data/cortex.db` by default. Set
`CORTEX_DATABASE_PATH` to use another path, such as
`CORTEX_DATABASE_PATH=/var/lib/cortex/cortex.db`. The parent directory is
created when migrations run or `/readyz` first checks storage, and the default
`data/` directory is ignored by Git.

Apply schema migrations explicitly before starting the service:

```bash
uv sync
uv run alembic upgrade head
uv run uvicorn cortex_backend.app:app --reload
```

Owner setup requires a high-entropy `CORTEX_SETUP_SECRET`. The setup route is
disabled when the secret is absent and can only create the first owner. Keep
the value in the local-only `.env` file or a deployment secret store; never
commit or log it.

For a local installation, set the secret before starting the service and use
the setup endpoint once:

```bash
CORTEX_SETUP_SECRET='replace-with-a-high-entropy-secret' \
  uv run uvicorn cortex_backend.app:app --reload

curl -c cookies.txt \
  -H 'X-Setup-Secret: replace-with-a-high-entropy-secret' \
  -H 'Content-Type: application/json' \
  -d '{"email":"owner@example.com","password":"replace-with-a-12-character-password"}' \
  http://127.0.0.1:8000/api/v1/auth/setup
```

The response sets an HttpOnly `cortex_session` cookie and a readable
`cortex_csrf` cookie. Call `GET /api/v1/auth/csrf` to rotate and return a CSRF
token, then send that value in `X-CSRF-Token` together with the cookie for
unsafe authenticated requests. Configure browser origins as a JSON array in
`CORTEX_CORS_ORIGINS`, for example
`["http://localhost:3000"]`; the default is deny-all for cross-origin access.
The browser setup wizard first verifies the secret with
`POST /api/v1/auth/setup/verify` using the `X-Setup-Secret` header; this request
does not create an owner or session. Owner creation still happens only through
`POST /api/v1/auth/setup`.

The initial service exposes:

- `GET /healthz` for dependency-free liveness.
- `GET /readyz` for storage readiness.
- `GET /api/v1` for versioned API metadata.
- `/api/v1/auth/*` for local-owner setup, login, logout, current-user, CSRF,
  and password-change operations.
- `GET /mcp` as an explicit not-yet-configured MCP transport placeholder.

## Verification

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```

The backend now has a persistent SQLite storage foundation, versioned auth
schema, and local-owner authentication. Task, knowledge, finance, self-hosting,
and MCP domain tools remain deferred until their own vertical slices are
designed. To roll back the application after the additive auth migration,
deploy the previous application while leaving the new tables in place. Only
run `uv run alembic downgrade -1` against a backed-up local database when
intentionally removing the auth schema.

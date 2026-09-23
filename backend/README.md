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
image, or full domain functionality. Turso/libSQL, hosted services, mobile
synchronization, external identity providers, password recovery, agent tokens,
and semantic vector storage are optional or deferred rather than current
backend requirements.

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

If upgrading an existing installation, make a copy of the SQLite database
before applying this migration. Migration `0007_notes_html_content` converts
legacy Markdown note bodies to sanitized HTML and is intentionally
forward-only; automatic downgrade cannot restore the original source.

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
  -d '{"email":"owner@example.com","password":"replace-with-a-12-character-password","mcp_api_key":"replace-with-a-32-character-or-longer-key"}' \
  http://127.0.0.1:8000/api/v1/auth/setup
```

The setup request must choose exactly one MCP credential source. Provide a
separate `mcp_api_key` with at least 32 characters, or use the setup secret
explicitly instead:

```json
{
  "email": "owner@example.com",
  "password": "replace-with-a-12-character-password",
  "use_setup_secret_as_mcp_key": true
}
```

Cortex stores only a hash of the selected credential. If the setup secret is
reused, it is hashed during owner creation and is not checked during normal
MCP requests; it may be removed from the runtime environment afterward. Do
not log or commit either raw credential.

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
- `/api/v1/activity-logs` for authenticated activity-log append and history
  queries with filtering and cursor pagination.
- `/api/v1/notes` for authenticated sanitized-HTML note and journal-entry CRUD,
  normalized tags, local full-text search, cursor pagination, soft deletion,
  and restoration.
- `/api/v1/tasks` for authenticated task CRUD, filtering, and cursor pagination.
- `/mcp` as an authenticated Streamable HTTP MCP transport exposing the same
  task, note, and activity-log operations to agents. MCP clients may send
  either an existing session token or the configured static MCP key as a
  bearer token in the `Authorization` header. Static keys are accepted only
  on `/mcp`; REST endpoints continue to require the browser session and CSRF
  protections.
- `/api/v1/auth/mcp-key` for authenticated owners to inspect non-secret key
  status, replace the key, or revoke it. The raw key is never returned. A
  replacement invalidates the previous key; revocation leaves session-token
  MCP access intact.

To connect Codex using a static key, export it only in the shell or secret
manager used to launch Codex and register the Streamable HTTP server:

```bash
export CORTEX_MCP_TOKEN='the-key-selected-during-setup'
codex mcp add cortex \
  --url http://127.0.0.1:8000/mcp/ \
  --bearer-token-env-var CORTEX_MCP_TOKEN
```

When setup-secret reuse was selected, `CORTEX_MCP_TOKEN` should contain that
same setup-secret value. The backend still authenticates against the stored
hash after `CORTEX_SETUP_SECRET` is removed from its environment.

Existing installations remain session-only until the owner creates a key in
the authenticated settings UI or with `PUT /api/v1/auth/mcp-key`.

Activity records are append-only, owner-scoped, and support bounded listing
with structured JSON metadata. Automatic task/auth event producers remain
deferred.

Notes store sanitized HTML bodies, optional titles, optional date-only journal
dates, and owner-scoped normalized tags. REST and MCP accept legacy Markdown
input and normalize it to HTML before storage; note responses always return
sanitized HTML in `body`. Note search uses the local SQLite FTS5
extension and treats the `search` parameter as plain keywords with AND
semantics; raw FTS operators are not part of the API contract. Normal note
reads hide soft-deleted records, while `include_deleted=true` and the restore
operation support recovery.

Tasks use the statuses `backlog`, `todo`, `in_progress`, `done`, and `canceled`
and the priorities `none`, `low`, `medium`, and `high`. Task tags are supplied
inline, normalized per owner, and replaced atomically on update. `start_at` and
`due_at` must be timezone-aware ISO datetimes. Deletes are soft deletes and
excluded from normal task reads.

Recurring tasks use an owner-scoped series with materialized task occurrences.
Create one by adding a `recurrence` object to `POST /api/v1/tasks`; supported
frequencies are `daily`, `weekly`, `monthly`, and `yearly`. The recurrence
object stores an IANA timezone, interval, applicable weekday/month selectors,
and either an inclusive `until_date` or `occurrence_count`. A recurring task
must have a timezone-aware `start_at` or `due_at` anchor. Future occurrences
are generated lazily through a 90-day horizon, with bounded backfill when the
service has been offline. Existing occurrences can be edited independently;
series edits update only future, non-exception occurrences.

Series can be inspected and managed through `/api/v1/task-series` and the
matching MCP tools. Pausing or ending a series stops new generation but leaves
already-materialized occurrences intact. `POST /api/v1/tasks/{task_id}/skip`
retains a skipped occurrence as a canceled task for history.

## Verification

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```

The backend now has a persistent SQLite storage foundation, versioned auth,
task, recurrence, activity-log, and notes schemas, local-owner authentication,
and shared REST/MCP domain slices. Knowledge, finance, and self-hosting
packaging remain deferred. To roll back the application after the additive task,
recurrence, activity-log, and notes migrations, deploy the previous application
while leaving the new tables in place. Only run a downgrade against a backed-up
local database when intentionally removing these schemas.
Use `uv run alembic downgrade 0001_auth_foundation` only when intentionally
removing the task, recurrence, activity-log, and notes schemas together.

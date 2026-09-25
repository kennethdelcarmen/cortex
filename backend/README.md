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

## Minimum system requirements

Cortex is self-hosting friendly: the core service stores data locally in SQLite
and the local filesystem. It does not require a Cortex-operated cloud service,
hosted OCR provider, or external identity provider.

For the current native development/runtime setup, use:

- A 64-bit macOS or Linux system. The planned Docker Compose deployment targets
  Linux, VPS, and NAS environments; a production container image is not yet
  included in this repository.
- Python 3.12.x and `uv` for the backend. The backend declares Python
  `>=3.12,<3.13`.
- Node.js 20.9 or newer and pnpm for the Next.js frontend. The current Next.js
  package requires Node.js `>=20.9.0`.
- A writable persistent data volume for the SQLite database and `data/files`.
  Keep those two data sets together for backup and restore.
- LibreOffice for Office-to-PDF conversion and Tesseract OCR plus the required
  language data for image text extraction. These are local system packages,
  not hosted services.

As an initial practical baseline for one local owner—not a load-tested capacity
guarantee—use at least 2 CPU cores, 4 GB RAM, and 2 GB of free application
storage, plus additional space for uploaded files, derived artifacts, database
growth, and backups. Larger documents and concurrent processing need more CPU,
memory, and storage.

The service can start without LibreOffice or Tesseract, but file processing will
be reported as degraded. Uploads, downloads, and supported processing paths
remain available; install the missing tool and retry affected files after
restarting the backend.

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

Uploaded source bytes and derived context artifacts are stored below
`data/files` by default. Set `CORTEX_FILE_STORAGE_PATH` to move that directory,
and set `CORTEX_FILE_MAX_SIZE_BYTES` to change the per-file upload limit (25 MiB
by default). The file directory and SQLite database must be backed up and
restored together: the database contains source metadata, durable processing
jobs, and artifact manifests, while the filesystem contains raw and derived
bytes. File migrations `0011_file_context_pipeline` and
`0012_normalize_file_context_timestamps` are forward-only for normal
operations; the first migration's downgrade is backup-only because the removed
upload MIME metadata cannot be reconstructed.

File processing runs in a restart-safe local worker. Configure
`CORTEX_FILE_PROCESSING_ENABLED`, `CORTEX_FILE_PROCESSING_POLL_SECONDS`,
`CORTEX_FILE_PROCESSING_LEASE_SECONDS`, `CORTEX_FILE_PROCESSING_MAX_ATTEMPTS`,
and `CORTEX_FILE_PROCESSING_TIMEOUT_SECONDS` for worker behavior. Office
sources use a headless LibreOffice-compatible `soffice` command, selected with
`CORTEX_FILE_CONVERTER_COMMAND`; archive-based Office formats retain a text
fallback for context extraction when PDF conversion is unavailable, but the file
drawer does not render that fallback as an Office preview. Image OCR uses
Tesseract, selected with `CORTEX_FILE_OCR_COMMAND`, and
`CORTEX_FILE_OCR_LANGUAGE` (default `eng`) selects the installed language data.
The worker searches the process PATH and common macOS/Linux install locations,
but it does not install system tools.
Install and verify the tools before enabling production processing, for example:

```bash
# macOS with Homebrew
brew install --cask libreoffice
brew install tesseract
soffice --headless --version
tesseract --version
tesseract --list-langs

# Debian/Ubuntu
sudo apt-get install libreoffice tesseract-ocr tesseract-ocr-eng
soffice --headless --version
tesseract --list-langs
```

Set `CORTEX_FILE_OCR_LANGUAGE` to an installed language code, or a `+`-joined
combination such as `eng+deu`. Missing tools make `/readyz` report
`status: "degraded"` with stable capability warnings while uploads and source
downloads remain available. Missing executables fail fast without consuming
automatic retry attempts; use the file retry action after fixing the runtime.
PDF extraction uses the backend's bundled PDF adapter. Audio and video are
retained as immutable sources but remain unsupported until extractors are
added. Processing failures retain the raw source and no automatic purge is
included.

Apply schema migrations explicitly before starting the service:

```bash
uv sync
uv run alembic upgrade head
uv run uvicorn cortex_backend.app:app --reload
```

The service does not run Alembic automatically. When file processing is
enabled, `/readyz` remains unavailable until the database and file-processing
worker have both completed their readiness checks; `/healthz` remains
dependency-free.

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
- `/api/v1/tags` for the authenticated shared tag catalog. Tags are normalized
  and owner-scoped, use one of the named palette colors `rose`, `sea-glass`,
  `amber`, `slate`, `plum`, `violet`, `sand`, or `destructive`, and can be
  archived and restored without removing historical note or task memberships.
- `/api/v1/tasks` for authenticated task CRUD, filtering, and cursor pagination.
- `/api/v1/files` for authenticated multipart uploads, immutable source
  metadata listing, attachment downloads, bounded processing status/context,
  authenticated derived preview streams, soft deletion, restoration, and
  processing retries. Raw `/content` downloads always use attachment
  semantics. The backend owns Office conversion, PDF text extraction, and
  image OCR; browser-side file parsers are not part of the storage contract.
- `/mcp` as an authenticated Streamable HTTP MCP transport exposing the same
  task, note, activity-log, and immutable file-metadata/context operations to
  agents. MCP clients
  may send either an existing session token or the configured static MCP key as
  a bearer token in the `Authorization` header. Static keys are accepted only
  on `/mcp`; REST endpoints continue to require the browser session and CSRF
  protections. The MCP catalog surface is read-only through `list_tags`; agents
  may apply existing active tags but cannot mutate the catalog.
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
dates, and tags selected from the shared owner-scoped catalog. REST and MCP
accept legacy Markdown input and normalize it to HTML before storage; note
responses always return sanitized HTML in `body`. Note search uses the local SQLite FTS5
extension and treats the `search` parameter as plain keywords with AND
semantics; raw FTS operators are not part of the API contract. Normal note
reads hide soft-deleted records, while `include_deleted=true` and the restore
operation support recovery.

Tasks use the statuses `backlog`, `todo`, `in_progress`, `done`, and `canceled`
and the priorities `none`, `low`, `medium`, and `high`. Task tags are selected
from the shared catalog, normalized per owner, and replaced atomically on
update. REST task and note writes reject unknown or newly archived tag names
and include the allowed active catalog names in the error. `start_at` and
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
task, recurrence, activity-log, notes, and immutable file-context schemas, local-
owner authentication, and shared REST/MCP domain slices. Knowledge, finance,
and self-hosting packaging remain deferred. To roll back the application after
the additive file-context migration, deploy the previous application while
leaving the new tables and derived artifacts in place. Only run a downgrade
against a backed-up local database when intentionally removing these schemas;
restore the database, raw files, and derived artifacts as one backup set.
Use `uv run alembic downgrade 0001_auth_foundation` only when intentionally
removing the task, recurrence, activity-log, notes, and file schemas together.

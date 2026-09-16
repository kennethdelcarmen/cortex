# Cortex Repository Instructions

## Project Context

Cortex is a personal life manager: a cross-platform, hybrid-interface productivity tool with two equivalent access paths:

- A visual, real-time dashboard for manual user control.
- A Model Context Protocol (MCP) gateway through which AI agents such as Claude, Cursor, and inline chat can retrieve context and execute actions.

The intended product direction is local-first and self-hostable. The canonical future deployment is a user-managed Docker Compose stack on Linux, a VPS, or a NAS; Cortex-operated cloud infrastructure is not required for the core product. Business logic belongs in a unified Python service layer that serves both REST endpoints for the web client and MCP transports for AI agents. The repository now contains the backend service foundation and an initial frontend scaffold; domain workflows and deployment packaging remain to be added.

### Architecture Baseline

- FastAPI REST routers and a FastMCP tool registry expose the same service functions. Keep these adapters thin and do not duplicate business logic between them.
- A SQLite-compatible local database file in a mounted application data volume is the planned default persistence model. Turso/libSQL may be evaluated later as an optional adapter; it is not a prerequisite for self-hosting.
- The frontend is a standalone Next.js App Router application under frontend/, using the latest stable Next.js baseline selected at initialization and delivered as part of the self-hosted stack.
- The Python FastAPI backend is planned to run as a user-managed container; no production container or Compose configuration exists yet.
- The core product must not require a Cortex-operated cloud service. Optional hosted integrations may be added later only when they do not make local operation dependent on them.
- Keep deployment portable and avoid introducing a dependency on a heavy managed BaaS platform without an explicit architectural decision.

### Primary Modules

#### Task and Schedule Engine

The planned execution layer handles structured execution, time-blocking, and daily priorities. Future scope includes Kanban boards, calendar views, drag-and-drop status tracking, AI-generated focus blocks, daily agendas, and automatic rescheduling of overdue items. Its relational data includes tasks, priority tags, and time-block constraints.

#### Second Brain and Knowledge Base

The planned RAG and semantic-memory layer indexes Markdown files, journals, and daily reflections. Local full-text search is the baseline retrieval capability. Optional semantic retrieval may use a configured provider later; vector embeddings and their storage format are deferred and must not be treated as current implementation requirements.

#### Financial and Expense Engine

The planned numeric aggregation layer tracks cash flow, budgets, and account health. Future scope includes balances, monthly category limits, spending progress, natural-language expense logging, and budget checks. Its relational data includes accounts, categorized transaction ledgers, and monthly budget allocations.

## Engineering Standards

### Ownership and boundaries

- Put domain behavior in focused service functions with explicit inputs, outputs, and error semantics.
- Keep REST and MCP interfaces behaviorally aligned by routing both through the shared service layer.
- Keep data ownership and lifecycle visible. Treat schema changes, migrations, synchronization, and vector storage as explicit compatibility concerns. Offline-first mobile synchronization is deferred and must not be assumed by current work.
- Prefer small, reversible changes that match existing module boundaries. Avoid abstractions and broad refactors without a concrete ownership or maintenance benefit.

### Correctness, security, and privacy

- Treat user input, files, network responses, database content, and environment values as untrusted.
- Minimize data exposure and retention. Never log credentials, tokens, secrets, or unnecessary personal or financial data.
- Make authentication, authorization, validation, and audit-sensitive behavior explicit and reviewable.
- Preserve data integrity when changing persistence or mutation behavior. If offline synchronization is introduced later, document its invariants explicitly before implementation.

### User experience and accessibility

- Build the complete user workflow, including loading, empty, error, and success states.
- Preserve semantic HTML and native controls where possible. Ensure keyboard access, logical focus order, useful labels, readable contrast, screen-reader-friendly dynamic updates, and support for reduced motion and text scaling.
- Keep layouts stable across supported viewports; do not rely on color alone to communicate meaning.

### Performance and reliability

- Optimize measured or plausible bottlenecks without sacrificing clarity. Avoid unnecessary work in hot paths, repeated rendering, blocking I/O, and unbounded queries or loops.
- Keep resource lifecycles explicit: close handles, cancel work, and clean up listeners.
- For launch-impacting changes, consider observability, failure detection, rollback, backup, and support implications before calling the work production-ready.

### Testing and validation

- Prefer deterministic, isolated tests that describe externally visible behavior.
- Cover normal paths, edge cases, error handling, permission boundaries, migrations, synchronization, and regressions when relevant.
- When changing shared services, verify representative REST and MCP paths for parity.
- For important UI changes, validate rendered behavior in a browser or equivalent visual output when feasible.
- Run the smallest meaningful focused checks first, then broaden validation according to risk. Report exactly what was and was not verified.

### Documentation and Git workflow

- Keep behavior, contracts, setup, decisions, and operational procedures documented near the workflow they describe.
- Update documentation when changing behavior, public interfaces, configuration, or operational expectations.
- Inspect worktree state before editing. Preserve unrelated user changes and avoid destructive Git operations unless explicitly requested.
- Keep commits focused when commits are requested, and explain the maintainer- or user-relevant reason for the change.

## Repository Status and Tooling

This repository currently contains a FastAPI/FastMCP backend under `backend/` with typed settings, health and readiness routes, application composition, persistent SQLite storage, and local-owner authentication. It also contains an initial Next.js frontend scaffold under `frontend/`. Domain workflows, self-hosting packaging, and deployment configuration remain to be added. Do not invent project commands or paths. Establish and document verified setup, development, test, and deployment commands in the appropriate project documentation.

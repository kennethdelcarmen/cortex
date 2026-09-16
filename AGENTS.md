# Cortex Repository Instructions

## Project Context

Cortex is a personal life manager: a cross-platform, hybrid-interface productivity tool with two equivalent access paths:

- A visual, real-time dashboard for manual user control.
- A Model Context Protocol (MCP) gateway through which AI agents such as Claude, Cursor, and inline chat can retrieve context and execute actions.

The current architecture baseline is a $0-cost, serverless/edge-native system. Business logic belongs in a unified Python service layer that serves both REST endpoints for the web client and Server-Sent Events (SSE) for MCP tools.

### Architecture Baseline

- FastAPI REST routers and a FastMCP tool registry expose the same service functions. Keep these adapters thin and do not duplicate business logic between them.
- Turso (libSQL) is the planned embedded edge database, providing distributed SQLite storage, local reads, vector embeddings through `libsql_vector`, and offline-first mobile synchronization.
- The frontend is planned as a Next.js 14 App Router application hosted on Vercel.
- The Python FastAPI backend is planned for a free-tier serverless deployment on Koyeb or Render.
- Keep deployment portable and avoid introducing a dependency on a heavy managed BaaS platform without an explicit architectural decision.

### Primary Modules

#### Task and Schedule Engine

The execution layer handles structured execution, time-blocking, and daily priorities. It supports Kanban boards, calendar views, drag-and-drop status tracking, AI-generated focus blocks, daily agendas, and automatic rescheduling of overdue items. Its relational data includes tasks, priority tags, and time-block constraints.

#### Second Brain and Knowledge Base

The RAG and semantic-memory layer indexes Markdown files, journals, and daily reflections. It stores document metadata, raw text chunks, and 1536-dimensional `F32_BLOB` vector embeddings in Turso for semantic retrieval and visual document management.

#### Financial and Expense Engine

The numeric aggregation layer tracks cash flow, budgets, and account health. It computes balances, monthly category limits, and spending progress, and supports natural-language expense logging and budget checks. Its relational data includes accounts, categorized transaction ledgers, and monthly budget allocations.

## Engineering Standards

### Ownership and boundaries

- Put domain behavior in focused service functions with explicit inputs, outputs, and error semantics.
- Keep REST and MCP interfaces behaviorally aligned by routing both through the shared service layer.
- Keep data ownership and lifecycle visible. Treat schema changes, migrations, synchronization, and vector storage as explicit compatibility concerns.
- Prefer small, reversible changes that match existing module boundaries. Avoid abstractions and broad refactors without a concrete ownership or maintenance benefit.

### Correctness, security, and privacy

- Treat user input, files, network responses, database content, and environment values as untrusted.
- Minimize data exposure and retention. Never log credentials, tokens, secrets, or unnecessary personal or financial data.
- Make authentication, authorization, validation, and audit-sensitive behavior explicit and reviewable.
- Preserve offline-first and synchronization invariants when changing persistence or mutation behavior.

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

This repository is currently a bootstrap repository with no implementation files, manifests, directory conventions, dependency definitions, test runner, or deployment configuration. Do not invent project commands or paths. When implementation begins, establish the toolchain deliberately and document verified setup, development, test, and deployment commands in the appropriate project documentation.

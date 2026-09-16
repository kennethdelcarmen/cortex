<!-- BEGIN:nextjs-agent-rules -->

# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->

# Cortex Frontend Engineering Guide

This guide applies to the frontend/ subtree and supplements the repository
AGENTS.md. The frontend is a standalone Next.js App Router application that
serves the visual access path to the shared Cortex backend.

## Architecture and ownership

- Keep route composition in src/app.
- Keep reusable visual primitives in src/components and shadcn components in
  src/components/ui.
- Keep browser-safe API helpers in src/lib/api.
- Keep future Zustand stores in src/stores and create them only for real local
  interaction state.
- Keep feature-specific components, queries, schemas, and types close to the
  feature once domain work begins.

Next layouts and pages are Server Components by default. Use Client
Components only for state, event handlers, lifecycle effects, browser APIs,
or third-party components that require them. Do not import secrets or
server-only modules into client code.

## State boundaries

- TanStack Query owns remote data, cache freshness, loading/error state, and
  mutation invalidation.
- Zustand owns local UI state such as navigation, filters, drafts, and display
  preferences.
- Do not copy server records into Zustand as a second cache.
- Do not create a global or persisted store speculatively.
- React Server Components must not read from or write to Zustand stores.
- Any future persisted state must be non-sensitive and must handle hydration
  explicitly.

The QueryClient is created once per browser session in src/app/providers.tsx.
Providers should wrap children as narrowly as the app allows.

## API and security

- Use src/lib/api/client.ts for browser requests to the FastAPI service.
- Include credentials for the backend session cookies.
- Forward the readable cortex_csrf cookie on unsafe requests when present.
- Treat all response bodies as untrusted and validate important payloads with
  Zod schemas.
- The only browser-exposed configuration value is NEXT_PUBLIC_API_URL.
- Never place setup secrets, API keys, credentials, or tokens in NEXT_PUBLIC_
  variables, source files, logs, or committed environment files.
- Local backend CORS must include http://localhost:3000 before authenticated
  cross-origin browser requests are used.

## UI and accessibility

- Follow DESIGN.md for the visual language and content hierarchy.
- Use shadcn/ui components as open source in-repository code; customize the
  generated component when the product needs a different behavior or visual
  treatment.
- Preserve semantic HTML, visible focus states, keyboard access, readable
  contrast, text scaling, reduced motion, and screen-reader-friendly labels.
- Build loading, empty, error, hover, focus, and mobile behavior as part of
  each workflow rather than as follow-up polish.
- Do not rely on color alone to communicate status or priority.

## Commands

Run commands from frontend/:

    pnpm dev
    pnpm lint
    pnpm typecheck
    pnpm build

Keep pnpm-lock.yaml committed with package.json changes. Do not add a second
package manager or a root JavaScript workspace without an explicit decision.

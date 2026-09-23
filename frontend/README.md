# Cortex Frontend

The visual access path for Cortex. This is a standalone Next.js App Router
application using TypeScript, Tailwind CSS, shadcn/ui, TanStack Query, Zustand,
and Zod.

## Local setup

Run from this directory:

    pnpm install
    pnpm dev

Open http://localhost:3000.

Copy .env.example to .env.local when connecting to the local backend. Keep the
frontend and API hostnames consistent locally (localhost for both) because the
browser session and CSRF cookies are host-scoped. The browser API URL is
configured with NEXT_PUBLIC_API_URL. The backend must allow http://localhost:3000
in CORTEX_CORS_ORIGINS before authenticated requests are made. On a new
installation, open /setup, enter the CORTEX_SETUP_SECRET configured for the
backend, and choose either a separate 32-character-or-longer MCP key or the
explicit setup-secret reuse option before creating the first owner account.
Returning users can sign in at /login. Authenticated owners can later rotate
or revoke the MCP key from /settings; the raw key is never displayed again.

## Project conventions

- Server Components are the default for pages and layouts.
- TanStack Query owns remote/server state.
- Zustand is reserved for client-only interaction state and has no store until
  a real workflow needs one.
- shadcn/ui components live in src/components/ui and are open for local
  customization.
- API requests go through src/lib/api/client.ts.

See AGENTS.md for engineering rules and DESIGN.md for the visual direction.

## Verification

    pnpm lint
    pnpm typecheck
    pnpm build

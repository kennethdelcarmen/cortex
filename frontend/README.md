# Cortex Frontend

The visual access path for Cortex. This is a standalone Next.js App Router
application using TypeScript, Tailwind CSS, shadcn/ui, TanStack Query, Zustand,
and Zod.

## Local setup

Run from this directory:

    pnpm install
    pnpm dev

Open http://localhost:3000.

Copy .env.example to .env.local when connecting to the local backend. The
browser API URL is configured with NEXT_PUBLIC_API_URL. The backend must allow
http://localhost:3000 in CORTEX_CORS_ORIGINS before authenticated requests are
made.

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

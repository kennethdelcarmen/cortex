import Link from "next/link";
import type { ReactNode } from "react";

type AuthLayoutProps = {
  eyebrow?: string;
  title: string;
  description: string;
  children: ReactNode;
  footer?: ReactNode;
};

export function AuthLayout({
  eyebrow = "Cortex / local-first life manager",
  title,
  description,
  children,
  footer,
}: AuthLayoutProps) {
  return (
    <main className="min-h-[100svh] bg-background px-5 py-8 sm:px-8 sm:py-12">
      <div className="mx-auto grid min-h-[calc(100svh-4rem)] w-full max-w-5xl items-center gap-10 lg:grid-cols-[minmax(0,0.9fr)_minmax(22rem,1fr)] lg:gap-20">
        <section className="max-w-xl">
          <Link
            href="/"
            className="inline-flex rounded-sm font-mono text-xs font-medium uppercase tracking-[0.24em] text-primary outline-none transition-colors hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/40"
          >
            {eyebrow}
          </Link>
          <p className="mt-10 max-w-md font-mono text-xs uppercase tracking-[0.18em] text-muted-foreground">
            Your private command center
          </p>
          <h1 className="mt-4 max-w-xl text-4xl font-semibold tracking-[-0.045em] text-foreground sm:text-5xl">
            {title}
          </h1>
          <p className="mt-5 max-w-lg text-base leading-7 text-muted-foreground sm:text-lg">
            {description}
          </p>
        </section>

        <section className="w-full">
          <div className="rounded-2xl border border-border/80 bg-card p-6 shadow-[0_24px_80px_-44px_color-mix(in_oklab,var(--primary)_40%,transparent)] sm:p-8">
            {children}
          </div>
          {footer ? (
            <p className="mt-5 text-center text-sm text-muted-foreground">
              {footer}
            </p>
          ) : null}
        </section>
      </div>
    </main>
  );
}

export function AuthLoading({ message = "Checking your workspace…" }: { message?: string }) {
  return (
    <main
      className="flex min-h-[100svh] items-center justify-center bg-background px-5 py-8"
      aria-busy="true"
    >
      <div className="w-full max-w-md rounded-2xl border border-border/80 bg-card p-8 shadow-[0_24px_80px_-44px_color-mix(in_oklab,var(--primary)_40%,transparent)]">
        <div className="motion-safe:animate-pulse">
          <div className="h-3 w-36 rounded-full bg-muted" />
          <div className="mt-5 h-10 w-4/5 rounded-lg bg-muted" />
          <div className="mt-4 h-4 w-full rounded-full bg-muted" />
          <div className="mt-2 h-4 w-3/4 rounded-full bg-muted" />
        </div>
        <p className="mt-8 font-mono text-xs uppercase tracking-[0.14em] text-muted-foreground">
          {message}
        </p>
      </div>
    </main>
  );
}

export function InlineError({ message }: { message: string }) {
  return (
    <div
      role="alert"
      aria-live="polite"
      className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm leading-6 text-destructive"
    >
      {message}
    </div>
  );
}

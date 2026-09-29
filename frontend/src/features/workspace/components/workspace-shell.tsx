"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowUpRight, Clock3, LogOut } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";
import { BlockingErrorDialog, useFeedback } from "@/components/feedback";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { useActivityLogger } from "@/features/activity/hooks";
import {
  AuthLayout,
  AuthLoading,
} from "@/features/auth/components/auth-layout";
import { authQueryKey, describeAuthError, logout } from "@/features/auth/api";
import { useCurrentUser } from "@/features/auth/hooks";
import { cn } from "@/lib/utils";
import { CaptureMenu } from "./capture-menu";
import { ActivityFeed } from "@/features/activity/components/activity-feed";
import {
  moduleDefinitions,
  type WorkspaceModule,
  type WorkspaceNavigationItem,
  workspaceNavigation,
} from "../workspace-config";

type WorkspaceShellProps = {
  email: string;
  children: ReactNode;
  sidebarContent?: ReactNode;
};

function isActiveNavigationItem(pathname: string | null, item: WorkspaceNavigationItem) {
  if (item.key === "home") {
    return pathname === "/";
  }

  return pathname === item.href || pathname?.startsWith(`${item.href}/`);
}

function SignOutButton({
  compact = false,
  isPending,
  onSignOut,
}: {
  compact?: boolean;
  isPending: boolean;
  onSignOut: () => void;
}) {
  return (
    <Button
      type="button"
      variant={compact ? "ghost" : "outline"}
      size={compact ? "icon" : "sm"}
      aria-label={compact ? "Sign out" : undefined}
      onClick={onSignOut}
      disabled={isPending}
    >
      <LogOut aria-hidden="true" />
      {!compact ? (isPending ? "Signing out…" : "Sign out") : null}
    </Button>
  );
}

function WorkspaceNavLink({
  item,
  mobile = false,
}: {
  item: WorkspaceNavigationItem;
  mobile?: boolean;
}) {
  const pathname = usePathname();
  const active = isActiveNavigationItem(pathname, item);
  const Icon = item.icon;

  return (
    <Link
      href={item.href}
      aria-current={active ? "page" : undefined}
      className={cn(
        "group relative flex min-h-11 items-center gap-3 rounded-md text-sm outline-none transition-colors focus-visible:ring-3 focus-visible:ring-ring/50",
        mobile
          ? "min-w-16 flex-1 flex-col justify-center gap-1 px-2 py-1 text-[0.68rem]"
          : "px-3 py-2.5",
        active
          ? "bg-chart-4/10 font-medium text-foreground"
          : "text-muted-foreground hover:bg-muted/70 hover:text-foreground",
      )}
    >
      {!mobile ? (
        <span
          aria-hidden="true"
          className={cn(
            "absolute inset-y-2 left-0 w-0.5 rounded-full bg-chart-4 transition-opacity",
            active ? "opacity-100" : "opacity-0",
          )}
        />
      ) : null}
      <Icon aria-hidden="true" className={cn(mobile ? "size-4" : "size-4")} />
      <span>{item.label}</span>
    </Link>
  );
}

function MemorySubNavigation() {
  const pathname = usePathname();

  return (
    <nav
      aria-label="Memory views"
      className="ml-4 mt-1 space-y-0.5 border-l border-border/80 pl-3"
    >
      {[
        { href: "/memory", label: "Journal & Notes" },
        { href: "/memory/files", label: "Files" },
      ].map((view) => {
        const active = pathname === view.href;

        return (
          <Link
            key={view.href}
            href={view.href}
            aria-current={active ? "page" : undefined}
            className={cn(
              "rounded-md text-sm outline-none transition-colors focus-visible:ring-3 focus-visible:ring-ring/50",
              "block px-3 py-1.5 text-xs",
              active
                ? "bg-chart-4/10 font-medium text-foreground"
                : "text-muted-foreground hover:bg-muted/70 hover:text-foreground",
            )}
          >
            {view.label}
          </Link>
        );
      })}
    </nav>
  );
}

function MoneySubNavigation() {
  const pathname = usePathname();

  return (
    <nav
      aria-label="Money views"
      className="ml-4 mt-1 space-y-0.5 border-l border-border/80 pl-3"
    >
      <Link
        href="/money"
        aria-current={pathname === "/money" ? "page" : undefined}
        className={cn(
          "block rounded-md px-3 py-1.5 text-xs outline-none transition-colors focus-visible:ring-3 focus-visible:ring-ring/50",
          pathname === "/money"
            ? "bg-chart-4/10 font-medium text-foreground"
            : "text-muted-foreground hover:bg-muted/70 hover:text-foreground",
        )}
      >
        Overview
      </Link>
      <Link
        href="/money/transactions"
        aria-current={pathname.startsWith("/money/transactions") ? "page" : undefined}
        className={cn(
          "block rounded-md px-3 py-1.5 text-xs outline-none transition-colors focus-visible:ring-3 focus-visible:ring-ring/50",
          pathname.startsWith("/money/transactions")
            ? "bg-chart-4/10 font-medium text-foreground"
            : "text-muted-foreground hover:bg-muted/70 hover:text-foreground",
        )}
      >
        Transactions
      </Link>
      <Link
        href="/money/accounts"
        aria-current={pathname.startsWith("/money/accounts") ? "page" : undefined}
        className={cn(
          "block rounded-md px-3 py-1.5 text-xs outline-none transition-colors focus-visible:ring-3 focus-visible:ring-ring/50",
          pathname.startsWith("/money/accounts")
            ? "bg-chart-4/10 font-medium text-foreground"
            : "text-muted-foreground hover:bg-muted/70 hover:text-foreground",
        )}
      >
        Accounts
      </Link>
      <Link
        href="/money/budgets"
        aria-current={pathname.startsWith("/money/budgets") ? "page" : undefined}
        className={cn(
          "block rounded-md px-3 py-1.5 text-xs outline-none transition-colors focus-visible:ring-3 focus-visible:ring-ring/50",
          pathname.startsWith("/money/budgets")
            ? "bg-chart-4/10 font-medium text-foreground"
            : "text-muted-foreground hover:bg-muted/70 hover:text-foreground",
        )}
      >
        Budgets
      </Link>
    </nav>
  );
}

function WorkspaceSidebar({
  email,
  isSigningOut,
  onSignOut,
  sidebarContent,
}: {
  email: string;
  isSigningOut: boolean;
  onSignOut: () => void;
  sidebarContent?: ReactNode;
}) {
  return (
    <aside className="sticky top-0 hidden h-svh w-60 shrink-0 border-r border-border/80 bg-background lg:flex lg:flex-col">
      <div className="flex min-h-0 flex-1 flex-col px-5 py-7">
        <Link
          href="/"
          aria-label="Cortex home"
          className="group w-fit rounded-sm outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
        >
          <span className="block font-mono text-sm font-medium uppercase tracking-[0.25em] text-primary-strong transition-colors group-hover:text-foreground">
            Cortex
          </span>
          <span className="mt-2 block font-mono text-[0.62rem] uppercase tracking-[0.14em] text-muted-foreground">
            Personal command center
          </span>
        </Link>

        <nav
          aria-label="Primary workspace"
          className="mt-12 min-h-0 flex-1 overflow-y-auto overscroll-contain pr-1"
        >
          <p className="px-3 font-mono text-[0.62rem] uppercase tracking-[0.18em] text-muted-foreground">
            Workspace
          </p>
          <div className="mt-3 space-y-1">
            {workspaceNavigation.map((item) => (
              <div key={item.key}>
                <WorkspaceNavLink item={item} />
                {item.key === "memory" ? <MemorySubNavigation /> : null}
                {item.key === "money" ? <MoneySubNavigation /> : null}
                {item.key === "focus" ? sidebarContent : null}
              </div>
            ))}
          </div>
        </nav>

        <div className="shrink-0">
          <Separator className="mt-5 mb-5" />
          <Card size="sm" className="mb-5 border-border/70 bg-card/50 p-3 ring-0">
            <div className="flex items-center gap-2">
              <span className="size-1.5 rounded-full bg-primary" aria-hidden="true" />
              <span className="font-mono text-[0.65rem] font-medium uppercase tracking-[0.15em] text-primary-strong">
                Local
              </span>
            </div>
            <p className="mt-2 text-xs leading-5 text-muted-foreground">
              Your data stays close to the service you run.
            </p>
          </Card>
          <div className="space-y-3">
            <span className="block truncate font-mono text-[0.65rem] text-muted-foreground">
              {email}
            </span>
            <SignOutButton
              isPending={isSigningOut}
              onSignOut={onSignOut}
            />
          </div>
        </div>
      </div>
    </aside>
  );
}

function MobileWorkspaceHeader({
  isSigningOut,
  onSignOut,
}: {
  isSigningOut: boolean;
  onSignOut: () => void;
}) {
  return (
    <header className="sticky top-0 z-30 border-b border-border/80 bg-background lg:hidden">
      <div className="flex h-16 items-center justify-between gap-4 px-4 sm:px-6">
        <Link
          href="/"
          className="rounded-sm font-mono text-sm font-medium uppercase tracking-[0.23em] text-primary-strong outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
        >
          Cortex
        </Link>
        <div className="flex items-center gap-1">
          <CaptureMenu compact />
          <SignOutButton compact isPending={isSigningOut} onSignOut={onSignOut} />
        </div>
      </div>
    </header>
  );
}

function MobileWorkspaceNav() {
  return (
    <nav
      aria-label="Mobile workspace"
      className="fixed inset-x-0 bottom-0 z-40 border-t border-border/80 bg-background px-2 pt-2 pb-[calc(env(safe-area-inset-bottom)+0.5rem)] lg:hidden"
    >
      <div className="mx-auto flex max-w-md items-stretch justify-between gap-1">
        {workspaceNavigation.map((item) => (
          <WorkspaceNavLink key={item.key} item={item} mobile />
        ))}
      </div>
    </nav>
  );
}

export function WorkspaceShell({ email, children, sidebarContent }: WorkspaceShellProps) {
  const queryClient = useQueryClient();
  const feedback = useFeedback();
  const logActivity = useActivityLogger();
  const mutation = useMutation({
    mutationFn: async () => {
      await logActivity({ event_type: "auth.logged_out" });
      return logout();
    },
    onSuccess: () => {
      queryClient.setQueryData(authQueryKey, null);
    },
    onError: (reason) =>
      feedback.error({
        title: "Sign out failed",
        description: describeAuthError(reason),
      }),
  });

  const signOut = () => {
    mutation.mutate();
  };

  return (
    <div className="min-h-svh bg-background text-foreground">
      <div className="mx-auto flex min-h-svh w-full max-w-[1600px]">
        <WorkspaceSidebar
          email={email}
          isSigningOut={mutation.isPending}
          onSignOut={signOut}
          sidebarContent={sidebarContent}
        />
        <div className="min-w-0 flex-1">
          <MobileWorkspaceHeader
            isSigningOut={mutation.isPending}
            onSignOut={signOut}
          />
          <main className="mx-auto w-full max-w-[1240px] px-5 pb-28 pt-7 sm:px-8 sm:pt-10 lg:px-10 lg:pb-12 lg:pt-12">
            {children}
          </main>
        </div>
      </div>
      <MobileWorkspaceNav />
    </div>
  );
}

function CurrentDateLabel() {
  const now = new Date();
  const dateLabel = new Intl.DateTimeFormat(undefined, {
    weekday: "long",
    month: "long",
    day: "numeric",
    year: "numeric",
  }).format(now);

  return (
    <time
      dateTime={now.toISOString().slice(0, 10)}
      suppressHydrationWarning
      className="font-mono text-[0.68rem] uppercase tracking-[0.18em] text-primary-strong"
    >
      {dateLabel}
    </time>
  );
}

function HomeDashboard() {
  return (
    <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_18rem] lg:gap-14">
      <div className="min-w-0">
        <header className="flex flex-col gap-5 border-b border-border/70 pb-6 sm:flex-row sm:items-end sm:justify-between sm:gap-8">
          <div className="max-w-2xl">
            <CurrentDateLabel />
            <h1 className="mt-3 text-3xl font-semibold tracking-[-0.035em] text-foreground sm:text-4xl">
              Today, in reach.
            </h1>
            <p className="mt-3 max-w-xl text-base leading-7 text-muted-foreground sm:text-base">
              Keep the next meaningful action close, with the rest of your life nearby.
            </p>
          </div>
          <div className="hidden shrink-0 lg:block">
            <CaptureMenu />
          </div>
        </header>

        <section aria-labelledby="focus-sequence-title" className="mt-7 sm:mt-8">
          <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
            <div>
              <p className="font-mono text-[0.66rem] uppercase tracking-[0.18em] text-muted-foreground">
                Today
              </p>
              <h2 id="focus-sequence-title" className="mt-2 text-xl font-medium tracking-[-0.025em] sm:text-2xl">
                Focus sequence
              </h2>
            </div>
            <span className="font-mono text-[0.65rem] uppercase tracking-[0.14em] text-muted-foreground">
              No items yet
            </span>
          </div>

          <Card className="relative overflow-hidden rounded-xl border-border/80 p-0 shadow-[0_20px_60px_-44px_color-mix(in_oklab,var(--foreground)_45%,transparent)]">
            <span className="absolute inset-y-0 left-0 w-1 bg-primary/75" aria-hidden="true" />
            <div className="p-6 sm:p-8">
              <div className="flex items-center gap-2 text-primary-strong">
                <Clock3 aria-hidden="true" className="size-4" />
                <p className="font-mono text-[0.66rem] font-medium uppercase tracking-[0.16em]">
                  Ready for your first move
                </p>
              </div>
              <h3 className="mt-4 max-w-lg text-xl font-medium tracking-[-0.025em] sm:text-2xl">
                Give today a clear beginning.
              </h3>
              <p className="mt-3 max-w-xl text-sm leading-6 text-muted-foreground sm:text-base">
                Your focus sequence will appear here when task and time-block capture is connected. The rust rail will mark priority; labels will keep status and context explicit.
              </p>
              <p className="mt-6 font-mono text-[0.66rem] uppercase tracking-[0.14em] text-muted-foreground">
                Use Add above to shape the day.
              </p>
            </div>
          </Card>
        </section>
      </div>

      <HomeContextRail />
    </div>
  );
}

function HomeContextRail() {
  return (
    <aside className="min-w-0 lg:pt-1" aria-labelledby="context-rail-title">
      <section>
        <p className="font-mono text-[0.66rem] uppercase tracking-[0.18em] text-muted-foreground">
          At a glance
        </p>
        <h2 id="context-rail-title" className="mt-3 max-w-xs text-xl font-medium tracking-[-0.025em]">
          Keep the rest in reach.
        </h2>
        <nav aria-label="Workspace modules" className="mt-7 divide-y divide-border/70 border-y border-border/70">
          {Object.values(moduleDefinitions).map((module) => {
            const Icon = module.icon;

            return (
              <Link
                key={module.key}
                href={module.href}
                className="group flex gap-3 py-4 outline-none transition-colors focus-visible:ring-3 focus-visible:ring-ring/50"
              >
                <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-md border border-border bg-card text-primary-strong transition-colors group-hover:border-primary/40">
                  <Icon aria-hidden="true" className="size-4" />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="flex items-center justify-between gap-2">
                    <span className="text-sm font-medium text-foreground">{module.label}</span>
                    <ArrowUpRight aria-hidden="true" className="size-3.5 text-muted-foreground transition-transform group-hover:-translate-y-0.5 group-hover:translate-x-0.5" />
                  </span>
                  <span className="mt-1 block text-xs leading-5 text-muted-foreground">{module.description}</span>
                </span>
              </Link>
            );
          })}
        </nav>
      </section>

      <section className="mt-10">
        <Separator className="mb-6" />
        <p className="font-mono text-[0.66rem] uppercase tracking-[0.18em] text-muted-foreground">
          Workspace
        </p>
        <div className="mt-4 flex items-center gap-2">
          <span className="size-1.5 rounded-full bg-primary" aria-hidden="true" />
          <Badge variant="outline" className="h-auto rounded-full border-primary/30 px-2 py-0.5 font-mono text-[0.68rem] font-medium uppercase tracking-[0.14em] text-primary-strong">
            Local by default
          </Badge>
        </div>
        <p className="mt-3 text-xs leading-5 text-muted-foreground">
          The visual workspace and agent tools share the same service boundary.
        </p>
      </section>

      <ActivityFeed />
    </aside>
  );
}

export function WorkspaceHome({ email }: { email: string }) {
  return (
    <WorkspaceShell email={email}>
      <HomeDashboard />
    </WorkspaceShell>
  );
}

export function WorkspaceRouteGuard({ children }: { children: ReactNode }) {
  const router = useRouter();
  const currentUser = useCurrentUser();

  useEffect(() => {
    if (currentUser.isSuccess && !currentUser.data) {
      router.replace("/login");
    }
  }, [currentUser.data, currentUser.isSuccess, router]);

  if (currentUser.isPending || (currentUser.isSuccess && !currentUser.data)) {
    return <AuthLoading message="Opening your workspace…" />;
  }

  if (currentUser.isError) {
    return (
      <>
        <AuthLayout
          title="Cortex is taking a moment."
          description="The local service did not answer the workspace check."
        >
          <div className="h-12" aria-hidden="true" />
        </AuthLayout>
        <BlockingErrorDialog
          open
          title="Cortex is taking a moment."
          description={describeAuthError(currentUser.error)}
          action={{
            label: "Try again",
            onClick: () => void currentUser.refetch(),
            pending: currentUser.isFetching,
            pendingLabel: "Checking…",
          }}
        />
      </>
    );
  }

  return <>{children}</>;
}

export function WorkspaceModuleRoute({ moduleKey }: { moduleKey: WorkspaceModule }) {
  const currentUser = useCurrentUser();

  return (
    <WorkspaceRouteGuard>
      {currentUser.data ? (
        <WorkspaceModulePage email={currentUser.data.email} moduleKey={moduleKey} />
      ) : null}
    </WorkspaceRouteGuard>
  );
}

export function WorkspaceModulePage({
  email,
  moduleKey,
}: {
  email: string;
  moduleKey: WorkspaceModule;
}) {
  const moduleDefinition = moduleDefinitions[moduleKey];
  const Icon = moduleDefinition.icon;

  return (
    <WorkspaceShell email={email}>
      <div className="max-w-3xl">
        <header className="flex flex-col gap-5 border-b border-border/70 pb-6 sm:flex-row sm:items-end sm:justify-between sm:gap-8">
          <div>
            <p className="font-mono text-[0.68rem] uppercase tracking-[0.18em] text-primary-strong">
              {moduleDefinition.label} / workspace
            </p>
            <h1 className="mt-3 text-3xl font-semibold tracking-[-0.035em] sm:text-4xl">
              {moduleDefinition.label}
            </h1>
            <p className="mt-3 max-w-xl text-base leading-7 text-muted-foreground sm:text-base">
              {moduleDefinition.description}. A focused place for this part of the life already in motion.
            </p>
          </div>
          <div className="hidden shrink-0 lg:block">
            <CaptureMenu />
          </div>
        </header>

        <Card className="relative mt-7 overflow-hidden rounded-xl border-border/80 p-0 shadow-[0_20px_60px_-44px_color-mix(in_oklab,var(--foreground)_45%,transparent)]">
          <span className="absolute inset-y-0 left-0 w-1 bg-primary/75" aria-hidden="true" />
          <div className="p-6 sm:p-8">
            <div className="flex items-center gap-3">
              <span className="flex size-9 items-center justify-center rounded-md border border-border bg-background text-primary-strong">
                <Icon aria-hidden="true" className="size-4" />
              </span>
              <span className="font-mono text-[0.66rem] font-medium uppercase tracking-[0.16em] text-primary-strong">
                Coming next
              </span>
            </div>
            <h2 className="mt-4 max-w-2xl text-xl font-medium tracking-[-0.025em] sm:text-2xl">
              {moduleDefinition.emptyTitle}
            </h2>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-muted-foreground sm:text-base">
              {moduleDefinition.emptyDescription}
            </p>
            <Link
              href="/"
              className={buttonVariants({
                variant: "outline",
                size: "lg",
                className: "mt-7",
              })}
            >
              Return to Today <ArrowUpRight data-icon="inline-end" aria-hidden="true" />
            </Link>
          </div>
        </Card>
      </div>
    </WorkspaceShell>
  );
}

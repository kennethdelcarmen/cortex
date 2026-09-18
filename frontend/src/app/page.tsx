"use client";

import { ArrowRight } from "lucide-react";
import Link from "next/link";
import { buttonVariants } from "@/components/ui/button";
import { BlockingErrorDialog } from "@/components/feedback";
import { AuthLayout, AuthLoading } from "@/features/auth/components/auth-layout";
import { describeAuthError } from "@/features/auth/api";
import { useCurrentUser } from "@/features/auth/hooks";
import { WorkspaceHome } from "@/features/workspace/components/workspace-shell";

function AuthChoice() {
  return (
    <AuthLayout
      title="A clear surface for the life you’re carrying."
      description="Set up a private local workspace for tasks, notes, schedules, and money—or sign back in to the one you already run."
    >
      <div className="space-y-3">
        <Link
          href="/setup"
          className={buttonVariants({ size: "lg", className: "w-full" })}
        >
          Set up Cortex <ArrowRight data-icon="inline-end" aria-hidden="true" />
        </Link>
        <Link
          href="/login"
          className={buttonVariants({
            variant: "outline",
            size: "lg",
            className: "w-full",
          })}
        >
          Sign in to your workspace
        </Link>
      </div>
      <p className="mt-6 border-t border-border/70 pt-5 font-mono text-[0.68rem] uppercase leading-5 tracking-[0.12em] text-muted-foreground">
        Local by default · your data stays close to the service you run
      </p>
    </AuthLayout>
  );
}

export default function Home() {
  const currentUser = useCurrentUser();

  if (currentUser.isPending) {
    return <AuthLoading />;
  }

  if (currentUser.isError) {
    return (
      <>
        <AuthChoice />
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

  return currentUser.data ? (
    <WorkspaceHome email={currentUser.data.email} />
  ) : (
    <AuthChoice />
  );
}

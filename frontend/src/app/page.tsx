"use client";

import { ArrowRight } from "lucide-react";
import Link from "next/link";
import { Button, buttonVariants } from "@/components/ui/button";
import {
  AuthLayout,
  AuthLoading,
  InlineError,
} from "@/features/auth/components/auth-layout";
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
      <AuthLayout
        title="Cortex is taking a moment."
        description="The local service did not answer the workspace check."
      >
        <div className="space-y-5">
          <InlineError message={describeAuthError(currentUser.error)} />
          <Button
            type="button"
            className="w-full"
            onClick={() => currentUser.refetch()}
          >
            Try again
          </Button>
        </div>
      </AuthLayout>
    );
  }

  return currentUser.data ? (
    <WorkspaceHome email={currentUser.data.email} />
  ) : (
    <AuthChoice />
  );
}

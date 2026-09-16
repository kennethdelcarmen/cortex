"use client";

import { useRouter } from "next/navigation";
import type { ReactNode } from "react";
import { useEffect } from "react";
import { Button } from "@/components/ui/button";
import { describeAuthError } from "../api";
import { useCurrentUser } from "../hooks";
import { AuthLayout, AuthLoading, InlineError } from "./auth-layout";

export function AuthRouteGuard({ children }: { children: ReactNode }) {
  const router = useRouter();
  const currentUser = useCurrentUser();

  useEffect(() => {
    if (currentUser.data) {
      router.replace("/");
    }
  }, [currentUser.data, router]);

  if (currentUser.isPending || currentUser.data) {
    return (
      <AuthLoading
        message={currentUser.data ? "Opening your workspace…" : undefined}
      />
    );
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

  return children;
}

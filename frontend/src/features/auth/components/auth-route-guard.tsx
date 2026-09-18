"use client";

import { useRouter } from "next/navigation";
import type { ReactNode } from "react";
import { useEffect } from "react";
import { BlockingErrorDialog } from "@/components/feedback";
import { describeAuthError } from "../api";
import { useCurrentUser } from "../hooks";
import { AuthLayout, AuthLoading } from "./auth-layout";

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

  return children;
}

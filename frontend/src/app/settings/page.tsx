"use client";

import { Settings2 } from "lucide-react";
import { McpAccessSettings } from "@/features/settings/components/mcp-access-settings";
import {
  WorkspaceRouteGuard,
  WorkspaceShell,
} from "@/features/workspace/components/workspace-shell";
import { useCurrentUser } from "@/features/auth/hooks";

export default function SettingsPage() {
  const currentUser = useCurrentUser();

  return (
    <WorkspaceRouteGuard>
      {currentUser.data ? (
        <WorkspaceShell email={currentUser.data.email}>
          <div className="max-w-3xl">
            <header className="border-b border-border/70 pb-6">
              <div className="flex items-center gap-3">
                <span className="flex size-9 items-center justify-center rounded-md border border-border bg-background text-primary-strong">
                  <Settings2 aria-hidden="true" className="size-4" />
                </span>
                <p className="font-mono text-[0.68rem] uppercase tracking-[0.18em] text-primary-strong">
                  Workspace / settings
                </p>
              </div>
              <h1 className="mt-4 text-3xl font-semibold tracking-[-0.035em] sm:text-4xl">
                Settings
              </h1>
              <p className="mt-3 max-w-xl text-base leading-7 text-muted-foreground">
                Keep your owner account and trusted agent access under your control.
              </p>
            </header>
            <div className="mt-7">
              <McpAccessSettings />
            </div>
          </div>
        </WorkspaceShell>
      ) : null}
    </WorkspaceRouteGuard>
  );
}

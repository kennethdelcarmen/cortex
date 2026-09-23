"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyRound, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useFeedback } from "@/components/feedback";
import { PasswordField } from "@/features/auth/components/password-field";
import {
  describeAuthError,
  getMcpApiKeyStatus,
  replaceMcpApiKey,
  revokeMcpApiKey,
} from "@/features/auth/api";

const MCP_API_KEY_QUERY = ["auth", "mcp-key"] as const;

function formatDate(value: string | null) {
  if (!value) {
    return "Not available";
  }

  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

export function McpAccessSettings() {
  const queryClient = useQueryClient();
  const feedback = useFeedback();
  const [key, setKey] = useState("");
  const [keyError, setKeyError] = useState<string>();
  const [confirmingRevoke, setConfirmingRevoke] = useState(false);
  const status = useQuery({
    queryKey: MCP_API_KEY_QUERY,
    queryFn: getMcpApiKeyStatus,
  });

  const update = useMutation({
    mutationFn: replaceMcpApiKey,
    onSuccess: (nextStatus) => {
      setKey("");
      setKeyError(undefined);
      queryClient.setQueryData(MCP_API_KEY_QUERY, nextStatus);
      feedback.success({
        title: "MCP access key saved",
        description: "Use the new key as Codex’s bearer token.",
      });
    },
    onError: (error) => {
      setKeyError(describeAuthError(error));
    },
  });

  const revoke = useMutation({
    mutationFn: revokeMcpApiKey,
    onSuccess: async () => {
      setConfirmingRevoke(false);
      await queryClient.invalidateQueries({ queryKey: MCP_API_KEY_QUERY });
      feedback.success({
        title: "MCP access revoked",
        description: "Existing static-key clients can no longer access MCP tools.",
      });
    },
    onError: (error) => {
      setConfirmingRevoke(false);
      feedback.error({
        title: "MCP access could not be revoked",
        description: describeAuthError(error),
      });
    },
  });

  function submitKey() {
    if (key.length < 32) {
      setKeyError("Use at least 32 characters.");
      return;
    }

    setKeyError(undefined);
    update.mutate(key);
  }

  if (status.isPending) {
    return <p className="text-sm text-muted-foreground" role="status">Loading access settings…</p>;
  }

  if (status.isError) {
    return (
      <Card className="border-destructive/30 bg-destructive/5">
        <CardContent className="p-6">
          <p className="text-sm text-destructive">{describeAuthError(status.error)}</p>
          <Button className="mt-4" variant="outline" onClick={() => void status.refetch()}>
            Try again
          </Button>
        </CardContent>
      </Card>
    );
  }

  const keyStatus = status.data;
  const active = keyStatus.configured && !keyStatus.revoked;

  return (
    <div className="space-y-6">
      <Card className="border-border/80">
        <CardHeader>
          <div className="flex items-start gap-3">
            <span className="flex size-9 shrink-0 items-center justify-center rounded-md border border-border bg-background text-primary-strong">
              <ShieldCheck aria-hidden="true" className="size-4" />
            </span>
            <div>
              <CardTitle>MCP access</CardTitle>
              <CardDescription className="mt-1.5 leading-6">
                Give Codex and other trusted agents a long-lived bearer key for Cortex’s MCP
                tools. This key grants the same owner access as your account.
              </CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="rounded-lg border border-border/70 bg-muted/30 p-4">
            <div className="flex items-center gap-2 text-sm font-medium">
              <KeyRound aria-hidden="true" className="size-4 text-primary-strong" />
              <span>{active ? "Active MCP key" : keyStatus.revoked ? "MCP key revoked" : "No MCP key configured"}</span>
            </div>
            <p className="mt-2 text-xs leading-5 text-muted-foreground">
              {keyStatus.configured
                ? `Last changed ${formatDate(keyStatus.updated_at)}`
                : "Existing browser sessions can still use MCP until you configure a static key."}
            </p>
          </div>

          <div className="space-y-3">
            <PasswordField
              id="mcp-api-key"
              label={keyStatus.configured ? "Replace MCP access key" : "Set MCP access key"}
              hint="At least 32 characters. The raw key is never shown after saving."
              error={keyError}
              name="mcp-api-key"
              autoComplete="new-password"
              value={key}
              onChange={(event) => {
                setKey(event.target.value);
                setKeyError(undefined);
              }}
              disabled={update.isPending || revoke.isPending}
            />
            <Button type="button" onClick={submitKey} disabled={update.isPending || revoke.isPending}>
              {update.isPending ? "Saving…" : keyStatus.configured ? "Rotate key" : "Save key"}
            </Button>
          </div>

          {keyStatus.configured && !keyStatus.revoked ? (
            <div className="border-t border-border/70 pt-5">
              {confirmingRevoke ? (
                <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4">
                  <p className="text-sm font-medium text-foreground">Revoke this MCP key?</p>
                  <p className="mt-1 text-xs leading-5 text-muted-foreground">
                    Codex will receive an authentication error until you save a new key.
                  </p>
                  <div className="mt-4 flex flex-wrap gap-2">
                    <Button
                      type="button"
                      variant="destructive"
                      onClick={() => revoke.mutate()}
                      disabled={revoke.isPending}
                    >
                      {revoke.isPending ? "Revoking…" : "Confirm revoke"}
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      onClick={() => setConfirmingRevoke(false)}
                      disabled={revoke.isPending}
                    >
                      Keep key
                    </Button>
                  </div>
                </div>
              ) : (
                <Button
                  type="button"
                  variant="destructive"
                  onClick={() => setConfirmingRevoke(true)}
                  disabled={update.isPending || revoke.isPending}
                >
                  Revoke MCP key
                </Button>
              )}
            </div>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}

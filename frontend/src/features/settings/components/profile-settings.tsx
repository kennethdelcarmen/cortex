"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { UserRound } from "lucide-react";
import { useState } from "react";
import { useFeedback } from "@/components/feedback";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { authQueryKey, describeAuthError, updateProfile, type User } from "@/features/auth/api";

export function ProfileSettings({ user }: { user: User }) {
  const queryClient = useQueryClient();
  const feedback = useFeedback();
  const [displayName, setDisplayName] = useState(user.display_name ?? "");
  const mutation = useMutation({
    mutationFn: () => updateProfile(displayName),
    onSuccess: (nextUser) => {
      queryClient.setQueryData(authQueryKey, nextUser);
      setDisplayName(nextUser.display_name ?? "");
      feedback.success({
        title: "Profile saved",
        description: "Your Home greeting is up to date.",
      });
    },
    onError: (error) =>
      feedback.error({
        title: "Profile could not be saved",
        description: describeAuthError(error),
      }),
  });

  return (
    <Card className="border-border/80">
      <CardHeader>
        <div className="flex items-start gap-3">
          <span className="flex size-9 shrink-0 items-center justify-center rounded-md border border-border bg-background text-primary-strong">
            <UserRound aria-hidden="true" className="size-4" />
          </span>
          <div>
            <CardTitle>Profile</CardTitle>
            <CardDescription className="mt-1.5 leading-6">
              Choose the name Cortex uses in your daily greeting.
            </CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <form
          className="flex flex-col gap-3 sm:flex-row sm:items-end"
          onSubmit={(event) => {
            event.preventDefault();
            mutation.mutate();
          }}
        >
          <div className="min-w-0 flex-1 space-y-2">
            <Label htmlFor="profile-display-name">Display name</Label>
            <Input
              id="profile-display-name"
              value={displayName}
              maxLength={80}
              onChange={(event) => setDisplayName(event.target.value)}
              placeholder="Your name"
              disabled={mutation.isPending}
            />
          </div>
          <Button type="submit" disabled={mutation.isPending}>
            {mutation.isPending ? "Saving…" : "Save profile"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

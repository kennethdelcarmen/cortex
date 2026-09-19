"use client";

import { useQuery } from "@tanstack/react-query";
import { formatDistanceToNow } from "date-fns";
import { Activity, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import {
  listActivityLogs,
  recentActivityQueryKey,
  type ActivityLog,
} from "../api";

const RECENT_ACTIVITY_LIMIT = 6;

function metadataText(log: ActivityLog, key: string) {
  const value = log.metadata[key];
  return typeof value === "string" && value.trim() ? value : null;
}

function metadataTextList(log: ActivityLog, key: string) {
  const value = log.metadata[key];

  if (!Array.isArray(value)) {
    return [];
  }

  return value.filter((item): item is string => typeof item === "string");
}

function activityCopy(log: ActivityLog) {
  const title = metadataText(log, "title");

  switch (log.event_type) {
    case "task.created":
      return {
        summary: "Created task",
        detail: title,
      };
    case "task.updated": {
      const fields = metadataTextList(log, "changed_fields");
      const status = metadataText(log, "status");
      const priority = metadataText(log, "priority");
      const values = [
        fields.length > 0 ? fields.join(", ") : null,
        status ? `Status: ${status.replaceAll("_", " ")}` : null,
        priority ? `Priority: ${priority}` : null,
      ].filter((value): value is string => Boolean(value));

      return {
        summary: "Updated task",
        detail: [title, values.join(" · ")].filter(Boolean).join(" · ") || null,
      };
    }
    case "task.deleted":
      return {
        summary: "Deleted task",
        detail: title,
      };
    case "auth.logged_in":
      return {
        summary: "Signed in",
        detail: null,
      };
    case "auth.setup_completed":
      return {
        summary: "Created the owner workspace",
        detail: null,
      };
    case "auth.logged_out":
      return {
        summary: "Signed out",
        detail: null,
      };
    default:
      return {
        summary: "Activity recorded",
        detail: log.event_type,
      };
  }
}

function activityTime(createdAt: string) {
  const date = new Date(createdAt);

  if (Number.isNaN(date.valueOf())) {
    return "Unknown time";
  }

  return formatDistanceToNow(date, { addSuffix: true });
}

function ActivityFeedSkeleton() {
  return (
    <div className="mt-5 space-y-4" aria-hidden="true">
      {Array.from({ length: 3 }).map((_, index) => (
        <div key={index} className="flex gap-3">
          <Skeleton className="mt-1.5 size-2 shrink-0 rounded-full" />
          <div className="min-w-0 flex-1 space-y-2">
            <Skeleton className="h-3.5 w-4/5" />
            <Skeleton className="h-3 w-2/5" />
          </div>
        </div>
      ))}
    </div>
  );
}

function ActivityItem({ log }: { log: ActivityLog }) {
  const copy = activityCopy(log);

  return (
    <li className="flex gap-3 border-b border-border/70 py-3 last:border-b-0 last:pb-0 first:pt-0">
      <span
        className="mt-1.5 size-2 shrink-0 rounded-full bg-primary"
        aria-hidden="true"
      />
      <div className="min-w-0 flex-1">
        <div className="flex items-start justify-between gap-3">
          <p className="min-w-0 text-sm font-medium leading-5 text-foreground">
            {copy.summary}
          </p>
          <time
            dateTime={log.created_at}
            title={new Date(log.created_at).toLocaleString()}
            className="shrink-0 font-mono text-[0.62rem] uppercase tracking-[0.08em] text-muted-foreground"
          >
            {activityTime(log.created_at)}
          </time>
        </div>
        {copy.detail ? (
          <p className="mt-1 truncate text-xs leading-5 text-muted-foreground">
            {copy.detail}
          </p>
        ) : null}
      </div>
    </li>
  );
}

export function ActivityFeed() {
  const query = useQuery({
    queryKey: recentActivityQueryKey,
    queryFn: () => listActivityLogs(RECENT_ACTIVITY_LIMIT),
  });

  return (
    <section className="mt-10" aria-labelledby="recent-activity-title">
      <Separator className="mb-6" />
      <div className="flex items-end justify-between gap-3">
        <div>
          <p className="font-mono text-[0.66rem] uppercase tracking-[0.18em] text-muted-foreground">
            History
          </p>
          <h2 id="recent-activity-title" className="mt-3 text-xl font-medium tracking-[-0.025em]">
            Recent activity
          </h2>
        </div>
        <Activity aria-hidden="true" className="size-4 text-primary" />
      </div>

      {query.isPending ? (
        <ActivityFeedSkeleton />
      ) : query.isError ? (
        <div className="mt-5 rounded-md border border-border/70 bg-card/40 p-4">
          <p className="text-sm font-medium text-foreground">Activity is unavailable.</p>
          <p className="mt-1 text-xs leading-5 text-muted-foreground">
            The rest of your workspace is still available.
          </p>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="mt-3"
            onClick={() => void query.refetch()}
            disabled={query.isFetching}
          >
            <RefreshCw aria-hidden="true" className={query.isFetching ? "animate-spin" : undefined} />
            {query.isFetching ? "Retrying…" : "Try again"}
          </Button>
        </div>
      ) : query.data.items.length === 0 ? (
        <div className="mt-5 border-y border-border/70 py-4">
          <p className="text-sm font-medium text-foreground">Nothing recorded yet.</p>
          <p className="mt-1 text-xs leading-5 text-muted-foreground">
            Completed actions will stay close here.
          </p>
        </div>
      ) : (
        <ol className="mt-5" aria-label="Recent activity items">
          {query.data.items.map((log) => (
            <ActivityItem key={log.id} log={log} />
          ))}
        </ol>
      )}
    </section>
  );
}

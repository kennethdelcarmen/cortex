import { z } from "zod";
import { apiFetch } from "@/lib/api/client";

const ACTIVITY_LOG_TIMEOUT_MS = 1_500;

const activityMetadataSchema = z.record(z.string(), z.unknown());

export const activityLogSchema = z.object({
  id: z.string().min(1),
  user_id: z.string().min(1),
  event_type: z.string().min(1),
  entity_type: z.string().min(1).nullable(),
  entity_id: z.string().min(1).nullable(),
  metadata: activityMetadataSchema,
  created_at: z.string().min(1),
});

const activityLogListResponseSchema = z.object({
  items: z.array(activityLogSchema),
  next_cursor: z.string().nullable(),
});

export type ActivityLog = z.infer<typeof activityLogSchema>;
export type ActivityLogPage = z.infer<typeof activityLogListResponseSchema>;
export type ActivityLogMetadata = z.infer<typeof activityMetadataSchema>;

export type ActivityEventType =
  | "task.created"
  | "task.updated"
  | "task.deleted"
  | "auth.logged_in"
  | "auth.setup_completed"
  | "auth.logged_out";

export type ActivityLogWriteInput = {
  event_type: ActivityEventType;
  entity_type?: string | null;
  entity_id?: string | null;
  metadata?: ActivityLogMetadata;
};

export const activityLogQueryKey = ["activity-logs"] as const;
export const recentActivityQueryKey = [...activityLogQueryKey, "recent"] as const;

export function listActivityLogs(limit = 6) {
  const params = new URLSearchParams({ limit: String(limit) });

  return apiFetch(
    `/api/v1/activity-logs?${params.toString()}`,
    {},
    activityLogListResponseSchema,
  );
}

export function appendActivityLog(
  payload: ActivityLogWriteInput,
  signal?: AbortSignal,
) {
  return apiFetch(
    "/api/v1/activity-logs",
    {
      method: "POST",
      body: JSON.stringify({
        event_type: payload.event_type,
        entity_type: payload.entity_type ?? null,
        entity_id: payload.entity_id ?? null,
        metadata: payload.metadata ?? {},
      }),
      signal,
    },
    activityLogSchema,
  );
}

export async function tryAppendActivityLog(
  payload: ActivityLogWriteInput,
): Promise<boolean> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), ACTIVITY_LOG_TIMEOUT_MS);

  try {
    await appendActivityLog(payload, controller.signal);
    return true;
  } catch {
    return false;
  } finally {
    clearTimeout(timeout);
  }
}

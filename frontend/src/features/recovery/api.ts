import { z } from "zod";
import { apiFetch } from "@/lib/api/client";

export const recoveryItemTypeSchema = z.enum(["task", "note", "file", "tag"]);
export const recoveryMutationStatusSchema = z.enum([
  "restored",
  "permanently_deleted",
  "failed",
]);

export const recoveryItemSchema = z.object({
  type: recoveryItemTypeSchema,
  id: z.string().min(1),
  label: z.string().min(1),
  removed_at: z.string().min(1),
  created_at: z.string().min(1),
});

const recoveryListResponseSchema = z.object({
  items: z.array(recoveryItemSchema),
  next_cursor: z.string().nullable(),
});

export const recoveryItemReferenceSchema = z.object({
  type: recoveryItemTypeSchema,
  id: z.string().min(1),
});

const recoveryErrorSchema = z.object({
  code: z.string().min(1),
  message: z.string().min(1),
});

const recoveryMutationResultSchema = z.object({
  item: recoveryItemReferenceSchema,
  status: recoveryMutationStatusSchema,
  error: recoveryErrorSchema.nullable(),
});

const recoveryMutationResponseSchema = z.object({
  results: z.array(recoveryMutationResultSchema),
});

export type RecoveryItemType = z.infer<typeof recoveryItemTypeSchema>;
export type RecoveryItem = z.infer<typeof recoveryItemSchema>;
export type RecoveryListPage = z.infer<typeof recoveryListResponseSchema>;
export type RecoveryItemReference = z.infer<typeof recoveryItemReferenceSchema>;
export type RecoveryMutationResult = z.infer<typeof recoveryMutationResultSchema>;
export type RecoveryMutationResponse = z.infer<typeof recoveryMutationResponseSchema>;

export const recoveryQueryKey = ["recovery"] as const;

export function listRecoveryItems(cursor?: string, limit = 50) {
  const params = new URLSearchParams({ limit: String(limit) });

  if (cursor) {
    params.set("cursor", cursor);
  }

  return apiFetch(
    `/api/v1/recovery?${params.toString()}`,
    {},
    recoveryListResponseSchema,
  );
}

function mutateRecoveryItems(
  path: "/restore" | "/permanent-delete",
  items: RecoveryItemReference[],
) {
  return apiFetch(
    `/api/v1/recovery${path}`,
    {
      method: "POST",
      body: JSON.stringify({ items }),
    },
    recoveryMutationResponseSchema,
  );
}

export function restoreRecoveryItems(items: RecoveryItemReference[]) {
  return mutateRecoveryItems("/restore", items);
}

export function permanentlyDeleteRecoveryItems(items: RecoveryItemReference[]) {
  return mutateRecoveryItems("/permanent-delete", items);
}

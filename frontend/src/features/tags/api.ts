import { z } from "zod";
import { apiFetch } from "@/lib/api/client";

export const tagColorSchema = z.enum([
  "rose",
  "sea-glass",
  "amber",
  "slate",
  "plum",
  "violet",
  "sand",
  "destructive",
]);

export const tagSchema = z.object({
  id: z.string().min(1),
  name: z.string().min(1),
  color: tagColorSchema,
  active: z.boolean(),
  created_at: z.string().min(1),
  archived_at: z.string().min(1).nullable(),
});

const tagListResponseSchema = z.object({
  items: z.array(tagSchema),
});

export type TagColor = z.infer<typeof tagColorSchema>;
export type Tag = z.infer<typeof tagSchema>;

export const TAG_COLORS: Array<{ value: TagColor; label: string }> = [
  { value: "rose", label: "Rose" },
  { value: "sea-glass", label: "Sea glass" },
  { value: "amber", label: "Amber" },
  { value: "slate", label: "Slate" },
  { value: "plum", label: "Plum" },
  { value: "violet", label: "Violet" },
  { value: "sand", label: "Sand" },
  { value: "destructive", label: "Destructive" },
];

export const tagsQueryKey = ["tags"] as const;

export function getTags(includeInactive = false) {
  const params = new URLSearchParams();
  if (includeInactive) {
    params.set("include_inactive", "true");
  }

  return apiFetch(
    `/api/v1/tags${params.size ? `?${params.toString()}` : ""}`,
    {},
    tagListResponseSchema,
  );
}

export function createTag(payload: { name: string; color?: TagColor }) {
  return apiFetch(
    "/api/v1/tags",
    { method: "POST", body: JSON.stringify(payload) },
    tagSchema,
  );
}

export function updateTag(
  tagId: string,
  payload: { name?: string; color?: TagColor },
) {
  return apiFetch(
    `/api/v1/tags/${encodeURIComponent(tagId)}`,
    { method: "PATCH", body: JSON.stringify(payload) },
    tagSchema,
  );
}

export function archiveTag(tagId: string) {
  return apiFetch(
    `/api/v1/tags/${encodeURIComponent(tagId)}`,
    { method: "DELETE" },
    tagSchema,
  );
}

export function restoreTag(tagId: string) {
  return apiFetch(
    `/api/v1/tags/${encodeURIComponent(tagId)}/restore`,
    { method: "POST" },
    tagSchema,
  );
}

export function permanentlyDeleteTag(tagId: string) {
  return apiFetch<void>(
    `/api/v1/tags/${encodeURIComponent(tagId)}/permanent`,
    { method: "DELETE" },
  );
}

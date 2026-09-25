import { z } from "zod";
import { apiFetch, apiFetchBlob } from "@/lib/api/client";

export const storedFileSchema = z.object({
  id: z.string().min(1),
  name: z.string().min(1),
  size_bytes: z.number().int().nonnegative(),
  sha256: z.string().length(64),
  context_status: z.enum(["pending", "processing", "ready", "unsupported", "failed"]),
  created_at: z.string().min(1),
  updated_at: z.string().min(1),
  deleted_at: z.string().nullable(),
});

export const fileContextSchema = z.object({
  file_id: z.string().min(1),
  name: z.string().min(1),
  status: z.enum(["pending", "processing", "ready", "unsupported", "failed"]),
  text: z.string().nullable(),
  truncated: z.boolean(),
  preview_kind: z.enum(["text", "pdf", "image"]).nullable(),
  error: z.string().nullable(),
  processed_at: z.string().nullable(),
});

const storedFileListResponseSchema = z.object({
  items: z.array(storedFileSchema),
  next_cursor: z.string().nullable(),
});

export type StoredFile = z.infer<typeof storedFileSchema>;
export type StoredFileListPage = z.infer<typeof storedFileListResponseSchema>;
export type FileContext = z.infer<typeof fileContextSchema>;

export const filesQueryKey = ["files"] as const;

export function listFiles(cursor?: string) {
  const params = new URLSearchParams({ limit: "50" });

  if (cursor) {
    params.set("cursor", cursor);
  }

  return apiFetch(
    `/api/v1/files?${params.toString()}`,
    {},
    storedFileListResponseSchema,
  );
}

export function uploadFile(file: globalThis.File) {
  const formData = new FormData();
  formData.append("file", file);

  return apiFetch(
    "/api/v1/files",
    {
      method: "POST",
      body: formData,
    },
    storedFileSchema,
  );
}

export function downloadFile(fileId: string) {
  return apiFetchBlob(`/api/v1/files/${encodeURIComponent(fileId)}/content`);
}

export function getFileContext(fileId: string, maxCharacters = 20_000) {
  const params = new URLSearchParams({ max_characters: String(maxCharacters) });
  return apiFetch(
    `/api/v1/files/${encodeURIComponent(fileId)}/preview?${params.toString()}`,
    {},
    fileContextSchema,
  );
}

export function downloadPreview(fileId: string) {
  return apiFetchBlob(`/api/v1/files/${encodeURIComponent(fileId)}/preview/content`);
}

export function deleteFile(fileId: string) {
  return apiFetch<void>(`/api/v1/files/${encodeURIComponent(fileId)}`, {
    method: "DELETE",
  });
}

export function retryFileProcessing(fileId: string) {
  return apiFetch(
    `/api/v1/files/${encodeURIComponent(fileId)}/processing/retry`,
    { method: "POST" },
    storedFileSchema,
  );
}

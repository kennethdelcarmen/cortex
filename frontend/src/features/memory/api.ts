import { z } from "zod";
import { apiFetch } from "@/lib/api/client";
import { storedFileSchema } from "./files-api";
import { tagColorSchema } from "@/features/tags/api";

export const noteSchema = z.object({
  id: z.string().min(1),
  title: z.string().nullable(),
  body: z.string().min(1),
  journal_date: z.string().nullable(),
  tags: z.array(z.string()),
  attachments: z.array(storedFileSchema),
  created_at: z.string().min(1),
  updated_at: z.string().min(1),
  deleted_at: z.string().nullable(),
});

const noteListResponseSchema = z.object({
  items: z.array(noteSchema),
  next_cursor: z.string().nullable(),
});

const noteSummaryResponseSchema = z.object({
  tags: z.array(
    z.object({
      name: z.string().min(1),
      count: z.number().int().nonnegative(),
      color: tagColorSchema,
      active: z.boolean(),
    }),
  ),
});

export type Note = z.infer<typeof noteSchema>;
export type NoteListPage = z.infer<typeof noteListResponseSchema>;
export type NoteSummary = z.infer<typeof noteSummaryResponseSchema>;

export type NoteListFilters = {
  search?: string;
  tag?: string;
};

export type NoteWriteInput = {
  title: string | null;
  body: string;
  journal_date: string | null;
  tags: string[];
  file_ids: string[];
};

export const notesQueryKey = ["notes"] as const;
export const noteSummaryQueryKey = [...notesQueryKey, "summary"] as const;

function buildNotesPath(filters: NoteListFilters, cursor?: string) {
  const params = new URLSearchParams();

  if (filters.search) {
    params.set("search", filters.search);
  }

  if (filters.tag) {
    params.set("tag", filters.tag);
  }

  params.set("limit", "50");

  if (cursor) {
    params.set("cursor", cursor);
  }

  return `/api/v1/notes?${params.toString()}`;
}

export function listNotes(filters: NoteListFilters, cursor?: string) {
  return apiFetch(buildNotesPath(filters, cursor), {}, noteListResponseSchema);
}

export function getNoteSummary() {
  return apiFetch(
    "/api/v1/notes/summary",
    {},
    noteSummaryResponseSchema,
  );
}

export function getNote(noteId: string) {
  return apiFetch(
    `/api/v1/notes/${encodeURIComponent(noteId)}`,
    {},
    noteSchema,
  );
}

export function createNote(payload: NoteWriteInput) {
  return apiFetch(
    "/api/v1/notes",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    noteSchema,
  );
}

export function updateNote(noteId: string, payload: NoteWriteInput) {
  return apiFetch(
    `/api/v1/notes/${encodeURIComponent(noteId)}`,
    {
      method: "PATCH",
      body: JSON.stringify(payload),
    },
    noteSchema,
  );
}

export function deleteNote(noteId: string) {
  return apiFetch<void>(`/api/v1/notes/${encodeURIComponent(noteId)}`, {
    method: "DELETE",
  });
}

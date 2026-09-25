"use client";

import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import {
  BookOpenText,
  CalendarDays,
  ChevronDown,
  ChevronRight,
  LoaderCircle,
  Pencil,
  Plus,
  Search,
  Trash2,
} from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { BlockingErrorDialog, useFeedback } from "@/components/feedback";
import { TagBadge } from "@/components/tag-badge";
import { TagPicker } from "@/components/tag-picker";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api/client";
import { cn } from "@/lib/utils";
import {
  createNote,
  deleteNote,
  getNote,
  getNoteSummary,
  listNotes,
  noteSummaryQueryKey,
  notesQueryKey,
  updateNote,
  type Note,
  type NoteListFilters,
  type NoteListPage,
  type NoteWriteInput,
} from "../api";
import { clearMemorySelection, parseMemoryUrlState } from "../memory-filters";
import { ConfirmDialog } from "./confirm-dialog";
import { htmlToText } from "./html-content";
import { RichTextEditor } from "./rich-text-editor";
import {
  WorkspaceRouteGuard,
  WorkspaceShell,
} from "@/features/workspace/components/workspace-shell";
import { useCurrentUser } from "@/features/auth/hooks";
import type { Tag, TagColor } from "@/features/tags/api";
import { createTag, getTags, tagsQueryKey } from "@/features/tags/api";

type NoteDraft = {
  title: string;
  body: string;
  journalDate: string;
  tags: string[];
};

const todayFormatter = new Intl.DateTimeFormat(undefined, {
  month: "short",
  day: "numeric",
  year: "numeric",
});

const updatedFormatter = new Intl.DateTimeFormat(undefined, {
  month: "short",
  day: "numeric",
  hour: "numeric",
  minute: "2-digit",
});

function localDateInput(date = new Date()) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function formatJournalDate(value: string | null) {
  if (!value) {
    return "Undated";
  }

  return todayFormatter.format(new Date(`${value}T12:00:00`));
}

function formatUpdatedAt(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Recently" : updatedFormatter.format(date);
}

function noteTitle(note: Note) {
  if (note.title?.trim()) {
    return note.title;
  }

  const firstLine = htmlToText(note.body)
    .split("\n")
    .map((line) => line.trim())
    .find(Boolean);

  return firstLine?.slice(0, 72) || "Untitled note";
}

function noteExcerpt(body: string) {
  const excerpt = htmlToText(body);

  return excerpt.length > 156 ? `${excerpt.slice(0, 156).trimEnd()}…` : excerpt;
}

function createBlankDraft(): NoteDraft {
  return {
    title: "",
    body: "",
    journalDate: localDateInput(),
    tags: [],
  };
}

function noteToDraft(note: Note): NoteDraft {
  return {
    title: note.title ?? "",
    body: note.body,
    journalDate: note.journal_date ?? "",
    tags: note.tags,
  };
}

function draftPayload(draft: NoteDraft): NoteWriteInput {
  return {
    title: draft.title.trim() || null,
    body: draft.body.trim(),
    journal_date: draft.journalDate || null,
    tags: draft.tags,
  };
}

function isSessionError(error: unknown) {
  return error instanceof ApiError && error.code === "unauthenticated";
}

function describeNoteError(error: unknown) {
  if (!(error instanceof ApiError)) {
    return "The note request could not be completed. Try again.";
  }

  switch (error.code) {
    case "network_error":
      return "Cortex could not be reached. Check that the backend is running and try again.";
    case "invalid_note_cursor":
      return "This note list expired. Refresh the list and try again.";
    case "invalid_note_query":
      return "That note search could not be used. Try a shorter search or clear the filter.";
    case "invalid_note_tag":
      return "Tags must be non-empty and no longer than 64 characters.";
    case "note_not_found":
      return "That note is no longer available. Refresh the list to continue.";
    case "unauthenticated":
      return "Your session has ended. Sign in again to continue.";
    default:
      return "The note request could not be completed. Try again.";
  }
}

function TagEditor({
  tags,
  availableTags,
  onCreateTag,
  disabled,
  onChange,
}: {
  tags: string[];
  availableTags: Tag[];
  onCreateTag?: (payload: { name: string; color: TagColor }) => Promise<Tag>;
  disabled: boolean;
  onChange: (tags: string[]) => void;
}) {
  return (
    <div className="space-y-2">
      <Label htmlFor="note-tags">Tags</Label>
      <TagPicker
        id="note-tags"
        tags={availableTags}
        value={tags}
        onChange={onChange}
        onCreateTag={onCreateTag}
        disabled={disabled}
      />
    </div>
  );
}

function NoteListItem({
  note,
  selected,
  onSelect,
}: {
  note: Note;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <li>
      <button
        type="button"
        aria-current={selected ? "true" : undefined}
        onClick={onSelect}
        className={cn(
          "group relative block w-full overflow-hidden border-b border-border/70 px-4 py-4 text-left outline-none transition-colors focus-visible:z-10 focus-visible:ring-3 focus-visible:ring-ring/50",
          selected
            ? "bg-primary/8"
            : "hover:bg-muted/55",
        )}
      >
        <span
          aria-hidden="true"
          className={cn(
            "absolute inset-y-0 left-0 w-1 bg-primary transition-opacity",
            selected ? "opacity-100" : "opacity-0 group-hover:opacity-50",
          )}
        />
        <div className="flex items-start gap-2">
          <span
            aria-hidden="true"
            className={cn(
              "mt-1.5 size-2 shrink-0 rounded-full",
              note.journal_date ? "bg-primary-strong" : "bg-muted-foreground/55",
            )}
          />
          <span className="min-w-0 flex-1">
            <span className="block truncate font-mono text-sm font-medium text-foreground">
              {noteTitle(note)}
            </span>
            <span className="mt-2 block line-clamp-2 text-sm leading-5 text-muted-foreground">
              {noteExcerpt(note.body) || "No preview text yet."}
            </span>
          </span>
          <ChevronRight
            aria-hidden="true"
            className={cn(
              "mt-0.5 size-4 shrink-0 text-muted-foreground transition-transform",
              selected && "translate-x-0.5 text-primary-strong",
            )}
          />
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 pl-4 font-mono text-[0.64rem] uppercase tracking-[0.08em] text-muted-foreground">
          <span>{formatJournalDate(note.journal_date)}</span>
          <span aria-hidden="true">·</span>
          <span>{formatUpdatedAt(note.updated_at)}</span>
          {note.tags.slice(0, 2).map((tag) => (
            <span key={tag} className="text-primary-strong">
              #{tag}
            </span>
          ))}
        </div>
      </button>
    </li>
  );
}

function NoteListSkeleton() {
  return (
    <div className="divide-y divide-border/70" aria-hidden="true">
      {["w-4/5", "w-3/5", "w-11/12", "w-2/3"].map((width, index) => (
        <div key={index} className="space-y-3 px-4 py-5">
          <Skeleton className={`h-4 ${width}`} />
          <Skeleton className="h-3 w-full" />
          <Skeleton className="h-3 w-2/5" />
        </div>
      ))}
    </div>
  );
}

function NotePanelSkeleton() {
  return (
    <div className="space-y-6 p-5 sm:p-7" aria-hidden="true">
      <div className="space-y-3">
        <Skeleton className="h-8 w-4/5" />
        <Skeleton className="h-4 w-2/5" />
      </div>
      <div className="space-y-3">
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-11/12" />
        <Skeleton className="h-4 w-3/5" />
      </div>
      <Skeleton className="h-44 w-full" />
    </div>
  );
}

function NotePanel({
  note,
  draft,
  availableTags,
  onCreateTag,
  editing,
  saving,
  onDraftChange,
  onEdit,
  onCancel,
  onSave,
  onDelete,
}: {
  note: Note | null;
  draft: NoteDraft;
  availableTags: Tag[];
  onCreateTag?: (payload: { name: string; color: TagColor }) => Promise<Tag>;
  editing: boolean;
  saving: boolean;
  onDraftChange: (draft: NoteDraft) => void;
  onEdit: () => void;
  onCancel: () => void;
  onSave: () => void;
  onDelete: () => void;
}) {
  const htmlChange = useCallback(
    (body: string) => onDraftChange({ ...draft, body }),
    [draft, onDraftChange],
  );

  if (!note && !editing) {
    return (
      <div className="flex min-h-[32rem] flex-col items-center justify-center px-6 py-12 text-center sm:px-10">
        <span className="flex size-12 items-center justify-center rounded-lg border border-primary/30 bg-primary/8 text-primary-strong">
          <BookOpenText aria-hidden="true" className="size-5" />
        </span>
        <h2 className="mt-5 text-xl font-semibold tracking-[-0.025em]">
          Choose a note to keep close.
        </h2>
        <p className="mt-3 max-w-md text-sm leading-6 text-muted-foreground">
          Your selected journal entry or note will open here with its date, tags, and full writing surface.
        </p>
      </div>
    );
  }

  const title = editing ? draft.title : note ? noteTitle(note) : "New journal entry";
  const editorIdentity = `${note?.id ?? "new"}-${editing ? "edit" : "read"}`;

  return (
    <div className="min-w-0">
      <header className="border-b border-border/70 px-5 py-5 sm:px-7 sm:py-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0 flex-1">
            {editing ? (
              <div className="space-y-2">
                <Label htmlFor="note-title">Title</Label>
                <Input
                  id="note-title"
                  value={draft.title}
                  onChange={(event) =>
                    onDraftChange({ ...draft, title: event.target.value })
                  }
                  placeholder="Give this entry a clear title"
                  maxLength={200}
                  className="h-11 border-0 bg-transparent px-0 text-2xl font-semibold tracking-[-0.035em] shadow-none focus-visible:ring-0 sm:text-3xl"
                />
              </div>
            ) : (
              <h2 className="max-w-3xl text-2xl font-semibold tracking-[-0.035em] sm:text-3xl">
                {title}
              </h2>
            )}
            <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[0.64rem] uppercase tracking-[0.1em] text-muted-foreground">
              <span className="inline-flex items-center gap-1.5">
                <CalendarDays aria-hidden="true" className="size-3.5" />
                {formatJournalDate(editing ? draft.journalDate || null : note?.journal_date ?? null)}
              </span>
              {note ? <span>Updated {formatUpdatedAt(note.updated_at)}</span> : <span>Unsaved</span>}
            </div>
          </div>
          {!editing && note ? (
            <div className="flex shrink-0 items-center gap-2">
              <Button type="button" variant="outline" size="sm" onClick={onEdit}>
                <Pencil data-icon="inline-start" aria-hidden="true" />
                Edit
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                aria-label="Delete note"
                onClick={onDelete}
              >
                <Trash2 aria-hidden="true" />
              </Button>
            </div>
          ) : null}
        </div>

        {editing ? (
          <div className="mt-5 grid gap-5 sm:grid-cols-[11rem_minmax(0,1fr)]">
            <div className="space-y-2">
              <Label htmlFor="note-date">Journal date</Label>
              <Input
                id="note-date"
                type="date"
                value={draft.journalDate}
                onChange={(event) =>
                  onDraftChange({ ...draft, journalDate: event.target.value })
                }
              />
            </div>
            <TagEditor
              tags={draft.tags}
              availableTags={availableTags}
              onCreateTag={onCreateTag}
              disabled={saving}
              onChange={(tags) => onDraftChange({ ...draft, tags })}
            />
          </div>
        ) : (
          <div className="mt-4 flex flex-wrap items-center gap-1.5">
            {note?.tags.length ? (
              note.tags.map((tag) => (
                <TagBadge
                  key={tag}
                  name={tag}
                  color={availableTags.find((item) => item.name === tag)?.color}
                  active={availableTags.find((item) => item.name === tag)?.active ?? false}
                />
              ))
            ) : (
              <span className="font-mono text-[0.66rem] uppercase tracking-[0.1em] text-muted-foreground">
                No tags
              </span>
            )}
          </div>
        )}
      </header>

      <div className="memory-editor px-5 py-6 sm:px-7 sm:py-8">
        <RichTextEditor
          key={editorIdentity}
          initialHtml={draft.body}
          readOnly={!editing}
          onHtmlChange={htmlChange}
        />
      </div>

      {editing ? (
        <footer className="flex flex-wrap items-center justify-between gap-3 border-t border-border/70 px-5 py-4 sm:px-7">
          <span className="font-mono text-[0.64rem] uppercase tracking-[0.1em] text-muted-foreground">
            Rich text is saved as sanitized HTML
          </span>
          <div className="flex items-center gap-2">
            <Button type="button" variant="outline" onClick={onCancel} disabled={saving}>
              Cancel
            </Button>
            <Button type="button" onClick={onSave} disabled={saving}>
              {saving ? <LoaderCircle data-icon="inline-start" className="animate-spin" aria-hidden="true" /> : null}
              {saving ? "Saving…" : note ? "Save changes" : "Save entry"}
            </Button>
          </div>
        </footer>
      ) : null}
    </div>
  );
}

function MemoryWorkspace() {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  const feedback = useFeedback();
  const searchParamsValue = searchParams.toString();
  const urlState = useMemo(
    () => parseMemoryUrlState(new URLSearchParams(searchParamsValue)),
    [searchParamsValue],
  );
  const filters = useMemo<NoteListFilters>(
    () => ({
      search: urlState.search || undefined,
      tag: urlState.tag,
    }),
    [urlState.search, urlState.tag],
  );
  const listQueryKey = [...notesQueryKey, "list", filters] as const;
  const notesQuery = useInfiniteQuery({
    queryKey: listQueryKey,
    queryFn: ({ pageParam }: { pageParam: string | undefined }) =>
      listNotes(filters, pageParam),
    initialPageParam: "",
    getNextPageParam: (lastPage: NoteListPage) => lastPage.next_cursor ?? undefined,
  });
  const noteSummaryQuery = useQuery({
    queryKey: noteSummaryQueryKey,
    queryFn: getNoteSummary,
  });
  const tagCatalogQuery = useQuery({
    queryKey: tagsQueryKey,
    queryFn: () => getTags(true),
  });
  const tagCatalog = useMemo(
    () => tagCatalogQuery.data?.items ?? [],
    [tagCatalogQuery.data?.items],
  );
  const noteFilterTags = useMemo(() => {
    const summaryTags = noteSummaryQuery.data?.tags ?? [];
    const selectedTag = urlState.tag
      ? tagCatalog.find((tag) => tag.name === urlState.tag)
      : undefined;

    if (!selectedTag || summaryTags.some((tag) => tag.name === selectedTag.name)) {
      return summaryTags;
    }

    return [
      ...summaryTags,
      {
        name: selectedTag.name,
        count: 0,
        color: selectedTag.color,
        active: selectedTag.active,
      },
    ];
  }, [noteSummaryQuery.data?.tags, tagCatalog, urlState.tag]);
  const createTagMutation = useMutation({
    mutationFn: createTag,
    onSuccess: (tag) => {
      queryClient.setQueryData(tagsQueryKey, (current: { items: Tag[] } | undefined) => ({
        items: [...(current?.items ?? []).filter((item) => item.id !== tag.id), tag],
      }));
    },
  });
  const notes = useMemo(
    () => notesQuery.data?.pages.flatMap((page) => page.items) ?? [],
    [notesQuery.data],
  );
  const selectedNoteFromList = urlState.noteId
    ? notes.find((note) => note.id === urlState.noteId) ?? null
    : null;
  const selectedNoteQuery = useQuery({
    queryKey: [...notesQueryKey, "detail", urlState.noteId ?? "none"],
    queryFn: () => getNote(urlState.noteId ?? ""),
    enabled: Boolean(urlState.noteId && urlState.noteId !== "new" && !selectedNoteFromList),
  });
  const selectedNote =
    urlState.noteId === "new"
      ? null
      : selectedNoteFromList ?? selectedNoteQuery.data ?? null;
  const [draft, setDraft] = useState<NoteDraft | null>(null);
  const [editing, setEditing] = useState(false);
  const [pendingSelection, setPendingSelection] = useState<string | null>(null);
  const [discardOpen, setDiscardOpen] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<Note | null>(null);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [sessionError, setSessionError] = useState<string>();
  const selectionKey = `${urlState.noteId ?? "none"}:${selectedNote?.id ?? "none"}`;
  const [draftSelectionKey, setDraftSelectionKey] = useState("");

  if (draftSelectionKey !== selectionKey) {
    setDraftSelectionKey(selectionKey);
    if (urlState.noteId === "new") {
      setDraft(createBlankDraft());
      setEditing(true);
    } else if (selectedNote) {
      setDraft(noteToDraft(selectedNote));
      setEditing(false);
    } else if (!urlState.noteId) {
      setDraft(null);
      setEditing(false);
    }
  }

  const updateUrl = useCallback(
    (update: (params: URLSearchParams) => void, replace = true) => {
      const params = new URLSearchParams(searchParamsValue);
      update(params);
      const nextQuery = params.toString();
      const nextUrl = nextQuery ? `${pathname}?${nextQuery}` : pathname;

      if (replace) {
        router.replace(nextUrl, { scroll: false });
      } else {
        router.push(nextUrl, { scroll: false });
      }
    },
    [pathname, router, searchParamsValue],
  );

  const baselineDraft = useMemo(() => {
    if (urlState.noteId === "new" || !selectedNote) {
      return createBlankDraft();
    }

    return noteToDraft(selectedNote);
  }, [selectedNote, urlState.noteId]);
  const isDirty = Boolean(
    editing &&
      draft &&
      JSON.stringify(draft) !== JSON.stringify(baselineDraft),
  );

  useEffect(() => {
    if (urlState.noteId || !notesQuery.isSuccess || !notes[0]) {
      return;
    }

    updateUrl((params) => params.set("note", notes[0].id));
  }, [notes, notesQuery.isSuccess, updateUrl, urlState.noteId]);

  useEffect(() => {
    if (
      !urlState.noteId ||
      urlState.noteId === "new" ||
      selectedNoteFromList ||
      !selectedNoteQuery.isError ||
      !(selectedNoteQuery.error instanceof ApiError) ||
      selectedNoteQuery.error.code !== "note_not_found"
    ) {
      return;
    }

    updateUrl(clearMemorySelection);
    feedback.error({
      title: "Note unavailable",
      description: "That note was deleted or is no longer available.",
    });
  }, [
    feedback,
    selectedNoteFromList,
    selectedNoteQuery.error,
    selectedNoteQuery.isError,
    updateUrl,
    urlState.noteId,
  ]);

  const saveMutation = useMutation({
    mutationFn: ({ noteId, payload }: { noteId?: string; payload: NoteWriteInput }) =>
      noteId ? updateNote(noteId, payload) : createNote(payload),
    onSuccess: (savedNote) => {
      queryClient.setQueryData(
        [...notesQueryKey, "detail", savedNote.id],
        savedNote,
      );
      void queryClient.invalidateQueries({ queryKey: notesQueryKey });
      void queryClient.invalidateQueries({ queryKey: noteSummaryQueryKey });
      setDraft(noteToDraft(savedNote));
      setEditing(false);
      updateUrl((params) => params.set("note", savedNote.id));
      feedback.success({
        title: savedNote.id === urlState.noteId ? "Note saved." : "Journal entry saved.",
      });
    },
    onError: (error) => {
      if (isSessionError(error)) {
        setSessionError(describeNoteError(error));
        return;
      }

      feedback.error({
        title: "Note could not be saved.",
        description: describeNoteError(error),
      });
    },
  });
  const deleteMutation = useMutation({
    mutationFn: (noteId: string) => deleteNote(noteId),
    onSuccess: () => {
      const deletedNoteId = pendingDelete?.id;
      void queryClient.invalidateQueries({ queryKey: notesQueryKey });
      void queryClient.invalidateQueries({ queryKey: noteSummaryQueryKey });
      setDeleteOpen(false);
      setPendingDelete(null);
      if (deletedNoteId && deletedNoteId === urlState.noteId) {
        updateUrl(clearMemorySelection);
      }
      feedback.success({ title: "Note moved out of your active memory." });
    },
    onError: (error) => {
      if (isSessionError(error)) {
        setSessionError(describeNoteError(error));
        return;
      }

      feedback.error({
        title: "Note could not be deleted.",
        description: describeNoteError(error),
      });
    },
  });

  function selectNote(noteId: string | null) {
    updateUrl((params) => {
      if (noteId) {
        params.set("note", noteId);
      } else {
        params.delete("note");
      }
    }, false);
  }

  function requestSelection(noteId: string | null) {
    if (isDirty) {
      setPendingSelection(noteId);
      setDiscardOpen(true);
      return;
    }

    selectNote(noteId);
  }

  function handleCancel() {
    if (isDirty) {
      setPendingSelection(urlState.noteId === "new" ? null : urlState.noteId ?? null);
      setDiscardOpen(true);
      return;
    }

    setEditing(false);
    if (urlState.noteId === "new") {
      selectNote(null);
    }
  }

  function discardAndContinue() {
    setDiscardOpen(false);
    setDraft(null);
    setEditing(false);
    selectNote(pendingSelection);
    setPendingSelection(null);
  }

  function handleSave() {
    if (!draft) {
      return;
    }

    if (!htmlToText(draft.body)) {
      feedback.error({
        title: "Write something before saving.",
        description: "A note needs a body. The title and journal date can stay empty.",
      });
      return;
    }

    if (draft.title.length > 200) {
      feedback.error({
        title: "The title is too long.",
        description: "Keep the title under 200 characters.",
      });
      return;
    }

    saveMutation.mutate({
      noteId: urlState.noteId && urlState.noteId !== "new" ? urlState.noteId : undefined,
      payload: draftPayload(draft),
    });
  }

  const listHasData = notes.length > 0;
  const listError = notesQuery.error;
  const blockingError = Boolean(listError && !listHasData);

  return (
    <div className="space-y-7">
      <header className="border-b border-border/70 pb-6">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between lg:gap-8">
          <div className="max-w-2xl">
            <p className="font-mono text-[0.68rem] uppercase tracking-[0.18em] text-primary-strong">
              Memory / notes & journal
            </p>
            <div className="mt-3 flex flex-wrap items-center gap-3">
              <h1 className="text-3xl font-semibold tracking-[-0.035em] sm:text-4xl">
                Journal & Notes
              </h1>
              <Badge
                variant="outline"
                className="rounded-md border-primary/30 bg-primary/8 font-mono text-[0.64rem] font-medium uppercase tracking-[0.1em] text-primary-strong"
              >
                Local memory
              </Badge>
            </div>
            <p className="mt-3 max-w-xl text-base leading-7 text-muted-foreground">
              Keep the thoughts, observations, and working context you want to find again.
            </p>
          </div>
          <Button type="button" size="lg" onClick={() => requestSelection("new")}>
            <Plus data-icon="inline-start" aria-hidden="true" />
            New entry
          </Button>
        </div>

        <div className="mt-6 flex flex-col gap-3 lg:flex-row lg:items-center">
          <div className="relative w-full shrink-0 lg:max-w-xl">
            <Search
              aria-hidden="true"
              className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
            />
            <Input
              aria-label="Search notes"
              value={urlState.search}
              onChange={(event) => {
                const value = event.target.value.slice(0, 200);
                updateUrl((params) => {
                  if (value.trim()) {
                    params.set("q", value);
                  } else {
                    params.delete("q");
                  }
                });
              }}
              placeholder="Search notes, tags, or journal text"
              className="h-10 pl-9"
            />
          </div>
          <div className="min-w-0 flex-1" aria-label="Note tags">
            <div className="flex min-w-0 items-center gap-2 overflow-x-auto pb-1">
              <Button
                type="button"
                size="sm"
                variant={!urlState.tag ? "secondary" : "ghost"}
                aria-pressed={!urlState.tag}
                onClick={() => updateUrl((params) => params.delete("tag"))}
                className="shrink-0"
              >
                All
              </Button>
              {noteSummaryQuery.isPending ? (
                <span className="shrink-0 px-2 text-xs text-muted-foreground" role="status">
                  Loading tags…
                </span>
              ) : noteSummaryQuery.isError ? (
                <span className="shrink-0 px-2 text-xs text-muted-foreground" role="status">
                  Tag filters unavailable
                </span>
              ) : noteFilterTags.length ? (
                noteFilterTags.map((tag) => (
                  <Button
                    key={tag.name}
                    type="button"
                    size="sm"
                    variant={urlState.tag === tag.name ? "secondary" : "ghost"}
                    aria-pressed={urlState.tag === tag.name}
                    onClick={() =>
                      updateUrl((params) => {
                        if (urlState.tag === tag.name) {
                          params.delete("tag");
                        } else {
                          params.set("tag", tag.name);
                        }
                      })
                    }
                    className="shrink-0 gap-1.5 font-mono text-xs"
                  >
                    <TagBadge name={tag.name} color={tag.color} active={tag.active} />
                    <span className="text-muted-foreground">{tag.count}</span>
                  </Button>
                ))
              ) : (
                <span className="shrink-0 px-2 text-xs text-muted-foreground">
                  No note tags yet
                </span>
              )}
            </div>
          </div>
        </div>
      </header>

      <div className="grid min-w-0 gap-5 lg:grid-cols-[minmax(18rem,24rem)_minmax(0,1fr)] lg:items-start">
        <section
          aria-labelledby="memory-list-title"
          className="min-w-0 overflow-hidden rounded-xl border border-border/80 bg-card/55"
        >
          <div className="flex items-center justify-between gap-3 border-b border-border/70 px-4 py-3">
            <div>
              <p className="font-mono text-[0.64rem] uppercase tracking-[0.16em] text-muted-foreground">
                Active timeline
              </p>
              <h2 id="memory-list-title" className="mt-1 text-sm font-medium">
                Pinned & recent
              </h2>
            </div>
            <span className="font-mono text-[0.64rem] uppercase tracking-[0.1em] text-muted-foreground">
              Modified
              <ChevronDown aria-hidden="true" className="ml-1 inline size-3" />
            </span>
          </div>

          {notesQuery.isPending ? <NoteListSkeleton /> : null}
          {notesQuery.isSuccess && !notes.length ? (
            <div className="px-5 py-12 text-center">
              <BookOpenText aria-hidden="true" className="mx-auto size-6 text-primary-strong" />
              <h3 className="mt-4 text-base font-medium">
                {urlState.search || urlState.tag ? "No notes match this view." : "Your memory is still quiet."}
              </h3>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">
                {urlState.search || urlState.tag
                  ? "Clear the search or tag filter, or try a different phrase."
                  : "Start with a journal entry and keep the useful parts of the day close."}
              </p>
              {!urlState.search && !urlState.tag ? (
                <Button type="button" size="sm" className="mt-5" onClick={() => requestSelection("new")}>
                  <Plus data-icon="inline-start" aria-hidden="true" />
                  Write first entry
                </Button>
              ) : null}
            </div>
          ) : null}
          {notesQuery.isSuccess && notes.length ? (
            <>
              <ol aria-label="Notes and journal entries">
                {notes.map((note) => (
                  <NoteListItem
                    key={note.id}
                    note={note}
                    selected={note.id === urlState.noteId}
                    onSelect={() => requestSelection(note.id)}
                  />
                ))}
              </ol>
              {notesQuery.hasNextPage ? (
                <div className="border-t border-border/70 p-3">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="w-full"
                    onClick={() => void notesQuery.fetchNextPage()}
                    disabled={notesQuery.isFetchingNextPage}
                  >
                    {notesQuery.isFetchingNextPage ? "Loading more…" : "Load more notes"}
                  </Button>
                </div>
              ) : null}
            </>
          ) : null}
          {listError && listHasData ? (
            <div className="border-t border-destructive/20 bg-destructive/5 px-4 py-3 text-sm text-destructive">
              {describeNoteError(listError)}
              <Button
                type="button"
                variant="link"
                size="sm"
                className="ml-1 h-auto px-1 text-destructive"
                onClick={() => void notesQuery.refetch()}
              >
                Retry
              </Button>
            </div>
          ) : null}
        </section>

        <section
          aria-label="Selected note"
          className="min-w-0 overflow-hidden rounded-xl border border-border/80 bg-card shadow-[0_20px_60px_-44px_color-mix(in_oklab,var(--foreground)_45%,transparent)]"
        >
          {urlState.noteId && urlState.noteId !== "new" && selectedNoteQuery.isPending && !selectedNote ? (
            <NotePanelSkeleton />
          ) : null}
          {draft ? (
            <NotePanel
              note={selectedNote}
              draft={draft}
              availableTags={tagCatalog}
              onCreateTag={(payload) => createTagMutation.mutateAsync(payload)}
              editing={editing}
              saving={saveMutation.isPending}
              onDraftChange={setDraft}
              onEdit={() => setEditing(true)}
              onCancel={handleCancel}
              onSave={handleSave}
              onDelete={() => {
                if (selectedNote) {
                  setPendingDelete(selectedNote);
                  setDeleteOpen(true);
                }
              }}
            />
          ) : !selectedNoteQuery.isPending ? (
            <NotePanel
              note={null}
              draft={createBlankDraft()}
              availableTags={tagCatalog}
              onCreateTag={(payload) => createTagMutation.mutateAsync(payload)}
              editing={false}
              saving={false}
              onDraftChange={() => undefined}
              onEdit={() => undefined}
              onCancel={() => undefined}
              onSave={() => undefined}
              onDelete={() => undefined}
            />
          ) : null}
        </section>
      </div>

      <ConfirmDialog
        open={discardOpen}
        title="Discard this draft?"
        description="Your unsaved changes will be removed from this page. Saved notes will stay safe in your local workspace."
        confirmLabel="Discard changes"
        pending={false}
        onOpenChange={setDiscardOpen}
        onConfirm={discardAndContinue}
      />
      <ConfirmDialog
        open={deleteOpen}
        title="Delete this note?"
        description={`“${pendingDelete ? noteTitle(pendingDelete) : "This note"}” will be removed from active note views. Cortex keeps it as a soft-deleted record for recovery later.`}
        confirmLabel="Delete note"
        cancelLabel="Keep note"
        pending={deleteMutation.isPending}
        destructive
        onOpenChange={setDeleteOpen}
        onConfirm={() => {
          if (pendingDelete) {
            deleteMutation.mutate(pendingDelete.id);
          }
        }}
      />
      <BlockingErrorDialog
        open={Boolean(sessionError) || blockingError}
        title={sessionError ? "Your session has ended." : "Notes could not load."}
        description={sessionError ?? describeNoteError(listError)}
        action={
          sessionError
            ? {
                label: "Sign in again",
                onClick: () => router.replace("/login"),
              }
            : {
                label: "Try again",
                onClick: () => void notesQuery.refetch(),
                pending: notesQuery.isFetching,
                pendingLabel: "Loading…",
              }
        }
      />
    </div>
  );
}

export function MemoryPage({ email }: { email: string }) {
  return (
    <WorkspaceShell email={email}>
      <MemoryWorkspace />
    </WorkspaceShell>
  );
}

export function MemoryPageSkeleton() {
  return (
    <div className="mx-auto w-full max-w-[1240px] space-y-7 px-5 pb-12 pt-7 sm:px-8 sm:pt-10 lg:px-10 lg:pt-12" aria-hidden="true">
      <div className="space-y-4 border-b border-border/70 pb-6">
        <Skeleton className="h-3 w-40" />
        <Skeleton className="h-10 w-72" />
        <Skeleton className="h-5 w-full max-w-xl" />
        <Skeleton className="h-10 w-full max-w-xl" />
      </div>
      <div className="grid gap-5 lg:grid-cols-[minmax(18rem,24rem)_minmax(0,1fr)]">
        <div className="overflow-hidden rounded-xl border border-border/80 bg-card/55">
          <NoteListSkeleton />
        </div>
        <div className="rounded-xl border border-border/80 bg-card">
          <NotePanelSkeleton />
        </div>
      </div>
    </div>
  );
}

export function MemoryRoute() {
  const currentUser = useCurrentUser();

  return (
    <WorkspaceRouteGuard>
      {currentUser.data ? (
        <Suspense fallback={<MemoryPageSkeleton />}>
          <MemoryPage email={currentUser.data.email} />
        </Suspense>
      ) : null}
    </WorkspaceRouteGuard>
  );
}

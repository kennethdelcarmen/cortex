"use client";

import { useInfiniteQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArchiveRestore,
  FileText,
  FolderArchive,
  LoaderCircle,
  NotebookPen,
  RotateCcw,
  Tag,
  Trash2,
  type LucideIcon,
} from "lucide-react";
import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { BlockingErrorDialog, useFeedback } from "@/components/feedback";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api/client";
import { noteSummaryQueryKey, notesQueryKey } from "@/features/memory/api";
import { filesQueryKey } from "@/features/memory/files-api";
import { useCurrentUser } from "@/features/auth/hooks";
import { taskQueryKey, taskSeriesQueryKey, taskSummaryQueryKey } from "@/features/tasks/api";
import { tagsQueryKey } from "@/features/tags/api";
import {
  listRecoveryItems,
  permanentlyDeleteRecoveryItems,
  recoveryQueryKey,
  restoreRecoveryItems,
  type RecoveryItem,
  type RecoveryItemReference,
  type RecoveryItemType,
  type RecoveryMutationResponse,
} from "../api";
import { ConfirmDialog } from "@/features/memory/components/confirm-dialog";
import {
  WorkspaceRouteGuard,
  WorkspaceShell,
} from "@/features/workspace/components/workspace-shell";

type RecoveryFilter = "all" | RecoveryItemType;

const dateFormatter = new Intl.DateTimeFormat(undefined, {
  month: "short",
  day: "numeric",
  year: "numeric",
  hour: "numeric",
  minute: "2-digit",
});

const typeOptions: Array<{ value: RecoveryFilter; label: string }> = [
  { value: "all", label: "All records" },
  { value: "task", label: "Tasks" },
  { value: "note", label: "Notes" },
  { value: "file", label: "Files" },
  { value: "tag", label: "Tags" },
];

const typeDetails: Record<RecoveryItemType, { label: string; icon: LucideIcon }> = {
  task: { label: "Task", icon: ArchiveRestore },
  note: { label: "Note", icon: NotebookPen },
  file: { label: "File", icon: FileText },
  tag: { label: "Tag", icon: Tag },
};

function itemKey(item: RecoveryItemReference) {
  return `${item.type}:${item.id}`;
}

function formatDate(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Recently" : dateFormatter.format(date);
}

function displayLabel(item: RecoveryItem) {
  return item.type === "tag" ? `#${item.label}` : item.label;
}

function isSessionError(error: unknown) {
  return error instanceof ApiError && error.code === "unauthenticated";
}

function describeRecoveryError(error: unknown) {
  if (!(error instanceof ApiError)) {
    return "The Trash request could not be completed. Try again.";
  }

  switch (error.code) {
    case "network_error":
      return "Cortex could not be reached. Check that the backend is running and try again.";
    case "invalid_recovery_cursor":
      return "This Trash list expired. Refresh the list and try again.";
    case "invalid_recovery_query":
      return "That Trash list request was invalid. Refresh the list and try again.";
    case "recovery_item_not_found":
      return "One of these records is no longer available. Refresh the list and try again.";
    case "file_storage_unavailable":
      return "File storage is temporarily unavailable. Try again shortly.";
    case "unauthenticated":
      return "Your session has ended. Sign in again to continue.";
    default:
      return "The Trash request could not be completed. Try again.";
  }
}

function TrashListSkeleton() {
  return (
    <div className="divide-y divide-border/70" aria-hidden="true">
      {["w-2/5", "w-3/5", "w-1/2", "w-4/5"].map((width, index) => (
        <div key={index} className="flex items-start gap-4 px-4 py-5 sm:px-5">
          <Skeleton className="mt-1 size-4 rounded-[4px]" />
          <Skeleton className="size-10 rounded-lg" />
          <div className="min-w-0 flex-1 space-y-2">
            <Skeleton className={`h-4 ${width}`} />
            <Skeleton className="h-3 w-3/5" />
          </div>
          <Skeleton className="hidden h-8 w-24 sm:block" />
        </div>
      ))}
    </div>
  );
}

function RecoveryRow({
  item,
  selected,
  pending,
  onToggle,
  onRestore,
  onDelete,
}: {
  item: RecoveryItem;
  selected: boolean;
  pending: boolean;
  onToggle: (checked: boolean) => void;
  onRestore: () => void;
  onDelete: () => void;
}) {
  const details = typeDetails[item.type];
  const Icon = details.icon;

  return (
    <li
      className={`flex flex-col gap-4 border-l-2 px-4 py-4 transition-colors sm:flex-row sm:items-center sm:px-5 ${
        selected
          ? "border-primary bg-primary/8"
          : "border-transparent hover:bg-muted/35"
      }`}
    >
      <Checkbox
        checked={selected}
        onCheckedChange={(checked) => onToggle(checked === true)}
        aria-label={`Select ${details.label.toLowerCase()} ${displayLabel(item)}`}
        disabled={pending}
        className="mt-0.5 self-start sm:mt-0"
      />
      <div className="flex min-w-0 flex-1 items-start gap-4">
        <span className="flex size-10 shrink-0 items-center justify-center rounded-lg border border-primary/25 bg-primary/10 text-primary-strong">
          <Icon aria-hidden="true" className="size-5" />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="min-w-0 truncate text-sm font-medium" title={displayLabel(item)}>
              {displayLabel(item)}
            </p>
            <Badge
              variant="outline"
              className="rounded-md border-border/80 font-mono text-[0.6rem] uppercase tracking-[0.1em] text-muted-foreground"
            >
              {details.label}
            </Badge>
          </div>
          <p className="mt-1 flex flex-wrap gap-x-2 gap-y-1 font-mono text-[0.64rem] uppercase tracking-[0.07em] text-muted-foreground">
            <span>Removed {formatDate(item.removed_at)}</span>
            <span aria-hidden="true">·</span>
            <span>Created {formatDate(item.created_at)}</span>
          </p>
        </div>
      </div>
      <div className="flex shrink-0 items-center gap-2 self-end sm:self-auto">
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={onRestore}
          disabled={pending}
        >
          {pending ? <LoaderCircle data-icon="inline-start" className="animate-spin" /> : <RotateCcw data-icon="inline-start" />}
          Restore
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="text-destructive hover:bg-destructive/10 hover:text-destructive"
          onClick={onDelete}
          disabled={pending}
        >
          <Trash2 data-icon="inline-start" />
          Delete permanently
        </Button>
      </div>
    </li>
  );
}

function TrashWorkspace({ email }: { email: string }) {
  const queryClient = useQueryClient();
  const feedback = useFeedback();
  const router = useRouter();
  const [filter, setFilter] = useState<RecoveryFilter>("all");
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(() => new Set());
  const [deleteTarget, setDeleteTarget] = useState<RecoveryItemReference[] | null>(null);
  const [sessionError, setSessionError] = useState<string>();

  const query = useInfiniteQuery({
    queryKey: recoveryQueryKey,
    queryFn: ({ pageParam }: { pageParam: string | undefined }) => listRecoveryItems(pageParam),
    initialPageParam: "",
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });

  const items = useMemo(
    () => query.data?.pages.flatMap((page) => page.items) ?? [],
    [query.data],
  );
  const visibleItems = useMemo(
    () => (filter === "all" ? items : items.filter((item) => item.type === filter)),
    [filter, items],
  );
  const selectedItems = useMemo(
    () => items.filter((item) => selectedKeys.has(itemKey(item))),
    [items, selectedKeys],
  );
  const visibleKeys = useMemo(
    () => visibleItems.map((item) => itemKey(item)),
    [visibleItems],
  );
  const selectedVisibleCount = visibleKeys.filter((key) => selectedKeys.has(key)).length;
  const allVisibleSelected = visibleKeys.length > 0 && selectedVisibleCount === visibleKeys.length;
  const someVisibleSelected = selectedVisibleCount > 0 && !allVisibleSelected;
  const mutationItems = deleteTarget ?? selectedItems;

  function updateSelection(item: RecoveryItemReference, checked: boolean) {
    setSelectedKeys((current) => {
      const next = new Set(current);
      if (checked) next.add(itemKey(item));
      else next.delete(itemKey(item));
      return next;
    });
  }

  function toggleVisibleSelection(checked: boolean) {
    setSelectedKeys((current) => {
      const next = new Set(current);
      for (const key of visibleKeys) {
        if (checked) next.add(key);
        else next.delete(key);
      }
      return next;
    });
  }

  async function invalidateAffectedQueries() {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: recoveryQueryKey }),
      queryClient.invalidateQueries({ queryKey: taskQueryKey }),
      queryClient.invalidateQueries({ queryKey: taskSummaryQueryKey }),
      queryClient.invalidateQueries({ queryKey: taskSeriesQueryKey }),
      queryClient.invalidateQueries({ queryKey: notesQueryKey }),
      queryClient.invalidateQueries({ queryKey: noteSummaryQueryKey }),
      queryClient.invalidateQueries({ queryKey: filesQueryKey }),
      queryClient.invalidateQueries({ queryKey: tagsQueryKey }),
    ]);
  }

  function handleMutationResult(response: RecoveryMutationResponse, action: "restore" | "delete") {
    const successfulKeys = new Set(
      response.results
        .filter((result) => result.status !== "failed")
        .map((result) => itemKey(result.item)),
    );
    const failedResults = response.results.filter((result) => result.status === "failed");

    setSelectedKeys((current) => {
      const next = new Set(current);
      for (const key of successfulKeys) next.delete(key);
      return next;
    });

    if (failedResults.length) {
      const successCount = response.results.length - failedResults.length;
      feedback.error({
        title: `${successCount} ${successCount === 1 ? "record" : "records"} ${action === "restore" ? "restored" : "deleted"}.`,
        description: `${failedResults.length} ${failedResults.length === 1 ? "record remains" : "records remain"} selected. ${failedResults[0]?.error?.message ?? "Try the action again."}`,
      });
    } else {
      feedback.success({
        title: `${response.results.length} ${response.results.length === 1 ? "record" : "records"} ${action === "restore" ? "restored" : "deleted permanently"}.`,
      });
    }

    setDeleteTarget(null);
    void invalidateAffectedQueries();
  }

  const restoreMutation = useMutation({
    mutationFn: restoreRecoveryItems,
    onSuccess: (response) => handleMutationResult(response, "restore"),
    onError: (error) => {
      if (isSessionError(error)) {
        setSessionError(describeRecoveryError(error));
        return;
      }
      feedback.error({ title: "Records could not be restored.", description: describeRecoveryError(error) });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: permanentlyDeleteRecoveryItems,
    onSuccess: (response) => handleMutationResult(response, "delete"),
    onError: (error) => {
      if (isSessionError(error)) {
        setSessionError(describeRecoveryError(error));
        return;
      }
      feedback.error({ title: "Records could not be deleted permanently.", description: describeRecoveryError(error) });
    },
  });

  const isMutating = restoreMutation.isPending || deleteMutation.isPending;
  const listSessionError = isSessionError(query.error) ? describeRecoveryError(query.error) : undefined;
  const activeSessionError = sessionError ?? listSessionError;
  const listBlockingError = Boolean(query.error && !query.data);
  const empty = query.isSuccess && visibleItems.length === 0;
  const nextPageError = query.isFetchNextPageError ? query.error : null;
  const nextPageFetch = query.fetchNextPage;

  function requestPermanentDelete(itemsToDelete: RecoveryItemReference[]) {
    if (!itemsToDelete.length) return;
    setDeleteTarget(itemsToDelete);
  }

  return (
    <WorkspaceShell email={email}>
      <div className="max-w-5xl">
        <header className="border-b border-border/70 pb-6">
          <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between lg:gap-8">
            <div className="max-w-2xl">
              <p className="font-mono text-[0.68rem] uppercase tracking-[0.18em] text-primary-strong">
                Workspace / trash
              </p>
              <div className="mt-3 flex flex-wrap items-center gap-3">
                <h1 className="text-3xl font-semibold tracking-[-0.035em] sm:text-4xl">Trash</h1>
                <Badge variant="outline" className="rounded-md border-destructive/25 bg-destructive/8 font-mono text-[0.64rem] font-medium uppercase tracking-[0.1em] text-destructive">
                  Recovery space
                </Badge>
              </div>
              <p className="mt-3 max-w-xl text-base leading-7 text-muted-foreground">
                Deleted and archived records stay here until you restore them or remove them permanently.
              </p>
            </div>
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
              <label className="flex items-center gap-3 text-sm text-muted-foreground">
                <span className="sr-only">Filter Trash by type</span>
                <Select
                  value={filter}
                  onValueChange={(value) => {
                    setFilter(value as RecoveryFilter);
                    setSelectedKeys(new Set());
                  }}
                >
                  <SelectTrigger aria-label="Filter Trash by type" className="h-10 w-full bg-background sm:w-44">
                    <SelectValue>{typeOptions.find((option) => option.value === filter)?.label}</SelectValue>
                  </SelectTrigger>
                  <SelectContent>
                    {typeOptions.map((option) => (
                      <SelectItem key={option.value} value={option.value}>
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </label>
            </div>
          </div>
        </header>

        <section aria-labelledby="trash-list-title" className="mt-7 min-w-0 overflow-hidden rounded-xl border border-border/80 bg-card/55">
          <div className="flex flex-col gap-4 border-b border-border/70 px-4 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-5">
            <div>
              <p className="font-mono text-[0.64rem] uppercase tracking-[0.16em] text-muted-foreground">
                {query.isPending ? "Checking locally" : `${visibleItems.length} loaded`}
              </p>
              <h2 id="trash-list-title" className="mt-1 text-sm font-medium">Records awaiting a decision</h2>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <label className="flex items-center gap-2 text-sm text-muted-foreground">
                <Checkbox
                  checked={allVisibleSelected}
                  indeterminate={someVisibleSelected}
                  onCheckedChange={(checked) => toggleVisibleSelection(checked === true)}
                  disabled={!visibleItems.length || isMutating}
                  aria-label="Select all loaded Trash records"
                />
                Select all loaded
              </label>
              {selectedItems.length ? (
                <Badge variant="outline" className="border-primary/30 bg-primary/8 text-primary-strong">
                  {selectedItems.length} selected
                </Badge>
              ) : null}
            </div>
          </div>

          {selectedItems.length ? (
            <div className="flex flex-col gap-3 border-b border-primary/20 bg-primary/8 px-4 py-3 sm:flex-row sm:items-center sm:justify-between sm:px-5">
              <div className="flex items-center gap-2 text-sm text-primary-strong">
                <FolderArchive aria-hidden="true" className="size-4" />
                <span>{selectedItems.length} loaded {selectedItems.length === 1 ? "record" : "records"} selected</span>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() => restoreMutation.mutate(selectedItems.map(({ type, id }) => ({ type, id })))}
                  disabled={isMutating}
                >
                  {restoreMutation.isPending ? <LoaderCircle data-icon="inline-start" className="animate-spin" /> : <RotateCcw data-icon="inline-start" />}
                  Restore selected
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="destructive"
                  onClick={() => requestPermanentDelete(selectedItems.map(({ type, id }) => ({ type, id })))}
                  disabled={isMutating}
                >
                  <Trash2 data-icon="inline-start" />
                  Delete permanently
                </Button>
              </div>
            </div>
          ) : null}

          {query.isPending ? <TrashListSkeleton /> : null}
          {empty ? (
            <div className="px-5 py-16 text-center">
              <Trash2 aria-hidden="true" className="mx-auto size-8 text-primary-strong" />
              <h3 className="mt-4 text-base font-medium">{filter === "all" ? "Trash is empty." : `No ${typeOptions.find((option) => option.value === filter)?.label.toLowerCase()} here.`}</h3>
              <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-muted-foreground">
                {filter === "all" ? "Deleted notes, tasks, files, and archived tags will appear here when they need a second look." : "Try another type or load more records to check older entries."}
              </p>
            </div>
          ) : null}
          {visibleItems.length ? (
            <ul className="divide-y divide-border/70">
              {visibleItems.map((item) => (
                <RecoveryRow
                  key={itemKey(item)}
                  item={item}
                  selected={selectedKeys.has(itemKey(item))}
                  pending={isMutating}
                  onToggle={(checked) => updateSelection(item, checked)}
                  onRestore={() => restoreMutation.mutate([{ type: item.type, id: item.id }])}
                  onDelete={() => requestPermanentDelete([{ type: item.type, id: item.id }])}
                />
              ))}
            </ul>
          ) : null}
          {nextPageError && !isSessionError(nextPageError) ? (
            <div className="flex flex-col items-center justify-center gap-3 border-t border-border/70 px-4 py-5 text-center sm:flex-row sm:text-left sm:px-5">
              <p className="text-sm text-destructive" role="alert">
                More Trash records could not load. {describeRecoveryError(nextPageError)}
              </p>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => void nextPageFetch()}
                disabled={query.isFetchingNextPage}
              >
                {query.isFetchingNextPage ? "Loading…" : "Try again"}
              </Button>
            </div>
          ) : query.hasNextPage ? (
            <div className="border-t border-border/70 px-4 py-4 text-center sm:px-5">
              <Button
                type="button"
                variant="outline"
                size="lg"
                onClick={() => void query.fetchNextPage()}
                disabled={query.isFetchingNextPage}
              >
                {query.isFetchingNextPage ? "Loading more…" : "Load more records"}
              </Button>
            </div>
          ) : null}
        </section>
      </div>

      <ConfirmDialog
        open={Boolean(deleteTarget)}
        title={mutationItems.length === 1 ? "Delete this record permanently?" : `Delete ${mutationItems.length} records permanently?`}
        description="This removes the selected records and any associated stored data permanently. This cannot be undone."
        confirmLabel="Delete permanently"
        cancelLabel="Keep records"
        pending={deleteMutation.isPending}
        destructive
        onOpenChange={(open) => {
          if (!open && !deleteMutation.isPending) setDeleteTarget(null);
        }}
        onConfirm={() => {
          if (mutationItems.length) deleteMutation.mutate(mutationItems);
        }}
      />
      <BlockingErrorDialog
        open={Boolean(activeSessionError) || listBlockingError}
        title={activeSessionError ? "Your session has ended." : "Trash could not load."}
        description={activeSessionError ?? (query.error ? describeRecoveryError(query.error) : "The Trash list could not be loaded.")}
        action={
          activeSessionError
            ? { label: "Sign in again", onClick: () => router.replace("/login") }
            : {
                label: "Try again",
                onClick: () => void query.refetch(),
                pending: query.isFetching,
                pendingLabel: "Loading…",
              }
        }
      />
    </WorkspaceShell>
  );
}

export function TrashPage() {
  const currentUser = useCurrentUser();

  return (
    <WorkspaceRouteGuard>
      {currentUser.data ? <TrashWorkspace email={currentUser.data.email} /> : null}
    </WorkspaceRouteGuard>
  );
}

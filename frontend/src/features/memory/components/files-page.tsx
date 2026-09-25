"use client";

import { useInfiniteQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Download,
  FileText,
  LoaderCircle,
  Trash2,
  Upload,
} from "lucide-react";
import { useCallback, useId, useMemo, useRef, useState, type DragEvent } from "react";
import { useRouter } from "next/navigation";
import { BlockingErrorDialog, useFeedback } from "@/components/feedback";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api/client";
import { useCurrentUser } from "@/features/auth/hooks";
import {
  deleteFile,
  downloadFile,
  filesQueryKey,
  listFiles,
  uploadFile,
  type StoredFile,
  type StoredFileListPage,
} from "../files-api";
import { ConfirmDialog } from "./confirm-dialog";
import { FilePreviewDrawer } from "./file-preview";
import {
  WorkspaceRouteGuard,
  WorkspaceShell,
} from "@/features/workspace/components/workspace-shell";

const dateFormatter = new Intl.DateTimeFormat(undefined, {
  month: "short",
  day: "numeric",
  year: "numeric",
  hour: "numeric",
  minute: "2-digit",
});

function formatBytes(value: number) {
  if (value < 1024) {
    return `${value} B`;
  }

  const units = ["KB", "MB", "GB"];
  let size = value;
  let unitIndex = -1;
  do {
    size /= 1024;
    unitIndex += 1;
  } while (size >= 1024 && unitIndex < units.length - 1);

  return `${size.toFixed(size >= 10 ? 0 : 1)} ${units[unitIndex]}`;
}

function formatDate(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Recently" : dateFormatter.format(date);
}

function isSessionError(error: unknown) {
  return error instanceof ApiError && error.code === "unauthenticated";
}

function describeFileError(error: unknown) {
  if (!(error instanceof ApiError)) {
    return "The file request could not be completed. Try again.";
  }

  switch (error.code) {
    case "network_error":
      return "Cortex could not be reached. Check that the backend is running and try again.";
    case "file_too_large":
      return "That file is larger than the server allows.";
    case "invalid_file_name":
      return "The filename must contain safe, non-empty content and be no longer than 255 characters.";
    case "invalid_file_cursor":
      return "This file list expired. Refresh the list and try again.";
    case "invalid_file_query":
      return "That file list request was invalid. Refresh the list and try again.";
    case "file_not_found":
      return "That file is no longer available. Refresh the list to continue.";
    case "file_content_missing":
      return "The file metadata exists, but its contents are unavailable.";
    case "file_storage_unavailable":
      return "File storage is temporarily unavailable. Try again shortly.";
    case "unauthenticated":
      return "Your session has ended. Sign in again to continue.";
    default:
      return "The file request could not be completed. Try again.";
  }
}

function contextStatusLabel(status: StoredFile["context_status"]) {
  switch (status) {
    case "ready":
      return "Context ready";
    case "processing":
      return "Preparing context";
    case "unsupported":
      return "Stored · not supported yet";
    case "failed":
      return "Processing failed";
    case "pending":
      return "Waiting for context worker";
    default:
      return "Waiting for context worker";
  }
}

type UploadFailure = { file: File; message: string; sessionError: boolean };

function describeUploadFailures(failures: UploadFailure[]) {
  const names = failures.map(({ file }) => file.name);
  const visibleNames = names.slice(0, 3).join(", ");
  const remainingCount = names.length - 3;
  const nameSummary = remainingCount > 0 ? `${visibleNames}, and ${remainingCount} more` : visibleNames;
  return `${nameSummary}. ${failures[0]?.message ?? "Try again."}`;
}

function FileListSkeleton() {
  return (
    <div className="divide-y divide-border/70" aria-hidden="true">
      {["w-2/5", "w-3/5", "w-1/2", "w-4/5"].map((width, index) => (
        <div key={index} className="flex items-center gap-4 px-4 py-5 sm:px-5">
          <Skeleton className="size-10 rounded-lg" />
          <div className="min-w-0 flex-1 space-y-2">
            <Skeleton className={`h-4 ${width}`} />
            <Skeleton className="h-3 w-1/2" />
          </div>
          <Skeleton className="hidden h-8 w-20 sm:block" />
        </div>
      ))}
    </div>
  );
}

function UploadDialog({
  open,
  uploading,
  onFiles,
  onOpenChange,
}: {
  open: boolean;
  uploading: boolean;
  onFiles: (files: File[]) => void;
  onOpenChange: (open: boolean) => void;
}) {
  const inputId = useId();
  const [dragActive, setDragActive] = useState(false);

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragActive(false);
    if (!uploading) {
      onFiles(Array.from(event.dataTransfer.files));
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="w-[min(34rem,calc(100vw-2rem))] rounded-xl border-border bg-card p-6 text-card-foreground shadow-none sm:max-w-none sm:p-7">
        <DialogHeader>
          <DialogTitle className="text-xl font-semibold tracking-[-0.025em]">Add files to memory</DialogTitle>
          <DialogDescription className="mt-3 text-sm leading-6 text-muted-foreground">
            Drop one or more source files below. Cortex stores the originals and prepares context in the background.
          </DialogDescription>
        </DialogHeader>
        <div
          aria-label="File dropzone"
          onDragEnter={(event) => {
            event.preventDefault();
            if (!uploading) setDragActive(true);
          }}
          onDragOver={(event) => {
            event.preventDefault();
            event.dataTransfer.dropEffect = "copy";
          }}
          onDragLeave={(event) => {
            if (event.currentTarget === event.target) setDragActive(false);
          }}
          onDrop={handleDrop}
          className={`flex min-h-56 flex-col items-center justify-center rounded-xl border border-dashed px-5 py-8 text-center transition-colors ${dragActive ? "border-primary-strong bg-primary/10" : "border-border bg-background/60"}`}
        >
          <span className="flex size-12 items-center justify-center rounded-xl border border-primary/30 bg-primary/10 text-primary-strong">
            <Upload aria-hidden="true" className="size-6" />
          </span>
          <p className="mt-4 text-base font-medium">{dragActive ? "Release to upload" : "Drop files here"}</p>
          <p className="mt-1 text-sm text-muted-foreground">Multiple files are supported.</p>
          <label
            htmlFor={inputId}
            className="mt-5 inline-flex h-10 cursor-pointer items-center justify-center rounded-lg bg-primary px-4 text-sm font-medium text-primary-foreground outline-none transition-colors hover:bg-primary/80 focus-within:ring-3 focus-within:ring-ring/50"
          >
            Browse files
            <input
              id={inputId}
              type="file"
              multiple
              className="sr-only"
              disabled={uploading}
              onChange={(event) => {
                onFiles(Array.from(event.target.files ?? []));
                event.target.value = "";
              }}
            />
          </label>
          <p className="mt-4 font-mono text-[0.64rem] uppercase tracking-[0.1em] text-muted-foreground">
            Originals stay in your local Cortex storage
          </p>
        </div>
        <DialogFooter className="mt-1 flex-row justify-end gap-2 border-0 bg-transparent p-0">
          <DialogClose type="button" render={<Button variant="outline" size="lg" />}>Cancel</DialogClose>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function FileRow({
  file,
  downloading,
  onOpen,
  onDownload,
  onDelete,
}: {
  file: StoredFile;
  downloading: boolean;
  onOpen: () => void;
  onDownload: () => void;
  onDelete: () => void;
}) {
  return (
    <li className="flex flex-col gap-4 px-4 py-4 sm:flex-row sm:items-center sm:px-5">
      <button
        type="button"
        className="flex min-w-0 flex-1 items-center gap-4 rounded-lg text-left outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
        onClick={onOpen}
      >
        <span className="flex size-10 shrink-0 items-center justify-center rounded-lg border border-primary/25 bg-primary/8 text-primary-strong">
          <FileText aria-hidden="true" className="size-5" />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-medium" title={file.name}>{file.name}</span>
          <span className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 font-mono text-[0.64rem] uppercase tracking-[0.08em] text-muted-foreground">
            <span>{formatBytes(file.size_bytes)}</span>
            <span aria-hidden="true">·</span>
            <span>{contextStatusLabel(file.context_status)}</span>
            <span aria-hidden="true">·</span>
            <span>Added {formatDate(file.created_at)}</span>
          </span>
        </span>
      </button>
      <div className="flex shrink-0 items-center gap-1 self-end sm:self-auto">
        <Button type="button" variant="ghost" size="icon-sm" aria-label={`Download ${file.name}`} onClick={onDownload} disabled={downloading}>
          {downloading ? <LoaderCircle aria-hidden="true" className="animate-spin" /> : <Download aria-hidden="true" />}
        </Button>
        <Button
          type="button"
          variant="destructive"
          size="icon-sm"
          className="border-destructive/25 bg-destructive/10 hover:bg-destructive/20"
          aria-label={`Remove ${file.name}`}
          onClick={onDelete}
        >
          <Trash2 aria-hidden="true" />
        </Button>
      </div>
    </li>
  );
}

function FilesWorkspace() {
  const queryClient = useQueryClient();
  const feedback = useFeedback();
  const router = useRouter();
  const [uploadOpen, setUploadOpen] = useState(false);
  const [uploading, setUploading] = useState(false);
  const uploadingRef = useRef(false);
  const [deleteTarget, setDeleteTarget] = useState<StoredFile | null>(null);
  const [drawerFile, setDrawerFile] = useState<StoredFile | null>(null);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  const [sessionError, setSessionError] = useState<string>();

  const filesQuery = useInfiniteQuery({
    queryKey: filesQueryKey,
    queryFn: ({ pageParam }: { pageParam: string | undefined }) => listFiles(pageParam),
    initialPageParam: "",
    getNextPageParam: (lastPage: StoredFileListPage) => lastPage.next_cursor ?? undefined,
    refetchInterval: 5000,
  });
  const files = useMemo(() => filesQuery.data?.pages.flatMap((page) => page.items) ?? [], [filesQuery.data]);

  const { mutateAsync: uploadFileAsync } = useMutation({ mutationFn: uploadFile });
  const deleteMutation = useMutation({
    mutationFn: deleteFile,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: filesQueryKey });
      setDeleteTarget(null);
      setDrawerFile(null);
      feedback.success({ title: "File removed from active memory.", description: "Cortex keeps the source for recovery later." });
    },
    onError: (error) => {
      if (isSessionError(error)) {
        setSessionError(describeFileError(error));
        return;
      }
      feedback.error({ title: "File could not be removed.", description: describeFileError(error) });
    },
  });

  const handleSessionError = useCallback(() => {
    setSessionError("Your session has ended. Sign in again to continue.");
  }, []);

  async function handleFiles(selectedFiles: File[]) {
    if (!selectedFiles.length || uploadingRef.current) return;
    setUploadOpen(false);
    uploadingRef.current = true;
    setUploading(true);
    let uploadedCount = 0;
    const failures: UploadFailure[] = [];

    for (const file of selectedFiles) {
      try {
        await uploadFileAsync(file);
        uploadedCount += 1;
      } catch (error) {
        failures.push({ file, message: describeFileError(error), sessionError: isSessionError(error) });
        if (isSessionError(error)) setSessionError(describeFileError(error));
      }
    }

    uploadingRef.current = false;
    setUploading(false);
    if (uploadedCount) {
      void queryClient.invalidateQueries({ queryKey: filesQueryKey });
      feedback.success({ title: `${uploadedCount} ${uploadedCount === 1 ? "file" : "files"} added to memory.` });
    }
    const reportableFailures = failures.filter((failure) => !failure.sessionError);
    if (reportableFailures.length) {
      feedback.error({
        title: `${reportableFailures.length} ${reportableFailures.length === 1 ? "file" : "files"} could not be uploaded.`,
        description: describeUploadFailures(reportableFailures),
        action: { label: "Retry failed", onClick: () => void handleFiles(reportableFailures.map(({ file }) => file)) },
      });
    }
  }

  async function handleDownload(file: StoredFile) {
    setDownloadingId(file.id);
    try {
      const blob = await downloadFile(file.id);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = file.name;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 0);
    } catch (error) {
      if (isSessionError(error)) setSessionError(describeFileError(error));
      else feedback.error({ title: "File could not be downloaded.", description: describeFileError(error) });
    } finally {
      setDownloadingId(null);
    }
  }

  const listError = filesQuery.error;
  const listSessionError = isSessionError(listError) ? describeFileError(listError) : undefined;
  const activeSessionError = sessionError ?? listSessionError;
  const blockingError = Boolean(listError && !files.length);

  return (
    <div className="space-y-7">
      <header className="border-b border-border/70 pb-6">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between lg:gap-8">
          <div className="max-w-2xl">
            <p className="font-mono text-[0.68rem] uppercase tracking-[0.18em] text-primary-strong">Memory / files</p>
            <div className="mt-3 flex flex-wrap items-center gap-3">
              <h1 className="text-3xl font-semibold tracking-[-0.035em] sm:text-4xl">File library</h1>
              <Badge variant="outline" className="rounded-md border-primary/30 bg-primary/8 font-mono text-[0.64rem] font-medium uppercase tracking-[0.1em] text-primary-strong">Local context</Badge>
            </div>
            <p className="mt-3 max-w-xl text-base leading-7 text-muted-foreground">Keep source files close to memory so Cortex can prepare context when you ask about your data.</p>
          </div>
          <Button type="button" className="w-full shrink-0 sm:w-auto" onClick={() => setUploadOpen(true)} disabled={uploading} aria-busy={uploading}>
            {uploading ? <LoaderCircle data-icon="inline-start" className="animate-spin" /> : <Upload data-icon="inline-start" />}
            {uploading ? "Uploading…" : "Add files"}
          </Button>
        </div>
      </header>

      <UploadDialog open={uploadOpen} uploading={uploading} onFiles={handleFiles} onOpenChange={setUploadOpen} />

      <section aria-labelledby="files-list-title" className="min-w-0 overflow-hidden rounded-xl border border-border/80 bg-card/55">
        <div className="flex items-center justify-between gap-3 border-b border-border/70 px-4 py-3 sm:px-5">
          <div>
            <p className="font-mono text-[0.64rem] uppercase tracking-[0.16em] text-muted-foreground">Stored locally</p>
            <h2 id="files-list-title" className="mt-1 text-sm font-medium">Recent sources</h2>
          </div>
          <span className="font-mono text-[0.64rem] uppercase tracking-[0.1em] text-muted-foreground">Context status</span>
        </div>
        {filesQuery.isPending ? <FileListSkeleton /> : null}
        {filesQuery.isSuccess && !files.length ? (
          <div className="px-5 py-14 text-center">
            <FileText aria-hidden="true" className="mx-auto size-7 text-primary-strong" />
            <h3 className="mt-4 text-base font-medium">Your source library is empty.</h3>
            <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-muted-foreground">Add a source file or reference to make it available to Cortex’s context pipeline.</p>
          </div>
        ) : null}
        {files.length ? (
          <>
            <ul aria-label="Stored files" className="divide-y divide-border/70">
              {files.map((file) => (
                <FileRow
                  key={file.id}
                  file={file}
                  downloading={downloadingId === file.id}
                  onOpen={() => setDrawerFile(file)}
                  onDownload={() => void handleDownload(file)}
                  onDelete={() => setDeleteTarget(file)}
                />
              ))}
            </ul>
            {filesQuery.hasNextPage ? (
              <div className="border-t border-border/70 p-3">
                <Button type="button" variant="outline" size="sm" className="w-full" onClick={() => void filesQuery.fetchNextPage()} disabled={filesQuery.isFetchingNextPage}>
                  {filesQuery.isFetchingNextPage ? <LoaderCircle data-icon="inline-start" className="animate-spin" /> : null}
                  {filesQuery.isFetchingNextPage ? "Loading more…" : "Load more files"}
                </Button>
              </div>
            ) : null}
          </>
        ) : null}
        {listError && files.length ? (
          <div className="border-t border-destructive/20 bg-destructive/5 px-4 py-3 text-sm text-destructive">
            {describeFileError(listError)}
            <Button type="button" variant="link" size="sm" className="ml-1 h-auto px-1 text-destructive" onClick={() => void filesQuery.refetch()}>Retry</Button>
          </div>
        ) : null}
      </section>

      <FilePreviewDrawer
        file={drawerFile}
        open={Boolean(drawerFile)}
        downloading={drawerFile ? downloadingId === drawerFile.id : false}
        deleting={deleteMutation.isPending}
        onOpenChange={(open) => {
          if (!open) setDrawerFile(null);
        }}
        onDownload={() => {
          if (drawerFile) void handleDownload(drawerFile);
        }}
        onDelete={() => {
          if (drawerFile) setDeleteTarget(drawerFile);
        }}
        onSessionError={handleSessionError}
      />

      <ConfirmDialog
        open={Boolean(deleteTarget)}
        title="Remove this source?"
        description={`“${deleteTarget?.name ?? "This source"}” will be removed from active memory. Cortex keeps it for recovery later.`}
        confirmLabel="Remove source"
        cancelLabel="Keep source"
        pending={deleteMutation.isPending}
        destructive
        onOpenChange={(open) => {
          if (!open && !deleteMutation.isPending) setDeleteTarget(null);
        }}
        onConfirm={() => {
          if (deleteTarget) deleteMutation.mutate(deleteTarget.id);
        }}
      />
      <BlockingErrorDialog
        open={Boolean(activeSessionError) || blockingError}
        title={activeSessionError ? "Your session has ended." : "Files could not load."}
        description={activeSessionError ?? describeFileError(listError)}
        action={activeSessionError ? { label: "Sign in again", onClick: () => router.push("/login") } : { label: "Try again", onClick: () => void filesQuery.refetch(), pending: filesQuery.isFetching, pendingLabel: "Loading…" }}
      />
    </div>
  );
}

export function MemoryFilesPage({ email }: { email: string }) {
  return (
    <WorkspaceShell email={email}>
      <FilesWorkspace />
    </WorkspaceShell>
  );
}

export function MemoryFilesPageSkeleton() {
  return (
    <div className="mx-auto w-full max-w-[1240px] space-y-7 px-5 pb-12 pt-7 sm:px-8 sm:pt-10 lg:px-10 lg:pt-12" aria-hidden="true">
      <div className="space-y-4 border-b border-border/70 pb-6">
        <Skeleton className="h-3 w-36" />
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-5 w-full max-w-xl" />
      </div>
      <div className="overflow-hidden rounded-xl border border-border/80 bg-card/55"><FileListSkeleton /></div>
    </div>
  );
}

export function MemoryFilesRoute() {
  const currentUser = useCurrentUser();
  return (
    <WorkspaceRouteGuard>
      {currentUser.data ? <MemoryFilesPage email={currentUser.data.email} /> : null}
    </WorkspaceRouteGuard>
  );
}

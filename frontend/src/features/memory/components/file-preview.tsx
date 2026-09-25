"use client";

import {
  AlertCircle,
  Download,
  FileWarning,
  LoaderCircle,
  RefreshCw,
} from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import {
  Drawer,
  DrawerClose,
  DrawerContent,
  DrawerDescription,
  DrawerFooter,
  DrawerHeader,
  DrawerTitle,
} from "@/components/ui/drawer";
import { ApiError } from "@/lib/api/client";
import { TagPicker } from "@/components/tag-picker";
import type { Tag, TagColor } from "@/features/tags/api";
import {
  downloadPreview,
  getFileContext,
  retryFileProcessing,
  type FileContext,
  type StoredFile,
} from "../files-api";

const OFFICE_EXTENSIONS = new Set(["doc", "docx", "xls", "xlsx", "ppt", "pptx", "odt", "ods", "odp"]);

function isOfficeFile(name: string) {
  const extension = name.split(".").pop()?.toLowerCase();
  return extension ? OFFICE_EXTENSIONS.has(extension) : false;
}

function describePreviewError(error: unknown) {
  if (error instanceof ApiError && error.code === "network_error") {
    return "Cortex could not be reached. Check that the backend is running and try again.";
  }
  if (error instanceof ApiError && error.code === "file_preview_unavailable") {
    return "A PDF preview is not available for this Office file. Fix LibreOffice and retry processing, or download the source file.";
  }
  return "This preview could not be prepared. You can still download the original file.";
}

function describeProcessingError(code: string | null) {
  switch (code) {
    case "file_converter_unavailable":
    case "office_converter_unavailable":
      return "LibreOffice is not available to prepare this document preview. Install it or configure CORTEX_FILE_CONVERTER_COMMAND, then retry.";
    case "file_ocr_unavailable":
    case "ocr_unavailable":
      return "Tesseract is not available to extract text from this image. Install it or configure CORTEX_FILE_OCR_COMMAND, then retry.";
    case "office_conversion_failed":
      return "LibreOffice could not convert this document. The source is still available to download; retry after checking the document or converter logs.";
    case "image_ocr_failed":
      return "Text could not be extracted from this image. The image itself is still available below.";
    case "office_text_extraction_failed":
      return "Text could not be extracted from this Office document. You can still download the original file.";
    default:
      return "The source was retained, but its context could not be prepared.";
  }
}

function StatusMessage({
  icon,
  title,
  description,
}: {
  icon: ReactNode;
  title: string;
  description: string;
}) {
  return (
    <div className="flex min-h-64 flex-col items-center justify-center rounded-xl border border-dashed border-border bg-background/60 px-6 py-10 text-center">
      <span className="text-primary-strong">{icon}</span>
      <p className="mt-4 text-sm font-medium">{title}</p>
      <p className="mt-2 max-w-sm text-sm leading-6 text-muted-foreground">{description}</p>
    </div>
  );
}

function PreviewContent({ context, previewUrl }: { context: FileContext; previewUrl: string | null }) {
  if (context.preview_kind === "image") {
    if (!previewUrl) {
      return (
        <StatusMessage
          icon={<LoaderCircle aria-hidden="true" className="size-8 animate-spin" />}
          title="Loading image"
          description="Fetching the stored image while context extraction continues in the backend."
        />
      );
    }

    return (
      <div className="space-y-3">
      <div className="flex min-h-64 items-center justify-center overflow-hidden rounded-xl border border-border bg-background p-3">
          {/* Blob URLs cannot use next/image's configured remote loader. */}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={previewUrl} alt={context.name} className="max-h-[min(62svh,42rem)] max-w-full object-contain" />
        </div>
        {context.status === "failed" ? (
          <p className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-900 dark:text-amber-100">
            {describeProcessingError(context.error)}
          </p>
        ) : context.status === "pending" || context.status === "processing" ? (
          <p className="rounded-lg border border-border bg-background/60 px-4 py-3 text-sm text-muted-foreground">
            Image text extraction is still running in the background.
          </p>
        ) : null}
      </div>
    );
  }

  if (context.status === "pending") {
    return (
      <StatusMessage
        icon={<LoaderCircle aria-hidden="true" className="size-8 animate-spin" />}
        title="Waiting for context worker"
        description="The original source is safely stored. The backend worker will claim it automatically when processing is enabled and running."
      />
    );
  }

  if (context.status === "processing") {
    return (
      <StatusMessage
        icon={<LoaderCircle aria-hidden="true" className="size-8 animate-spin" />}
        title="Preparing context"
        description="Cortex is converting and extracting this source for preview and future memory search."
      />
    );
  }

  if (context.status === "unsupported") {
    return (
      <StatusMessage
        icon={<FileWarning aria-hidden="true" className="size-8" />}
        title="Preview is not available yet"
        description="This source is stored safely, but Cortex does not have an extractor for it yet."
      />
    );
  }

  if (context.status === "failed") {
    return (
      <StatusMessage
        icon={<AlertCircle aria-hidden="true" className="size-8" />}
        title="Processing failed"
        description={describeProcessingError(context.error)}
      />
    );
  }

  if (context.preview_kind === "text") {
    return (
      <div className="overflow-hidden rounded-xl border border-border bg-background">
        <pre className="max-h-[min(62svh,42rem)] overflow-auto whitespace-pre-wrap break-words p-4 font-mono text-xs leading-6 text-foreground">
          {context.text || "No extractable text was found."}
        </pre>
        {context.truncated ? (
          <p className="border-t border-border px-4 py-3 text-xs text-muted-foreground">
            This preview is bounded. The complete extracted text remains available to the context pipeline.
          </p>
        ) : null}
      </div>
    );
  }

  if (context.status === "ready" && context.preview_kind === null) {
    return (
      <StatusMessage
        icon={<FileWarning aria-hidden="true" className="size-8" />}
        title="PDF preview unavailable"
        description="Cortex retained this Office file's extracted context, but could not prepare a PDF preview. Fix LibreOffice and retry processing, or download the source file."
      />
    );
  }

  if (!previewUrl) {
    return (
      <StatusMessage
        icon={<LoaderCircle aria-hidden="true" className="size-8 animate-spin" />}
        title="Loading preview"
        description="Fetching the derived preview artifact."
      />
    );
  }

  return (
    <iframe
      title={`Preview of ${context.name}`}
      src={previewUrl}
      className="min-h-[min(78svh,56rem)] w-full rounded-xl border border-border bg-white"
    />
  );
}

export function FilePreviewDrawer({
  file,
  open,
  downloading,
  deleting,
  onOpenChange,
  onDownload,
  onDelete,
  onSessionError,
  availableTags,
  onCreateTag,
  onTagsChange,
}: {
  file: StoredFile | null;
  open: boolean;
  downloading: boolean;
  deleting: boolean;
  onOpenChange: (open: boolean) => void;
  onDownload: () => void;
  onDelete: () => void;
  onSessionError: () => void;
  availableTags: Tag[];
  onCreateTag: (payload: { name: string; color: TagColor }) => Promise<Tag>;
  onTagsChange: (tags: string[]) => Promise<void>;
}) {
  const [context, setContext] = useState<FileContext | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fileTags, setFileTags] = useState<string[]>(() => file?.tags ?? []);
  const [tagSaving, setTagSaving] = useState(false);
  const [tagSaveError, setTagSaveError] = useState<string | null>(null);
  const [refreshToken, setRefreshToken] = useState(0);
  const fileId = file?.id;

  useEffect(() => {
    let cancelled = false;
    let objectUrl: string | null = null;
    let retryTimer: number | undefined;

    if (!fileId || !open) {
      return () => undefined;
    }

    queueMicrotask(() => {
      if (cancelled) {
        return;
      }
      setContext(null);
      setPreviewUrl(null);
      setError(null);
      setLoading(true);
    });

    void (async () => {
      try {
        const nextContext = await getFileContext(fileId);
        if (cancelled) {
          return;
        }
        setContext(nextContext);

        if (nextContext.preview_kind === "image" || nextContext.preview_kind === "pdf") {
          const blob = await downloadPreview(fileId);
          if (cancelled) {
            return;
          }
          objectUrl = URL.createObjectURL(blob);
          setPreviewUrl(objectUrl);
        } else if (nextContext.status === "pending" || nextContext.status === "processing") {
          retryTimer = window.setTimeout(() => setRefreshToken((value) => value + 1), 3000);
        }
      } catch (nextError) {
        if (nextError instanceof ApiError && nextError.code === "unauthenticated") {
          onSessionError();
        } else if (!cancelled) {
          setError(describePreviewError(nextError));
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    })();

    return () => {
      cancelled = true;
      if (retryTimer !== undefined) {
        window.clearTimeout(retryTimer);
      }
      if (objectUrl) {
        URL.revokeObjectURL(objectUrl);
      }
    };
  }, [fileId, onSessionError, open, refreshToken]);

  async function retry() {
    if (!file) {
      return;
    }

    setLoading(true);
    setError(null);
    try {
      await retryFileProcessing(file.id);
      const nextContext = await getFileContext(file.id);
      setContext(nextContext);
      setRefreshToken((value) => value + 1);
    } catch (nextError) {
      if (nextError instanceof ApiError && nextError.code === "unauthenticated") {
        onSessionError();
      } else {
        setError(describePreviewError(nextError));
      }
    } finally {
      setLoading(false);
    }
  }

  const canRetry =
    context?.status === "failed" ||
    (context?.status === "ready" && isOfficeFile(context.name) && context.preview_kind !== "pdf");

  async function saveTags(nextTags: string[]) {
    const previousTags = fileTags;
    setFileTags(nextTags);
    setTagSaving(true);
    setTagSaveError(null);
    try {
      await onTagsChange(nextTags);
    } catch (nextError) {
      setFileTags(previousTags);
      setTagSaveError(nextError instanceof Error ? nextError.message : "Tags could not be saved.");
    } finally {
      setTagSaving(false);
    }
  }

  return (
    <Drawer open={open} onOpenChange={onOpenChange} swipeDirection="right">
      <DrawerContent
        className="file-preview-drawer max-h-[96svh] bg-card text-card-foreground"
      >
        <div className="mx-auto flex w-full max-w-6xl flex-col overflow-hidden">
          <DrawerHeader className="border-b border-border/70 px-5 py-5 text-left sm:px-7">
            <DrawerTitle className="truncate text-xl tracking-[-0.025em]">{file?.name ?? "File preview"}</DrawerTitle>
            <DrawerDescription>
              {file ? "PDF preview and extracted context." : ""}
            </DrawerDescription>
            <div className="mt-3 min-w-0">
              <TagPicker
                id="file-tags"
                presentation="popover"
                tags={availableTags}
                value={fileTags}
                onChange={(nextTags) => void saveTags(nextTags)}
                onCreateTag={onCreateTag}
                disabled={tagSaving || !file}
              />
              {tagSaveError ? <p className="mt-2 text-xs text-destructive" role="alert">{tagSaveError}</p> : null}
            </div>
          </DrawerHeader>
          <div className="overflow-auto px-5 py-5 sm:px-7">
            {loading && !context ? (
              <StatusMessage
                icon={<LoaderCircle aria-hidden="true" className="size-8 animate-spin" />}
                title="Loading context"
                description="Reading the processing status for this source."
              />
            ) : error ? (
              <StatusMessage
                icon={<AlertCircle aria-hidden="true" className="size-8" />}
                title="Preview unavailable"
                description={error}
              />
            ) : context ? (
              <PreviewContent context={context} previewUrl={previewUrl} />
            ) : null}
          </div>
          <DrawerFooter className="flex-row flex-wrap justify-end gap-2 border-t border-border/70 bg-card px-5 py-4 sm:px-7">
            {canRetry ? (
              <Button type="button" variant="outline" size="sm" onClick={() => void retry()} disabled={loading}>
                {loading ? <LoaderCircle data-icon="inline-start" className="animate-spin" /> : <RefreshCw data-icon="inline-start" />}
                Retry processing
              </Button>
            ) : null}
            <Button type="button" variant="outline" size="sm" onClick={onDownload} disabled={downloading || !file}>
              {downloading ? <LoaderCircle data-icon="inline-start" className="animate-spin" /> : <Download data-icon="inline-start" />}
              Download source
            </Button>
            <Button
              type="button"
              variant="destructive"
              size="sm"
              className="border-destructive/30 bg-destructive/15 hover:bg-destructive/25"
              onClick={onDelete}
              disabled={deleting || !file}
            >
              Remove
            </Button>
            <DrawerClose render={<Button type="button" variant="ghost" size="sm" />}>Close</DrawerClose>
          </DrawerFooter>
        </div>
      </DrawerContent>
    </Drawer>
  );
}

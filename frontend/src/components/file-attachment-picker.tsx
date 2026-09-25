"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Download, Eye, FilePlus2, LoaderCircle, Paperclip, Search, X } from "lucide-react";
import { useEffect, useRef, useState, type ChangeEvent } from "react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError } from "@/lib/api/client";
import { FilePreviewDrawer } from "@/features/memory/components/file-preview";
import {
  downloadFile,
  filesQueryKey,
  listFiles,
  uploadFile,
  type StoredFile,
} from "@/features/memory/files-api";

const MAX_ATTACHMENTS = 20;

function describeError(error: unknown) {
  if (error instanceof ApiError && error.code === "network_error") {
    return "Cortex could not be reached. Check the backend and try again.";
  }
  if (error instanceof ApiError && error.code === "file_too_large") {
    return "Files must be 25 MiB or smaller.";
  }
  return "This file could not be uploaded.";
}

function formatSize(size: number) {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${Math.round(size / 1024)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

async function downloadAttachment(file: StoredFile) {
  const blob = await downloadFile(file.id);
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = file.name;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

export function FileAttachmentPicker({
  id,
  value,
  onChange,
  disabled = false,
  label = "Attachments",
}: {
  id: string;
  value: StoredFile[];
  onChange: (files: StoredFile[]) => void;
  disabled?: boolean;
  label?: string;
}) {
  const queryClient = useQueryClient();
  const inputRef = useRef<HTMLInputElement>(null);
  const valueRef = useRef(value);
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [uploadStates, setUploadStates] = useState<Record<string, "uploading" | "success" | "error">>({});
  const [uploadErrors, setUploadErrors] = useState<Record<string, string>>({});
  const [previewFile, setPreviewFile] = useState<StoredFile | null>(null);

  useEffect(() => {
    valueRef.current = value;
  }, [value]);

  const filesQuery = useQuery({
    queryKey: [...filesQueryKey, "picker", search],
    queryFn: () => listFiles({ search: search.trim() || undefined, tags: [], contextStatuses: [] }),
    enabled: open,
  });

  function openPicker() {
    setSelectedIds(value.map((file) => file.id));
    setOpen(true);
  }

  function toggleFile(file: StoredFile) {
    setSelectedIds((current) => {
      if (current.includes(file.id)) return current.filter((idValue) => idValue !== file.id);
      if (current.length >= MAX_ATTACHMENTS) return current;
      return [...current, file.id];
    });
  }

  async function handleUpload(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files ?? []);
    event.target.value = "";
    const remaining = MAX_ATTACHMENTS - selectedIds.length;
    if (!files.length || remaining <= 0) return;

    for (const file of files.slice(0, remaining)) {
      setUploadStates((current) => ({ ...current, [file.name]: "uploading" }));
      setUploadErrors((current) => ({ ...current, [file.name]: "" }));
      try {
        const uploaded = await uploadFile(file);
        setUploadStates((current) => ({ ...current, [file.name]: "success" }));
        setSelectedIds((current) => current.includes(uploaded.id) ? current : [...current, uploaded.id]);
        const nextValue = [...valueRef.current.filter((item) => item.id !== uploaded.id), uploaded];
        valueRef.current = nextValue;
        onChange(nextValue);
        await queryClient.invalidateQueries({ queryKey: filesQueryKey });
      } catch (error) {
        setUploadStates((current) => ({ ...current, [file.name]: "error" }));
        setUploadErrors((current) => ({ ...current, [file.name]: describeError(error) }));
      }
    }
  }

  function saveSelection() {
    const byId = new Map(value.map((file) => [file.id, file]));
    for (const file of filesQuery.data?.items ?? []) byId.set(file.id, file);
    onChange(selectedIds.flatMap((fileId) => {
      const file = byId.get(fileId);
      return file ? [file] : [];
    }));
    setOpen(false);
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-3">
        <Label htmlFor={id}>{label}</Label>
        <span className="font-mono text-[0.64rem] uppercase tracking-[0.1em] text-muted-foreground">
          {value.length}/{MAX_ATTACHMENTS}
        </span>
      </div>
      <div className="space-y-2">
        {value.length ? value.map((file) => (
          <div key={file.id} className="flex items-center gap-2 rounded-md border border-border/70 bg-background/50 px-3 py-2">
            <Paperclip aria-hidden="true" className="size-3.5 shrink-0 text-primary-strong" />
            <span className="min-w-0 flex-1 truncate text-sm">{file.name}</span>
            <span className="shrink-0 text-xs text-muted-foreground">{formatSize(file.size_bytes)}</span>
            <Button type="button" variant="ghost" size="icon-xs" aria-label={`Preview ${file.name}`} onClick={() => setPreviewFile(file)}>
              <Eye aria-hidden="true" />
            </Button>
            <Button type="button" variant="ghost" size="icon-xs" aria-label={`Download ${file.name}`} onClick={() => void downloadAttachment(file)}>
              <Download aria-hidden="true" />
            </Button>
            <Button type="button" variant="ghost" size="icon-xs" aria-label={`Remove ${file.name}`} disabled={disabled} onClick={() => onChange(value.filter((item) => item.id !== file.id))}>
              <X aria-hidden="true" />
            </Button>
          </div>
        )) : (
          <p className="rounded-md border border-dashed border-border/80 px-3 py-3 text-sm text-muted-foreground">No files attached yet.</p>
        )}
      </div>
      <Button id={id} type="button" variant="outline" size="sm" onClick={openPicker} disabled={disabled || value.length >= MAX_ATTACHMENTS}>
        <Paperclip data-icon="inline-start" aria-hidden="true" />
        {value.length ? "Manage files" : "Add files"}
      </Button>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="flex max-h-[min(88svh,44rem)] w-[min(42rem,calc(100vw-2rem))] flex-col overflow-hidden rounded-xl border-border bg-card p-0 text-card-foreground shadow-none sm:max-w-none">
          <DialogHeader className="border-b border-border/70 px-6 py-5">
            <DialogTitle>Attach files</DialogTitle>
            <DialogDescription>Select existing files or upload new sources. Uploads remain in Files even if you cancel this record.</DialogDescription>
          </DialogHeader>
          <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-6 py-5">
            <div className="flex flex-col gap-2 sm:flex-row">
              <div className="relative min-w-0 flex-1">
                <Search aria-hidden="true" className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                <Input aria-label="Search files" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search existing files" className="pl-9" />
              </div>
              <input ref={inputRef} className="sr-only" type="file" multiple onChange={(event) => void handleUpload(event)} />
              <Button type="button" variant="outline" onClick={() => inputRef.current?.click()} disabled={selectedIds.length >= MAX_ATTACHMENTS}>
                <FilePlus2 data-icon="inline-start" aria-hidden="true" /> Upload files
              </Button>
            </div>
            {Object.entries(uploadStates).filter(([, state]) => state !== "success").map(([name, state]) => (
              <p key={name} className={state === "error" ? "text-sm text-destructive" : "text-sm text-muted-foreground"} role={state === "error" ? "alert" : "status"}>
                {state === "uploading" ? <LoaderCircle className="mr-1 inline size-3.5 animate-spin" aria-hidden="true" /> : null}
                {name}: {state === "error" ? uploadErrors[name] : "Uploading…"}
              </p>
            ))}
            {filesQuery.isPending ? <p className="py-8 text-center text-sm text-muted-foreground" role="status">Loading files…</p> : null}
            {filesQuery.isError ? <p className="py-8 text-center text-sm text-destructive" role="alert">Files could not be loaded. Try again.</p> : null}
            {filesQuery.isSuccess && !filesQuery.data.items.length ? <p className="py-8 text-center text-sm text-muted-foreground">No matching files. Upload a new source to attach it.</p> : null}
            <div className="space-y-2">
              {filesQuery.data?.items.map((file) => {
                const checked = selectedIds.includes(file.id);
                return (
                  <label key={file.id} className="flex cursor-pointer items-center gap-3 rounded-md border border-border/70 px-3 py-3 hover:bg-muted/35">
                    <Checkbox checked={checked} onCheckedChange={() => toggleFile(file)} disabled={!checked && selectedIds.length >= MAX_ATTACHMENTS} />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-medium">{file.name}</span>
                      <span className="text-xs text-muted-foreground">{formatSize(file.size_bytes)}</span>
                    </span>
                    {checked ? <Check aria-hidden="true" className="size-4 text-primary-strong" /> : null}
                    <Button type="button" variant="ghost" size="icon-xs" aria-label={`Preview ${file.name}`} onClick={(event) => { event.preventDefault(); setPreviewFile(file); }}>
                      <Eye aria-hidden="true" />
                    </Button>
                  </label>
                );
              })}
            </div>
          </div>
          <DialogFooter className="mx-0! mb-0! flex-col-reverse items-stretch gap-2 rounded-none border-t border-border/70 bg-card px-6 py-4 sm:flex-row sm:items-center sm:justify-end sm:px-7">
            <DialogClose type="button" render={<Button variant="outline" disabled={Object.values(uploadStates).includes("uploading")} />}>Cancel</DialogClose>
            <Button type="button" onClick={saveSelection} disabled={Object.values(uploadStates).includes("uploading")}>Save selection ({selectedIds.length})</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <FilePreviewDrawer
        key={previewFile?.id ?? "no-preview"}
        file={previewFile}
        open={Boolean(previewFile)}
        downloading={false}
        deleting={false}
        onOpenChange={(isOpen) => { if (!isOpen) setPreviewFile(null); }}
        onDownload={() => { if (previewFile) void downloadAttachment(previewFile); }}
        onDelete={() => undefined}
        onSessionError={() => undefined}
        availableTags={[]}
        onCreateTag={async () => { throw new Error("Tags are managed in Files."); }}
        onTagsChange={async () => undefined}
        showTags={false}
        allowDelete={false}
      />
    </div>
  );
}

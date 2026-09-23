"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Pencil, RotateCcw, Tag as TagIcon, Trash2 } from "lucide-react";
import { useState } from "react";
import { useFeedback } from "@/components/feedback";
import { TagBadge, tagColorSwatchClass } from "@/components/tag-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
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
import { noteSummaryQueryKey, notesQueryKey } from "@/features/memory/api";
import { taskQueryKey, taskSeriesQueryKey, taskSummaryQueryKey } from "@/features/tasks/api";
import {
  TAG_COLORS,
  archiveTag,
  createTag,
  getTags,
  permanentlyDeleteTag,
  restoreTag,
  tagsQueryKey,
  updateTag,
  type Tag,
  type TagColor,
} from "@/features/tags/api";

function describeError(error: unknown) {
  if (error instanceof ApiError && error.code === "tag_name_conflict") {
    return "That tag name is already in your catalog.";
  }
  if (error instanceof ApiError && error.code === "tag_inactive") {
    return "That tag is archived. Restore it before using it.";
  }
  if (error instanceof ApiError && error.code === "tag_must_be_archived") {
    return "Only archived tags can be deleted permanently.";
  }
  return error instanceof Error ? error.message : "The tag catalog could not be updated.";
}

function PalettePicker({
  value,
  onChange,
  id,
}: {
  value: TagColor;
  onChange: (value: TagColor) => void;
  id: string;
}) {
  return (
    <div id={id} className="flex flex-wrap gap-1.5" aria-label="Tag color">
      {TAG_COLORS.map((option) => (
        <button
          key={option.value}
          type="button"
          aria-label={option.label}
          aria-pressed={value === option.value}
          title={option.label}
          onClick={() => onChange(option.value)}
          className={`size-7 rounded-full border-2 outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 ${
            tagColorSwatchClass(option.value)
          } ${
            value === option.value ? "ring-2 ring-ring ring-offset-2 ring-offset-card" : ""
          }`}
        >
          {value === option.value ? <Check aria-hidden="true" className="mx-auto size-3.5 text-white" /> : null}
        </button>
      ))}
    </div>
  );
}

function TagRow({ tag }: { tag: Tag }) {
  const queryClient = useQueryClient();
  const feedback = useFeedback();
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(tag.name);
  const [color, setColor] = useState<TagColor>(tag.color);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleteError, setDeleteError] = useState<string>();

  const update = useMutation({
    mutationFn: () => updateTag(tag.id, { name, color }),
    onSuccess: (nextTag) => {
      queryClient.setQueryData<{ items: Tag[] }>(tagsQueryKey, (current) => ({
        items: (current?.items ?? []).map((item) => item.id === nextTag.id ? nextTag : item),
      }));
      setEditing(false);
      feedback.success({ title: `Tag #${nextTag.name} updated.` });
    },
    onError: (error) => feedback.error({ title: "Tag could not be updated.", description: describeError(error) }),
  });

  const archive = useMutation({
    mutationFn: () => archiveTag(tag.id),
    onSuccess: (nextTag) => {
      queryClient.setQueryData<{ items: Tag[] }>(tagsQueryKey, (current) => ({
        items: (current?.items ?? []).map((item) => item.id === nextTag.id ? nextTag : item),
      }));
      feedback.success({ title: `Tag #${nextTag.name} archived.` });
    },
    onError: (error) => feedback.error({ title: "Tag could not be archived.", description: describeError(error) }),
  });

  const restore = useMutation({
    mutationFn: () => restoreTag(tag.id),
    onSuccess: (nextTag) => {
      queryClient.setQueryData<{ items: Tag[] }>(tagsQueryKey, (current) => ({
        items: (current?.items ?? []).map((item) => item.id === nextTag.id ? nextTag : item),
      }));
      feedback.success({ title: `Tag #${nextTag.name} restored.` });
    },
    onError: (error) => feedback.error({ title: "Tag could not be restored.", description: describeError(error) }),
  });

  const permanentDelete = useMutation({
    mutationFn: () => permanentlyDeleteTag(tag.id),
    onSuccess: async () => {
      setDeleteOpen(false);
      setDeleteError(undefined);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: tagsQueryKey }),
        queryClient.invalidateQueries({ queryKey: notesQueryKey }),
        queryClient.invalidateQueries({ queryKey: noteSummaryQueryKey }),
        queryClient.invalidateQueries({ queryKey: taskQueryKey }),
        queryClient.invalidateQueries({ queryKey: taskSummaryQueryKey }),
        queryClient.invalidateQueries({ queryKey: taskSeriesQueryKey }),
      ]);
      feedback.success({ title: `Tag #${tag.name} deleted permanently.` });
    },
    onError: (error) => {
      const description = describeError(error);
      setDeleteError(description);
      feedback.error({ title: "Tag could not be deleted permanently.", description });
    },
  });

  const pending = update.isPending || archive.isPending || restore.isPending || permanentDelete.isPending;

  return (
    <>
    <li className="border-t border-border/70 py-4 first:border-t-0">
      {editing ? (
        <div className="space-y-3">
          <Label htmlFor={`tag-name-${tag.id}`}>Tag name</Label>
          <Input id={`tag-name-${tag.id}`} value={name} onChange={(event) => setName(event.target.value)} disabled={pending} />
          <Label htmlFor={`tag-color-${tag.id}`}>Palette color</Label>
          <PalettePicker id={`tag-color-${tag.id}`} value={color} onChange={setColor} />
          <div className="flex gap-2">
            <Button type="button" size="sm" onClick={() => update.mutate()} disabled={pending || !name.trim()}>
              {update.isPending ? "Saving…" : "Save changes"}
            </Button>
            <Button type="button" size="sm" variant="outline" onClick={() => { setName(tag.name); setColor(tag.color); setEditing(false); }} disabled={pending}>
              Cancel
            </Button>
          </div>
        </div>
      ) : (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <TagBadge name={tag.name} color={tag.color} active={tag.active} />
          <div className="flex flex-wrap gap-2">
            <Button type="button" size="sm" variant="outline" onClick={() => setEditing(true)} disabled={pending}>
              <Pencil aria-hidden="true" />
              Edit
            </Button>
            {tag.active ? (
              <Button type="button" size="sm" variant="outline" onClick={() => archive.mutate()} disabled={pending}>
                <Trash2 aria-hidden="true" />
                Archive
              </Button>
            ) : (
              <>
                <Button type="button" size="sm" variant="outline" onClick={() => restore.mutate()} disabled={pending}>
                  <RotateCcw aria-hidden="true" />
                  Restore
                </Button>
                <Button type="button" size="sm" variant="destructive" onClick={() => { setDeleteError(undefined); setDeleteOpen(true); }} disabled={pending}>
                  <Trash2 aria-hidden="true" />
                  Delete permanently
                </Button>
              </>
            )}
          </div>
        </div>
      )}
    </li>
    <Dialog
      open={deleteOpen}
      onOpenChange={(open) => {
        setDeleteOpen(open);
        if (open) {
          setDeleteError(undefined);
        }
      }}
    >
      <DialogContent showCloseButton={!permanentDelete.isPending}>
        <DialogHeader>
          <DialogTitle>Delete #{tag.name} permanently?</DialogTitle>
          <DialogDescription>
            This permanently removes the tag, all of its assignments on notes, tasks, and recurring task series, and its historical memberships. This cannot be undone.
          </DialogDescription>
        </DialogHeader>
        {deleteError ? <p className="text-sm text-destructive" role="alert">{deleteError}</p> : null}
        <DialogFooter>
          <DialogClose render={<Button type="button" variant="outline" disabled={permanentDelete.isPending} />}>Cancel</DialogClose>
          <Button type="button" variant="destructive" onClick={() => permanentDelete.mutate()} disabled={permanentDelete.isPending}>
            {permanentDelete.isPending ? "Deleting…" : "Delete permanently"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
    </>
  );
}

export function TagCatalogSettings() {
  const queryClient = useQueryClient();
  const feedback = useFeedback();
  const [name, setName] = useState("");
  const [color, setColor] = useState<TagColor>("slate");
  const query = useQuery({ queryKey: tagsQueryKey, queryFn: () => getTags(true) });
  const create = useMutation({
    mutationFn: () => createTag({ name, color }),
    onSuccess: (tag) => {
      queryClient.setQueryData<{ items: Tag[] }>(tagsQueryKey, (current) => ({
        items: [...(current?.items ?? []), tag],
      }));
      setName("");
      setColor("slate");
      feedback.success({ title: `Tag #${tag.name} created.` });
    },
    onError: (error) => feedback.error({ title: "Tag could not be created.", description: describeError(error) }),
  });

  if (query.isPending) {
    return <p className="text-sm text-muted-foreground" role="status">Loading tag catalog…</p>;
  }

  if (query.isError) {
    return (
      <Card className="border-destructive/30 bg-destructive/5">
        <CardContent className="p-6">
          <p className="text-sm text-destructive">{describeError(query.error)}</p>
          <Button className="mt-4" variant="outline" onClick={() => void query.refetch()}>Try again</Button>
        </CardContent>
      </Card>
    );
  }

  const tags = query.data.items;
  const activeTags = tags.filter((tag) => tag.active);
  const archivedTags = tags.filter((tag) => !tag.active);

  return (
    <Card className="border-border/80">
      <CardHeader>
        <div className="flex items-start gap-3">
          <span className="flex size-9 shrink-0 items-center justify-center rounded-md border border-border bg-background text-primary-strong">
            <TagIcon aria-hidden="true" className="size-4" />
          </span>
          <div>
            <CardTitle>Shared tag catalog</CardTitle>
            <CardDescription className="mt-1.5 leading-6">
              Notes, tasks, and recurring task series use the same fixed catalog. Archived tags keep their historical associations.
            </CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-6">
        <form className="space-y-3 rounded-lg border border-border/70 bg-muted/20 p-4" onSubmit={(event) => { event.preventDefault(); if (name.trim()) create.mutate(); }}>
          <Label htmlFor="new-tag-name">Create a tag</Label>
          <Input id="new-tag-name" value={name} onChange={(event) => setName(event.target.value)} placeholder="e.g. planning" disabled={create.isPending} />
          <Label htmlFor="new-tag-color">Palette color</Label>
          <PalettePicker id="new-tag-color" value={color} onChange={setColor} />
          <Button type="submit" disabled={create.isPending || !name.trim()}>{create.isPending ? "Creating…" : "Create tag"}</Button>
        </form>

        <div>
          <h3 className="text-sm font-medium">Active tags</h3>
          {activeTags.length ? <ul className="mt-2"><>{activeTags.map((tag) => <TagRow key={tag.id} tag={tag} />)}</></ul> : <p className="mt-2 text-sm text-muted-foreground">No active tags yet.</p>}
        </div>

        <div>
          <h3 className="text-sm font-medium">Archived tags</h3>
          {archivedTags.length ? <ul className="mt-2"><>{archivedTags.map((tag) => <TagRow key={tag.id} tag={tag} />)}</></ul> : <p className="mt-2 text-sm text-muted-foreground">Archived tags will appear here.</p>}
        </div>
      </CardContent>
    </Card>
  );
}

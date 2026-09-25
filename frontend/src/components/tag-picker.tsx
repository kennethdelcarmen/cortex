"use client";

import { Check, ChevronDown, Plus, X } from "lucide-react";
import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Popover,
  PopoverContent,
  PopoverDescription,
  PopoverHeader,
  PopoverTitle,
  PopoverTrigger,
} from "@/components/ui/popover";
import { TagBadge, tagColorClass, tagColorSwatchClass } from "@/components/tag-badge";
import { TAG_COLORS, type Tag, type TagColor } from "@/features/tags/api";
import { cn } from "@/lib/utils";

type TagPickerPresentation = "inline" | "popover";

type TagPickerProps = {
  id: string;
  tags: Tag[];
  value: string[];
  onChange: (value: string[]) => void;
  onCreateTag?: (payload: { name: string; color: TagColor }) => Promise<Tag>;
  disabled?: boolean;
  maxTags?: number;
  presentation?: TagPickerPresentation;
};

export function TagPicker({
  id,
  tags,
  value,
  onChange,
  onCreateTag,
  disabled = false,
  maxTags = 20,
  presentation = "inline",
}: TagPickerProps) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [createColor, setCreateColor] = useState<TagColor>("slate");
  const [createPending, setCreatePending] = useState(false);
  const [createError, setCreateError] = useState<string>();
  const byName = useMemo(() => new Map(tags.map((tag) => [tag.name, tag])), [tags]);
  const activeTags = tags.filter((tag) => tag.active);
  const normalizedSearch = search.trim().toLowerCase();
  const visibleTags = activeTags.filter((tag) =>
    !normalizedSearch || tag.name.includes(normalizedSearch),
  );
  const exactMatch = activeTags.some((tag) => tag.name === normalizedSearch);
  const existingMatch = tags.some((tag) => tag.name === normalizedSearch);

  function toggleTag(name: string) {
    if (value.includes(name)) {
      onChange(value.filter((item) => item !== name));
      return;
    }
    if (value.length < maxTags) {
      onChange([...value, name]);
    }
  }

  function removeTag(name: string) {
    onChange(value.filter((item) => item !== name));
  }

  async function createTag() {
    const name = normalizedSearch;
    if (!onCreateTag || !name || exactMatch || createPending) {
      return;
    }

    setCreatePending(true);
    setCreateError(undefined);
    try {
      const created = await onCreateTag({ name, color: createColor });
      if (!value.includes(created.name) && value.length < maxTags) {
        onChange([...value, created.name]);
      }
      setSearch("");
      setCreateColor("slate");
    } catch (error) {
      setCreateError(error instanceof Error ? error.message : "The tag could not be created.");
    } finally {
      setCreatePending(false);
    }
  }

  const pickerContent = (
    <>
      <PopoverHeader>
        <PopoverTitle>{presentation === "popover" ? "Edit file tags" : "Choose tags"}</PopoverTitle>
        <PopoverDescription>Only tags from your shared catalog can be assigned.</PopoverDescription>
      </PopoverHeader>
      {presentation === "popover" ? (
        <div className="mt-3 border-b border-border/70 pb-3">
          <p className="text-xs font-medium uppercase tracking-[0.12em] text-muted-foreground">Assigned tags</p>
          {value.length ? (
            <div className="mt-2 flex flex-wrap gap-1.5" aria-label="Assigned tags">
              {value.map((name) => {
                const tag = byName.get(name);
                return (
                  <span key={name} className="inline-flex items-center gap-1">
                    <TagBadge name={name} color={tag?.color} active={tag?.active ?? true} />
                    <button
                      type="button"
                      aria-label={`Remove tag ${name}`}
                      className="-ml-2 rounded-sm p-1 text-muted-foreground outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/60"
                      onClick={() => removeTag(name)}
                      disabled={disabled}
                    >
                      <X aria-hidden="true" className="size-3" />
                    </button>
                  </span>
                );
              })}
            </div>
          ) : (
            <p className="mt-2 text-sm text-muted-foreground">No tags assigned.</p>
          )}
        </div>
      ) : null}
      <Input
        autoFocus
        value={search}
        onChange={(event) => setSearch(event.target.value)}
        placeholder="Search tags"
        aria-label="Search tags"
        className="mt-2"
        disabled={disabled}
      />
      <div
        className="mt-2 max-h-48 space-y-1 overflow-y-auto"
        role="listbox"
        aria-label="Available tags"
        aria-multiselectable="true"
      >
        {visibleTags.length ? visibleTags.map((tag) => {
          const selected = value.includes(tag.name);
          return (
            <button
              key={tag.id}
              type="button"
              role="option"
              aria-selected={selected}
              onClick={() => toggleTag(tag.name)}
              disabled={disabled || (!selected && value.length >= maxTags)}
              className="flex min-h-10 w-full items-center gap-2 rounded-md px-2 text-left text-sm outline-none hover:bg-muted/60 focus-visible:ring-2 focus-visible:ring-ring/60 disabled:pointer-events-none disabled:opacity-50"
            >
              <span className={cn("size-2.5 rounded-full", tagColorClass(tag.color))} aria-hidden="true" />
              <span className="min-w-0 flex-1 truncate">#{tag.name}</span>
              {selected ? <Check aria-hidden="true" className="size-4 text-primary-strong" /> : null}
            </button>
          );
        }) : (
          <p className="px-2 py-3 text-sm text-muted-foreground">No active tags match.</p>
        )}
      </div>
      {onCreateTag && normalizedSearch && !existingMatch ? (
        <div className="mt-3 border-t border-border/70 pt-3">
          <p className="text-xs text-muted-foreground">Create #{normalizedSearch}</p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {TAG_COLORS.map((option) => (
              <button
                key={option.value}
                type="button"
                aria-label={`Use ${option.label} for ${normalizedSearch}`}
                aria-pressed={createColor === option.value}
                onClick={() => setCreateColor(option.value)}
                disabled={disabled || createPending}
                className={cn(
                  "size-7 rounded-full border-2 outline-none focus-visible:ring-2 focus-visible:ring-ring/60 disabled:opacity-50",
                  tagColorSwatchClass(option.value),
                  createColor === option.value && "ring-2 ring-ring ring-offset-2 ring-offset-popover",
                )}
              />
            ))}
          </div>
          <Button type="button" size="sm" className="mt-3 w-full" onClick={() => void createTag()} disabled={disabled || createPending}>
            {createPending ? "Creating…" : `Create #${normalizedSearch}`}
          </Button>
          {createError ? <p className="mt-2 text-xs text-destructive" role="alert">{createError}</p> : null}
        </div>
      ) : null}
      {normalizedSearch && !exactMatch && existingMatch ? (
        <p className="mt-3 border-t border-border/70 pt-3 text-xs text-muted-foreground">
          That tag is archived. Restore it in Settings before assigning it.
        </p>
      ) : null}
      {presentation === "popover" ? (
        <p className="mt-3 text-xs leading-5 text-muted-foreground">Up to {maxTags} catalog tags.</p>
      ) : null}
    </>
  );

  if (presentation === "popover") {
    return (
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger
          render={
            <Button
              id={id}
              type="button"
              variant="ghost"
              disabled={disabled}
              aria-label={value.length ? `Edit file tags. Assigned: ${value.join(", ")}` : "Add tags"}
              className="h-auto min-h-9 w-full justify-start gap-1.5 overflow-hidden rounded-md px-1.5 py-1 text-left hover:bg-muted/60"
            />
          }
        >
          {value.length ? (
            <>
              {value.slice(0, 3).map((name) => {
                const tag = byName.get(name);
                return <TagBadge key={name} name={name} color={tag?.color} active={tag?.active ?? true} />;
              })}
              {value.length > 3 ? <span className="shrink-0 text-xs text-muted-foreground">+{value.length - 3}</span> : null}
            </>
          ) : (
            <>
              <Plus aria-hidden="true" className="size-4 text-muted-foreground" />
              <span className="text-sm text-muted-foreground">Add tags</span>
            </>
          )}
          <ChevronDown aria-hidden="true" className="ml-auto size-3.5 shrink-0 text-muted-foreground" />
        </PopoverTrigger>
        <PopoverContent align="start" className="w-[min(24rem,calc(100vw-2rem))] p-3">
          {pickerContent}
        </PopoverContent>
      </Popover>
    );
  }

  return (
    <div className="space-y-2">
      <div
        id={id}
        className="flex min-h-11 flex-wrap items-center gap-1.5 rounded-lg border border-input bg-background px-2 py-1.5"
      >
        {value.map((name) => {
          const tag = byName.get(name);
          return (
            <span key={name} className="inline-flex items-center gap-1">
              <TagBadge name={name} color={tag?.color} active={tag?.active ?? true} />
              <button
                type="button"
                aria-label={`Remove tag ${name}`}
                className="-ml-2 rounded-sm p-1 text-muted-foreground outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/60"
                onClick={() => removeTag(name)}
                disabled={disabled}
              >
                <X aria-hidden="true" className="size-3" />
              </button>
            </span>
          );
        })}
        <Popover open={open} onOpenChange={setOpen}>
          <PopoverTrigger
            render={
              <Button
                type="button"
                variant="ghost"
                size="sm"
                disabled={disabled || value.length >= maxTags}
                aria-label="Add tag"
                className="h-8 gap-1.5 text-muted-foreground"
              />
            }
          >
            <Plus aria-hidden="true" />
            {value.length ? "Add tag" : "Choose tags"}
            <ChevronDown aria-hidden="true" className="size-3.5" />
          </PopoverTrigger>
          <PopoverContent align="start" className="w-[min(22rem,calc(100vw-2rem))] p-3">
            {pickerContent}
          </PopoverContent>
        </Popover>
      </div>
      <p className="text-xs leading-5 text-muted-foreground">Up to {maxTags} catalog tags.</p>
    </div>
  );
}

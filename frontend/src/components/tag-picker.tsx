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

type TagPickerProps = {
  id: string;
  tags: Tag[];
  value: string[];
  onChange: (value: string[]) => void;
  onCreateTag?: (payload: { name: string; color: TagColor }) => Promise<Tag>;
  disabled?: boolean;
  maxTags?: number;
};

export function TagPicker({
  id,
  tags,
  value,
  onChange,
  onCreateTag,
  disabled = false,
  maxTags = 20,
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
                onClick={() => onChange(value.filter((item) => item !== name))}
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
            <PopoverHeader>
              <PopoverTitle>Choose tags</PopoverTitle>
              <PopoverDescription>Only tags from your shared catalog can be assigned.</PopoverDescription>
            </PopoverHeader>
            <Input
              autoFocus
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search tags"
              aria-label="Search tags"
              className="mt-2"
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
                    className="flex min-h-10 w-full items-center gap-2 rounded-md px-2 text-left text-sm outline-none hover:bg-muted/60 focus-visible:ring-2 focus-visible:ring-ring/60"
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
                      className={cn(
                        "size-7 rounded-full border-2 outline-none focus-visible:ring-2 focus-visible:ring-ring/60",
                        tagColorSwatchClass(option.value),
                        createColor === option.value && "ring-2 ring-ring ring-offset-2 ring-offset-popover",
                      )}
                    />
                  ))}
                </div>
                <Button type="button" size="sm" className="mt-3 w-full" onClick={() => void createTag()} disabled={createPending}>
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
          </PopoverContent>
        </Popover>
      </div>
      <p className="text-xs leading-5 text-muted-foreground">Up to {maxTags} catalog tags.</p>
    </div>
  );
}

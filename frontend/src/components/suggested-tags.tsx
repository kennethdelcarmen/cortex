"use client";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

type SuggestedTagsProps = {
  selectedTags: string[];
  suggestions: string[];
  pending?: boolean;
  disabled?: boolean;
  onSelect: (tag: string) => void;
};

export function SuggestedTags({
  selectedTags,
  suggestions,
  pending = false,
  disabled = false,
  onSelect,
}: SuggestedTagsProps) {
  const selected = new Set(selectedTags.map((tag) => tag.trim().toLowerCase()));
  const visibleSuggestions = suggestions.slice(0, 6);

  if (!pending && visibleSuggestions.length === 0) {
    return null;
  }

  return (
    <div
      className="mt-2 space-y-2"
      aria-label="Most used tags"
      aria-busy={pending}
    >
      <p className="font-mono text-[0.64rem] uppercase tracking-[0.12em] text-muted-foreground">
        Most used
      </p>
      {pending ? (
        <div className="flex flex-wrap gap-2" aria-hidden="true">
          <Skeleton className="h-9 w-20 rounded-full" />
          <Skeleton className="h-9 w-24 rounded-full" />
          <Skeleton className="h-9 w-16 rounded-full" />
        </div>
      ) : (
        <div className="flex flex-wrap gap-2">
          {visibleSuggestions.map((tag) => {
            const isSelected = selected.has(tag.toLowerCase());

            return (
              <Button
                key={tag}
                type="button"
                size="sm"
                variant={isSelected ? "secondary" : "outline"}
                className="min-h-9 rounded-full px-3 font-mono text-xs"
                aria-pressed={isSelected}
                disabled={disabled || isSelected}
                onClick={() => onSelect(tag)}
              >
                #{tag}
              </Button>
            );
          })}
        </div>
      )}
    </div>
  );
}

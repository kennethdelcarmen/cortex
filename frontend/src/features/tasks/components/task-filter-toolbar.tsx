"use client";

import { CalendarDays, Check, Search, SlidersHorizontal, X } from "lucide-react";
import { useEffect, useState } from "react";
import type { DateRange } from "react-day-picker";
import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import { Input } from "@/components/ui/input";
import {
  Popover,
  PopoverContent,
  PopoverDescription,
  PopoverHeader,
  PopoverTitle,
  PopoverTrigger,
} from "@/components/ui/popover";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { TaskSummary } from "../api";
import {
  formatTaskDateRange,
  taskViewLabel,
  type TaskUrlState,
  type TaskView,
} from "../task-filters";
import { cn } from "@/lib/utils";
import { TagBadge } from "@/components/tag-badge";

type TaskFilterToolbarProps = {
  state: TaskUrlState;
  summary?: TaskSummary;
  isSummaryPending: boolean;
  onViewChange: (view: TaskView) => void;
  onSearchChange: (value: string) => void;
  onTagToggle: (tag: string) => void;
  onTagsClear: () => void;
  onCustomRangeApply: (from: string, to: string) => void;
  onCustomRangeClear: () => void;
  tagCatalog: Array<{ name: string; color: import("@/features/tags/api").TagColor; active: boolean }>;
};

function valueToDate(value?: string) {
  if (!value) {
    return undefined;
  }

  const date = new Date(`${value}T12:00:00`);
  return Number.isNaN(date.getTime()) ? undefined : date;
}

function dateToValue(date: Date) {
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

function TagFilter({
  state,
  summary,
  isSummaryPending,
  onTagToggle,
  onTagsClear,
  tagCatalog,
}: Pick<TaskFilterToolbarProps, "state" | "summary" | "isSummaryPending" | "onTagToggle" | "onTagsClear" | "tagCatalog">) {
  const [open, setOpen] = useState(false);
  const selectedLabel = state.tags.length
    ? state.tags.map((tag) => `#${tag}`).join(", ")
    : "All";

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger
        render={
          <Button
            type="button"
            variant="outline"
            size="sm"
            aria-label={`Filter by tags: ${selectedLabel}`}
            className="min-w-0 justify-between gap-2 bg-background font-normal"
          />
        }
      >
        <span className="flex min-w-0 items-center gap-2">
          <SlidersHorizontal aria-hidden="true" className="size-3.5 shrink-0 text-muted-foreground" />
          <span className="truncate">Tags: {selectedLabel}</span>
        </span>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-72 p-3">
        <PopoverHeader>
          <PopoverTitle>Filter by tags</PopoverTitle>
          <PopoverDescription>Choose one tag to match.</PopoverDescription>
        </PopoverHeader>
        <div className="mt-2 max-h-56 space-y-1 overflow-y-auto">
          {isSummaryPending && !summary ? (
            <p className="px-2 py-3 text-sm text-muted-foreground">Loading tags…</p>
          ) : summary?.tags.length ? (
            summary.tags.map((tag) => {
              const checked = state.tags.includes(tag.name);

              return (
                <label
                  key={tag.name}
                  className="flex min-h-10 cursor-pointer items-center gap-3 rounded-md px-2 hover:bg-muted/60"
                >
                  <input
                    type="radio"
                    name="task-tag-filter"
                    checked={checked}
                    onChange={() => onTagToggle(tag.name)}
                    aria-label={`Filter by ${tag.name}`}
                    className="size-4 accent-primary"
                  />
                  <TagBadge
                    name={tag.name}
                    color={tagCatalog.find((item) => item.name === tag.name)?.color ?? tag.color}
                    active={tagCatalog.find((item) => item.name === tag.name)?.active ?? tag.active}
                    className="min-w-0 flex-1 justify-start truncate border-0 bg-transparent px-0 text-sm"
                  />
                  <span className="font-mono text-xs text-muted-foreground">{tag.count}</span>
                </label>
              );
            })
          ) : (
            <p className="px-2 py-3 text-sm text-muted-foreground">Create a task tag to filter by it.</p>
          )}
        </div>
        {state.tags.length ? (
          <Button type="button" variant="ghost" size="sm" className="mt-2 w-full" onClick={onTagsClear}>
            Clear tag filter
          </Button>
        ) : null}
      </PopoverContent>
    </Popover>
  );
}

function DateRangeFilter({
  state,
  onCustomRangeApply,
  onCustomRangeClear,
}: Pick<TaskFilterToolbarProps, "state" | "onCustomRangeApply" | "onCustomRangeClear">) {
  const [open, setOpen] = useState(false);
  const [range, setRange] = useState<DateRange | undefined>(() => ({
    from: valueToDate(state.from),
    to: valueToDate(state.to),
  }));

  function handleOpenChange(nextOpen: boolean) {
    if (nextOpen) {
      setRange({
        from: valueToDate(state.from),
        to: valueToDate(state.to),
      });
    }
    setOpen(nextOpen);
  }

  function apply() {
    if (!range?.from || !range.to) {
      return;
    }

    onCustomRangeApply(dateToValue(range.from), dateToValue(range.to));
    setOpen(false);
  }

  function clear() {
    onCustomRangeClear();
    setRange(undefined);
    setOpen(false);
  }

  const label = state.view === "custom"
    ? formatTaskDateRange(state.from, state.to)
    : "Date range";

  return (
    <Popover open={open} onOpenChange={handleOpenChange}>
      <PopoverTrigger
        render={
          <Button
            type="button"
            variant="outline"
            size="sm"
            aria-label={`Filter by ${label}`}
            className={cn(
              "min-w-0 justify-between gap-2 bg-background font-normal",
              state.view === "custom" && "border-primary/50 text-foreground",
            )}
          />
        }
      >
        <span className="flex min-w-0 items-center gap-2">
          <CalendarDays aria-hidden="true" className="size-3.5 shrink-0 text-muted-foreground" />
          <span className="truncate">{label}</span>
        </span>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-auto p-3">
        <PopoverHeader>
          <PopoverTitle>Custom due dates</PopoverTitle>
          <PopoverDescription>Choose an inclusive local date range.</PopoverDescription>
        </PopoverHeader>
        <Calendar
          mode="range"
          selected={range}
          onSelect={setRange}
          numberOfMonths={1}
          autoFocus
          className="mt-2"
        />
        <div className="flex justify-end gap-2 border-t border-border/70 pt-3">
          {state.view === "custom" ? (
            <Button type="button" variant="ghost" size="sm" onClick={clear}>
              Clear
            </Button>
          ) : null}
          <Button type="button" size="sm" disabled={!range?.from || !range.to} onClick={apply}>
            <Check aria-hidden="true" />
            Apply
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  );
}

export function TaskFilterToolbar({
  state,
  summary,
  isSummaryPending,
  onViewChange,
  onSearchChange,
  onTagToggle,
  onTagsClear,
  onCustomRangeApply,
  onCustomRangeClear,
  tagCatalog,
}: TaskFilterToolbarProps) {
  const [searchDraft, setSearchDraft] = useState(state.search);

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => setSearchDraft(state.search));
    return () => window.cancelAnimationFrame(frame);
  }, [state.search]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      const normalized = searchDraft.trim().slice(0, 200);
      if (normalized !== state.search) {
        onSearchChange(normalized);
      }
    }, 300);

    return () => window.clearTimeout(timer);
  }, [onSearchChange, searchDraft, state.search]);

  const viewOptions = state.view === "custom"
    ? ["all", "today", "upcoming", "overdue", "high-priority", "custom"] as const
    : ["all", "today", "upcoming", "overdue", "high-priority"] as const;

  return (
    <div className="mt-5 rounded-xl border border-border/80 bg-card/60 p-2.5 shadow-[0_16px_48px_-40px_color-mix(in_oklab,var(--foreground)_35%,transparent)]">
      <div className="flex min-w-0 flex-col gap-2.5 lg:flex-row">
        <div className="relative min-w-0 flex-1">
          <Search
            aria-hidden="true"
            className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
          />
          <Input
            type="search"
            value={searchDraft}
            maxLength={200}
            onChange={(event) => setSearchDraft(event.target.value)}
            placeholder="Search tasks"
            aria-label="Search tasks"
            className="h-10 bg-background pl-9 pr-9"
          />
          {searchDraft ? (
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              aria-label="Clear task search"
              onClick={() => setSearchDraft("")}
              className="absolute right-1 top-1/2 -translate-y-1/2 text-muted-foreground"
            >
              <X aria-hidden="true" />
            </Button>
          ) : null}
        </div>

        <div className="grid min-w-0 gap-2 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] lg:flex lg:shrink-0">
          <Select
            value={state.view}
            onValueChange={(value) => {
              if (value !== "custom") {
                onViewChange(value as TaskView);
              }
            }}
          >
            <SelectTrigger size="sm" aria-label="Choose task view" className="h-10 w-full bg-background lg:hidden">
              <SelectValue>{taskViewLabel(state.view)}</SelectValue>
            </SelectTrigger>
            <SelectContent>
              {viewOptions.map((view) => (
                <SelectItem key={view} value={view}>
                  {taskViewLabel(view)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          <TagFilter
            state={state}
            summary={summary}
            isSummaryPending={isSummaryPending}
            onTagToggle={onTagToggle}
            onTagsClear={onTagsClear}
            tagCatalog={tagCatalog}
          />
          <DateRangeFilter
            state={state}
            onCustomRangeApply={onCustomRangeApply}
            onCustomRangeClear={onCustomRangeClear}
          />
        </div>
      </div>
    </div>
  );
}

"use client";

import { ArrowDown, ArrowUp, CalendarDays, ListTodo, Tag } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { TaskSummary } from "../api";
import {
  formatTaskDateRange,
  taskViewLabel,
  type TaskUrlState,
  type TaskView,
} from "../task-filters";
import { cn } from "@/lib/utils";

type TaskViewNavigationProps = {
  state: TaskUrlState;
  summary?: TaskSummary;
  isSummaryPending: boolean;
  onViewChange: (view: TaskView) => void;
  onTagToggle: (tag: string) => void;
};

const viewOptions: Array<{ value: Exclude<TaskView, "custom">; icon: typeof ListTodo }> = [
  { value: "all", icon: ListTodo },
  { value: "today", icon: CalendarDays },
  { value: "upcoming", icon: ArrowDown },
  { value: "overdue", icon: ArrowUp },
  { value: "high-priority", icon: ArrowUp },
];

function countForView(summary: TaskSummary | undefined, view: Exclude<TaskView, "custom">) {
  if (!summary) {
    return undefined;
  }

  return view === "all" ? summary.all : summary[view.replace("-", "_") as "today" | "upcoming" | "overdue" | "high_priority"];
}

function NavigationButton({
  label,
  count,
  selected,
  icon: Icon,
  onClick,
}: {
  label: string;
  count?: number;
  selected: boolean;
  icon: typeof ListTodo;
  onClick: () => void;
}) {
  return (
    <Button
      type="button"
      variant="ghost"
      size="sm"
      aria-current={selected ? "page" : undefined}
      onClick={onClick}
      className={cn(
        "h-9 w-full justify-start gap-2 px-2.5 text-xs font-normal",
        selected
          ? "bg-primary/10 font-medium text-foreground"
          : "text-muted-foreground hover:bg-muted/70 hover:text-foreground",
      )}
    >
      <Icon aria-hidden="true" className={cn("size-3.5", selected && "text-primary")} />
      <span className="min-w-0 flex-1 truncate">{label}</span>
      {count !== undefined ? (
        <span className="font-mono text-[0.62rem] text-muted-foreground">{count}</span>
      ) : null}
    </Button>
  );
}

export function TaskViewNavigation({
  state,
  summary,
  isSummaryPending,
  onViewChange,
  onTagToggle,
}: TaskViewNavigationProps) {
  return (
    <div className="mt-4 border-l border-border/70 pl-2">
      <p className="px-2.5 font-mono text-[0.6rem] uppercase tracking-[0.16em] text-muted-foreground">
        Focus views
      </p>
      <div className="mt-2 space-y-0.5">
        {viewOptions.map(({ value, icon }) => (
          <NavigationButton
            key={value}
            label={taskViewLabel(value)}
            count={countForView(summary, value)}
            selected={state.view === value}
            icon={icon}
            onClick={() => onViewChange(value)}
          />
        ))}
        {state.view === "custom" ? (
          <NavigationButton
            label={formatTaskDateRange(state.from, state.to)}
            selected
            icon={CalendarDays}
            onClick={() => onViewChange("custom")}
          />
        ) : null}
      </div>

      <div className="mt-5">
        <p className="flex items-center gap-2 px-2.5 font-mono text-[0.6rem] uppercase tracking-[0.16em] text-muted-foreground">
          <Tag aria-hidden="true" className="size-3" />
          Tags
        </p>
        <div className="mt-2 space-y-0.5">
          {isSummaryPending && !summary ? (
            <div className="space-y-2 px-2.5" aria-label="Loading tags">
              <span className="block h-3 w-24 animate-pulse rounded bg-muted" />
              <span className="block h-3 w-20 animate-pulse rounded bg-muted" />
            </div>
          ) : summary?.tags.length ? (
            summary.tags.map((tag) => {
              const selected = state.tags.includes(tag.name);

              return (
                <Button
                  key={tag.name}
                  type="button"
                  variant="ghost"
                  size="sm"
                  aria-pressed={selected}
                  onClick={() => onTagToggle(tag.name)}
                  className={cn(
                    "h-8 w-full justify-start gap-2 px-2.5 text-xs font-normal",
                    selected
                      ? "bg-primary/10 font-medium text-foreground"
                      : "text-muted-foreground hover:bg-muted/70 hover:text-foreground",
                  )}
                >
                  <span className="min-w-0 flex-1 truncate text-left">#{tag.name}</span>
                  <span className="font-mono text-[0.62rem] text-muted-foreground">{tag.count}</span>
                </Button>
              );
            })
          ) : (
            <p className="px-2.5 text-xs text-muted-foreground">No tags yet</p>
          )}
        </div>
      </div>
    </div>
  );
}

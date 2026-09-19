"use client";

import { ArrowRight, CalendarDays, Clock3, ListTodo, Pencil, Plus } from "lucide-react";
import { useRef, type KeyboardEvent } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";
import type { Task, TaskPriority, TaskStatus } from "../api";
import {
  dueUrgency,
  formatDateTime,
  priorityOption,
  statusOption,
  statusLabel,
  TASK_PRIORITIES,
  TASK_STATUSES,
  urgencyLabel,
} from "../utils";
import { TaskOptionValue } from "./task-option-value";

export type TaskListTab = "all" | TaskStatus;

type TaskListProps = {
  tasks: Task[];
  counts: Record<TaskListTab, number>;
  selectedTab: TaskListTab;
  now: Date;
  isUpdatingTaskId?: string;
  onTabChange: (tab: TaskListTab) => void;
  onStatusChange: (task: Task, status: TaskStatus) => void;
  onPriorityChange: (task: Task, priority: TaskPriority) => void;
  onOpenDetails: (task: Task) => void;
  onAddTask: () => void;
};

const ALL_TAB = {
  value: "all" as const,
  label: "All",
  icon: ListTodo,
  colorClass: "text-primary",
};

function TaskTabs({
  counts,
  selectedTab,
  onTabChange,
}: Pick<TaskListProps, "counts" | "selectedTab" | "onTabChange">) {
  const tabRefs = useRef<Partial<Record<TaskListTab, HTMLButtonElement | null>>>({});
  const tabs: Array<{
    value: TaskListTab;
    label: string;
    icon: typeof ALL_TAB.icon;
    colorClass: string;
  }> = [ALL_TAB, ...TASK_STATUSES];

  function focusTab(tab: TaskListTab) {
    onTabChange(tab);
    requestAnimationFrame(() => tabRefs.current[tab]?.focus());
  }

  function handleKeyDown(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    let nextIndex: number | null = null;

    if (event.key === "ArrowRight") {
      nextIndex = (index + 1) % tabs.length;
    } else if (event.key === "ArrowLeft") {
      nextIndex = (index - 1 + tabs.length) % tabs.length;
    } else if (event.key === "Home") {
      nextIndex = 0;
    } else if (event.key === "End") {
      nextIndex = tabs.length - 1;
    }

    if (nextIndex === null) {
      return;
    }

    event.preventDefault();
    focusTab(tabs[nextIndex].value);
  }

  return (
    <div
      role="tablist"
      aria-label="Task status"
      aria-orientation="horizontal"
      className="flex gap-1 overflow-x-auto border-b border-border/70 pb-px"
    >
      {tabs.map((tab, index) => {
        const selected = tab.value === selectedTab;
        const Icon = tab.icon;

        return (
          <button
            key={tab.value}
            ref={(element) => {
              tabRefs.current[tab.value] = element;
            }}
            type="button"
            role="tab"
            aria-selected={selected}
            aria-controls="task-list-panel"
            tabIndex={selected ? 0 : -1}
            onClick={() => onTabChange(tab.value)}
            onKeyDown={(event) => handleKeyDown(event, index)}
            className={cn(
              "relative flex min-h-11 shrink-0 items-center gap-2 rounded-t-md px-3 text-sm font-medium text-muted-foreground outline-none transition-colors hover:bg-muted/60 hover:text-foreground focus-visible:z-10 focus-visible:ring-3 focus-visible:ring-ring/50 sm:px-4",
              selected && "text-foreground",
            )}
          >
            <Icon
              aria-hidden="true"
              className={cn("size-4", selected ? tab.colorClass : "text-muted-foreground")}
            />
            <span>{tab.label}</span>
            <span
              className={cn(
                "min-w-5 rounded-full px-1.5 py-0.5 text-center font-mono text-[0.65rem] leading-none",
                selected ? "bg-primary/12 text-primary" : "bg-muted text-muted-foreground",
              )}
            >
              {counts[tab.value]}
            </span>
            <span
              aria-hidden="true"
              className={cn(
                "absolute inset-x-2 -bottom-px h-0.5 rounded-full bg-transparent transition-colors sm:inset-x-3",
                selected && "bg-primary",
              )}
            />
          </button>
        );
      })}
    </div>
  );
}

function TaskRow({
  task,
  now,
  isUpdating,
  onStatusChange,
  onPriorityChange,
  onOpenDetails,
}: {
  task: Task;
  now: Date;
  isUpdating: boolean;
  onStatusChange: (status: TaskStatus) => void;
  onPriorityChange: (priority: TaskPriority) => void;
  onOpenDetails: () => void;
}) {
  const status = statusOption(task.status);
  const priority = priorityOption(task.priority);
  const urgency = dueUrgency(task.due_at, now);

  return (
    <li className="border-b border-border/70 last:border-b-0">
      <article
        aria-busy={isUpdating}
        onClick={(event) => {
          if (
            event.target instanceof Element &&
            event.target.closest("button, a, input, textarea, select, [role='combobox']")
          ) {
            return;
          }

          onOpenDetails();
        }}
        className={cn(
          "grid cursor-pointer gap-4 p-4 transition-colors hover:bg-muted/25 sm:grid-cols-[minmax(0,1fr)_auto] lg:grid-cols-[minmax(0,1fr)_auto_auto_auto_auto] lg:items-center",
          task.status === "canceled" && "opacity-80",
        )}
      >
        <div className="min-w-0">
          <div className="flex min-w-0 items-start gap-2">
            <span
              aria-hidden="true"
              className={cn("mt-1.5 size-2 shrink-0 rounded-full bg-current", status.colorClass)}
            />
            <button
              type="button"
              onClick={onOpenDetails}
              className={cn(
                "min-w-0 flex-1 text-left text-sm font-medium leading-5 text-foreground outline-none hover:text-primary focus-visible:rounded-sm focus-visible:ring-3 focus-visible:ring-ring/50",
                (task.status === "done" || task.status === "canceled") &&
                  "line-through decoration-primary/50",
              )}
            >
              {task.title}
            </button>
          </div>

          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 pl-4 text-xs text-muted-foreground">
            {task.start_at ? (
              <span className="inline-flex items-center gap-1.5 font-mono">
                <CalendarDays aria-hidden="true" className="size-3.5" />
                {formatDateTime(task.start_at)}
              </span>
            ) : null}
            {task.due_at ? (
              <span
                className={cn(
                  "inline-flex items-center gap-1.5 whitespace-nowrap font-mono",
                  urgency === "overdue" && "font-medium text-destructive",
                  urgency === "today" && "font-medium text-primary",
                )}
              >
                {task.start_at ? (
                  <ArrowRight aria-hidden="true" className="size-3 shrink-0 text-muted-foreground/70" />
                ) : (
                  <Clock3 aria-hidden="true" className="size-3.5" />
                )}
                {urgencyLabel(urgency)} · {formatDateTime(task.due_at)}
              </span>
            ) : !task.start_at ? (
              <span className="inline-flex items-center gap-1.5 font-mono">
                <Clock3 aria-hidden="true" className="size-3.5" />
                {urgencyLabel(urgency)}
              </span>
            ) : null}
            {task.tags.map((tag) => (
              <Badge
                key={tag}
                variant="outline"
                className="h-auto rounded-full bg-background px-1.5 py-0 text-[0.65rem]"
              >
                #{tag}
              </Badge>
            ))}
          </div>
        </div>

        <Select
          value={task.status}
          onValueChange={(value) => onStatusChange(value as TaskStatus)}
          disabled={isUpdating}
        >
          <SelectTrigger
            size="sm"
            aria-label={`Change status for ${task.title}`}
            className={cn("w-full bg-background sm:w-auto", status.colorClass)}
          >
            <SelectValue>
              <TaskOptionValue option={status} />
            </SelectValue>
          </SelectTrigger>
          <SelectContent onClick={(event) => event.stopPropagation()}>
            {TASK_STATUSES.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                <TaskOptionValue option={option} />
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select
          value={task.priority}
          onValueChange={(value) => onPriorityChange(value as TaskPriority)}
          disabled={isUpdating}
        >
          <SelectTrigger
            size="sm"
            aria-label={`Change priority for ${task.title}`}
            className={cn("w-full bg-background sm:w-auto", priority.colorClass)}
          >
            <SelectValue>
              <TaskOptionValue option={priority} />
            </SelectValue>
          </SelectTrigger>
          <SelectContent onClick={(event) => event.stopPropagation()}>
            {TASK_PRIORITIES.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                <TaskOptionValue option={option} />
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          aria-label={`Open details for ${task.title}`}
          onClick={onOpenDetails}
          disabled={isUpdating}
          className="justify-self-start text-muted-foreground hover:text-foreground sm:justify-self-end"
        >
          <Pencil aria-hidden="true" />
        </Button>
      </article>
    </li>
  );
}

export function TaskList({
  tasks,
  counts,
  selectedTab,
  now,
  isUpdatingTaskId,
  onTabChange,
  onStatusChange,
  onPriorityChange,
  onOpenDetails,
  onAddTask,
}: TaskListProps) {
  return (
    <div>
      <div className="flex min-w-0 items-end gap-3">
        <div className="min-w-0 flex-1">
          <TaskTabs
            counts={counts}
            selectedTab={selectedTab}
            onTabChange={onTabChange}
          />
        </div>
        <Button
          type="button"
          size="lg"
          onClick={onAddTask}
          className="shrink-0"
        >
          <Plus aria-hidden="true" />
          Add task
        </Button>
      </div>
      <div
        id="task-list-panel"
        role="tabpanel"
        aria-label={`${selectedTab === "all" ? "All" : statusLabel(selectedTab)} tasks`}
        tabIndex={0}
        className="mt-4 overflow-hidden rounded-xl border border-border/80 bg-card outline-none focus-visible:ring-3 focus-visible:ring-ring/40"
      >
        {tasks.length === 0 ? (
          <div className="px-6 py-12 text-center sm:px-8">
            <p className="text-base font-medium text-foreground">
              Nothing is {selectedTab === "all" ? "here" : statusLabel(selectedTab).toLowerCase()} right now.
            </p>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">
              Choose another status tab or add a new task to this list.
            </p>
          </div>
        ) : (
          <ul aria-label="Tasks">
            {tasks.map((task) => (
              <TaskRow
                key={task.id}
                task={task}
                now={now}
                isUpdating={isUpdatingTaskId === task.id}
                onStatusChange={(status) => onStatusChange(task, status)}
                onPriorityChange={(priority) => onPriorityChange(task, priority)}
                onOpenDetails={() => onOpenDetails(task)}
              />
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

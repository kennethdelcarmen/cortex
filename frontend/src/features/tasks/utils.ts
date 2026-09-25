import {
  ArrowDown,
  ArrowUp,
  Ban,
  CheckCircle2,
  Circle,
  Equal,
  Inbox,
  LoaderCircle,
  Minus,
  type LucideIcon,
} from "lucide-react";
import type { Task, TaskPriority, TaskStatus } from "./api";

export type TaskStatusOption = {
  value: TaskStatus;
  label: string;
  icon: LucideIcon;
  colorClass: string;
};

export type TaskPriorityOption = {
  value: TaskPriority;
  label: string;
  icon: LucideIcon;
  colorClass: string;
};

export type TaskDateTimeValue = {
  date: string;
  time: string;
};

export const TASK_STATUSES: TaskStatusOption[] = [
  {
    value: "backlog",
    label: "Backlog",
    icon: Inbox,
    colorClass: "text-muted-foreground",
  },
  {
    value: "todo",
    label: "To do",
    icon: Circle,
    colorClass: "text-chart-4",
  },
  {
    value: "in_progress",
    label: "In progress",
    icon: LoaderCircle,
    colorClass: "text-chart-3",
  },
  {
    value: "done",
    label: "Done",
    icon: CheckCircle2,
    colorClass: "text-chart-2",
  },
  {
    value: "canceled",
    label: "Canceled",
    icon: Ban,
    colorClass: "text-destructive",
  },
];

export const TASK_PRIORITIES: TaskPriorityOption[] = [
  {
    value: "none",
    label: "No priority",
    icon: Minus,
    colorClass: "text-muted-foreground",
  },
  {
    value: "low",
    label: "Low",
    icon: ArrowDown,
    colorClass: "text-chart-2",
  },
  {
    value: "medium",
    label: "Medium",
    icon: Equal,
    colorClass: "text-chart-3",
  },
  {
    value: "high",
    label: "High",
    icon: ArrowUp,
    colorClass: "text-primary-strong",
  },
];

export const ACTIVE_STATUSES: TaskStatus[] = ["backlog", "todo", "in_progress"];

export const STATUS_GROUPS = TASK_STATUSES;

export function statusLabel(status: TaskStatus) {
  return TASK_STATUSES.find((option) => option.value === status)?.label ?? status;
}

export function priorityLabel(priority: TaskPriority) {
  return (
    TASK_PRIORITIES.find((option) => option.value === priority)?.label ?? priority
  );
}

export function statusOption(status: TaskStatus) {
  return TASK_STATUSES.find((option) => option.value === status) ?? TASK_STATUSES[0];
}

export function priorityOption(priority: TaskPriority) {
  return TASK_PRIORITIES.find((option) => option.value === priority) ?? TASK_PRIORITIES[0];
}

function pad(value: number) {
  return String(value).padStart(2, "0");
}

export function currentLocalDateInput(now = new Date()) {
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

export function toLocalDateTimeInput(value: string | null) {
  if (!value) {
    return "";
  }

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return "";
  }

  return [
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`,
    `${pad(date.getHours())}:${pad(date.getMinutes())}`,
  ].join("T");
}

export function toLocalDateTimeParts(value: string | null): TaskDateTimeValue {
  const input = toLocalDateTimeInput(value);

  if (!input) {
    return { date: "", time: "" };
  }

  const [date = "", time = ""] = input.split("T");
  return { date, time };
}

export function localDateTimeToIso(value: string) {
  if (!value) {
    return null;
  }

  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date.toISOString();
}

export function localDateTimePartsToIso(value: TaskDateTimeValue) {
  if (!value.date) {
    return null;
  }

  return localDateTimeToIso(`${value.date}T${value.time || "00:00"}`);
}

export function adjustDueDateForStart(
  startAt: TaskDateTimeValue,
  dueAt: TaskDateTimeValue,
) {
  if (!startAt.date || !dueAt.date || dueAt.date >= startAt.date) {
    return dueAt;
  }

  return { ...dueAt, date: startAt.date };
}

export function dueDateTimeAfterStart(startAt: TaskDateTimeValue, minutes = 30) {
  if (!startAt.date || !startAt.time) {
    return undefined;
  }

  const startIso = localDateTimePartsToIso(startAt);

  if (!startIso) {
    return undefined;
  }

  const due = new Date(startIso);
  due.setMinutes(due.getMinutes() + minutes);

  return toLocalDateTimeParts(due.toISOString());
}

export function taskDateTimeError(value: TaskDateTimeValue) {
  if (!value.date) {
    if (value.time) {
      return "Choose a date before setting a time.";
    }

    return undefined;
  }

  const dateMatch = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value.date);
  const timeValue = value.time || "00:00";
  const timeMatch = /^(\d{2}):(\d{2})$/.exec(timeValue);
  const iso = localDateTimePartsToIso(value);

  if (!dateMatch || !timeMatch || !iso) {
    return "Use a valid local date and time.";
  }

  const date = new Date(`${value.date}T${timeValue}`);
  const matchesInput =
    date.getFullYear() === Number(dateMatch[1]) &&
    date.getMonth() + 1 === Number(dateMatch[2]) &&
    date.getDate() === Number(dateMatch[3]) &&
    date.getHours() === Number(timeMatch[1]) &&
    date.getMinutes() === Number(timeMatch[2]);

  if (!matchesInput) {
    return "Use a valid local date and time.";
  }

  return undefined;
}

export function localDateToIso(value: string, endOfDay = false) {
  if (!value) {
    return undefined;
  }

  const date = new Date(`${value}T00:00`);

  if (Number.isNaN(date.getTime())) {
    return undefined;
  }

  if (endOfDay) {
    date.setDate(date.getDate() + 1);
  }

  return date.toISOString();
}

export function parseTagInput(value: string) {
  return Array.from(
    new Set(
      value
        .split(",")
        .map((tag) => tag.trim().toLowerCase())
        .filter(Boolean),
    ),
  );
}

export function tagsToInput(tags: string[]) {
  return tags.join(", ");
}

export function appendTagInput(value: string, tag: string) {
  const normalizedTag = tag.trim().toLowerCase();
  if (!normalizedTag || parseTagInput(value).includes(normalizedTag)) {
    return value;
  }

  const trimmedValue = value.trimEnd();
  if (!trimmedValue) {
    return normalizedTag;
  }

  return `${trimmedValue}${trimmedValue.endsWith(",") ? " " : ", "}${normalizedTag}`;
}

export function formatDateTime(value: string | null) {
  if (!value) {
    return "No date set";
  }

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return "Date unavailable";
  }

  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

export type DueUrgency = "overdue" | "today" | "tomorrow" | "upcoming";

export function dueUrgency(value: string | null, now = new Date()): DueUrgency | null {
  if (!value) {
    return null;
  }

  const due = new Date(value);

  if (Number.isNaN(due.getTime())) {
    return null;
  }

  if (due.getTime() < now.getTime()) {
    return "overdue";
  }

  const today = new Date(now);
  today.setHours(0, 0, 0, 0);
  const tomorrow = new Date(today);
  tomorrow.setDate(tomorrow.getDate() + 1);
  const dayAfterTomorrow = new Date(tomorrow);
  dayAfterTomorrow.setDate(dayAfterTomorrow.getDate() + 1);

  if (due < tomorrow) {
    return "today";
  }

  if (due < dayAfterTomorrow) {
    return "tomorrow";
  }

  return "upcoming";
}

export function taskDueUrgency(
  task: Pick<Task, "due_at" | "status">,
  now = new Date(),
): DueUrgency | null {
  if (task.status === "done" || task.status === "canceled") {
    return null;
  }

  return dueUrgency(task.due_at, now);
}

export function urgencyLabel(urgency: DueUrgency | null) {
  switch (urgency) {
    case "overdue":
      return "Overdue";
    case "today":
      return "Due today";
    case "tomorrow":
      return "Due tomorrow";
    case "upcoming":
      return "Upcoming";
    default:
      return "No due date";
  }
}

export function isDueToday(task: Task, now = new Date()) {
  return taskDueUrgency(task, now) === "today";
}

export function isOverdue(task: Task, now = new Date()) {
  return taskDueUrgency(task, now) === "overdue";
}

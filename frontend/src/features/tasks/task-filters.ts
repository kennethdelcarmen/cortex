import type { TaskListFilters, TaskPriority } from "./api";
import { ACTIVE_STATUSES, currentLocalDateInput, localDateToIso } from "./utils";

export const TASK_VIEWS = [
  "all",
  "today",
  "upcoming",
  "overdue",
  "high-priority",
  "custom",
] as const;

export const TASK_LAYOUTS = ["list", "calendar"] as const;

export type TaskView = (typeof TASK_VIEWS)[number];
export type TaskLayout = (typeof TASK_LAYOUTS)[number];

export type TaskUrlState = {
  layout: TaskLayout;
  view: TaskView;
  search: string;
  tags: string[];
  from?: string;
  to?: string;
};

const taskViewSet = new Set<string>(TASK_VIEWS);
const taskLayoutSet = new Set<string>(TASK_LAYOUTS);
const localDatePattern = /^\d{4}-\d{2}-\d{2}$/;

function validLocalDate(value: string | null) {
  if (!value || !localDatePattern.test(value)) {
    return undefined;
  }

  const date = new Date(`${value}T12:00:00`);

  if (Number.isNaN(date.getTime())) {
    return undefined;
  }

  const [year, month, day] = value.split("-").map(Number);

  return date.getFullYear() === year &&
    date.getMonth() + 1 === month &&
    date.getDate() === day
    ? value
    : undefined;
}

export function parseTaskUrlState(params: URLSearchParams): TaskUrlState {
  const rawView = params.get("view");
  const candidateView = rawView && taskViewSet.has(rawView) ? rawView : "all";
  const rawLayout = params.get("layout");
  const layout = rawLayout && taskLayoutSet.has(rawLayout)
    ? rawLayout as TaskLayout
    : "list";
  const from = validLocalDate(params.get("from"));
  const to = validLocalDate(params.get("to"));
  const customRangeIsValid = Boolean(from && to && from <= to);
  const view = candidateView === "custom" && !customRangeIsValid
    ? "all"
    : candidateView as TaskView;
  const tag = params
    .getAll("tag")
    .map((value) => value.trim().toLowerCase())
    .find(Boolean);

  return {
    layout,
    view,
    search: params.get("q")?.trim().slice(0, 200) ?? "",
    tags: tag ? [tag] : [],
    from,
    to,
  };
}

export function taskViewLabel(view: TaskView) {
  switch (view) {
    case "today":
      return "Today";
    case "upcoming":
      return "Upcoming";
    case "overdue":
      return "Overdue";
    case "high-priority":
      return "High Priority";
    case "custom":
      return "Custom dates";
    default:
      return "All Tasks";
  }
}

export function taskListFiltersForState(
  state: TaskUrlState,
  now = new Date(),
): TaskListFilters {
  const filters: TaskListFilters = {
    statuses: state.view === "all" ? [] : [...ACTIVE_STATUSES],
    priorities: [],
    tags: state.tags,
    search: state.search || undefined,
  };
  const today = currentLocalDateInput(now);

  switch (state.view) {
    case "today":
      filters.dueFrom = localDateToIso(today);
      filters.dueTo = localDateToIso(today, true);
      break;
    case "upcoming":
      filters.dueFrom = localDateToIso(today, true);
      break;
    case "overdue":
      filters.dueTo = now.toISOString();
      break;
    case "high-priority":
      filters.priorities = ["high" satisfies TaskPriority];
      break;
    case "custom":
      if (state.from && state.to) {
        filters.dueFrom = localDateToIso(state.from);
        filters.dueTo = localDateToIso(state.to, true);
      }
      break;
    default:
      break;
  }

  return filters;
}

export function clearTaskListUrlState(params: URLSearchParams) {
  params.delete("view");
  params.delete("q");
  params.delete("tag");
  params.delete("from");
  params.delete("to");
}

export function taskSummaryTimezone() {
  return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
}

export function formatTaskDateRange(from?: string, to?: string) {
  if (!from || !to) {
    return "Date range";
  }

  const formatter = new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
  });

  return `${formatter.format(new Date(`${from}T12:00:00`))} – ${formatter.format(new Date(`${to}T12:00:00`))}`;
}

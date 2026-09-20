import { z } from "zod";
import { apiFetch } from "@/lib/api/client";

export const taskStatusSchema = z.enum([
  "backlog",
  "todo",
  "in_progress",
  "done",
  "canceled",
]);

export const taskPrioritySchema = z.enum(["none", "low", "medium", "high"]);
export const taskListOrderSchema = z.enum(["due", "board"]);
export const recurrenceFrequencySchema = z.enum(["daily", "weekly", "monthly", "yearly"]);
export const recurrenceStateSchema = z.enum(["active", "paused", "ended"]);
export const recurrenceWeekdaySchema = z.enum([
  "monday",
  "tuesday",
  "wednesday",
  "thursday",
  "friday",
  "saturday",
  "sunday",
]);

export const taskRecurrenceSchema = z.object({
  timezone: z.string().min(1),
  frequency: recurrenceFrequencySchema,
  interval: z.number().int().min(1),
  weekdays: z.array(recurrenceWeekdaySchema),
  month_day: z.number().int().min(1).max(31).nullable(),
  month: z.number().int().min(1).max(12).nullable(),
  day: z.number().int().min(1).max(31).nullable(),
  until_date: z.string().min(1).nullable(),
  occurrence_count: z.number().int().min(1).nullable(),
});

export const taskSchema = z.object({
  id: z.string().min(1),
  title: z.string().min(1),
  description: z.string().nullable(),
  status: taskStatusSchema,
  priority: taskPrioritySchema,
  position: z.number().int().nonnegative(),
  start_at: z.string().min(1).nullable(),
  due_at: z.string().min(1).nullable(),
  tags: z.array(z.string()),
  created_at: z.string().min(1),
  updated_at: z.string().min(1),
  series_id: z.string().min(1).nullable(),
  occurrence_key: z.string().min(1).nullable(),
  series_exception: z.boolean(),
  skipped_at: z.string().min(1).nullable(),
});

const taskListResponseSchema = z.object({
  items: z.array(taskSchema),
  next_cursor: z.string().nullable(),
});

const taskSummaryResponseSchema = z.object({
  all: z.number().int().nonnegative(),
  today: z.number().int().nonnegative(),
  upcoming: z.number().int().nonnegative(),
  overdue: z.number().int().nonnegative(),
  high_priority: z.number().int().nonnegative(),
  tags: z.array(
    z.object({
      name: z.string().min(1),
      count: z.number().int().nonnegative(),
    }),
  ),
});

const taskSeriesSchema = z.object({
  id: z.string().min(1),
  state: recurrenceStateSchema,
  title: z.string().min(1),
  description: z.string().nullable(),
  status: taskStatusSchema,
  priority: taskPrioritySchema,
  tags: z.array(z.string()),
  recurrence: taskRecurrenceSchema,
  materialized_through_at: z.string().min(1).nullable(),
  created_at: z.string().min(1),
  updated_at: z.string().min(1),
});

const taskSeriesListResponseSchema = z.object({
  items: z.array(taskSeriesSchema),
});

export type Task = z.infer<typeof taskSchema>;
export type TaskStatus = z.infer<typeof taskStatusSchema>;
export type TaskPriority = z.infer<typeof taskPrioritySchema>;
export type TaskListOrder = z.infer<typeof taskListOrderSchema>;
export type TaskListPage = z.infer<typeof taskListResponseSchema>;
export type TaskSummary = z.infer<typeof taskSummaryResponseSchema>;
export type RecurrenceFrequency = z.infer<typeof recurrenceFrequencySchema>;
export type RecurrenceState = z.infer<typeof recurrenceStateSchema>;
export type RecurrenceWeekday = z.infer<typeof recurrenceWeekdaySchema>;
export type TaskRecurrence = z.infer<typeof taskRecurrenceSchema>;
export type TaskSeries = z.infer<typeof taskSeriesSchema>;
export type TaskSeriesList = z.infer<typeof taskSeriesListResponseSchema>;

export type TaskRecurrenceInput = {
  timezone: string;
  frequency: RecurrenceFrequency;
  interval: number;
  weekdays: RecurrenceWeekday[];
  month_day: number | null;
  month: number | null;
  day: number | null;
  until_date: string | null;
  occurrence_count: number | null;
};

export type TaskListFilters = {
  statuses: TaskStatus[];
  priorities: TaskPriority[];
  tags: string[];
  search?: string;
  dueFrom?: string;
  dueTo?: string;
  scheduledFrom?: string;
  scheduledTo?: string;
};

export type TaskWriteInput = {
  title: string;
  description: string | null;
  status: TaskStatus;
  priority: TaskPriority;
  start_at: string | null;
  due_at: string | null;
  tags: string[];
  recurrence?: TaskRecurrenceInput;
};

export type TaskEditableField = Exclude<keyof TaskWriteInput, "recurrence">;
export type TaskUpdateInput = Partial<Omit<TaskWriteInput, "recurrence">>;

export const taskQueryKey = ["tasks"] as const;
export const taskSummaryQueryKey = ["task-summary"] as const;
export const taskSeriesQueryKey = ["task-series"] as const;

function appendValues(params: URLSearchParams, key: string, values: string[]) {
  for (const value of values) {
    params.append(key, value);
  }
}

function buildTaskListPath(
  filters: TaskListFilters,
  cursor?: string,
  order: TaskListOrder = "due",
) {
  const params = new URLSearchParams();
  appendValues(params, "status", filters.statuses);
  appendValues(params, "priority", filters.priorities);
  appendValues(params, "tag", filters.tags);

  if (filters.search) {
    params.set("search", filters.search);
  }

  if (filters.dueFrom) {
    params.set("due_from", filters.dueFrom);
  }

  if (filters.dueTo) {
    params.set("due_to", filters.dueTo);
  }

  if (filters.scheduledFrom) {
    params.set("scheduled_from", filters.scheduledFrom);
  }

  if (filters.scheduledTo) {
    params.set("scheduled_to", filters.scheduledTo);
  }

  params.set("limit", "100");
  params.set("order", order);

  if (cursor) {
    params.set("cursor", cursor);
  }

  return `/api/v1/tasks?${params.toString()}`;
}

export function listTasks(
  filters: TaskListFilters,
  cursor?: string,
  order: TaskListOrder = "due",
) {
  return apiFetch(
    buildTaskListPath(filters, cursor, order),
    {},
    taskListResponseSchema,
  );
}

export function getTaskSummary(timezone: string) {
  const params = new URLSearchParams({ timezone });

  return apiFetch(
    `/api/v1/tasks/summary?${params.toString()}`,
    {},
    taskSummaryResponseSchema,
  );
}

export function createTask(payload: TaskWriteInput) {
  return apiFetch(
    "/api/v1/tasks",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    taskSchema,
  );
}

export function updateTask(taskId: string, payload: TaskUpdateInput) {
  return apiFetch(
    `/api/v1/tasks/${encodeURIComponent(taskId)}`,
    {
      method: "PATCH",
      body: JSON.stringify(payload),
    },
    taskSchema,
  );
}

export function deleteTask(taskId: string) {
  return apiFetch<void>(`/api/v1/tasks/${encodeURIComponent(taskId)}`, {
    method: "DELETE",
  });
}

export function skipTask(taskId: string) {
  return apiFetch(
    `/api/v1/tasks/${encodeURIComponent(taskId)}/skip`,
    { method: "POST" },
    taskSchema,
  );
}

export function listTaskSeries(limit = 100) {
  return apiFetch(
    `/api/v1/task-series?limit=${limit}`,
    {},
    taskSeriesListResponseSchema,
  );
}

export function getTaskSeries(seriesId: string) {
  return apiFetch(
    `/api/v1/task-series/${encodeURIComponent(seriesId)}`,
    {},
    taskSeriesSchema,
  );
}

export type TaskSeriesUpdateInput = {
  title?: string;
  description?: string | null;
  status?: TaskStatus;
  priority?: TaskPriority;
  tags?: string[];
  recurrence?: TaskRecurrenceInput;
};

export function updateTaskSeries(seriesId: string, payload: TaskSeriesUpdateInput) {
  return apiFetch(
    `/api/v1/task-series/${encodeURIComponent(seriesId)}`,
    { method: "PATCH", body: JSON.stringify(payload) },
    taskSeriesSchema,
  );
}

function transitionTaskSeries(seriesId: string, action: "pause" | "resume" | "end") {
  return apiFetch(
    `/api/v1/task-series/${encodeURIComponent(seriesId)}/${action}`,
    { method: "POST" },
    taskSeriesSchema,
  );
}

export function pauseTaskSeries(seriesId: string) {
  return transitionTaskSeries(seriesId, "pause");
}

export function resumeTaskSeries(seriesId: string) {
  return transitionTaskSeries(seriesId, "resume");
}

export function endTaskSeries(seriesId: string) {
  return transitionTaskSeries(seriesId, "end");
}

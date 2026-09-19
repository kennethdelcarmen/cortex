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
});

const taskListResponseSchema = z.object({
  items: z.array(taskSchema),
  next_cursor: z.string().nullable(),
});

export type Task = z.infer<typeof taskSchema>;
export type TaskStatus = z.infer<typeof taskStatusSchema>;
export type TaskPriority = z.infer<typeof taskPrioritySchema>;
export type TaskListOrder = z.infer<typeof taskListOrderSchema>;
export type TaskListPage = z.infer<typeof taskListResponseSchema>;

export type TaskListFilters = {
  statuses: TaskStatus[];
  priorities: TaskPriority[];
  tags: string[];
  dueFrom?: string;
  dueTo?: string;
};

export type TaskWriteInput = {
  title: string;
  description: string | null;
  status: TaskStatus;
  priority: TaskPriority;
  start_at: string | null;
  due_at: string | null;
  tags: string[];
};

export type TaskEditableField = keyof TaskWriteInput;
export type TaskUpdateInput = Partial<TaskWriteInput>;

export const taskQueryKey = ["tasks"] as const;

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

  if (filters.dueFrom) {
    params.set("due_from", filters.dueFrom);
  }

  if (filters.dueTo) {
    params.set("due_to", filters.dueTo);
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

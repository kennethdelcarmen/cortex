"use client";

import {
  useInfiniteQuery,
  useMutation,
  useQueryClient,
} from "@tanstack/react-query";
import { Clock3, Plus } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { BlockingErrorDialog, useFeedback } from "@/components/feedback";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api/client";
import {
  createTask,
  deleteTask,
  listTasks,
  taskQueryKey,
  updateTask,
  type Task,
  type TaskListFilters,
  type TaskPriority,
  type TaskStatus,
  type TaskUpdateInput,
} from "../api";
import { statusLabel, TASK_STATUSES } from "../utils";
import {
  formValuesToPayload,
  TaskFormSheet,
  type TaskFormValues,
} from "./task-form-sheet";
import { TaskList, type TaskListTab } from "./task-list";
import {
  WorkspaceRouteGuard,
  WorkspaceShell,
} from "@/features/workspace/components/workspace-shell";
import { useCurrentUser } from "@/features/auth/hooks";

const taskListFilters: TaskListFilters = {
  statuses: [],
  priorities: [],
  tags: [],
};

const statusOrder = new Map<TaskStatus, number>(
  TASK_STATUSES.map((status, index) => [status.value, index]),
);

function compareDueDates(left: Task, right: Task) {
  if (left.due_at === null && right.due_at !== null) {
    return 1;
  }
  if (left.due_at !== null && right.due_at === null) {
    return -1;
  }
  if (left.due_at !== right.due_at) {
    return (left.due_at ?? "").localeCompare(right.due_at ?? "");
  }

  return left.created_at.localeCompare(right.created_at) || left.id.localeCompare(right.id);
}

function orderTasks(tasks: Task[], includeStatusGroups: boolean) {
  return [...tasks].sort((left, right) => {
    if (includeStatusGroups) {
      const statusDifference =
        (statusOrder.get(left.status) ?? 0) - (statusOrder.get(right.status) ?? 0);
      if (statusDifference !== 0) {
        return statusDifference;
      }
    }

    return compareDueDates(left, right);
  });
}

function describeTaskError(error: unknown) {
  if (!(error instanceof ApiError)) {
    return "The task request could not be completed. Try again.";
  }

  switch (error.code) {
    case "network_error":
      return "Cortex could not be reached. Check that the backend is running and try again.";
    case "invalid_task_dates":
      return "The start time must be before or equal to the due time.";
    case "invalid_task_timezone":
      return "Task dates need a timezone. Check the date and time fields and try again.";
    case "invalid_task_tag":
      return "Each tag must be non-empty and no longer than 64 characters.";
    case "invalid_task_cursor":
      return "This task page expired. Refresh the list and try again.";
    case "task_not_found":
      return "That task is no longer available. Refresh the list to continue.";
    case "unauthenticated":
      return "Your session has ended. Sign in again to continue.";
    default:
      return "The task request could not be completed. Try again.";
  }
}

function isSessionError(error: unknown) {
  return error instanceof ApiError && error.code === "unauthenticated";
}

function TaskListSkeleton() {
  return (
    <div className="mt-4 overflow-hidden rounded-xl border border-border/80 bg-card" aria-hidden="true">
      <div className="flex gap-3 border-b border-border/70 px-3 py-3 sm:px-4">
        {Array.from({ length: 4 }).map((_, index) => (
          <Skeleton key={index} className="h-8 w-24" />
        ))}
      </div>
      <div className="divide-y divide-border/70">
        {["w-3/5", "w-4/5", "w-2/5"].map((width) => (
          <div key={width} className="grid gap-4 p-4 sm:grid-cols-[minmax(0,1fr)_7rem_7rem_2rem]">
            <div>
              <Skeleton className={`h-4 ${width}`} />
              <Skeleton className="mt-3 h-3 w-40" />
            </div>
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-8 w-full" />
            <Skeleton className="size-7" />
          </div>
        ))}
      </div>
    </div>
  );
}

function DeleteTaskDialog({
  task,
  open,
  isDeleting,
  onOpenChange,
  onConfirm,
}: {
  task: Task | null;
  open: boolean;
  isDeleting: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: () => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        showCloseButton={false}
        className="w-[min(28rem,calc(100vw-2rem))] rounded-xl border-border bg-card p-6 text-card-foreground shadow-[0_24px_80px_-35px_color-mix(in_oklab,var(--foreground)_65%,transparent)] sm:max-w-none sm:p-7"
      >
        <DialogHeader>
          <DialogTitle className="text-xl font-semibold tracking-[-0.025em]">
            Delete this task?
          </DialogTitle>
          <DialogDescription className="mt-3 text-sm leading-6 text-muted-foreground">
            “{task?.title}” will be removed from your task views. This is a soft delete and cannot be undone from this page.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter className="mt-7 flex-row justify-end gap-2 border-0 bg-transparent p-0">
          <DialogClose
            type="button"
            render={<Button variant="outline" size="lg" disabled={isDeleting} />}
          >
            Keep task
          </DialogClose>
          <Button
            type="button"
            variant="destructive"
            size="lg"
            onClick={onConfirm}
            disabled={isDeleting}
          >
            {isDeleting ? "Deleting…" : "Delete task"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function TasksPage({ email }: { email: string }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const feedback = useFeedback();
  const [selectedTab, setSelectedTab] = useState<TaskListTab>("all");
  const [sheetOpen, setSheetOpen] = useState(false);
  const [editingTask, setEditingTask] = useState<Task | null>(null);
  const [pendingDelete, setPendingDelete] = useState<Task | null>(null);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [sessionError, setSessionError] = useState<string>();
  const [optimisticTasks, setOptimisticTasks] = useState<Task[] | null>(null);

  const query = useInfiniteQuery({
    queryKey: [...taskQueryKey, taskListFilters],
    queryFn: ({ pageParam }: { pageParam: string | undefined }) =>
      listTasks(taskListFilters, pageParam, "due"),
    initialPageParam: "",
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });

  const tasks = useMemo(
    () => query.data?.pages.flatMap((page) => page.items) ?? [],
    [query.data],
  );
  const visibleTasks = optimisticTasks ?? tasks;
  const now = new Date();
  const tabCounts = useMemo<Record<TaskListTab, number>>(() => {
    const counts: Record<TaskListTab, number> = {
      all: visibleTasks.length,
      backlog: 0,
      todo: 0,
      in_progress: 0,
      done: 0,
      canceled: 0,
    };

    for (const task of visibleTasks) {
      counts[task.status] += 1;
    }

    return counts;
  }, [visibleTasks]);
  const tabTasks = useMemo(() => {
    const filtered = selectedTab === "all"
      ? visibleTasks
      : visibleTasks.filter((task) => task.status === selectedTab);
    return orderTasks(filtered, selectedTab === "all");
  }, [selectedTab, visibleTasks]);

  const saveMutation = useMutation({
    mutationFn: ({
      task,
      payload,
    }: {
      task: Task | null;
      payload: ReturnType<typeof formValuesToPayload>;
    }) => (task ? updateTask(task.id, payload) : createTask(payload)),
    onSuccess: (_savedTask, variables) => {
      setOptimisticTasks(null);
      void queryClient.invalidateQueries({ queryKey: taskQueryKey });
      setSheetOpen(false);
      setEditingTask(null);
      feedback.success({
        title: variables.task ? "Task updated." : "Task added to the list.",
      });
    },
    onError: (error, variables) => {
      if (isSessionError(error)) {
        setSessionError(describeTaskError(error));
        return;
      }

      feedback.error({
        title: variables.task ? "Task could not be updated." : "Task could not be added.",
        description: describeTaskError(error),
      });
    },
  });

  const inlineUpdateMutation = useMutation({
    mutationFn: ({
      taskId,
      payload,
    }: {
      taskId: string;
      field: "status" | "priority";
      payload: TaskUpdateInput;
    }) => updateTask(taskId, payload),
    onMutate: async (variables) => {
      await queryClient.cancelQueries({ queryKey: taskQueryKey });
      const previousTasks = optimisticTasks ?? tasks;
      setOptimisticTasks(
        previousTasks.map((task) =>
          task.id === variables.taskId ? { ...task, ...variables.payload } : task,
        ),
      );
      return { previousTasks };
    },
    onSuccess: (_savedTask, variables) => {
      setOptimisticTasks(null);
      void queryClient.invalidateQueries({ queryKey: taskQueryKey });
      feedback.success({
        title: variables.field === "status" ? "Status updated." : "Priority updated.",
      });
    },
    onError: (error, _variables, context) => {
      setOptimisticTasks(context?.previousTasks ?? null);
      void queryClient.invalidateQueries({ queryKey: taskQueryKey });
      if (isSessionError(error)) {
        setSessionError(describeTaskError(error));
        return;
      }

      feedback.error({
        title: "Task could not be updated.",
        description: describeTaskError(error),
      });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (taskId: string) => deleteTask(taskId),
    onSuccess: () => {
      setOptimisticTasks(null);
      void queryClient.invalidateQueries({ queryKey: taskQueryKey });
      setDeleteOpen(false);
      setPendingDelete(null);
      setSheetOpen(false);
      setEditingTask(null);
      feedback.success({ title: "Task deleted." });
    },
    onError: (error) => {
      if (isSessionError(error)) {
        setSessionError(describeTaskError(error));
        return;
      }

      feedback.error({
        title: "Task could not be deleted.",
        description: describeTaskError(error),
      });
    },
  });

  function openCreate() {
    saveMutation.reset();
    setEditingTask(null);
    setSheetOpen(true);
  }

  function openEdit(task: Task) {
    saveMutation.reset();
    setEditingTask(task);
    setSheetOpen(true);
  }

  function closeSheet(open: boolean) {
    setSheetOpen(open);
    if (!open) {
      saveMutation.reset();
      setEditingTask(null);
    }
  }

  function handleSave(values: TaskFormValues) {
    saveMutation.mutate({ task: editingTask, payload: formValuesToPayload(values) });
  }

  function handleStatusChange(task: Task, status: TaskStatus) {
    if (status === task.status) {
      return;
    }

    inlineUpdateMutation.mutate({
      taskId: task.id,
      field: "status",
      payload: { status },
    });
  }

  function handlePriorityChange(task: Task, priority: TaskPriority) {
    if (priority === task.priority) {
      return;
    }

    inlineUpdateMutation.mutate({
      taskId: task.id,
      field: "priority",
      payload: { priority },
    });
  }

  function requestDelete(task: Task) {
    setSheetOpen(false);
    setPendingDelete(task);
    setDeleteOpen(true);
  }

  function closeDelete(open: boolean) {
    setDeleteOpen(open);
    if (!open) {
      deleteMutation.reset();
      setPendingDelete(null);
    }
  }

  const nextPageError = query.isFetchNextPageError ? query.error : null;
  const nextPageFetch = query.fetchNextPage;

  useEffect(() => {
    if (!nextPageError || isSessionError(nextPageError)) {
      return;
    }

    feedback.error({
      title: "More tasks could not load.",
      description: describeTaskError(nextPageError),
      action: {
        label: "Try again",
        onClick: () => void nextPageFetch(),
      },
    });
  }, [feedback, nextPageError, nextPageFetch]);

  const hasInitialTaskSessionError = Boolean(
    query.isError && !query.data && isSessionError(query.error),
  );
  const hasBlockingTaskSessionError = Boolean(
    sessionError || hasInitialTaskSessionError || (nextPageError && isSessionError(nextPageError)),
  );
  const selectedTabLabel = selectedTab === "all" ? "All" : statusLabel(selectedTab);

  return (
    <WorkspaceShell email={email}>
      <section aria-labelledby="task-list-title" className="mt-0">
        <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="font-mono text-[0.66rem] uppercase tracking-[0.18em] text-muted-foreground">
              Workflow
            </p>
            <h2 id="task-list-title" className="mt-2 text-xl font-medium tracking-[-0.025em] sm:text-2xl">
              {selectedTabLabel} tasks
            </h2>
          </div>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 font-mono text-[0.65rem] uppercase tracking-[0.12em] text-muted-foreground">
            <span>{query.isPending ? "Loading" : `${tabCounts.all} in view`}</span>
            <span>{tabCounts.in_progress} in motion</span>
          </div>
        </div>

        {query.isPending ? (
          <TaskListSkeleton />
        ) : query.isError && !query.data ? (
          <div className="mt-4 min-h-64 rounded-xl border border-border/70 bg-card/40" aria-hidden="true" />
        ) : visibleTasks.length === 0 ? (
          <Card className="relative mt-4 overflow-hidden rounded-xl border-border/80 p-6 shadow-[0_20px_60px_-44px_color-mix(in_oklab,var(--foreground)_45%,transparent)] sm:p-8">
            <span className="absolute inset-y-0 left-0 w-1 bg-primary/75" aria-hidden="true" />
            <div className="flex items-center gap-2 text-primary">
              <Clock3 aria-hidden="true" className="size-4" />
              <p className="font-mono text-[0.66rem] font-medium uppercase tracking-[0.16em]">
                {visibleTasks.length === 0 ? "Ready for a first task" : `No ${selectedTabLabel.toLowerCase()} tasks`}
              </p>
            </div>
            <h3 className="mt-4 max-w-lg text-xl font-medium tracking-[-0.025em] sm:text-2xl">
              {visibleTasks.length === 0 ? "Start with one clear next action." : `Nothing is ${selectedTabLabel.toLowerCase()} right now.`}
            </h3>
            <p className="mt-3 max-w-xl text-sm leading-6 text-muted-foreground sm:text-base">
              {visibleTasks.length === 0
                ? "Capture a specific task and keep it close enough to move forward."
                : "Choose another status tab or add a new task to this list."}
            </p>
            <div className="mt-6 flex flex-wrap gap-2">
              {visibleTasks.length > 0 && selectedTab !== "all" ? (
                <Button type="button" variant="outline" onClick={() => setSelectedTab("all")}>
                  View all tasks
                </Button>
              ) : null}
              <Button type="button" onClick={openCreate}>
                <Plus aria-hidden="true" />
                Add task
              </Button>
            </div>
          </Card>
        ) : (
          <div className="space-y-5">
            <TaskList
              tasks={tabTasks}
              counts={tabCounts}
              selectedTab={selectedTab}
              now={now}
              isUpdatingTaskId={
                inlineUpdateMutation.isPending
                  ? inlineUpdateMutation.variables?.taskId
                  : undefined
              }
              onTabChange={setSelectedTab}
              onStatusChange={handleStatusChange}
              onPriorityChange={handlePriorityChange}
              onEdit={openEdit}
              onAddTask={openCreate}
            />
            {query.hasNextPage ? (
              <div className="flex justify-center">
                <Button
                  type="button"
                  variant="outline"
                  size="lg"
                  onClick={() => void query.fetchNextPage()}
                  disabled={query.isFetchingNextPage}
                >
                  {query.isFetchingNextPage ? "Loading more…" : "Load more tasks"}
                </Button>
              </div>
            ) : null}
          </div>
        )}
      </section>

      <TaskFormSheet
        key={`${sheetOpen ? "open" : "closed"}-${editingTask?.id ?? "new"}`}
        open={sheetOpen}
        task={editingTask}
        isSaving={saveMutation.isPending}
        onOpenChange={closeSheet}
        onSubmit={handleSave}
        onDeleteRequest={editingTask ? () => requestDelete(editingTask) : undefined}
      />
      <DeleteTaskDialog
        task={pendingDelete}
        open={deleteOpen}
        isDeleting={deleteMutation.isPending}
        onOpenChange={closeDelete}
        onConfirm={() => {
          if (pendingDelete) {
            deleteMutation.mutate(pendingDelete.id);
          }
        }}
      />
      <BlockingErrorDialog
        open={hasBlockingTaskSessionError || Boolean(query.isError && !query.data)}
        title={hasBlockingTaskSessionError ? "Your session has ended." : "Tasks could not load."}
        description={
          sessionError ??
          (nextPageError
            ? describeTaskError(nextPageError)
            : query.error
              ? describeTaskError(query.error)
              : "The task list could not be loaded.")
        }
        action={
          hasBlockingTaskSessionError
            ? {
                label: "Sign in again",
                onClick: () => router.replace("/login"),
              }
            : {
                label: "Try again",
                onClick: () => void query.refetch(),
                pending: query.isFetching,
                pendingLabel: "Loading…",
              }
        }
      />
    </WorkspaceShell>
  );
}

export function TasksRoute() {
  const currentUser = useCurrentUser();

  return (
    <WorkspaceRouteGuard>
      {currentUser.data ? <TasksPage email={currentUser.data.email} /> : null}
    </WorkspaceRouteGuard>
  );
}

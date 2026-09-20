"use client";

import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
  type InfiniteData,
} from "@tanstack/react-query";
import { CalendarDays, Clock3, ListTodo, Plus } from "lucide-react";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
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
import { cn } from "@/lib/utils";
import { useActivityLogger } from "@/features/activity/hooks";
import {
  createTask,
  deleteTask,
  endTaskSeries,
  getTaskSeries,
  getTaskSummary,
  listTasks,
  pauseTaskSeries,
  resumeTaskSeries,
  skipTask,
  taskQueryKey,
  taskSeriesQueryKey,
  taskSummaryQueryKey,
  updateTask,
  updateTaskSeries,
  type Task,
  type TaskEditableField,
  type TaskListPage,
  type TaskPriority,
  type TaskSeriesUpdateInput,
  type TaskStatus,
  type TaskUpdateInput,
} from "../api";
import { statusLabel, TASK_STATUSES, toLocalDateTimeParts, type TaskDateTimeValue } from "../utils";
import {
  parseTaskUrlState,
  clearTaskListUrlState,
  taskListFiltersForState,
  taskSummaryTimezone,
  taskViewLabel,
  type TaskLayout,
  type TaskUrlState,
  type TaskView,
} from "../task-filters";
import {
  formValuesToPayload,
  TaskCreateDialog,
  type TaskFormValues,
} from "./task-create-dialog";
import { TaskDetailsDrawer } from "./task-details-drawer";
import { TaskSeriesDialog } from "./task-series-dialog";
import { TaskFilterToolbar } from "./task-filter-toolbar";
import {
  initialTaskCalendarRange,
  TaskCalendar,
  type TaskCalendarCreateSelection,
  type TaskCalendarRange,
} from "./task-calendar";
import { TaskList, type TaskListTab } from "./task-list";
import { TaskViewNavigation } from "./task-view-navigation";
import {
  WorkspaceRouteGuard,
  WorkspaceShell,
} from "@/features/workspace/components/workspace-shell";
import { useCurrentUser } from "@/features/auth/hooks";

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
    case "invalid_task_recurrence":
      return "Choose a valid repeat pattern and end condition.";
    case "invalid_task_recurrence_timezone":
      return "That time zone is not available. Choose a valid IANA time zone, such as Asia/Manila.";
    case "recurrence_anchor_required":
      return "Set a start or due time to choose the first occurrence.";
    case "invalid_task_series_state":
      return "This recurring series changed before the action completed. Refresh and try again.";
    case "task_occurrence_required":
      return "Only a recurring task occurrence can be skipped.";
    case "task_series_not_found":
      return "That recurring series is no longer available. Refresh the task and try again.";
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

function TaskLayoutToggle({
  layout,
  onChange,
}: {
  layout: TaskLayout;
  onChange: (layout: TaskLayout) => void;
}) {
  const options: Array<{
    value: TaskLayout;
    label: string;
    icon: typeof ListTodo;
  }> = [
    { value: "list", label: "List", icon: ListTodo },
    { value: "calendar", label: "Calendar", icon: CalendarDays },
  ];

  return (
    <div
      aria-label="Task layout"
      className="inline-flex rounded-lg border border-border/80 bg-card/60 p-1"
      role="group"
    >
      {options.map(({ value, label, icon: Icon }) => {
        const selected = layout === value;

        return (
          <Button
            key={value}
            type="button"
            variant={selected ? "secondary" : "ghost"}
            size="sm"
            aria-pressed={selected}
            onClick={() => onChange(value)}
            className={cn(
              "h-8 gap-1.5 px-2.5 text-xs",
              selected ? "text-foreground" : "text-muted-foreground",
            )}
          >
            <Icon aria-hidden="true" className="size-3.5" />
            {label}
          </Button>
        );
      })}
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
        className="w-[min(28rem,calc(100vw-2rem))] rounded-xl border-border bg-card p-6 text-card-foreground shadow-none sm:max-w-none sm:p-7"
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

function SeriesActionDialog({
  action,
  open,
  isPending,
  onOpenChange,
  onConfirm,
}: {
  action: "end" | "skip" | null;
  open: boolean;
  isPending: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: () => void;
}) {
  const isEnd = action === "end";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        showCloseButton={false}
        className="w-[min(30rem,calc(100vw-2rem))] rounded-xl border-border bg-card p-6 text-card-foreground shadow-none sm:max-w-none sm:p-7"
      >
        <DialogHeader>
          <DialogTitle className="text-xl font-semibold tracking-[-0.025em]">
            {isEnd ? "End this recurring series?" : "Skip this occurrence?"}
          </DialogTitle>
          <DialogDescription className="mt-3 text-sm leading-6 text-muted-foreground">
            {isEnd
              ? "Existing occurrences will stay in your task views. Cortex will stop generating future occurrences until you restart the series."
              : "Only this occurrence will be canceled. The rest of the recurring series will continue as scheduled."}
          </DialogDescription>
        </DialogHeader>
        <DialogFooter className="mt-7 flex-row justify-end gap-2 border-0 bg-transparent p-0">
          <DialogClose type="button" render={<Button variant="outline" size="lg" disabled={isPending} />}>Keep it</DialogClose>
          <Button type="button" variant={isEnd ? "destructive" : "default"} size="lg" onClick={onConfirm} disabled={isPending}>
            {isPending ? "Working…" : isEnd ? "End series" : "Skip occurrence"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function TasksPage({ email }: { email: string }) {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  const feedback = useFeedback();
  const logActivity = useActivityLogger();
  const [selectedTab, setSelectedTab] = useState<TaskListTab>("all");
  const [currentTime, setCurrentTime] = useState(() => new Date());
  const [timezone] = useState(() => taskSummaryTimezone());
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [createDialogStartAt, setCreateDialogStartAt] = useState<TaskDateTimeValue>();
  const [detailsTaskId, setDetailsTaskId] = useState<string | null>(null);
  const [detailsDrawerOpen, setDetailsDrawerOpen] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<Task | null>(null);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [sessionError, setSessionError] = useState<string>();
  const [calendarRange, setCalendarRange] = useState<TaskCalendarRange>(() =>
    initialTaskCalendarRange(),
  );

  const searchParamsValue = searchParams.toString();
  const urlState = useMemo<TaskUrlState>(
    () => parseTaskUrlState(new URLSearchParams(searchParamsValue)),
    [searchParamsValue],
  );
  const taskListFilters = useMemo(
    () => taskListFiltersForState(urlState, currentTime),
    [currentTime, urlState],
  );
  const taskListQueryKey = useMemo(
    () => [...taskQueryKey, "list", taskListFilters] as const,
    [taskListFilters],
  );
  const calendarTaskFilters = useMemo(
    () => ({
      statuses: [],
      priorities: [],
      tags: [],
      scheduledFrom: calendarRange.start.toISOString(),
      scheduledTo: calendarRange.end.toISOString(),
    }),
    [calendarRange],
  );
  const calendarTaskQueryKey = useMemo(
    () => [...taskQueryKey, "calendar", calendarTaskFilters] as const,
    [calendarTaskFilters],
  );

  useEffect(() => {
    const timer = window.setInterval(() => setCurrentTime(new Date()), 60_000);
    return () => window.clearInterval(timer);
  }, []);

  const summaryQuery = useQuery({
    queryKey: [...taskSummaryQueryKey, timezone],
    queryFn: () => getTaskSummary(timezone),
    enabled: Boolean(timezone),
  });

  const query = useInfiniteQuery({
    queryKey: taskListQueryKey,
    queryFn: ({ pageParam }: { pageParam: string | undefined }) =>
      listTasks(taskListFilters, pageParam, "due"),
    initialPageParam: "",
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    enabled: urlState.layout === "list",
  });

  const calendarQuery = useInfiniteQuery({
    queryKey: calendarTaskQueryKey,
    queryFn: ({ pageParam }: { pageParam: string | undefined }) =>
      listTasks(calendarTaskFilters, pageParam, "due"),
    initialPageParam: "",
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    enabled: urlState.layout === "calendar",
  });

  const updateTaskUrl = useCallback(
    (update: (params: URLSearchParams) => void, replace = false) => {
      const params = new URLSearchParams(searchParamsValue);
      update(params);
      const queryString = params.toString();
      const nextUrl = queryString ? `${pathname}?${queryString}` : pathname;

      if (replace) {
        router.replace(nextUrl, { scroll: false });
      } else {
        router.push(nextUrl, { scroll: false });
      }
    },
    [pathname, router, searchParamsValue],
  );

  const handleViewChange = useCallback(
    (view: TaskView) => {
      setSelectedTab("all");
      updateTaskUrl((params) => {
        params.delete("layout");
        if (view === "all") {
          params.delete("view");
        } else {
          params.set("view", view);
        }

        if (view !== "custom") {
          params.delete("from");
          params.delete("to");
        }
      });
    },
    [updateTaskUrl],
  );

  const handleLayoutChange = useCallback(
    (layout: TaskLayout) => {
      setSelectedTab("all");
      updateTaskUrl((params) => {
        if (layout === "list") {
          params.delete("layout");
        } else {
          params.set("layout", layout);
          clearTaskListUrlState(params);
        }
      });
    },
    [updateTaskUrl],
  );

  const handleCalendarRangeChange = useCallback((range: TaskCalendarRange) => {
    setCalendarRange((current) => {
      if (
        current.start.getTime() === range.start.getTime() &&
        current.end.getTime() === range.end.getTime()
      ) {
        return current;
      }

      return range;
    });
  }, []);

  const handleSearchChange = useCallback(
    (value: string) => {
      updateTaskUrl((params) => {
        if (value) {
          params.set("q", value);
        } else {
          params.delete("q");
        }
      }, true);
    },
    [updateTaskUrl],
  );

  const handleTagToggle = useCallback(
    (tag: string) => {
      updateTaskUrl((params) => {
        const selectedTag = params.get("tag")?.trim().toLowerCase();
        params.delete("tag");

        if (selectedTag !== tag) {
          params.set("tag", tag);
        }
      });
    },
    [updateTaskUrl],
  );

  const handleTagsClear = useCallback(() => {
    updateTaskUrl((params) => params.delete("tag"));
  }, [updateTaskUrl]);

  const handleCustomRangeApply = useCallback(
    (from: string, to: string) => {
      setSelectedTab("all");
      updateTaskUrl((params) => {
        params.set("view", "custom");
        params.set("from", from);
        params.set("to", to);
      });
    },
    [updateTaskUrl],
  );

  const handleCustomRangeClear = useCallback(() => {
    setSelectedTab("all");
    updateTaskUrl((params) => {
      params.delete("view");
      params.delete("from");
      params.delete("to");
    });
  }, [updateTaskUrl]);

  const handleClearFilters = useCallback(() => {
    updateTaskUrl(clearTaskListUrlState);
  }, [updateTaskUrl]);

  const tasks = useMemo(
    () => query.data?.pages.flatMap((page) => page.items) ?? [],
    [query.data],
  );
  const calendarTasks = useMemo(
    () => calendarQuery.data?.pages.flatMap((page) => page.items) ?? [],
    [calendarQuery.data],
  );
  const visibleTasks = urlState.layout === "calendar" ? calendarTasks : tasks;
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

  const selectedTask = detailsTaskId
    ? [...visibleTasks, ...tasks, ...calendarTasks].find((task) => task.id === detailsTaskId) ?? null
    : null;
  const [seriesEditOpen, setSeriesEditOpen] = useState(false);
  const [seriesAction, setSeriesAction] = useState<"end" | "skip" | null>(null);

  const seriesQuery = useQuery({
    queryKey: [...taskSeriesQueryKey, selectedTask?.series_id ?? "none"],
    queryFn: () => getTaskSeries(selectedTask?.series_id ?? ""),
    enabled: Boolean(selectedTask?.series_id && detailsDrawerOpen),
  });

  function getCachedTask(taskId: string) {
    for (const [, cachedData] of queryClient.getQueriesData<InfiniteData<TaskListPage>>({
      queryKey: taskQueryKey,
    })) {
      const task = cachedData?.pages.flatMap((page) => page.items).find((item) => item.id === taskId);
      if (task) {
        return task;
      }
    }

    return undefined;
  }

  function updateTaskInCache(taskId: string, updater: (task: Task) => Task) {
    queryClient.setQueriesData<InfiniteData<TaskListPage>>({ queryKey: taskQueryKey }, (current) => {
      if (!current) {
        return current;
      }

      return {
        ...current,
        pages: current.pages.map((page) => ({
          ...page,
          items: page.items.map((task) => (task.id === taskId ? updater(task) : task)),
        })),
      };
    });
  }

  const createMutation = useMutation({
    mutationFn: createTask,
    onSuccess: (task) => {
      void logActivity({
        event_type: "task.created",
        entity_type: "task",
        entity_id: task.id,
        metadata: { title: task.title },
      });
      void queryClient.invalidateQueries({ queryKey: taskQueryKey });
      void queryClient.invalidateQueries({ queryKey: taskSummaryQueryKey });
      setCreateDialogOpen(false);
      feedback.success({ title: "Task added to the list." });
    },
    onError: (error) => {
      if (isSessionError(error)) {
        setSessionError(describeTaskError(error));
        return;
      }

      feedback.error({
        title: "Task could not be added.",
        description: describeTaskError(error),
      });
    },
  });

  const taskUpdateMutation = useMutation({
    mutationFn: ({ taskId, payload }: {
      taskId: string;
      field: TaskEditableField;
      payload: TaskUpdateInput;
      notify?: boolean;
    }) => updateTask(taskId, payload),
    onMutate: async (variables) => {
      await queryClient.cancelQueries({ queryKey: taskQueryKey });
      const previousTask = getCachedTask(variables.taskId);
      const previousValue = previousTask?.[variables.field];
      const optimisticValue = variables.payload[variables.field];

      updateTaskInCache(variables.taskId, (task) => ({ ...task, ...variables.payload }));

      return { previousValue, optimisticValue };
    },
    onSuccess: (savedTask, variables) => {
      const metadata: Record<string, unknown> = {
        title: savedTask.title,
        changed_fields: [variables.field],
      };

      if (variables.field === "status") {
        metadata.status = savedTask.status;
      }

      if (variables.field === "priority") {
        metadata.priority = savedTask.priority;
      }

      void logActivity({
        event_type: "task.updated",
        entity_type: "task",
        entity_id: savedTask.id,
        metadata,
      });
      void queryClient.invalidateQueries({ queryKey: taskQueryKey });
      void queryClient.invalidateQueries({ queryKey: taskSummaryQueryKey });

      if (variables.notify !== false) {
        feedback.success({
          title: variables.field === "status" ? "Status updated." : "Priority updated.",
        });
      }
    },
    onError: (error, variables, context) => {
      if (context) {
        updateTaskInCache(variables.taskId, (task) => {
          if (task[variables.field] !== context.optimisticValue) {
            return task;
          }

          return { ...task, [variables.field]: context.previousValue };
        });
      }

      void queryClient.invalidateQueries({ queryKey: taskQueryKey });
      if (isSessionError(error)) {
        setSessionError(describeTaskError(error));
        return;
      }

      if (variables.notify !== false) {
        feedback.error({
          title: "Task could not be updated.",
          description: describeTaskError(error),
        });
      }
    },
  });

  const seriesUpdateMutation = useMutation({
    mutationFn: ({ seriesId, payload }: { seriesId: string; payload: TaskSeriesUpdateInput }) =>
      updateTaskSeries(seriesId, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: taskQueryKey });
      void queryClient.invalidateQueries({ queryKey: taskSummaryQueryKey });
      void queryClient.invalidateQueries({ queryKey: taskSeriesQueryKey });
      setSeriesEditOpen(false);
      feedback.success({ title: "Recurring task updated." });
    },
    onError: (error) => {
      if (isSessionError(error)) {
        setSessionError(describeTaskError(error));
        return;
      }

      feedback.error({
        title: "Recurring task could not be updated.",
        description: describeTaskError(error),
      });
    },
  });

  const seriesTransitionMutation = useMutation({
    mutationFn: ({ seriesId, action }: { seriesId: string; action: "pause" | "resume" | "end" }) => {
      if (action === "pause") {
        return pauseTaskSeries(seriesId);
      }
      if (action === "resume") {
        return resumeTaskSeries(seriesId);
      }
      return endTaskSeries(seriesId);
    },
    onSuccess: (series) => {
      void queryClient.invalidateQueries({ queryKey: taskQueryKey });
      void queryClient.invalidateQueries({ queryKey: taskSummaryQueryKey });
      void queryClient.invalidateQueries({ queryKey: taskSeriesQueryKey });
      setSeriesAction(null);
      feedback.success({ title: `Series ${series.state === "active" ? "resumed" : series.state === "paused" ? "paused" : "ended"}.` });
    },
    onError: (error) => {
      if (isSessionError(error)) {
        setSessionError(describeTaskError(error));
        return;
      }

      feedback.error({
        title: "Series action could not be completed.",
        description: describeTaskError(error),
      });
    },
  });

  const skipMutation = useMutation({
    mutationFn: (taskId: string) => skipTask(taskId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: taskQueryKey });
      void queryClient.invalidateQueries({ queryKey: taskSummaryQueryKey });
      void queryClient.invalidateQueries({ queryKey: taskSeriesQueryKey });
      setSeriesAction(null);
      feedback.success({ title: "Occurrence skipped." });
    },
    onError: (error) => {
      if (isSessionError(error)) {
        setSessionError(describeTaskError(error));
        return;
      }

      feedback.error({
        title: "Occurrence could not be skipped.",
        description: describeTaskError(error),
      });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: ({ taskId }: { taskId: string; title: string }) => deleteTask(taskId),
    onSuccess: (_response, variables) => {
      void logActivity({
        event_type: "task.deleted",
        entity_type: "task",
        entity_id: variables.taskId,
        metadata: { title: variables.title },
      });
      void queryClient.invalidateQueries({ queryKey: taskQueryKey });
      void queryClient.invalidateQueries({ queryKey: taskSummaryQueryKey });
      setDeleteOpen(false);
      setPendingDelete(null);
      setDetailsDrawerOpen(false);
      setDetailsTaskId(null);
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

  function openCreate(initialStartAt?: TaskDateTimeValue) {
    createMutation.reset();
    setCreateDialogStartAt(initialStartAt);
    setCreateDialogOpen(true);
  }

  function openCreateFromCalendar({ date, allDay }: TaskCalendarCreateSelection) {
    const localValue = toLocalDateTimeParts(date.toISOString());
    openCreate({
      date: localValue.date,
      time: allDay ? "" : localValue.time,
    });
  }

  function openDetails(task: Task) {
    setDetailsTaskId(task.id);
    setDetailsDrawerOpen(true);
  }

  function closeCreateDialog(open: boolean) {
    setCreateDialogOpen(open);
    if (!open) {
      setCreateDialogStartAt(undefined);
      createMutation.reset();
    }
  }

  function closeDetailsDrawer(open: boolean) {
    setDetailsDrawerOpen(open);
    if (!open) {
      setDetailsTaskId(null);
    }
  }

  function openSeriesEdit() {
    if (!seriesQuery.data || seriesQuery.data.state === "ended") {
      return;
    }

    seriesUpdateMutation.reset();
    setSeriesEditOpen(true);
  }

  function closeSeriesEdit(open: boolean) {
    setSeriesEditOpen(open);
    if (!open) {
      seriesUpdateMutation.reset();
    }
  }

  function handleSeriesUpdate(payload: TaskSeriesUpdateInput) {
    if (!selectedTask?.series_id) {
      return;
    }

    seriesUpdateMutation.mutate({ seriesId: selectedTask.series_id, payload });
  }

  function handleSeriesTransition(action: "pause" | "resume" | "end") {
    if (!selectedTask?.series_id) {
      return;
    }

    seriesTransitionMutation.mutate({ seriesId: selectedTask.series_id, action });
  }

  function requestEndSeries() {
    setSeriesAction("end");
  }

  function requestSkipOccurrence() {
    setSeriesAction("skip");
  }

  function closeSeriesAction(open: boolean) {
    setSeriesAction(open ? seriesAction : null);
    if (!open) {
      seriesTransitionMutation.reset();
      skipMutation.reset();
    }
  }

  function confirmSeriesAction() {
    if (!selectedTask) {
      return;
    }

    if (seriesAction === "skip") {
      skipMutation.mutate(selectedTask.id);
    } else if (seriesAction === "end" && selectedTask.series_id) {
      seriesTransitionMutation.mutate({ seriesId: selectedTask.series_id, action: "end" });
    }
  }

  function handleCreate(values: TaskFormValues) {
    createMutation.mutate(formValuesToPayload(values));
  }

  async function saveTaskField(field: TaskEditableField, payload: TaskUpdateInput): Promise<void> {
    if (!detailsTaskId) {
      throw new Error("No task is selected.");
    }

    await taskUpdateMutation.mutateAsync({
      taskId: detailsTaskId,
      field,
      payload,
      notify: false,
    });
  }

  function handleStatusChange(task: Task, status: TaskStatus) {
    if (status === task.status) {
      return;
    }

    taskUpdateMutation.mutate({
      taskId: task.id,
      field: "status",
      payload: { status },
      notify: true,
    });
  }

  function handlePriorityChange(task: Task, priority: TaskPriority) {
    if (priority === task.priority) {
      return;
    }

    taskUpdateMutation.mutate({
      taskId: task.id,
      field: "priority",
      payload: { priority },
      notify: true,
    });
  }

  function requestDelete(task: Task) {
    setDetailsDrawerOpen(false);
    setDetailsTaskId(null);
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

  const isCalendarLayout = urlState.layout === "calendar";
  const activeQueryError = isCalendarLayout ? calendarQuery.error : query.error;
  const activeQueryHasData = isCalendarLayout ? calendarQuery.data : query.data;
  const activeQueryPending = isCalendarLayout ? calendarQuery.isPending : query.isPending;
  const nextPageError = isCalendarLayout
    ? calendarQuery.isFetchNextPageError
      ? calendarQuery.error
      : null
    : query.isFetchNextPageError
      ? query.error
      : null;
  const nextPageFetch = isCalendarLayout ? calendarQuery.fetchNextPage : query.fetchNextPage;

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
    activeQueryError && !activeQueryHasData && isSessionError(activeQueryError),
  );
  const hasBlockingTaskSessionError = Boolean(
    sessionError || hasInitialTaskSessionError || (nextPageError && isSessionError(nextPageError)),
  );
  const selectedTabLabel = selectedTab === "all" ? "All" : statusLabel(selectedTab);
  const selectedViewLabel = taskViewLabel(urlState.view);
  const pageTitle = isCalendarLayout
    ? "Calendar"
    : selectedTab === "all"
      ? selectedViewLabel
      : `${selectedViewLabel} · ${selectedTabLabel}`;
  const hasActiveFilters = Boolean(
    !isCalendarLayout && (
      urlState.search ||
      urlState.tags.length ||
      urlState.view !== "all" ||
      urlState.from ||
      urlState.to
    ),
  );
  return (
    <WorkspaceShell
      email={email}
      sidebarContent={
        <TaskViewNavigation
          state={urlState}
          summary={summaryQuery.data}
          isSummaryPending={summaryQuery.isPending}
          onViewChange={handleViewChange}
          onCalendarChange={() => handleLayoutChange("calendar")}
          onTagToggle={handleTagToggle}
        />
      }
    >
      <section aria-labelledby="task-list-title" className="mt-0">
        <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="font-mono text-[0.66rem] uppercase tracking-[0.18em] text-muted-foreground">
              Workflow
            </p>
            <h2 id="task-list-title" className="mt-2 text-xl font-medium tracking-[-0.025em] sm:text-2xl">
              {pageTitle}
            </h2>
          </div>
          <div className="flex flex-wrap items-center justify-end gap-3">
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 font-mono text-[0.65rem] uppercase tracking-[0.12em] text-muted-foreground">
              <span>{activeQueryPending ? "Loading" : `${tabCounts.all} in view`}</span>
              <span>{tabCounts.in_progress} in motion</span>
            </div>
            <TaskLayoutToggle layout={urlState.layout} onChange={handleLayoutChange} />
          </div>
        </div>

        {!isCalendarLayout ? (
          <TaskFilterToolbar
            state={urlState}
            summary={summaryQuery.data}
            isSummaryPending={summaryQuery.isPending}
            onViewChange={handleViewChange}
            onSearchChange={handleSearchChange}
            onTagToggle={handleTagToggle}
            onTagsClear={handleTagsClear}
            onCustomRangeApply={handleCustomRangeApply}
            onCustomRangeClear={handleCustomRangeClear}
          />
        ) : null}

        {isCalendarLayout ? (
          <TaskCalendar
            tasks={visibleTasks}
            isPending={calendarQuery.isPending}
            isFetching={calendarQuery.isFetching}
            hasNextPage={Boolean(calendarQuery.hasNextPage)}
            isFetchingNextPage={calendarQuery.isFetchingNextPage}
            onFetchNextPage={() => void calendarQuery.fetchNextPage()}
            onRangeChange={handleCalendarRangeChange}
            onOpenTask={openDetails}
            onCreateTask={openCreateFromCalendar}
          />
        ) : query.isPending ? (
          <TaskListSkeleton />
        ) : query.isError && !query.data ? (
          <div className="mt-4 min-h-64 rounded-xl border border-border/70 bg-card/40" aria-hidden="true" />
        ) : visibleTasks.length === 0 ? (
          <Card className="relative mt-4 overflow-hidden rounded-xl border-border/80 p-6 sm:p-8">
            <span className="absolute inset-y-0 left-0 w-1 bg-primary/75" aria-hidden="true" />
            <div className="flex items-center gap-2 text-primary-strong">
              <Clock3 aria-hidden="true" className="size-4" />
              <p className="font-mono text-[0.66rem] font-medium uppercase tracking-[0.16em]">
                {visibleTasks.length === 0
                  ? hasActiveFilters
                    ? "No matching tasks"
                    : "Ready for a first task"
                  : `No ${selectedTabLabel.toLowerCase()} tasks`}
              </p>
            </div>
            <h3 className="mt-4 max-w-lg text-xl font-medium tracking-[-0.025em] sm:text-2xl">
              {visibleTasks.length === 0
                ? hasActiveFilters
                  ? "Try clearing a filter or search for a different task."
                  : "Start with one clear next action."
                : `Nothing is ${selectedTabLabel.toLowerCase()} right now.`}
            </h3>
            <p className="mt-3 max-w-xl text-sm leading-6 text-muted-foreground sm:text-base">
              {visibleTasks.length === 0
                ? hasActiveFilters
                  ? "The current view does not contain any tasks that match these filters."
                  : "Capture a specific task and keep it close enough to move forward."
                : "Choose another status tab or add a new task to this list."}
            </p>
            <div className="mt-6 flex flex-wrap gap-2">
              {hasActiveFilters ? (
                <Button type="button" variant="outline" onClick={handleClearFilters}>
                  Clear filters
                </Button>
              ) : null}
              {visibleTasks.length > 0 && selectedTab !== "all" ? (
                <Button type="button" variant="outline" onClick={() => setSelectedTab("all")}>
                  View all tasks
                </Button>
              ) : null}
              <Button type="button" onClick={() => openCreate()}>
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
              now={currentTime}
              isUpdatingTaskId={
                taskUpdateMutation.isPending
                  ? taskUpdateMutation.variables?.taskId
                  : undefined
              }
              onTabChange={setSelectedTab}
              onStatusChange={handleStatusChange}
              onPriorityChange={handlePriorityChange}
              onOpenDetails={openDetails}
              onAddTask={() => openCreate()}
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

      <TaskCreateDialog
        key={`create-${createDialogOpen ? "open" : "closed"}`}
        open={createDialogOpen}
        isSaving={createMutation.isPending}
        initialStartAt={createDialogStartAt}
        onOpenChange={closeCreateDialog}
        onSubmit={handleCreate}
      />
      <TaskDetailsDrawer
        key={`details-${detailsDrawerOpen ? "open" : "closed"}-${detailsTaskId ?? "none"}`}
        open={detailsDrawerOpen && Boolean(selectedTask)}
        task={selectedTask}
        series={seriesQuery.data ?? null}
        isSeriesPending={Boolean(selectedTask?.series_id) && seriesQuery.isPending}
        isSeriesActionPending={seriesTransitionMutation.isPending || skipMutation.isPending}
        onOpenChange={closeDetailsDrawer}
        onSaveField={saveTaskField}
        onEditSeries={openSeriesEdit}
        onPauseSeries={() => handleSeriesTransition("pause")}
        onResumeSeries={() => handleSeriesTransition("resume")}
        onEndSeries={requestEndSeries}
        onSkipOccurrence={requestSkipOccurrence}
        onDeleteRequest={() => {
          if (selectedTask) {
            requestDelete(selectedTask);
          }
        }}
      />
      <TaskSeriesDialog
        key={`series-${seriesEditOpen ? "open" : "closed"}-${seriesQuery.data?.id ?? "none"}`}
        open={seriesEditOpen}
        series={seriesQuery.data ?? null}
        isSaving={seriesUpdateMutation.isPending}
        onOpenChange={closeSeriesEdit}
        onSubmit={handleSeriesUpdate}
      />
      <SeriesActionDialog
        action={seriesAction}
        open={Boolean(seriesAction)}
        isPending={seriesTransitionMutation.isPending || skipMutation.isPending}
        onOpenChange={closeSeriesAction}
        onConfirm={confirmSeriesAction}
      />
      <DeleteTaskDialog
        task={pendingDelete}
        open={deleteOpen}
        isDeleting={deleteMutation.isPending}
        onOpenChange={closeDelete}
        onConfirm={() => {
          if (pendingDelete) {
            deleteMutation.mutate({
              taskId: pendingDelete.id,
              title: pendingDelete.title,
            });
          }
        }}
      />
      <BlockingErrorDialog
        open={hasBlockingTaskSessionError || Boolean(activeQueryError && !activeQueryHasData)}
        title={hasBlockingTaskSessionError ? "Your session has ended." : "Tasks could not load."}
        description={
          sessionError ??
          (nextPageError
            ? describeTaskError(nextPageError)
            : activeQueryError
              ? describeTaskError(activeQueryError)
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
                onClick: () => void (isCalendarLayout ? calendarQuery.refetch() : query.refetch()),
                pending: isCalendarLayout ? calendarQuery.isFetching : query.isFetching,
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
      {currentUser.data ? (
        <Suspense fallback={<TaskListSkeleton />}>
          <TasksPage email={currentUser.data.email} />
        </Suspense>
      ) : null}
    </WorkspaceRouteGuard>
  );
}

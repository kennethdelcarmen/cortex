"use client";

import { useEffect, useRef, useState } from "react";
import { Pause, Play, Repeat2, SkipForward, Square, X } from "lucide-react";
import { SuggestedTags } from "@/components/suggested-tags";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Drawer, DrawerClose, DrawerContent, DrawerDescription, DrawerFooter, DrawerTitle } from "@/components/ui/drawer";
import { FieldError } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import type {
  Task,
  TaskEditableField,
  TaskPriority,
  TaskSeries,
  TaskStatus,
  TaskUpdateInput,
} from "../api";
import {
  recurrenceSummary,
  recurrenceValuesFromPayload,
  recurrenceStateLabel,
} from "../recurrence";
import {
  adjustDueDateForStart,
  appendTagInput,
  localDateTimePartsToIso,
  parseTagInput,
  priorityOption,
  statusOption,
  tagsToInput,
  TASK_PRIORITIES,
  TASK_STATUSES,
  taskDateTimeError,
  toLocalDateTimeParts,
  type TaskDateTimeValue,
} from "../utils";
import { TaskDateTimePicker } from "./task-date-time-picker";
import { TaskOptionValue } from "./task-option-value";

type TaskDetailsDrawerProps = {
  open: boolean;
  task: Task | null;
  onOpenChange: (open: boolean) => void;
  onSaveField: (field: TaskEditableField, payload: TaskUpdateInput) => Promise<void>;
  suggestedTags: string[];
  suggestionsPending: boolean;
  onDeleteRequest: () => void;
  series: TaskSeries | null;
  isSeriesPending?: boolean;
  isSeriesActionPending?: boolean;
  onEditSeries: () => void;
  onPauseSeries: () => void;
  onResumeSeries: () => void;
  onEndSeries: () => void;
  onSkipOccurrence: () => void;
};

type TaskDraft = {
  title: string;
  description: string;
  status: TaskStatus;
  priority: TaskPriority;
  startAt: TaskDateTimeValue;
  dueAt: TaskDateTimeValue;
  tags: string;
};

type FieldFeedback = {
  state: "saving" | "saved" | "error";
  message?: string;
};

function taskToDraft(task: Task | null): TaskDraft {
  return {
    title: task?.title ?? "",
    description: task?.description ?? "",
    status: task?.status ?? "backlog",
    priority: task?.priority ?? "none",
    startAt: toLocalDateTimeParts(task?.start_at ?? null),
    dueAt: toLocalDateTimeParts(task?.due_at ?? null),
    tags: tagsToInput(task?.tags ?? []),
  };
}

function describeFieldError(error: unknown) {
  if (error instanceof Error && error.message) {
    return error.message;
  }

  return "This field could not be saved. Try again.";
}

function fieldLabel(field: TaskEditableField) {
  switch (field) {
    case "title":
      return "Title";
    case "description":
      return "Description";
    case "status":
      return "Status";
    case "priority":
      return "Priority";
    case "start_at":
      return "Starts";
    case "due_at":
      return "Due";
    case "tags":
      return "Tags";
  }
}

function FieldState({
  field,
  feedback,
}: {
  field: TaskEditableField;
  feedback?: FieldFeedback;
}) {
  if (!feedback) {
    return null;
  }

  if (feedback.state === "error") {
    return (
      <FieldError id={`task-details-${field}-error`} aria-live="polite" className="mt-2">
        {feedback.message}
      </FieldError>
    );
  }

  return (
    <p className="mt-2 text-xs text-muted-foreground" aria-live="polite">
      {feedback.state === "saving" ? `Saving ${fieldLabel(field).toLowerCase()}…` : "Saved"}
    </p>
  );
}

export function TaskDetailsDrawer({
  open,
  task,
  onOpenChange,
  onSaveField,
  suggestedTags,
  suggestionsPending,
  onDeleteRequest,
  series,
  isSeriesPending = false,
  isSeriesActionPending = false,
  onEditSeries,
  onPauseSeries,
  onResumeSeries,
  onEndSeries,
  onSkipOccurrence,
}: TaskDetailsDrawerProps) {
  const [values, setValues] = useState<TaskDraft>(() => taskToDraft(task));
  const [feedback, setFeedback] = useState<Partial<Record<TaskEditableField, FieldFeedback>>>({});
  const draftTaskId = useRef<string | null>(task?.id ?? null);
  const tagsFieldRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (draftTaskId.current === (task?.id ?? null)) {
      return;
    }

    draftTaskId.current = task?.id ?? null;
    setValues(taskToDraft(task));
    setFeedback({});
  }, [task?.id, task]);

  function updateValue<Key extends keyof TaskDraft>(key: Key, value: TaskDraft[Key]) {
    setValues((current) => ({ ...current, [key]: value }));
    const field = key === "startAt" ? "start_at" : key === "dueAt" ? "due_at" : key;
    setFeedback((current) => {
      const next = { ...current };
      delete next[field as TaskEditableField];
      return next;
    });
  }

  function updateStartAt(value: TaskDateTimeValue) {
    setValues((current) => ({
      ...current,
      startAt: value,
      dueAt: adjustDueDateForStart(value, current.dueAt),
    }));
    setFeedback((current) => {
      const next = { ...current };
      delete next.start_at;
      delete next.due_at;
      return next;
    });
  }

  function payloadForField(field: TaskEditableField, draft: TaskDraft): { payload?: TaskUpdateInput; error?: string } {
    switch (field) {
      case "title": {
        const title = draft.title.trim();
        return title ? { payload: { title } } : { error: "Give this task a short, specific title." };
      }
      case "description":
        return { payload: { description: draft.description.trim() || null } };
      case "status":
        return { payload: { status: draft.status } };
      case "priority":
        return { payload: { priority: draft.priority } };
      case "start_at": {
        const startError = taskDateTimeError(draft.startAt);
        const dueError = taskDateTimeError(draft.dueAt);
        const startAt = localDateTimePartsToIso(draft.startAt);
        const dueAt = localDateTimePartsToIso(draft.dueAt);
        if (startError || dueError) {
          return { error: startError ?? dueError };
        }
        if (startAt && dueAt && new Date(startAt) > new Date(dueAt)) {
          return { error: "The start time must be before or equal to the due time." };
        }
        return { payload: { start_at: startAt } };
      }
      case "due_at": {
        const startError = taskDateTimeError(draft.startAt);
        const dueError = taskDateTimeError(draft.dueAt);
        const startAt = localDateTimePartsToIso(draft.startAt);
        const dueAt = localDateTimePartsToIso(draft.dueAt);
        if (startError || dueError) {
          return { error: dueError ?? startError };
        }
        if (startAt && dueAt && new Date(startAt) > new Date(dueAt)) {
          return { error: "The start time must be before or equal to the due time." };
        }
        return { payload: { due_at: dueAt } };
      }
      case "tags": {
        const tags = parseTagInput(draft.tags);
        if (tags.length > 20 || tags.some((tag) => tag.length > 64)) {
          return { error: "Use up to 20 non-empty tags, each no longer than 64 characters." };
        }
        return { payload: { tags } };
      }
    }
  }

  async function saveField(field: TaskEditableField, draft = values) {
    const result = payloadForField(field, draft);

    if (!result.payload) {
      setFeedback((current) => ({
        ...current,
        [field]: { state: "error", message: result.error },
      }));
      return;
    }

    setFeedback((current) => ({ ...current, [field]: { state: "saving" } }));

    try {
      await onSaveField(field, result.payload);
      setFeedback((current) => ({ ...current, [field]: { state: "saved" } }));
    } catch (error) {
      setFeedback((current) => ({
        ...current,
        [field]: { state: "error", message: describeFieldError(error) },
      }));
    }
  }

  function commitStartAt(value: TaskDateTimeValue) {
    const dueAt = adjustDueDateForStart(value, values.dueAt);
    const nextValues = { ...values, startAt: value, dueAt };

    setValues(nextValues);
    void saveField("start_at", nextValues);

    if (dueAt.date !== values.dueAt.date) {
      void saveField("due_at", nextValues);
    }
  }

  function handleSelectChange<Key extends "status" | "priority">(
    key: Key,
    value: TaskDraft[Key],
  ) {
    const nextValues = { ...values, [key]: value };
    setValues(nextValues);
    const field = key as TaskEditableField;
    setFeedback((current) => {
      const next = { ...current };
      delete next[field];
      return next;
    });
    void saveField(field, nextValues);
  }

  function addSuggestedTag(tag: string) {
    const nextTags = appendTagInput(values.tags, tag);
    if (nextTags === values.tags) {
      return;
    }

    const nextValues = { ...values, tags: nextTags };
    setValues(nextValues);
    void saveField("tags", nextValues);
  }

  const titleError = feedback.title?.state === "error";
  const descriptionError = feedback.description?.state === "error";
  const tagsError = feedback.tags?.state === "error";

  return (
    <Drawer open={open} onOpenChange={onOpenChange} swipeDirection="right">
      <DrawerContent className="min-h-[100svh] w-full max-w-xl gap-0 border-border bg-card p-0 text-card-foreground shadow-none sm:max-w-xl">
        <DrawerTitle className="sr-only">Task details</DrawerTitle>
        <DrawerDescription className="sr-only">
          Edit this task inline.
        </DrawerDescription>

        <div className="relative flex min-h-full flex-1 flex-col">
          <DrawerClose
            type="button"
            aria-label="Close task details"
            render={<Button variant="ghost" size="icon" className="absolute right-5 top-5 z-10" />}
          >
            <X aria-hidden="true" />
          </DrawerClose>

          <div className="flex-1 space-y-8 overflow-y-auto px-6 py-7 sm:px-8 sm:py-8">
            <div>
              <Label htmlFor="task-details-title" className="sr-only">
                Task title
              </Label>
              <Input
                id="task-details-title"
                value={values.title}
                onChange={(event) => updateValue("title", event.target.value)}
                onBlur={() => void saveField("title")}
                maxLength={200}
                aria-invalid={titleError}
                aria-describedby={titleError ? "task-details-title-error" : undefined}
                className="h-auto min-h-12 rounded-none border-0 border-b border-border/70 bg-transparent px-0 py-2 pr-12 !text-2xl font-semibold tracking-[-0.04em] shadow-none outline-none transition-colors placeholder:text-muted-foreground/70 focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/30 dark:bg-transparent sm:!text-3xl"
                placeholder="Task title"
              />
              <FieldState field="title" feedback={feedback.title} />
            </div>

            {task ? (
              <div className="space-y-7">
                <div>
                  <Label htmlFor="task-details-description" className="text-sm font-medium text-foreground">
                    Description
                  </Label>
                  <Textarea
                    id="task-details-description"
                    value={values.description}
                    onChange={(event) => updateValue("description", event.target.value)}
                    onBlur={() => void saveField("description")}
                    maxLength={10_000}
                    aria-invalid={descriptionError}
                    aria-describedby={descriptionError ? "task-details-description-error" : undefined}
                    placeholder="Add context only if it will help you move this forward."
                    className="mt-2 min-h-28 resize-y bg-background leading-6"
                  />
                  <FieldState field="description" feedback={feedback.description} />
                </div>

                <div className="grid gap-5 sm:grid-cols-2">
                  <div>
                    <Label htmlFor="task-details-status" className="text-sm font-medium text-foreground">
                      Status
                    </Label>
                    <Select
                      value={values.status}
                      onValueChange={(value) => handleSelectChange("status", value as TaskStatus)}
                    >
                      <SelectTrigger id="task-details-status" className="mt-2 min-h-11 w-full bg-background">
                        <SelectValue><TaskOptionValue option={statusOption(values.status)} /></SelectValue>
                      </SelectTrigger>
                      <SelectContent>
                        {TASK_STATUSES.map((option) => (
                          <SelectItem key={option.value} value={option.value}>
                            <TaskOptionValue option={option} />
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <FieldState field="status" feedback={feedback.status} />
                  </div>

                  <div>
                    <Label htmlFor="task-details-priority" className="text-sm font-medium text-foreground">
                      Priority
                    </Label>
                    <Select
                      value={values.priority}
                      onValueChange={(value) => handleSelectChange("priority", value as TaskPriority)}
                    >
                      <SelectTrigger id="task-details-priority" className="mt-2 min-h-11 w-full bg-background">
                        <SelectValue><TaskOptionValue option={priorityOption(values.priority)} /></SelectValue>
                      </SelectTrigger>
                      <SelectContent>
                        {TASK_PRIORITIES.map((option) => (
                          <SelectItem key={option.value} value={option.value}>
                            <TaskOptionValue option={option} />
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <FieldState field="priority" feedback={feedback.priority} />
                  </div>
                </div>

                <div>
                  <p className="text-sm font-medium text-foreground">Task window</p>
                  <p className="mt-1 text-xs leading-5 text-muted-foreground">
                    Dates use your browser’s local timezone. Time is optional; date-only values save at midnight.
                  </p>
                  <div className="mt-3 grid gap-5 sm:grid-cols-2">
                    <div>
                      <TaskDateTimePicker
                        id="task-details-start"
                        label="Starts"
                        value={values.startAt}
                        showFieldClear={false}
                        error={feedback.start_at?.state === "error" ? feedback.start_at.message : undefined}
                        onChange={updateStartAt}
                        onCommit={commitStartAt}
                      />
                      {feedback.start_at?.state === "saving" || feedback.start_at?.state === "saved" ? (
                        <FieldState field="start_at" feedback={feedback.start_at} />
                      ) : null}
                    </div>
                    <div>
                      <TaskDateTimePicker
                        id="task-details-due"
                        label="Due"
                        value={values.dueAt}
                        showFieldClear={false}
                        error={feedback.due_at?.state === "error" ? feedback.due_at.message : undefined}
                        onChange={(value) => updateValue("dueAt", value)}
                        onCommit={(value) => {
                          const nextValues = { ...values, dueAt: value };
                          setValues(nextValues);
                          void saveField("due_at", nextValues);
                        }}
                      />
                      {feedback.due_at?.state === "saving" || feedback.due_at?.state === "saved" ? (
                        <FieldState field="due_at" feedback={feedback.due_at} />
                      ) : null}
                    </div>
                  </div>
                </div>

                {task.series_id ? (
                  <section className="rounded-lg border border-border/80 bg-background/35 p-4 sm:p-5" aria-labelledby="task-details-series-heading">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="flex items-center gap-2">
                          <Repeat2 aria-hidden="true" className="size-4 text-primary-strong" />
                          <h3 id="task-details-series-heading" className="text-sm font-medium text-foreground">Repeats</h3>
                        </div>
                        <p className="mt-2 text-sm leading-5 text-foreground">
                          {series ? recurrenceSummary(recurrenceValuesFromPayload(series.recurrence)) : "Loading recurrence…"}
                        </p>
                      </div>
                      {series ? (
                        <Badge variant="outline" className="shrink-0 border-primary/35 bg-primary/10 text-primary-strong">
                          {recurrenceStateLabel(series.state)}
                        </Badge>
                      ) : null}
                    </div>

                    {task.series_exception ? (
                      <p className="mt-3 rounded-md bg-muted px-3 py-2 text-xs leading-5 text-muted-foreground">
                        Customized occurrence. Series edits will not overwrite this task.
                      </p>
                    ) : null}

                    {series ? (
                      <div className="mt-3 space-y-1 font-mono text-[0.68rem] text-muted-foreground">
                        <p>Time zone · {series.recurrence.timezone}</p>
                        <p>
                          Ends · {series.recurrence.until_date
                            ? series.recurrence.until_date
                            : series.recurrence.occurrence_count
                              ? `${series.recurrence.occurrence_count} occurrences`
                              : "Never"}
                        </p>
                      </div>
                    ) : null}

                    {isSeriesPending ? (
                      <p className="mt-3 text-xs text-muted-foreground" aria-live="polite">Loading series controls…</p>
                    ) : null}

                    {series ? (
                      <div className="mt-4 flex flex-wrap gap-2">
                        {series.state !== "ended" ? (
                          <Button type="button" variant="outline" size="sm" onClick={onEditSeries} disabled={isSeriesActionPending}>
                            Edit series
                          </Button>
                        ) : null}
                        {series.state === "active" ? (
                          <Button type="button" variant="outline" size="sm" onClick={onPauseSeries} disabled={isSeriesActionPending}>
                            <Pause aria-hidden="true" />
                            Pause series
                          </Button>
                        ) : null}
                        {series.state === "paused" || series.state === "ended" ? (
                          <Button type="button" variant="outline" size="sm" onClick={onResumeSeries} disabled={isSeriesActionPending}>
                            <Play aria-hidden="true" />
                            {series.state === "ended" ? "Restart series" : "Resume series"}
                          </Button>
                        ) : null}
                        {series.state !== "ended" ? (
                          <Button type="button" variant="outline" size="sm" onClick={onEndSeries} disabled={isSeriesActionPending}>
                            <Square aria-hidden="true" />
                            End series
                          </Button>
                        ) : null}
                        {!task.skipped_at ? (
                          <Button type="button" variant="ghost" size="sm" onClick={onSkipOccurrence} disabled={isSeriesActionPending} className="text-muted-foreground hover:text-foreground">
                            <SkipForward aria-hidden="true" />
                            Skip this occurrence
                          </Button>
                        ) : (
                          <span className="inline-flex items-center gap-1.5 text-xs font-medium text-destructive"><SkipForward aria-hidden="true" className="size-3.5" />Skipped</span>
                        )}
                      </div>
                    ) : null}

                    <p className="mt-4 text-xs leading-5 text-muted-foreground">
                      Series edits apply to future occurrences that have not been customized. Existing occurrences remain in place.
                    </p>
                  </section>
                ) : null}

                <div ref={tagsFieldRef}>
                  <Label htmlFor="task-details-tags" className="text-sm font-medium text-foreground">
                    Tags
                  </Label>
                  <Input
                    id="task-details-tags"
                    value={values.tags}
                    onChange={(event) => updateValue("tags", event.target.value)}
                    onBlur={(event) => {
                      const relatedTarget = event.relatedTarget;
                      if (relatedTarget instanceof Node && tagsFieldRef.current?.contains(relatedTarget)) {
                        return;
                      }

                      void saveField("tags");
                    }}
                    placeholder="work, home, focus"
                    aria-invalid={tagsError}
                    aria-describedby={tagsError ? "task-details-tags-error" : undefined}
                    className="mt-2 min-h-11 bg-background"
                  />
                  <SuggestedTags
                    selectedTags={parseTagInput(values.tags)}
                    suggestions={suggestedTags}
                    pending={suggestionsPending}
                    onSelect={addSuggestedTag}
                  />
                  <p className="mt-2 text-xs leading-5 text-muted-foreground">
                    Separate tags with commas. They will be normalized when saved.
                  </p>
                  <FieldState field="tags" feedback={feedback.tags} />
                </div>
              </div>
            ) : null}
          </div>

          {task ? (
            <DrawerFooter className="mt-auto flex-row justify-between gap-3 border-t border-border/70 bg-card px-6 py-5 sm:px-8">
              <Button type="button" variant="destructive" size="sm" onClick={onDeleteRequest}>
                Delete task
              </Button>
              <DrawerClose
                type="button"
                render={<Button variant="outline" size="lg" />}
              >
                Done
              </DrawerClose>
            </DrawerFooter>
          ) : null}
        </div>
      </DrawerContent>
    </Drawer>
  );
}

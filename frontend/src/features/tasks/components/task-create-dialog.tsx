"use client";

import { useState, type FormEvent } from "react";
import { FileAttachmentPicker } from "@/components/file-attachment-picker";
import { TagPicker } from "@/components/tag-picker";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field, FieldDescription, FieldError, FieldTitle } from "@/components/ui/field";
import { fieldDescribedBy, FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { currentLocalDateInput } from "@/lib/date";
import type { TaskPriority, TaskStatus } from "../api";
import type { StoredFile } from "@/features/memory/files-api";
import type { Tag, TagColor } from "@/features/tags/api";
import {
  defaultRecurrenceValues,
  recurrenceFormValidationError,
  recurrenceValuesToPayload,
  type RecurrenceFormErrorField,
  type RecurrenceFormValues,
} from "../recurrence";
import {
  adjustDueDateForStart,
  localDateTimePartsToIso,
  dueDateTimeAfterStart,
  priorityOption,
  statusOption,
  TASK_PRIORITIES,
  TASK_STATUSES,
  taskDateTimeError,
  type TaskDateTimeValue,
} from "../utils";
import { TaskDateTimePicker } from "./task-date-time-picker";
import { TaskOptionValue } from "./task-option-value";
import { TaskRecurrenceBuilder } from "./task-recurrence-builder";

export type TaskFormValues = {
  title: string;
  description: string;
  status: TaskStatus;
  priority: TaskPriority;
  startAt: TaskDateTimeValue;
  dueAt: TaskDateTimeValue;
  tags: string[];
  attachments: StoredFile[];
  recurrence: RecurrenceFormValues;
};

type TaskFormErrorField = "title" | "startAt" | "dueAt" | "taskWindow" | "recurrence";

type TaskCreateDialogProps = {
  open: boolean;
  isSaving: boolean;
  availableTags: Tag[];
  onCreateTag?: (payload: { name: string; color: TagColor }) => Promise<Tag>;
  initialStartAt?: TaskDateTimeValue;
  onOpenChange: (open: boolean) => void;
  onSubmit: (values: TaskFormValues) => void;
};

function defaultFormValues(initialStartAt?: TaskDateTimeValue): TaskFormValues {
  const today = currentLocalDateInput();
  const startAt = initialStartAt ?? { date: today, time: "" };
  const dueAt = initialStartAt
    ? dueDateTimeAfterStart(startAt) ?? { date: startAt.date, time: "" }
    : { date: today, time: "" };

  return {
    title: "",
    description: "",
    status: "backlog",
    priority: "none",
    startAt,
    dueAt,
    tags: [],
    attachments: [],
    recurrence: defaultRecurrenceValues(startAt),
  };
}

function sameWeekdays(left: RecurrenceFormValues["weekdays"], right: RecurrenceFormValues["weekdays"]) {
  return left.length === right.length && left.every((weekday) => right.includes(weekday));
}

function recurrenceDefaultsForStartChange(
  recurrence: RecurrenceFormValues,
  previousAnchor: TaskDateTimeValue,
  nextAnchor: TaskDateTimeValue,
) {
  const previousDefaults = defaultRecurrenceValues(previousAnchor);
  const nextDefaults = defaultRecurrenceValues(nextAnchor);

  return {
    ...recurrence,
    weekdays: sameWeekdays(recurrence.weekdays, previousDefaults.weekdays)
      ? nextDefaults.weekdays
      : recurrence.weekdays,
    monthDay: recurrence.monthDay === previousDefaults.monthDay
      ? nextDefaults.monthDay
      : recurrence.monthDay,
    month: recurrence.month === previousDefaults.month
      ? nextDefaults.month
      : recurrence.month,
    day: recurrence.day === previousDefaults.day ? nextDefaults.day : recurrence.day,
  };
}

export function TaskCreateDialog({
  open,
  isSaving,
  availableTags,
  onCreateTag,
  initialStartAt,
  onOpenChange,
  onSubmit,
}: TaskCreateDialogProps) {
  const [values, setValues] = useState<TaskFormValues>(() => defaultFormValues(initialStartAt));
  const [formError, setFormError] = useState<string>();
  const [fieldErrors, setFieldErrors] = useState<Partial<Record<TaskFormErrorField, string>>>({});

  function updateValue<Key extends keyof TaskFormValues>(
    key: Key,
    value: TaskFormValues[Key],
  ) {
    setValues((current) => ({ ...current, [key]: value }));
    setFormError(undefined);
    setFieldErrors((current) => {
      const next = { ...current };
      if (key === "title") {
        delete next.title;
      }
      if (key === "recurrence") {
        delete next.recurrence;
      }
      if (key === "startAt" || key === "dueAt") {
        if (key === "startAt") {
          delete next.startAt;
        } else {
          delete next.dueAt;
        }
        delete next.taskWindow;
      }
      return next;
    });
  }

  function handleStartChange(value: TaskDateTimeValue) {
    setValues((current) => {
      const dueAt = dueDateTimeAfterStart(value) ?? adjustDueDateForStart(value, current.dueAt);
      const previousAnchor = current.startAt.date ? current.startAt : current.dueAt;
      const nextAnchor = value.date ? value : dueAt;

      return {
        ...current,
        startAt: value,
        dueAt,
        recurrence: recurrenceDefaultsForStartChange(
          current.recurrence,
          previousAnchor,
          nextAnchor,
        ),
      };
    });
    setFormError(undefined);
    setFieldErrors((current) => {
      const next = { ...current };
      delete next.startAt;
      delete next.dueAt;
      delete next.taskWindow;
      delete next.recurrence;
      return next;
    });
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(undefined);
    setFieldErrors({});
    const title = values.title.trim();

    if (!title) {
      setFieldErrors({ title: "Give this task a short, specific title." });
      return;
    }

    const startError = taskDateTimeError(values.startAt);
    const dueError = taskDateTimeError(values.dueAt);

    if (startError || dueError) {
      setFieldErrors({
        ...(startError ? { startAt: startError } : {}),
        ...(dueError ? { dueAt: dueError } : {}),
      });
      return;
    }

    const startAt = localDateTimePartsToIso(values.startAt);
    const dueAt = localDateTimePartsToIso(values.dueAt);

    if (startAt && dueAt && new Date(startAt) > new Date(dueAt)) {
      setFieldErrors({
        taskWindow: "The start time must be before or equal to the due time.",
      });
      return;
    }

    const recurrenceValidation = recurrenceFormValidationError(
      values.recurrence,
      values.startAt.date ? values.startAt : values.dueAt,
    );
    if (recurrenceValidation) {
      setFieldErrors(
        recurrenceValidation.field === "anchor"
          ? { taskWindow: recurrenceValidation.message }
          : { recurrence: recurrenceValidation.message },
      );
      return;
    }

    onSubmit({ ...values, title });
  }

  const recurrenceValidation = recurrenceFormValidationError(
    values.recurrence,
    values.startAt.date ? values.startAt : values.dueAt,
  );
  const taskWindowError =
    fieldErrors.taskWindow ??
    (recurrenceValidation?.field === "anchor" ? recurrenceValidation.message : undefined);
  const recurrenceError =
    fieldErrors.recurrence ??
    (recurrenceValidation?.field === "anchor" ? undefined : recurrenceValidation?.message);
  const taskWindowErrorId = "task-create-window-error";
  const taskWindowHintId = "task-create-window-hint";
  const taskWindowDescribedBy = [
    taskWindowHintId,
    taskWindowError ? taskWindowErrorId : undefined,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="flex max-h-[min(90svh,48rem)] w-[min(38rem,calc(100vw-2rem))] flex-col overflow-hidden rounded-xl border-border bg-card p-0 text-card-foreground shadow-none sm:max-w-none"
      >
        <form
          onSubmit={handleSubmit}
          className="flex min-h-0 flex-1 flex-col"
          aria-describedby={formError ? "task-create-error" : undefined}
        >
          <DialogHeader className="border-b border-border/70 px-6 py-6 sm:px-7">
            <DialogTitle className="text-xl font-semibold tracking-[-0.03em]">
              Add task
            </DialogTitle>
            <DialogDescription className="mt-2 max-w-md text-sm leading-6">
              Capture the next meaningful action, then add enough context to make it movable.
            </DialogDescription>
          </DialogHeader>

          <div className="min-h-0 flex-1 space-y-6 overflow-y-auto px-6 py-6 sm:px-7">
            {formError ? (
              <FieldError id="task-create-error" aria-live="polite" className="leading-6">
                {formError}
              </FieldError>
            ) : null}

            <FormField id="task-create-title" label="Title" error={fieldErrors.title}>
              <Input
                id="task-create-title"
                name="title"
                type="text"
                autoFocus
                maxLength={200}
                value={values.title}
                onChange={(event) => updateValue("title", event.target.value)}
                placeholder="Name the next meaningful action"
                aria-invalid={fieldErrors.title ? true : undefined}
                aria-describedby={fieldDescribedBy("task-create-title", undefined, fieldErrors.title)}
                className="min-h-11 bg-background text-foreground"
                disabled={isSaving}
              />
            </FormField>

            <Field data-invalid={taskWindowError ? true : undefined} className="gap-1.5">
              <FieldTitle>Task window</FieldTitle>
              <FieldDescription id={taskWindowHintId} className="text-xs leading-5">
                Dates use your browser’s local timezone. Time is optional; date-only values save at midnight.
              </FieldDescription>
              <div className="mt-3 grid gap-5 sm:grid-cols-2">
                <div>
                  <TaskDateTimePicker
                    id="task-create-start"
                    label="Starts"
                    value={values.startAt}
                    error={fieldErrors.startAt}
                    invalid={Boolean(taskWindowError)}
                    describedBy={taskWindowDescribedBy}
                    onChange={handleStartChange}
                    disabled={isSaving}
                  />
                </div>
                <div>
                  <TaskDateTimePicker
                    id="task-create-due"
                    label="Due"
                    value={values.dueAt}
                    error={fieldErrors.dueAt}
                    invalid={Boolean(taskWindowError)}
                    describedBy={taskWindowDescribedBy}
                    onChange={(value) => updateValue("dueAt", value)}
                    disabled={isSaving}
                  />
                </div>
              </div>
              {taskWindowError ? (
                <FieldError id={taskWindowErrorId} aria-live="polite" className="leading-6">
                  {taskWindowError}
                </FieldError>
              ) : null}
            </Field>

            <div className="grid gap-5 sm:grid-cols-2">
              <FormField id="task-create-status" label="Status">
                <Select
                  value={values.status}
                  onValueChange={(value) => updateValue("status", value as TaskStatus)}
                  disabled={isSaving}
                >
                  <SelectTrigger id="task-create-status" className="min-h-11 w-full bg-background text-foreground">
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
              </FormField>
              <FormField id="task-create-priority" label="Priority">
                <Select
                  value={values.priority}
                  onValueChange={(value) => updateValue("priority", value as TaskPriority)}
                  disabled={isSaving}
                >
                  <SelectTrigger id="task-create-priority" className="min-h-11 w-full bg-background text-foreground">
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
              </FormField>
            </div>

            <TaskRecurrenceBuilder
              values={values.recurrence}
              anchor={values.startAt.date ? values.startAt : values.dueAt}
              onChange={(recurrence) => updateValue("recurrence", recurrence)}
              disabled={isSaving}
              error={recurrenceError}
              errorField={recurrenceValidation?.field === "anchor" ? undefined : recurrenceValidation?.field as RecurrenceFormErrorField | undefined}
            />

            <FormField id="task-create-description" label="Description">
              <Textarea
                id="task-create-description"
                name="description"
                maxLength={10_000}
                value={values.description}
                onChange={(event) => updateValue("description", event.target.value)}
                placeholder="Add context only if it will help you move this forward."
                className="min-h-28 resize-y bg-background text-foreground leading-6"
                disabled={isSaving}
              />
            </FormField>

            <FormField id="task-create-tags" label="Tags">
              <TagPicker
                id="task-create-tags"
                tags={availableTags}
                value={values.tags}
                onChange={(tags) => updateValue("tags", tags)}
                onCreateTag={onCreateTag}
                disabled={isSaving}
              />
            </FormField>

            <FormField id="task-create-attachments" label="Attachments">
              <FileAttachmentPicker
                id="task-create-attachments"
                value={values.attachments}
                onChange={(attachments) => updateValue("attachments", attachments)}
                disabled={isSaving}
                hideLabel
              />
            </FormField>
          </div>

          <DialogFooter className="mx-0! mb-0! flex-col-reverse items-stretch gap-2 rounded-none border-t border-border/70 bg-card px-6 py-4 sm:flex-row sm:items-center sm:justify-end sm:px-7">
            <DialogClose
              type="button"
              render={<Button variant="outline" size="lg" disabled={isSaving} className="w-full sm:w-auto" />}
            >
              Cancel
            </DialogClose>
            <Button type="submit" size="lg" disabled={isSaving} className="w-full sm:w-auto">
              {isSaving ? "Adding…" : values.recurrence.enabled ? "Add recurring task" : "Add task"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function formValuesToPayload(values: TaskFormValues) {
  const recurrence = recurrenceValuesToPayload(values.recurrence);

  return {
    title: values.title.trim(),
    description: values.description.trim() || null,
    status: values.status,
    priority: values.priority,
    start_at: localDateTimePartsToIso(values.startAt),
    due_at: localDateTimePartsToIso(values.dueAt),
    tags: values.tags,
    file_ids: values.attachments.map((file) => file.id),
    ...(recurrence ? { recurrence } : {}),
  };
}

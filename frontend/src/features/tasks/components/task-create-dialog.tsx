"use client";

import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { FieldError } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import type { TaskPriority, TaskStatus } from "../api";
import {
  adjustDueDateForStart,
  localDateTimePartsToIso,
  currentLocalDateInput,
  parseTagInput,
  priorityOption,
  statusOption,
  TASK_PRIORITIES,
  TASK_STATUSES,
  taskDateTimeError,
  type TaskDateTimeValue,
} from "../utils";
import { TaskDateTimePicker } from "./task-date-time-picker";
import { TaskOptionValue } from "./task-option-value";

export type TaskFormValues = {
  title: string;
  description: string;
  status: TaskStatus;
  priority: TaskPriority;
  startAt: TaskDateTimeValue;
  dueAt: TaskDateTimeValue;
  tags: string;
};

type TaskCreateDialogProps = {
  open: boolean;
  isSaving: boolean;
  onOpenChange: (open: boolean) => void;
  onSubmit: (values: TaskFormValues) => void;
};

function defaultFormValues(): TaskFormValues {
  const today = currentLocalDateInput();

  return {
    title: "",
    description: "",
    status: "backlog",
    priority: "none",
    startAt: { date: today, time: "" },
    dueAt: { date: today, time: "" },
    tags: "",
  };
}

export function TaskCreateDialog({
  open,
  isSaving,
  onOpenChange,
  onSubmit,
}: TaskCreateDialogProps) {
  const [values, setValues] = useState<TaskFormValues>(defaultFormValues);
  const [formError, setFormError] = useState<string>();

  function updateValue<Key extends keyof TaskFormValues>(
    key: Key,
    value: TaskFormValues[Key],
  ) {
    setValues((current) => ({ ...current, [key]: value }));
    setFormError(undefined);
  }

  function handleStartChange(value: TaskDateTimeValue) {
    setValues((current) => ({
      ...current,
      startAt: value,
      dueAt: adjustDueDateForStart(value, current.dueAt),
    }));
    setFormError(undefined);
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const title = values.title.trim();

    if (!title) {
      setFormError("Give this task a short, specific title.");
      return;
    }

    const startError = taskDateTimeError(values.startAt);
    const dueError = taskDateTimeError(values.dueAt);

    if (startError || dueError) {
      setFormError(startError ?? dueError);
      return;
    }

    const startAt = localDateTimePartsToIso(values.startAt);
    const dueAt = localDateTimePartsToIso(values.dueAt);

    if (startAt && dueAt && new Date(startAt) > new Date(dueAt)) {
      setFormError("The start time must be before or equal to the due time.");
      return;
    }

    onSubmit({ ...values, title });
  }

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

            <div>
              <Label htmlFor="task-create-title" className="text-sm text-foreground">
                Title
              </Label>
              <Input
                id="task-create-title"
                name="title"
                type="text"
                autoFocus
                maxLength={200}
                value={values.title}
                onChange={(event) => updateValue("title", event.target.value)}
                placeholder="Name the next meaningful action"
                className="mt-2 min-h-11 bg-background text-foreground"
                disabled={isSaving}
              />
            </div>

            <div>
              <p className="text-sm font-medium text-foreground">Task window</p>
              <p className="mt-1 text-xs leading-5 text-muted-foreground">
                Dates use your browser’s local timezone. Time is optional; date-only values save at midnight.
              </p>
              <div className="mt-3 grid gap-5 sm:grid-cols-2">
                <div>
                  <TaskDateTimePicker
                    id="task-create-start"
                    label="Starts"
                    value={values.startAt}
                    onChange={handleStartChange}
                    disabled={isSaving}
                  />
                </div>
                <div>
                  <TaskDateTimePicker
                    id="task-create-due"
                    label="Due"
                    value={values.dueAt}
                    onChange={(value) => updateValue("dueAt", value)}
                    disabled={isSaving}
                  />
                </div>
              </div>
            </div>

            <div className="grid gap-5 sm:grid-cols-2">
              <div>
                <Label htmlFor="task-create-status" className="text-sm text-foreground">
                  Status
                </Label>
                <Select
                  value={values.status}
                  onValueChange={(value) => updateValue("status", value as TaskStatus)}
                  disabled={isSaving}
                >
                  <SelectTrigger id="task-create-status" className="mt-2 min-h-11 w-full bg-background text-foreground">
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
              </div>
              <div>
                <Label htmlFor="task-create-priority" className="text-sm text-foreground">
                  Priority
                </Label>
                <Select
                  value={values.priority}
                  onValueChange={(value) => updateValue("priority", value as TaskPriority)}
                  disabled={isSaving}
                >
                  <SelectTrigger id="task-create-priority" className="mt-2 min-h-11 w-full bg-background text-foreground">
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
              </div>
            </div>

            <div>
              <Label htmlFor="task-create-description" className="text-sm text-foreground">
                Description
              </Label>
              <Textarea
                id="task-create-description"
                name="description"
                maxLength={10_000}
                value={values.description}
                onChange={(event) => updateValue("description", event.target.value)}
                placeholder="Add context only if it will help you move this forward."
                className="mt-2 min-h-28 resize-y bg-background text-foreground leading-6"
                disabled={isSaving}
              />
            </div>

            <div>
              <Label htmlFor="task-create-tags" className="text-sm text-foreground">
                Tags
              </Label>
              <Input
                id="task-create-tags"
                name="tags"
                type="text"
                value={values.tags}
                onChange={(event) => updateValue("tags", event.target.value)}
                placeholder="work, home, focus"
                className="mt-2 min-h-11 bg-background text-foreground"
                disabled={isSaving}
              />
              <p className="mt-2 text-xs leading-5 text-muted-foreground">
                Separate tags with commas. They will be normalized when saved.
              </p>
            </div>
          </div>

          <DialogFooter className="mx-0! mb-0! flex-col-reverse items-stretch gap-2 rounded-none border-t border-border/70 bg-card px-6 py-4 sm:flex-row sm:items-center sm:justify-end sm:px-7">
            <DialogClose
              type="button"
              render={<Button variant="outline" size="lg" disabled={isSaving} className="w-full sm:w-auto" />}
            >
              Cancel
            </DialogClose>
            <Button type="submit" size="lg" disabled={isSaving} className="w-full sm:w-auto">
              {isSaving ? "Adding…" : "Add task"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function formValuesToPayload(values: TaskFormValues) {
  return {
    title: values.title.trim(),
    description: values.description.trim() || null,
    status: values.status,
    priority: values.priority,
    start_at: localDateTimePartsToIso(values.startAt),
    due_at: localDateTimePartsToIso(values.dueAt),
    tags: parseTagInput(values.tags),
  };
}

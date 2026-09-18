"use client";

import { X } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { FieldError } from "@/components/ui/field";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Drawer,
  DrawerClose,
  DrawerContent,
  DrawerDescription,
  DrawerFooter,
  DrawerHeader,
  DrawerTitle,
} from "@/components/ui/drawer";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import type { Task, TaskPriority, TaskStatus } from "../api";
import {
  localDateTimeToIso,
  parseTagInput,
  priorityLabel,
  statusLabel,
  tagsToInput,
  toLocalDateTimeInput,
  TASK_PRIORITIES,
  TASK_STATUSES,
} from "../utils";

export type TaskFormValues = {
  title: string;
  description: string;
  status: TaskStatus;
  priority: TaskPriority;
  startAt: string;
  dueAt: string;
  tags: string;
};

type TaskFormSheetProps = {
  open: boolean;
  task: Task | null;
  isSaving: boolean;
  onOpenChange: (open: boolean) => void;
  onSubmit: (values: TaskFormValues) => void;
  onDeleteRequest?: () => void;
};

function defaultFormValues(task: Task | null): TaskFormValues {
  return {
    title: task?.title ?? "",
    description: task?.description ?? "",
    status: task?.status ?? "backlog",
    priority: task?.priority ?? "none",
    startAt: toLocalDateTimeInput(task?.start_at ?? null),
    dueAt: toLocalDateTimeInput(task?.due_at ?? null),
    tags: tagsToInput(task?.tags ?? []),
  };
}

export function TaskFormSheet({
  open,
  task,
  isSaving,
  onOpenChange,
  onSubmit,
  onDeleteRequest,
}: TaskFormSheetProps) {
  const [values, setValues] = useState(() => defaultFormValues(task));
  const [formError, setFormError] = useState<string>();

  function updateValue<Key extends keyof TaskFormValues>(
    key: Key,
    value: TaskFormValues[Key],
  ) {
    setValues((current) => ({ ...current, [key]: value }));
    setFormError(undefined);
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const title = values.title.trim();

    if (!title) {
      setFormError("Give this task a short, specific title.");
      return;
    }

    const startAt = localDateTimeToIso(values.startAt);
    const dueAt = localDateTimeToIso(values.dueAt);

    if ((values.startAt && !startAt) || (values.dueAt && !dueAt)) {
      setFormError("Use a valid local date and time for the task window.");
      return;
    }

    if (startAt && dueAt && new Date(startAt) > new Date(dueAt)) {
      setFormError("The start time must be before or equal to the due time.");
      return;
    }

    onSubmit({ ...values, title });
  }

  const heading = task ? "Edit task" : "Add a task";
  const description = task
    ? "Keep the next action clear, with enough context to make it movable."
    : "Capture something worth keeping close.";

  return (
    <Drawer open={open} onOpenChange={onOpenChange} swipeDirection="right">
      <DrawerContent
        className="min-h-[100svh] w-full max-w-xl gap-0 border-border bg-card p-0 text-card-foreground shadow-[-24px_0_70px_-44px_color-mix(in_oklab,var(--foreground)_65%,transparent)] sm:max-w-xl"
      >
        <form
          onSubmit={handleSubmit}
          className="flex min-h-full flex-1 flex-col"
          aria-describedby={formError ? "task-form-error" : undefined}
        >
                <DrawerHeader className="flex items-start justify-between gap-5 border-b border-border/70 px-6 py-6 sm:px-8">
                  <div>
                    <p className="font-mono text-[0.65rem] uppercase tracking-[0.18em] text-primary">
                      Focus / task
                    </p>
                    <DrawerTitle className="mt-3 text-2xl font-semibold tracking-[-0.035em]">
                      {heading}
                    </DrawerTitle>
                    <DrawerDescription className="mt-2 max-w-sm text-sm leading-6 text-muted-foreground">
                      {description}
                    </DrawerDescription>
                  </div>
                  <DrawerClose
                    type="button"
                    aria-label="Close task form"
                    render={<Button variant="ghost" size="icon" />}
                  >
                    <X aria-hidden="true" />
                  </DrawerClose>
                </DrawerHeader>

                <div className="flex-1 space-y-7 overflow-y-auto px-6 py-7 sm:px-8">
                  {formError ? (
                    <FieldError id="task-form-error" aria-live="polite" className="leading-6">
                      {formError}
                    </FieldError>
                  ) : null}

                  <div>
                    <Label htmlFor="task-title" className="text-sm text-foreground">Title</Label>
                    <Input
                      id="task-title"
                      name="title"
                      type="text"
                      autoFocus
                      required
                      maxLength={200}
                      value={values.title}
                      onChange={(event) => updateValue("title", event.target.value)}
                      placeholder="Name the next meaningful action"
                      className="mt-2 min-h-11 bg-background text-foreground"
                      disabled={isSaving}
                    />
                  </div>

                  <div>
                    <Label htmlFor="task-description" className="text-sm text-foreground">Description</Label>
                    <Textarea
                      id="task-description"
                      name="description"
                      maxLength={10_000}
                      value={values.description}
                      onChange={(event) => updateValue("description", event.target.value)}
                      placeholder="Add context only if it will help you move this forward."
                      className="mt-2 min-h-32 resize-y bg-background text-foreground leading-6"
                      disabled={isSaving}
                    />
                  </div>

                  <div className="grid gap-5 sm:grid-cols-2">
                    <div>
                      <Label htmlFor="task-status" className="text-sm text-foreground">Status</Label>
                      <Select
                        value={values.status}
                        onValueChange={(value) => updateValue("status", value as TaskStatus)}
                        disabled={isSaving}
                      >
                        <SelectTrigger id="task-status" className="mt-2 min-h-11 w-full bg-background text-foreground">
                          <SelectValue>{statusLabel(values.status)}</SelectValue>
                        </SelectTrigger>
                        <SelectContent>
                          {TASK_STATUSES.map((option) => (
                            <SelectItem key={option.value} value={option.value}>
                              {statusLabel(option.value)}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div>
                      <Label htmlFor="task-priority" className="text-sm text-foreground">Priority</Label>
                      <Select
                        value={values.priority}
                        onValueChange={(value) => updateValue("priority", value as TaskPriority)}
                        disabled={isSaving}
                      >
                        <SelectTrigger id="task-priority" className="mt-2 min-h-11 w-full bg-background text-foreground">
                          <SelectValue>{priorityLabel(values.priority)}</SelectValue>
                        </SelectTrigger>
                        <SelectContent>
                          {TASK_PRIORITIES.map((option) => (
                            <SelectItem key={option.value} value={option.value}>
                              {priorityLabel(option.value)}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                  </div>

                  <div>
                    <p className="text-sm font-medium text-foreground">Task window</p>
                    <p className="mt-1 text-xs leading-5 text-muted-foreground">
                      Times use your browser’s local timezone and are stored with an explicit offset.
                    </p>
                    <div className="mt-3 grid gap-5 sm:grid-cols-2">
                      <div>
                        <Label htmlFor="task-start" className="text-sm text-foreground">Starts</Label>
                        <Input
                          id="task-start"
                          name="start_at"
                          type="datetime-local"
                          value={values.startAt}
                          onChange={(event) => updateValue("startAt", event.target.value)}
                          className="mt-2 min-h-11 bg-background text-foreground"
                          disabled={isSaving}
                        />
                      </div>
                      <div>
                        <Label htmlFor="task-due" className="text-sm text-foreground">Due</Label>
                        <Input
                          id="task-due"
                          name="due_at"
                          type="datetime-local"
                          value={values.dueAt}
                          onChange={(event) => updateValue("dueAt", event.target.value)}
                          className="mt-2 min-h-11 bg-background text-foreground"
                          disabled={isSaving}
                        />
                      </div>
                    </div>
                  </div>

                  <div>
                    <Label htmlFor="task-tags" className="text-sm text-foreground">Tags</Label>
                    <Input
                      id="task-tags"
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

                <DrawerFooter className="mt-auto flex flex-wrap items-center justify-between gap-3 border-t border-border/70 bg-card px-6 py-5 sm:px-8">
                  {task && onDeleteRequest ? (
                    <Button
                      type="button"
                      variant="destructive"
                      size="sm"
                      onClick={onDeleteRequest}
                      disabled={isSaving}
                    >
                      Delete task
                    </Button>
                  ) : (
                    <span />
                  )}
                  <div className="ml-auto flex items-center gap-2">
                    <DrawerClose
                      type="button"
                      render={<Button variant="outline" size="lg" />}
                    >
                      Cancel
                    </DrawerClose>
                    <Button type="submit" size="lg" disabled={isSaving}>
                      {isSaving ? "Saving…" : task ? "Save changes" : "Add task"}
                    </Button>
                  </div>
                </DrawerFooter>
        </form>
      </DrawerContent>
    </Drawer>
  );
}

export function formValuesToPayload(values: TaskFormValues) {
  return {
    title: values.title.trim(),
    description: values.description.trim() || null,
    status: values.status,
    priority: values.priority,
    start_at: localDateTimeToIso(values.startAt),
    due_at: localDateTimeToIso(values.dueAt),
    tags: parseTagInput(values.tags),
  };
}

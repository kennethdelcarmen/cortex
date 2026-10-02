"use client";

import { useState, type FormEvent } from "react";
import { FileAttachmentPicker } from "@/components/file-attachment-picker";
import { TagPicker } from "@/components/tag-picker";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { FieldError } from "@/components/ui/field";
import { fieldDescribedBy, FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import type { TaskPriority, TaskSeries, TaskSeriesUpdateInput, TaskStatus } from "../api";
import type { Tag, TagColor } from "@/features/tags/api";
import type { StoredFile } from "@/features/memory/files-api";
import {
  recurrenceFormValidationError,
  recurrenceValuesFromPayload,
  recurrenceValuesToPayload,
  type RecurrenceFormErrorField,
  type RecurrenceFormValues,
} from "../recurrence";
import { priorityOption, statusOption, TASK_PRIORITIES, TASK_STATUSES } from "../utils";
import { TaskOptionValue } from "./task-option-value";
import { TaskRecurrenceBuilder } from "./task-recurrence-builder";

type TaskSeriesDialogProps = {
  open: boolean;
  series: TaskSeries | null;
  isSaving: boolean;
  availableTags: Tag[];
  onCreateTag?: (payload: { name: string; color: TagColor }) => Promise<Tag>;
  onOpenChange: (open: boolean) => void;
  onSubmit: (payload: TaskSeriesUpdateInput) => void;
};

type SeriesFormValues = {
  title: string;
  description: string;
  status: TaskStatus;
  priority: TaskPriority;
  tags: string[];
  attachments: StoredFile[];
  recurrence: RecurrenceFormValues;
};

function formValuesFromSeries(series: TaskSeries | null): SeriesFormValues {
  return {
    title: series?.title ?? "",
    description: series?.description ?? "",
    status: series?.status ?? "backlog",
    priority: series?.priority ?? "none",
    tags: series?.tags ?? [],
    attachments: series?.attachments ?? [],
    recurrence: series
      ? recurrenceValuesFromPayload(series.recurrence)
      : recurrenceValuesFromPayload({
          timezone: "UTC",
          frequency: "weekly",
          interval: 1,
          weekdays: ["monday"],
          month_day: null,
          month: null,
          day: null,
          until_date: null,
          occurrence_count: null,
        }),
  };
}

export function TaskSeriesDialog({
  open,
  series,
  isSaving,
  availableTags,
  onCreateTag,
  onOpenChange,
  onSubmit,
}: TaskSeriesDialogProps) {
  const [values, setValues] = useState<SeriesFormValues>(() => formValuesFromSeries(series));
  const [formError, setFormError] = useState<string>();
  const [fieldErrors, setFieldErrors] = useState<Partial<Record<"title" | "recurrence", string>>>({});

  function update<Key extends keyof SeriesFormValues>(key: Key, value: SeriesFormValues[Key]) {
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
      return next;
    });
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(undefined);
    setFieldErrors({});
    const title = values.title.trim();
    if (!title) {
      setFieldErrors({ title: "Give this recurring task a short, specific title." });
      return;
    }

    const recurrenceValidation = recurrenceFormValidationError(values.recurrence, {
      date: "2000-01-01",
      time: "",
    });
    if (recurrenceValidation) {
      setFieldErrors({ recurrence: recurrenceValidation.message });
      return;
    }

    const recurrence = recurrenceValuesToPayload(values.recurrence);
    if (!recurrence) {
      setFieldErrors({ recurrence: "Keep recurrence enabled for a series edit." });
      return;
    }

    onSubmit({
      title,
      description: values.description.trim() || null,
      status: values.status,
      priority: values.priority,
      tags: values.tags,
      file_ids: values.attachments.map((file) => file.id),
      recurrence,
    });
  }

  const recurrenceValidation = recurrenceFormValidationError(values.recurrence, {
    date: "2000-01-01",
    time: "",
  });
  const recurrenceError = fieldErrors.recurrence ?? recurrenceValidation?.message;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="flex max-h-[min(92svh,52rem)] w-[min(42rem,calc(100vw-2rem))] flex-col overflow-hidden rounded-xl border-border bg-card p-0 text-card-foreground shadow-none sm:max-w-none"
      >
        <form onSubmit={handleSubmit} className="flex min-h-0 flex-1 flex-col" aria-describedby={formError ? "task-series-error" : undefined}>
          <DialogHeader className="border-b border-border/70 px-6 py-6 sm:px-7">
            <DialogTitle className="text-xl font-semibold tracking-[-0.03em]">Edit recurring task</DialogTitle>
            <DialogDescription className="mt-2 max-w-md text-sm leading-6">
              Changes apply to future occurrences that have not been customized. Past and edited occurrences stay as they are.
            </DialogDescription>
          </DialogHeader>

          <div className="min-h-0 flex-1 space-y-6 overflow-y-auto px-6 py-6 sm:px-7">
            {formError ? <FieldError id="task-series-error" aria-live="polite" className="leading-6">{formError}</FieldError> : null}

            <FormField id="task-series-title" label="Title" error={fieldErrors.title}>
              <Input
                id="task-series-title"
                value={values.title}
                onChange={(event) => update("title", event.target.value)}
                maxLength={200}
                autoFocus
                disabled={isSaving}
                aria-invalid={fieldErrors.title ? true : undefined}
                aria-describedby={fieldDescribedBy("task-series-title", undefined, fieldErrors.title)}
                className="min-h-11 bg-background"
              />
            </FormField>

            <div className="grid gap-5 sm:grid-cols-2">
              <FormField id="task-series-status" label="Status">
                <Select value={values.status} onValueChange={(value) => update("status", value as TaskStatus)} disabled={isSaving}>
                  <SelectTrigger id="task-series-status" className="min-h-11 w-full bg-background">
                    <SelectValue><TaskOptionValue option={statusOption(values.status)} /></SelectValue>
                  </SelectTrigger>
                  <SelectContent>
                    {TASK_STATUSES.map((option) => <SelectItem key={option.value} value={option.value}><TaskOptionValue option={option} /></SelectItem>)}
                  </SelectContent>
                </Select>
              </FormField>
              <FormField id="task-series-priority" label="Priority">
                <Select value={values.priority} onValueChange={(value) => update("priority", value as TaskPriority)} disabled={isSaving}>
                  <SelectTrigger id="task-series-priority" className="min-h-11 w-full bg-background">
                    <SelectValue><TaskOptionValue option={priorityOption(values.priority)} /></SelectValue>
                  </SelectTrigger>
                  <SelectContent>
                    {TASK_PRIORITIES.map((option) => <SelectItem key={option.value} value={option.value}><TaskOptionValue option={option} /></SelectItem>)}
                  </SelectContent>
                </Select>
              </FormField>
            </div>

            <FormField id="task-series-description" label="Description">
              <Textarea
                id="task-series-description"
                value={values.description}
                onChange={(event) => update("description", event.target.value)}
                maxLength={10_000}
                disabled={isSaving}
                className="min-h-28 resize-y bg-background leading-6"
              />
            </FormField>

            <FormField id="task-series-tags" label="Tags">
              <TagPicker
                id="task-series-tags"
                tags={availableTags}
                value={values.tags}
                onChange={(tags) => update("tags", tags)}
                onCreateTag={onCreateTag}
                disabled={isSaving}
              />
            </FormField>

            <FormField id="task-series-attachments" label="Attachments">
              <FileAttachmentPicker
                id="task-series-attachments"
                value={values.attachments}
                onChange={(attachments) => update("attachments", attachments)}
                disabled={isSaving}
                hideLabel
              />
            </FormField>

            <section className="rounded-lg border border-border/80 bg-background/35 p-4 sm:p-5" aria-labelledby="task-series-repeat-heading">
              <div>
                <h3 id="task-series-repeat-heading" className="text-sm font-medium text-foreground">Repeat schedule</h3>
                <p className="mt-1 text-xs leading-5 text-muted-foreground">The original start time remains the series anchor.</p>
              </div>
              <div className="mt-5">
                <TaskRecurrenceBuilder
                  values={values.recurrence}
                  onChange={(recurrence) => update("recurrence", recurrence)}
                  disabled={isSaving}
                  showToggle={false}
                  idPrefix="task-series-recurrence"
                  error={recurrenceError}
                  errorField={recurrenceValidation?.field as RecurrenceFormErrorField | undefined}
                />
              </div>
            </section>
          </div>

          <DialogFooter className="mx-0! mb-0! flex-col-reverse items-stretch gap-2 rounded-none border-t border-border/70 bg-card px-6 py-4 sm:flex-row sm:items-center sm:justify-end sm:px-7">
            <DialogClose type="button" render={<Button variant="outline" size="lg" disabled={isSaving} className="w-full sm:w-auto" />}>Cancel</DialogClose>
            <Button type="submit" size="lg" disabled={isSaving} className="w-full sm:w-auto">{isSaving ? "Saving…" : "Save series"}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

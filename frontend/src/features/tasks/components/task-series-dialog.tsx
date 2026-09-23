"use client";

import { useState, type FormEvent } from "react";
import { SuggestedTags } from "@/components/suggested-tags";
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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import type { TaskPriority, TaskSeries, TaskSeriesUpdateInput, TaskStatus } from "../api";
import {
  recurrenceFormError,
  recurrenceValuesFromPayload,
  recurrenceValuesToPayload,
  type RecurrenceFormValues,
} from "../recurrence";
import { appendTagInput, parseTagInput, priorityOption, statusOption, TASK_PRIORITIES, TASK_STATUSES } from "../utils";
import { TaskOptionValue } from "./task-option-value";
import { TaskRecurrenceBuilder } from "./task-recurrence-builder";

type TaskSeriesDialogProps = {
  open: boolean;
  series: TaskSeries | null;
  isSaving: boolean;
  suggestedTags: string[];
  suggestionsPending: boolean;
  onOpenChange: (open: boolean) => void;
  onSubmit: (payload: TaskSeriesUpdateInput) => void;
};

type SeriesFormValues = {
  title: string;
  description: string;
  status: TaskStatus;
  priority: TaskPriority;
  tags: string;
  recurrence: RecurrenceFormValues;
};

function formValuesFromSeries(series: TaskSeries | null): SeriesFormValues {
  return {
    title: series?.title ?? "",
    description: series?.description ?? "",
    status: series?.status ?? "backlog",
    priority: series?.priority ?? "none",
    tags: series?.tags.join(", ") ?? "",
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
  suggestedTags,
  suggestionsPending,
  onOpenChange,
  onSubmit,
}: TaskSeriesDialogProps) {
  const [values, setValues] = useState<SeriesFormValues>(() => formValuesFromSeries(series));
  const [formError, setFormError] = useState<string>();

  function update<Key extends keyof SeriesFormValues>(key: Key, value: SeriesFormValues[Key]) {
    setValues((current) => ({ ...current, [key]: value }));
    setFormError(undefined);
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const title = values.title.trim();
    if (!title) {
      setFormError("Give this recurring task a short, specific title.");
      return;
    }

    const recurrenceError = recurrenceFormError(values.recurrence, { date: "2000-01-01", time: "" });
    if (recurrenceError) {
      setFormError(recurrenceError);
      return;
    }

    const recurrence = recurrenceValuesToPayload(values.recurrence);
    if (!recurrence) {
      setFormError("Keep recurrence enabled for a series edit.");
      return;
    }

    onSubmit({
      title,
      description: values.description.trim() || null,
      status: values.status,
      priority: values.priority,
      tags: parseTagInput(values.tags),
      recurrence,
    });
  }

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

            <div>
              <Label htmlFor="task-series-title" className="text-sm text-foreground">Title</Label>
              <Input
                id="task-series-title"
                value={values.title}
                onChange={(event) => update("title", event.target.value)}
                maxLength={200}
                autoFocus
                disabled={isSaving}
                className="mt-2 min-h-11 bg-background"
              />
            </div>

            <div className="grid gap-5 sm:grid-cols-2">
              <div>
                <Label htmlFor="task-series-status" className="text-sm text-foreground">Status</Label>
                <Select value={values.status} onValueChange={(value) => update("status", value as TaskStatus)} disabled={isSaving}>
                  <SelectTrigger id="task-series-status" className="mt-2 min-h-11 w-full bg-background">
                    <SelectValue><TaskOptionValue option={statusOption(values.status)} /></SelectValue>
                  </SelectTrigger>
                  <SelectContent>
                    {TASK_STATUSES.map((option) => <SelectItem key={option.value} value={option.value}><TaskOptionValue option={option} /></SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label htmlFor="task-series-priority" className="text-sm text-foreground">Priority</Label>
                <Select value={values.priority} onValueChange={(value) => update("priority", value as TaskPriority)} disabled={isSaving}>
                  <SelectTrigger id="task-series-priority" className="mt-2 min-h-11 w-full bg-background">
                    <SelectValue><TaskOptionValue option={priorityOption(values.priority)} /></SelectValue>
                  </SelectTrigger>
                  <SelectContent>
                    {TASK_PRIORITIES.map((option) => <SelectItem key={option.value} value={option.value}><TaskOptionValue option={option} /></SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div>
              <Label htmlFor="task-series-description" className="text-sm text-foreground">Description</Label>
              <Textarea
                id="task-series-description"
                value={values.description}
                onChange={(event) => update("description", event.target.value)}
                maxLength={10_000}
                disabled={isSaving}
                className="mt-2 min-h-28 resize-y bg-background leading-6"
              />
            </div>

            <div>
              <Label htmlFor="task-series-tags" className="text-sm text-foreground">Tags</Label>
              <Input
                id="task-series-tags"
                value={values.tags}
                onChange={(event) => update("tags", event.target.value)}
                disabled={isSaving}
                className="mt-2 min-h-11 bg-background"
                placeholder="work, home, focus"
              />
              <SuggestedTags
                selectedTags={parseTagInput(values.tags)}
                suggestions={suggestedTags}
                pending={suggestionsPending}
                disabled={isSaving}
                onSelect={(tag) => update("tags", appendTagInput(values.tags, tag))}
              />
              <p className="mt-2 text-xs leading-5 text-muted-foreground">Separate tags with commas.</p>
            </div>

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

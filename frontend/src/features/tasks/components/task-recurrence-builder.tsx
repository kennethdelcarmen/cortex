"use client";

import { Globe2, Repeat2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { FieldError } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { cn } from "@/lib/utils";
import {
  COMMON_TIMEZONES,
  RECURRENCE_FREQUENCIES,
  RECURRENCE_WEEKDAYS,
  recurrenceSummary,
  type RecurrenceFormValues,
} from "../recurrence";
import type { TaskDateTimeValue } from "../utils";

const monthFormatter = new Intl.DateTimeFormat(undefined, { month: "long" });

function monthName(month: number) {
  return monthFormatter.format(new Date(2020, month - 1, 1));
}

type TaskRecurrenceBuilderProps = {
  values: RecurrenceFormValues;
  anchor?: TaskDateTimeValue;
  onChange: (values: RecurrenceFormValues) => void;
  disabled?: boolean;
  error?: string;
  idPrefix?: string;
  showToggle?: boolean;
};

export function TaskRecurrenceBuilder({
  values,
  anchor,
  onChange,
  disabled = false,
  error,
  idPrefix = "task-recurrence",
  showToggle = true,
}: TaskRecurrenceBuilderProps) {
  function update<Key extends keyof RecurrenceFormValues>(
    key: Key,
    value: RecurrenceFormValues[Key],
  ) {
    onChange({ ...values, [key]: value });
  }

  function toggleWeekday(value: RecurrenceFormValues["weekdays"][number]) {
    const weekdays = values.weekdays.includes(value)
      ? values.weekdays.filter((weekday) => weekday !== value)
      : [...values.weekdays, value];
    onChange({ ...values, weekdays });
  }

  function changeFrequency(value: RecurrenceFormValues["frequency"]) {
    const weekdays =
      value === "weekly" && values.weekdays.length === 0
        ? [RECURRENCE_WEEKDAYS[0].value]
        : values.weekdays;
    onChange({ ...values, frequency: value, weekdays });
  }

  const content = (
    <div className="space-y-5 border-l-2 border-primary/70 pl-4 sm:pl-5">
      <div className="grid gap-3 sm:grid-cols-[auto_6rem_minmax(0,1fr)] sm:items-end">
        <div>
          <Label htmlFor={`${idPrefix}-frequency`} className="text-sm text-foreground">
            Repeat every
          </Label>
          <Select
            value={values.frequency}
            onValueChange={(value) => changeFrequency(value as RecurrenceFormValues["frequency"])}
            disabled={disabled}
          >
            <SelectTrigger id={`${idPrefix}-frequency`} className="mt-2 min-h-11 bg-background sm:min-w-32">
              <SelectValue>
                {RECURRENCE_FREQUENCIES.find((frequency) => frequency.value === values.frequency)?.label ?? "Week"}
              </SelectValue>
            </SelectTrigger>
            <SelectContent>
              {RECURRENCE_FREQUENCIES.map((frequency) => (
                <SelectItem key={frequency.value} value={frequency.value}>
                  {frequency.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <Input
          id={`${idPrefix}-interval`}
          type="number"
          min={1}
          max={365}
          value={values.interval}
          onChange={(event) => update("interval", Number(event.target.value) || 1)}
          disabled={disabled}
          className="mt-2 min-h-11 bg-background sm:mt-0"
          aria-label="Repeat interval"
        />
        <p className="pb-2 text-sm text-muted-foreground sm:pb-0">
          {values.interval === 1
            ? `${RECURRENCE_FREQUENCIES.find((frequency) => frequency.value === values.frequency)?.unit ?? "week"}`
            : `${RECURRENCE_FREQUENCIES.find((frequency) => frequency.value === values.frequency)?.unit ?? "week"}s`}
        </p>
      </div>

      {values.frequency === "weekly" ? (
        <fieldset>
          <legend className="text-sm font-medium text-foreground">On these days</legend>
          <div className="mt-2 grid grid-cols-4 gap-2 sm:grid-cols-7">
            {RECURRENCE_WEEKDAYS.map((weekday) => {
              const selected = values.weekdays.includes(weekday.value);
              return (
                <Button
                  key={weekday.value}
                  type="button"
                  variant={selected ? "secondary" : "outline"}
                  aria-pressed={selected}
                  aria-label={weekday.label}
                  disabled={disabled}
                  onClick={() => toggleWeekday(weekday.value)}
                  className={cn(
                    "min-h-10 px-2 text-xs",
                    selected && "border-primary/60 bg-primary/15 text-primary-strong",
                  )}
                >
                  {weekday.shortLabel}
                </Button>
              );
            })}
          </div>
        </fieldset>
      ) : null}

      {values.frequency === "monthly" ? (
        <div>
          <Label htmlFor={`${idPrefix}-month-day`} className="text-sm font-medium text-foreground">
            On day
          </Label>
          <Input
            id={`${idPrefix}-month-day`}
            type="number"
            min={1}
            max={31}
            value={values.monthDay}
            onChange={(event) =>
              update("monthDay", event.target.value === "" ? "" : Number(event.target.value))
            }
            disabled={disabled}
            className="mt-2 min-h-11 max-w-32 bg-background"
          />
          <p className="mt-2 text-xs leading-5 text-muted-foreground">
            If a month does not have that date, Cortex uses its last valid day.
          </p>
        </div>
      ) : null}

      {values.frequency === "yearly" ? (
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <Label htmlFor={`${idPrefix}-month`} className="text-sm font-medium text-foreground">
              In month
            </Label>
            <Select
              value={String(values.month)}
              onValueChange={(value) => update("month", Number(value))}
              disabled={disabled}
            >
              <SelectTrigger id={`${idPrefix}-month`} className="mt-2 min-h-11 w-full bg-background">
                <SelectValue>{monthName(values.month)}</SelectValue>
              </SelectTrigger>
              <SelectContent>
                {Array.from({ length: 12 }, (_, index) => {
                  const month = index + 1;
                  return (
                    <SelectItem key={month} value={String(month)}>
                      {monthName(month)}
                    </SelectItem>
                  );
                })}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label htmlFor={`${idPrefix}-day`} className="text-sm font-medium text-foreground">
              On day
            </Label>
            <Input
              id={`${idPrefix}-day`}
              type="number"
              min={1}
              max={31}
              value={values.day}
              onChange={(event) =>
                update("day", event.target.value === "" ? "" : Number(event.target.value))
              }
              disabled={disabled}
              className="mt-2 min-h-11 bg-background"
            />
          </div>
        </div>
      ) : null}

      <fieldset>
        <legend className="text-sm font-medium text-foreground">Ends</legend>
        <div className="mt-2 grid gap-2 sm:grid-cols-3">
          {([
            ["never", "Never"],
            ["date", "On date"],
            ["count", "After count"],
          ] as const).map(([mode, label]) => (
            <label
              key={mode}
              className={cn(
                "flex min-h-11 cursor-pointer items-center gap-2 rounded-md border px-3 text-sm transition-colors",
                values.endMode === mode
                  ? "border-primary/60 bg-primary/10 text-foreground"
                  : "border-border bg-background text-muted-foreground hover:bg-muted/50",
              )}
            >
              <input
                type="radio"
                name={`${idPrefix}-end-mode`}
                value={mode}
                checked={values.endMode === mode}
                onChange={() => update("endMode", mode)}
                disabled={disabled}
                className="size-4 accent-[var(--primary-strong)]"
              />
              {label}
            </label>
          ))}
        </div>
        {values.endMode === "date" ? (
          <div className="mt-3 max-w-56">
            <Label htmlFor={`${idPrefix}-until-date`} className="sr-only">
              End date
            </Label>
            <Input
              id={`${idPrefix}-until-date`}
              type="date"
              value={values.untilDate}
              onChange={(event) => update("untilDate", event.target.value)}
              disabled={disabled}
              className="min-h-11 bg-background"
            />
          </div>
        ) : null}
        {values.endMode === "count" ? (
          <div className="mt-3 flex max-w-56 items-center gap-2">
            <Label htmlFor={`${idPrefix}-occurrence-count`} className="sr-only">
              Number of occurrences
            </Label>
            <Input
              id={`${idPrefix}-occurrence-count`}
              type="number"
              min={1}
              max={100000}
              value={values.occurrenceCount}
              onChange={(event) => update("occurrenceCount", Number(event.target.value) || 1)}
              disabled={disabled}
              className="min-h-11 bg-background"
            />
            <span className="text-sm text-muted-foreground">occurrences</span>
          </div>
        ) : null}
      </fieldset>

      <div>
        <Label htmlFor={`${idPrefix}-timezone`} className="text-sm font-medium text-foreground">
          Time zone
        </Label>
        <div className="relative mt-2">
          <Globe2 aria-hidden="true" className="pointer-events-none absolute left-3 top-3.5 size-4 text-primary-strong" />
          <Input
            id={`${idPrefix}-timezone`}
            list={`${idPrefix}-timezone-options`}
            value={values.timezone}
            onChange={(event) => update("timezone", event.target.value)}
            disabled={disabled}
            className="min-h-11 bg-background pl-9 font-mono text-xs"
            placeholder="Asia/Manila"
          />
          <datalist id={`${idPrefix}-timezone-options`}>
            {COMMON_TIMEZONES.map((timezone) => (
              <option key={timezone} value={timezone} />
            ))}
          </datalist>
        </div>
        <p className="mt-2 text-xs leading-5 text-muted-foreground">
          Times repeat at the same local wall-clock time in this zone.
        </p>
      </div>

      <p className="rounded-md bg-accent/55 px-3 py-2.5 text-sm leading-5 text-accent-foreground" aria-live="polite">
        <Repeat2 aria-hidden="true" className="mr-1.5 inline-block size-4 align-[-0.15em] text-primary-strong" />
        {recurrenceSummary(values, anchor)}
      </p>

      {error ? <FieldError id={`${idPrefix}-error`} aria-live="polite" className="leading-6">{error}</FieldError> : null}
    </div>
  );

  if (!showToggle) {
    return content;
  }

  return (
    <section className="rounded-lg border border-border/80 bg-background/35 p-4 sm:p-5" aria-labelledby={`${idPrefix}-heading`}>
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Repeat2 aria-hidden="true" className="size-4 text-primary-strong" />
            <h3 id={`${idPrefix}-heading`} className="text-sm font-medium text-foreground">Repeat</h3>
          </div>
          <p className="mt-1 text-xs leading-5 text-muted-foreground">
            Create the same task on a rhythm that fits your life.
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2 text-sm text-foreground">
          <Checkbox
            id={`${idPrefix}-enabled`}
            checked={values.enabled}
            onCheckedChange={(checked) => {
              const enabled = checked === true;
              const timezone =
                enabled && values.timezone === "UTC" && typeof window !== "undefined"
                  ? Intl.DateTimeFormat().resolvedOptions().timeZone || values.timezone
                  : values.timezone;
              onChange({ ...values, enabled, timezone });
            }}
            disabled={disabled}
          />
          <Label htmlFor={`${idPrefix}-enabled`} className="cursor-pointer text-sm text-foreground">
            {values.enabled ? "On" : "Off"}
          </Label>
        </div>
      </div>
      {values.enabled ? <div className="mt-5">{content}</div> : null}
      {!values.enabled && error ? <FieldError id={`${idPrefix}-error`} aria-live="polite" className="mt-3 leading-6">{error}</FieldError> : null}
    </section>
  );
}

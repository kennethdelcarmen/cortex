"use client";

import { CalendarDays, Check, Clock3, RotateCcw } from "lucide-react";
import { useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import { FieldError } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import {
  Popover,
  PopoverContent,
  PopoverDescription,
  PopoverHeader,
  PopoverTitle,
  PopoverTrigger,
} from "@/components/ui/popover";
import { cn } from "@/lib/utils";
import type { TaskDateTimeValue } from "../utils";

type TaskDateTimePickerProps = {
  id: string;
  label: string;
  value: TaskDateTimeValue;
  error?: string;
  disabled?: boolean;
  showFieldClear?: boolean;
  onChange: (value: TaskDateTimeValue) => void;
  onCommit?: (value: TaskDateTimeValue) => void;
};

function dateValueToDate(value: string) {
  if (!value) {
    return undefined;
  }

  const date = new Date(`${value}T12:00:00`);
  return Number.isNaN(date.getTime()) ? undefined : date;
}

function dateToValue(date: Date) {
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

function formatDate(value: string) {
  const date = dateValueToDate(value);

  if (!date) {
    return "Pick a date";
  }

  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(date);
}

function formatTime(value: string) {
  if (!value) {
    return "Set time";
  }

  const [hours, minutes] = value.split(":").map(Number);
  const date = new Date();
  date.setHours(hours, minutes, 0, 0);

  return new Intl.DateTimeFormat(undefined, {
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

export function TaskDateTimePicker({
  id,
  label,
  value,
  error,
  disabled = false,
  showFieldClear = true,
  onChange,
  onCommit,
}: TaskDateTimePickerProps) {
  const [dateOpen, setDateOpen] = useState(false);
  const [timeOpen, setTimeOpen] = useState(false);
  const [timeDraft, setTimeDraft] = useState(value.time);
  const ignoreTimeClose = useRef(false);

  function commit(nextValue: TaskDateTimeValue) {
    onChange(nextValue);
    onCommit?.(nextValue);
  }

  function clearValue() {
    const nextValue = { date: "", time: "" };
    commit(nextValue);
    setDateOpen(false);
    ignoreTimeClose.current = true;
    setTimeOpen(false);
  }

  function handleDateSelect(date: Date | undefined) {
    if (!date) {
      return;
    }

    commit({ ...value, date: dateToValue(date) });
    setDateOpen(false);
  }

  function handleTimeOpenChange(nextOpen: boolean) {
    if (!nextOpen && timeOpen) {
      if (ignoreTimeClose.current) {
        ignoreTimeClose.current = false;
      } else {
        commit({ ...value, time: timeDraft });
      }
    }

    if (nextOpen) setTimeDraft(value.time);
    setTimeOpen(nextOpen);
  }

  function applyTime() {
    ignoreTimeClose.current = true;
    commit({ ...value, time: timeDraft });
    setTimeOpen(false);
  }

  const errorId = `${id}-error`;

  return (
    <div>
      <div className="flex items-center justify-between gap-3">
        <label htmlFor={`${id}-date`} className="text-sm font-medium text-foreground">
          {label}
        </label>
        {showFieldClear && (value.date || value.time) ? (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={clearValue}
            disabled={disabled}
            className="h-7 px-2 text-xs text-muted-foreground hover:text-foreground"
          >
            <RotateCcw aria-hidden="true" />
            Clear
          </Button>
        ) : null}
      </div>

      <div className="mt-2 grid grid-cols-[minmax(0,1fr)_minmax(0,0.72fr)] gap-2">
        <Popover open={dateOpen} onOpenChange={setDateOpen}>
          <PopoverTrigger
            render={
              <Button
                id={`${id}-date`}
                type="button"
                variant="outline"
                disabled={disabled}
                aria-describedby={error ? errorId : undefined}
                aria-invalid={Boolean(error)}
                className={cn(
                  "min-h-11 min-w-0 justify-start gap-2 bg-background font-normal",
                  error && "border-destructive",
                )}
              />
            }
          >
            <CalendarDays aria-hidden="true" className="size-4 shrink-0 text-muted-foreground" />
            <span className="truncate">{formatDate(value.date)}</span>
          </PopoverTrigger>
          <PopoverContent align="start" className="w-auto p-0">
            <PopoverHeader className="sr-only">
              <PopoverTitle>{label} date</PopoverTitle>
              <PopoverDescription>Choose a date for this task window.</PopoverDescription>
            </PopoverHeader>
            <Calendar
              mode="single"
              selected={dateValueToDate(value.date)}
              onSelect={handleDateSelect}
              autoFocus
            />
            {value.date || value.time ? (
              <div className="border-t border-border/70 p-2">
                <Button type="button" variant="ghost" size="sm" className="w-full" onClick={clearValue}>
                  Clear task window
                </Button>
              </div>
            ) : null}
          </PopoverContent>
        </Popover>

        <Popover open={timeOpen} onOpenChange={handleTimeOpenChange}>
          <PopoverTrigger
            render={
              <Button
                id={`${id}-time`}
                type="button"
                variant="outline"
                disabled={disabled}
                aria-describedby={error ? errorId : undefined}
                aria-invalid={Boolean(error)}
                className={cn(
                  "min-h-11 min-w-0 justify-start gap-2 bg-background font-normal",
                  error && "border-destructive",
                )}
              />
            }
          >
            <Clock3 aria-hidden="true" className="size-4 shrink-0 text-muted-foreground" />
            <span className="truncate">{formatTime(value.time)}</span>
          </PopoverTrigger>
          <PopoverContent align="end" className="w-64">
            <PopoverHeader>
              <PopoverTitle>{label} time</PopoverTitle>
              <PopoverDescription>Use your local timezone.</PopoverDescription>
            </PopoverHeader>
            <Input
              aria-label={`${label} time`}
              type="time"
              value={timeDraft}
              onChange={(event) => setTimeDraft(event.target.value)}
              autoFocus
              className="min-h-11 bg-background"
            />
            <div className="flex justify-end gap-2 pt-1">
              <Button type="button" variant="outline" size="sm" onClick={() => setTimeDraft("")}>
                Clear
              </Button>
              <Button type="button" size="sm" onClick={applyTime}>
                <Check aria-hidden="true" />
                Apply
              </Button>
            </div>
          </PopoverContent>
        </Popover>
      </div>
      {error ? <FieldError id={errorId} aria-live="polite" className="mt-2">{error}</FieldError> : null}
    </div>
  );
}

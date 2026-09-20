import type {
  RecurrenceFrequency,
  RecurrenceWeekday,
  TaskRecurrenceInput,
} from "./api";
import type { TaskDateTimeValue } from "./utils";

export const RECURRENCE_WEEKDAYS: Array<{
  value: RecurrenceWeekday;
  label: string;
  shortLabel: string;
}> = [
  { value: "monday", label: "Monday", shortLabel: "Mon" },
  { value: "tuesday", label: "Tuesday", shortLabel: "Tue" },
  { value: "wednesday", label: "Wednesday", shortLabel: "Wed" },
  { value: "thursday", label: "Thursday", shortLabel: "Thu" },
  { value: "friday", label: "Friday", shortLabel: "Fri" },
  { value: "saturday", label: "Saturday", shortLabel: "Sat" },
  { value: "sunday", label: "Sunday", shortLabel: "Sun" },
];

export const RECURRENCE_FREQUENCIES: Array<{
  value: RecurrenceFrequency;
  label: string;
  unit: string;
}> = [
  { value: "daily", label: "Day", unit: "day" },
  { value: "weekly", label: "Week", unit: "week" },
  { value: "monthly", label: "Month", unit: "month" },
  { value: "yearly", label: "Year", unit: "year" },
];

export type RecurrenceEndMode = "never" | "date" | "count";

export type RecurrenceFormValues = {
  enabled: boolean;
  timezone: string;
  frequency: RecurrenceFrequency;
  interval: number;
  weekdays: RecurrenceWeekday[];
  monthDay: number | "";
  month: number;
  day: number | "";
  endMode: RecurrenceEndMode;
  untilDate: string;
  occurrenceCount: number;
};

export const COMMON_TIMEZONES = [
  "UTC",
  "Asia/Manila",
  "Asia/Singapore",
  "Asia/Tokyo",
  "Australia/Sydney",
  "Europe/London",
  "Europe/Paris",
  "America/Los_Angeles",
  "America/Chicago",
  "America/New_York",
];

function localWeekday(dateValue: string) {
  if (!dateValue) {
    return "monday" as RecurrenceWeekday;
  }

  const date = new Date(`${dateValue}T12:00:00`);
  const index = date.getDay();
  return RECURRENCE_WEEKDAYS[index === 0 ? 6 : index - 1].value;
}

export function defaultRecurrenceValues(anchor?: TaskDateTimeValue): RecurrenceFormValues {
  const date = anchor?.date || new Date().toISOString().slice(0, 10);
  const weekday = localWeekday(date);

  return {
    enabled: false,
    timezone: "UTC",
    frequency: "weekly",
    interval: 1,
    weekdays: [weekday],
    monthDay: Number(date.slice(-2)) || 1,
    month: Number(date.slice(5, 7)) || 1,
    day: Number(date.slice(-2)) || 1,
    endMode: "never",
    untilDate: "",
    occurrenceCount: 10,
  };
}

export function recurrenceValuesFromPayload(
  recurrence: TaskRecurrenceInput,
): RecurrenceFormValues {
  return {
    enabled: true,
    timezone: recurrence.timezone,
    frequency: recurrence.frequency,
    interval: recurrence.interval,
    weekdays: recurrence.weekdays,
    monthDay: recurrence.month_day ?? 1,
    month: recurrence.month ?? 1,
    day: recurrence.day ?? 1,
    endMode: recurrence.until_date ? "date" : recurrence.occurrence_count ? "count" : "never",
    untilDate: recurrence.until_date ?? "",
    occurrenceCount: recurrence.occurrence_count ?? 10,
  };
}

export function recurrenceValuesToPayload(values: RecurrenceFormValues): TaskRecurrenceInput | undefined {
  if (!values.enabled) {
    return undefined;
  }

  const monthDay = typeof values.monthDay === "number" ? values.monthDay : 1;
  const day = typeof values.day === "number" ? values.day : 1;

  return {
    timezone: values.timezone.trim(),
    frequency: values.frequency,
    interval: Math.max(1, Math.min(365, values.interval || 1)),
    weekdays: values.frequency === "weekly" ? values.weekdays : [],
    month_day: values.frequency === "monthly" ? monthDay : null,
    month: values.frequency === "yearly" ? values.month : null,
    day: values.frequency === "yearly" ? day : null,
    until_date: values.endMode === "date" ? values.untilDate || null : null,
    occurrence_count:
      values.endMode === "count"
        ? Math.max(1, Math.min(100_000, values.occurrenceCount || 1))
        : null,
  };
}

export function recurrenceFormError(
  values: RecurrenceFormValues,
  anchor?: TaskDateTimeValue,
) {
  if (!values.enabled) {
    return undefined;
  }

  if (!values.timezone.trim()) {
    return "Choose a time zone for this recurring task.";
  }

  if (!anchor?.date) {
    return "Set a start or due time to choose the first occurrence.";
  }

  if (values.frequency === "weekly" && values.weekdays.length === 0) {
    return "Choose at least one day for a weekly task.";
  }

  if (
    values.frequency === "monthly" &&
    (values.monthDay === "" || values.monthDay < 1 || values.monthDay > 31)
  ) {
    return "Enter a day from 1 to 31.";
  }

  if (
    values.frequency === "yearly" &&
    (values.day === "" || values.day < 1 || values.day > 31)
  ) {
    return "Enter a day from 1 to 31.";
  }

  if (values.endMode === "date" && !values.untilDate) {
    return "Choose an end date or select Never.";
  }

  if (values.endMode === "count" && (!values.occurrenceCount || values.occurrenceCount < 1)) {
    return "Enter at least one occurrence or select Never.";
  }

  return undefined;
}

function frequencyText(values: RecurrenceFormValues) {
  const frequency = RECURRENCE_FREQUENCIES.find((item) => item.value === values.frequency);
  const unit = frequency?.unit ?? "week";
  const amount = values.interval === 1 ? "every" : `every ${values.interval}`;
  return `${amount} ${unit}${values.interval === 1 ? "" : "s"}`;
}

export function recurrenceSummary(
  values: RecurrenceFormValues,
  anchor?: TaskDateTimeValue,
) {
  const parts = [frequencyText(values)];

  if (values.frequency === "weekly") {
    const labels = RECURRENCE_WEEKDAYS
      .filter((weekday) => values.weekdays.includes(weekday.value))
      .map((weekday) => weekday.shortLabel);
    if (labels.length) {
      parts.push(`on ${labels.join(", ")}`);
    }
  } else if (values.frequency === "monthly") {
    parts.push(`on day ${values.monthDay || "…"}`);
  } else if (values.frequency === "yearly") {
    const month = new Intl.DateTimeFormat(undefined, { month: "long" }).format(
      new Date(2020, values.month - 1, 1),
    );
    parts.push(`on ${month} ${values.day || "…"}`);
  }

  if (anchor?.time) {
    const time = new Date(`2000-01-01T${anchor.time}`);
    if (!Number.isNaN(time.getTime())) {
      parts.push(`at ${new Intl.DateTimeFormat(undefined, {
        hour: "numeric",
        minute: "2-digit",
      }).format(time)}`);
    }
  }

  if (values.endMode === "date" && values.untilDate) {
    parts.push(`until ${new Intl.DateTimeFormat(undefined, {
      month: "short",
      day: "numeric",
      year: "numeric",
    }).format(new Date(`${values.untilDate}T12:00:00`))}`);
  } else if (values.endMode === "count") {
    parts.push(`for ${values.occurrenceCount} occurrence${values.occurrenceCount === 1 ? "" : "s"}`);
  }

  return parts.join(" ");
}

export function recurrenceStateLabel(state: "active" | "paused" | "ended") {
  switch (state) {
    case "paused":
      return "Paused";
    case "ended":
      return "Ended";
    default:
      return "Active";
  }
}

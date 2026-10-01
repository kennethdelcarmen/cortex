"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarClock, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { useFeedback } from "@/components/feedback";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
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
import { SelectItem, SelectSeparator } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { currentLocalDateInput } from "@/lib/date";
import { cn } from "@/lib/utils";
import {
  createMoneyCategory,
  createMoneyPayee,
  createMoneyRecurringTransaction,
  getMoneyRecurringTransaction,
  moneyRecurringTransactionsQueryKey,
  updateMoneyRecurringTransaction,
  type MoneyAccount,
  type MoneyCategory,
  type MoneyPayee,
  type MoneyRecurrenceFrequency,
  type MoneyRecurrenceInput,
  type MoneyRecurrenceWeekday,
  type MoneyRecurringPostingInput,
  type MoneyRecurringTransaction,
  type MoneyRecurringTransactionCreateInput,
  type MoneyRecurringTransactionUpdateInput,
} from "../api";
import { categoriesForKind, invalidateMoneyQueries } from "../hooks";
import {
  accountLabel,
  describeMoneyError,
  formatAmountInput,
} from "../utils";
import { MoneyResourceCreateDialog, type MoneyResourceKind } from "./money-resource-create-dialog";
import { MoneySelectField } from "./money-select-field";

type RecurringTransactionDrawerProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSaved?: () => void;
  recurringTransactionId?: string | null;
  defaultDate?: string;
  accounts: MoneyAccount[];
  payees: MoneyPayee[];
  categories: MoneyCategory[];
};

type RecurringEntryMode = "expense" | "income" | "transfer";
type EndMode = "none" | "date" | "count";

const recurrenceWeekdays: Array<{ value: MoneyRecurrenceWeekday; label: string; short: string }> = [
  { value: "monday", label: "Monday", short: "M" },
  { value: "tuesday", label: "Tuesday", short: "T" },
  { value: "wednesday", label: "Wednesday", short: "W" },
  { value: "thursday", label: "Thursday", short: "T" },
  { value: "friday", label: "Friday", short: "F" },
  { value: "saturday", label: "Saturday", short: "S" },
  { value: "sunday", label: "Sunday", short: "S" },
];

const months = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];

function browserTimezone() {
  return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
}

function weekdayForDate(value: string): MoneyRecurrenceWeekday {
  const date = new Date(`${value}T00:00:00`);
  return recurrenceWeekdays[date.getDay() === 0 ? 6 : date.getDay() - 1].value;
}

function dateLabel(value: string | null) {
  if (!value) return "None scheduled";
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(new Date(`${value}T00:00:00`));
}

function recurrenceLabel(recurrence: MoneyRecurrenceInput) {
  const interval = recurrence.interval === 1 ? "" : ` every ${recurrence.interval}`;
  if (recurrence.frequency === "weekly") {
    const days = (recurrence.weekdays ?? [])
      .map((day) => recurrenceWeekdays.find((item) => item.value === day)?.label)
      .filter(Boolean)
      .join(", ");
    return `Weekly${interval}${days ? ` on ${days}` : ""}`;
  }
  if (recurrence.frequency === "monthly") {
    return `Monthly${interval}${recurrence.month_day ? ` on day ${recurrence.month_day}` : ""}`;
  }
  const month = recurrence.month ? months[recurrence.month - 1] : "";
  return `Yearly${interval}${month && recurrence.day ? ` on ${month} ${recurrence.day}` : ""}`;
}

function guidedMode(
  schedule: MoneyRecurringTransaction,
  categories: MoneyCategory[],
): RecurringEntryMode | null {
  const accountPostings = schedule.postings.filter((posting) => posting.account_id);
  const categoryPostings = schedule.postings.filter((posting) => posting.category_id);
  if (accountPostings.length === 2 && categoryPostings.length === 0) return "transfer";
  if (accountPostings.length !== 1 || categoryPostings.length !== 1) return null;
  const category = categories.find((item) => item.id === categoryPostings[0].category_id);
  if (!category) return null;
  if (category.kind === "expense" && Number(accountPostings[0].amount) < 0) return "expense";
  if (category.kind === "income" && Number(accountPostings[0].amount) > 0) return "income";
  return null;
}

function recurrenceDraft(
  schedule: MoneyRecurringTransaction,
  categories: MoneyCategory[],
) {
  const mode = guidedMode(schedule, categories);
  if (!mode) return null;
  const accountPostings = schedule.postings.filter((posting) => posting.account_id);
  const categoryPostings = schedule.postings.filter((posting) => posting.category_id);
  const accountPosting = accountPostings.find((posting) => (
    mode === "income" ? Number(posting.amount) > 0 : Number(posting.amount) < 0
  )) ?? accountPostings[0];
  const destinationPosting = mode === "transfer"
    ? accountPostings.find((posting) => posting.id !== accountPosting.id)
    : undefined;
  const amount = accountPosting ? Math.abs(Number(accountPosting.amount)).toString() : "";
  const recurrence = schedule.recurrence;
  const endMode: EndMode = recurrence.until_date ? "date" : recurrence.occurrence_count ? "count" : "none";

  return {
    mode,
    date: schedule.start_date,
    name: schedule.name,
    payeeId: schedule.payee_id ?? "",
    memo: schedule.memo ?? "",
    amount: formatAmountInput(amount, accountPosting?.currency_code ?? "PHP"),
    accountId: accountPosting?.account_id ?? "",
    destinationAccountId: destinationPosting?.account_id ?? "",
    categoryId: categoryPostings[0]?.category_id ?? "",
    frequency: recurrence.frequency,
    interval: String(recurrence.interval),
    weekdays: recurrence.weekdays,
    monthDay: recurrence.month_day ? String(recurrence.month_day) : "",
    yearMonth: recurrence.month ? String(recurrence.month) : "",
    yearDay: recurrence.day ? String(recurrence.day) : "",
    endMode,
    untilDate: recurrence.until_date ?? "",
    occurrenceCount: recurrence.occurrence_count ? String(recurrence.occurrence_count) : "",
    timezone: recurrence.timezone,
  };
}

function ReadOnlyRecurringTemplate({
  schedule,
  accounts,
  categories,
  payees,
}: {
  schedule: MoneyRecurringTransaction;
  accounts: MoneyAccount[];
  categories: MoneyCategory[];
  payees: MoneyPayee[];
}) {
  const accountById = new Map(accounts.map((account) => [account.id, account]));
  const categoryById = new Map(categories.map((category) => [category.id, category]));
  const payee = payees.find((item) => item.id === schedule.payee_id);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="min-h-0 flex-1 space-y-6 overflow-y-auto px-6 py-6 sm:px-8">
        <div>
          <p className="font-mono text-[0.65rem] uppercase tracking-[0.14em] text-muted-foreground">
            {schedule.state} · starts {dateLabel(schedule.start_date)}
          </p>
          <h2 className="mt-2 text-xl font-semibold tracking-[-0.025em]">{schedule.name}</h2>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">
            {[payee?.name, schedule.memo, recurrenceLabel(schedule.recurrence)].filter(Boolean).join(" · ")}
          </p>
        </div>
        <div className="rounded-lg border border-border/70 bg-background p-4 text-sm">
          <p className="font-mono text-[0.62rem] uppercase tracking-[0.12em] text-muted-foreground">
            Advanced template
          </p>
          <p className="mt-2 leading-6 text-muted-foreground">
            This schedule has split postings and can be managed here, but the guided editor does not change its posting shape.
          </p>
        </div>
        <div className="space-y-3" aria-label="Recurring postings">
          {schedule.postings.map((posting) => {
            const account = posting.account_id ? accountById.get(posting.account_id) : undefined;
            const category = posting.category_id ? categoryById.get(posting.category_id) : undefined;
            return (
              <div key={posting.id} className="flex items-start justify-between gap-4 rounded-lg border border-border/70 bg-background p-4">
                <div>
                  <p className="text-sm font-medium">{account ? accountLabel(account) : category?.name ?? "Unknown posting"}</p>
                  <p className="mt-1 text-xs text-muted-foreground">{account ? "Account" : "Category"} · {posting.currency_code}</p>
                </div>
                <p className="font-mono text-sm font-medium">{posting.amount}</p>
              </div>
            );
          })}
        </div>
      </div>
      <DrawerFooter className="border-t border-border/70 bg-card px-6 py-4 sm:px-8">
        <DrawerClose render={<Button type="button" variant="outline" />}>Close</DrawerClose>
      </DrawerFooter>
    </div>
  );
}

export function RecurringTransactionDrawer({
  open,
  onOpenChange,
  onSaved,
  recurringTransactionId,
  defaultDate,
  accounts,
  payees,
  categories,
}: RecurringTransactionDrawerProps) {
  const queryClient = useQueryClient();
  const feedback = useFeedback();
  const [mode, setMode] = useState<RecurringEntryMode>("expense");
  const [date, setDate] = useState(defaultDate ?? currentLocalDateInput());
  const [name, setName] = useState("");
  const [payeeId, setPayeeId] = useState("");
  const [memo, setMemo] = useState("");
  const [amount, setAmount] = useState("");
  const [accountId, setAccountId] = useState("");
  const [destinationAccountId, setDestinationAccountId] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [frequency, setFrequency] = useState<MoneyRecurrenceFrequency>("monthly");
  const [interval, setInterval] = useState("1");
  const [weekdays, setWeekdays] = useState<MoneyRecurrenceWeekday[]>([]);
  const [monthDay, setMonthDay] = useState("");
  const [yearMonth, setYearMonth] = useState("");
  const [yearDay, setYearDay] = useState("");
  const [endMode, setEndMode] = useState<EndMode>("none");
  const [untilDate, setUntilDate] = useState("");
  const [occurrenceCount, setOccurrenceCount] = useState("");
  const [timezone, setTimezone] = useState("UTC");
  const [editing, setEditing] = useState(!recurringTransactionId);
  const [error, setError] = useState<string>();
  const [resourceDialogKind, setResourceDialogKind] = useState<MoneyResourceKind | null>(null);
  const [resourceDialogDisplayKind, setResourceDialogDisplayKind] = useState<MoneyResourceKind>("payee");
  const [resourceName, setResourceName] = useState("");
  const [resourceError, setResourceError] = useState<string>();
  const [resourceLabels, setResourceLabels] = useState<Record<string, string>>({});
  const initializedSessionRef = useRef<string | null>(null);

  const recurringQuery = useQuery({
    queryKey: [...moneyRecurringTransactionsQueryKey, recurringTransactionId],
    queryFn: () => getMoneyRecurringTransaction(recurringTransactionId ?? ""),
    enabled: open && Boolean(recurringTransactionId),
  });
  const schedule = recurringQuery.data;
  const activeAccounts = useMemo(() => accounts.filter((account) => !account.archived_at), [accounts]);
  const selectedAccount = activeAccounts.find((account) => account.id === accountId);
  const selectedCurrency = selectedAccount?.currency_code ?? "PHP";
  const modeCategories = mode === "transfer"
    ? []
    : categoriesForKind(categories, mode === "income" ? "income" : "expense");
  const scheduleMode = schedule ? guidedMode(schedule, categories) : null;

  useEffect(() => {
    if (!open) {
      initializedSessionRef.current = null;
      return;
    }
    if (recurringTransactionId && !schedule) return;
    const sessionKey = recurringTransactionId
      ? `${recurringTransactionId}:${schedule?.updated_at ?? ""}`
      : "new";
    if (initializedSessionRef.current === sessionKey) return;
    initializedSessionRef.current = sessionKey;
    let cancelled = false;

    queueMicrotask(() => {
      if (cancelled) return;
      setError(undefined);
      setResourceDialogKind(null);
      setResourceName("");
      setResourceError(undefined);
      setResourceLabels({});
      if (recurringTransactionId && schedule) {
        const draft = recurrenceDraft(schedule, categories);
        setEditing(Boolean(draft));
        setDate(schedule.start_date);
        setName(schedule.name);
        setPayeeId(schedule.payee_id ?? "");
        setMemo(schedule.memo ?? "");
        setTimezone(schedule.recurrence.timezone);
        if (!draft) return;
        setMode(draft.mode);
        setAmount(draft.amount);
        setAccountId(draft.accountId);
        setDestinationAccountId(draft.destinationAccountId);
        setCategoryId(draft.categoryId);
        setFrequency(draft.frequency);
        setInterval(draft.interval);
        setWeekdays(draft.weekdays);
        setMonthDay(draft.monthDay);
        setYearMonth(draft.yearMonth);
        setYearDay(draft.yearDay);
        setEndMode(draft.endMode);
        setUntilDate(draft.untilDate);
        setOccurrenceCount(draft.occurrenceCount);
        return;
      }
      setEditing(true);
      const nextDate = defaultDate ?? currentLocalDateInput();
      const firstExpenseCategory = categoriesForKind(categories, "expense")[0]?.id ?? "";
      setMode("expense");
      setDate(nextDate);
      setName("");
      setPayeeId("");
      setMemo("");
      setAmount("");
      setAccountId(activeAccounts[0]?.id ?? "");
      setDestinationAccountId(activeAccounts[1]?.id ?? "");
      setCategoryId(firstExpenseCategory);
      setFrequency("monthly");
      setInterval("1");
      setWeekdays([weekdayForDate(nextDate)]);
      setMonthDay(String(Number(nextDate.slice(-2))));
      setYearMonth(String(Number(nextDate.slice(5, 7))));
      setYearDay(String(Number(nextDate.slice(-2))));
      setEndMode("none");
      setUntilDate("");
      setOccurrenceCount("");
      setTimezone(browserTimezone());
    });

    return () => {
      cancelled = true;
    };
  }, [activeAccounts, categories, defaultDate, open, recurringTransactionId, schedule]);

  const createPayeeMutation = useMutation({ mutationFn: createMoneyPayee });
  const createCategoryMutation = useMutation({ mutationFn: createMoneyCategory });
  const saveMutation = useMutation({
    mutationFn: async (payload: MoneyRecurringTransactionCreateInput | MoneyRecurringTransactionUpdateInput) => {
      if (recurringTransactionId) {
        return updateMoneyRecurringTransaction(recurringTransactionId, payload as MoneyRecurringTransactionUpdateInput);
      }
      return createMoneyRecurringTransaction(payload as MoneyRecurringTransactionCreateInput);
    },
  });
  const pending = saveMutation.isPending || createPayeeMutation.isPending || createCategoryMutation.isPending;

  function handleResourceSelect(kind: MoneyResourceKind, value: string) {
    const createValue = kind === "payee" ? "__create_payee__" : "__create_category__";
    if (value === createValue) {
      setResourceDialogDisplayKind(kind);
      setResourceDialogKind(kind);
      setResourceName("");
      setResourceError(undefined);
      return;
    }
    if (kind === "payee") setPayeeId(value);
    else setCategoryId(value);
  }

  async function handleResourceSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!resourceDialogKind || !resourceName.trim()) return;
    setResourceError(undefined);
    const value = resourceName.trim();
    try {
      const created = resourceDialogKind === "payee"
        ? await createPayeeMutation.mutateAsync({ name: value })
        : await createCategoryMutation.mutateAsync({ name: value, kind: mode as "income" | "expense" });
      await invalidateMoneyQueries(queryClient);
      setResourceLabels((current) => ({ ...current, [created.id]: value }));
      if (resourceDialogKind === "payee") setPayeeId(created.id);
      else setCategoryId(created.id);
      setResourceDialogKind(null);
      setResourceName("");
      feedback.success({ title: `${resourceDialogKind === "payee" ? "Payee" : "Category"} created.` });
    } catch (reason) {
      setResourceError(describeMoneyError(reason));
    }
  }

  function toggleWeekday(day: MoneyRecurrenceWeekday, checked: boolean) {
    setWeekdays((current) => checked ? [...new Set([...current, day])] : current.filter((item) => item !== day));
  }

  function buildRecurrence(): MoneyRecurrenceInput | null {
    const parsedInterval = Number(interval);
    if (!timezone.trim()) {
      setError("Enter a timezone such as Asia/Manila or UTC.");
      return null;
    }
    if (!Number.isInteger(parsedInterval) || parsedInterval < 1 || parsedInterval > 365) {
      setError("Choose an interval between 1 and 365.");
      return null;
    }
    if (frequency === "weekly" && !weekdays.length) {
      setError("Choose at least one weekday for a weekly schedule.");
      return null;
    }
    const monthlyDay = Number(monthDay);
    const yearlyMonth = Number(yearMonth);
    const yearlyDay = Number(yearDay);
    const requestedOccurrenceCount = Number(occurrenceCount);
    const recurrence: MoneyRecurrenceInput = {
      timezone: timezone.trim(),
      frequency,
      interval: parsedInterval,
      weekdays: frequency === "weekly" ? weekdays : [],
      month_day: frequency === "monthly" ? monthlyDay : null,
      month: frequency === "yearly" ? yearlyMonth : null,
      day: frequency === "yearly" ? yearlyDay : null,
      until_date: endMode === "date" ? untilDate || null : null,
      occurrence_count: endMode === "count" ? requestedOccurrenceCount : null,
    };
    if (frequency === "monthly" && (!Number.isInteger(monthlyDay) || monthlyDay < 1 || monthlyDay > 31)) {
      setError("Choose a monthly day between 1 and 31.");
      return null;
    }
    if (frequency === "yearly" && (!Number.isInteger(yearlyMonth) || yearlyMonth < 1 || yearlyMonth > 12 || !Number.isInteger(yearlyDay) || yearlyDay < 1 || yearlyDay > 31)) {
      setError("Choose a valid month and day for the yearly schedule.");
      return null;
    }
    if (endMode === "date" && (!untilDate || untilDate < date)) {
      setError("The end date must be on or after the start date.");
      return null;
    }
    if (endMode === "count" && (!Number.isInteger(requestedOccurrenceCount) || requestedOccurrenceCount < 1 || requestedOccurrenceCount > 100000)) {
      setError("Choose an occurrence count between 1 and 100,000.");
      return null;
    }
    return recurrence;
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(undefined);
    const sourceAccount = activeAccounts.find((account) => account.id === accountId);
    const destinationAccount = activeAccounts.find((account) => account.id === destinationAccountId);
    const normalizedAmount = formatAmountInput(amount, sourceAccount?.currency_code ?? selectedCurrency);
    if (!date || !name.trim() || !sourceAccount || !normalizedAmount) {
      setError("Enter a name and start date, choose an account, and provide a positive amount before saving.");
      return;
    }
    if (mode === "transfer" && (!destinationAccount || destinationAccount.id === sourceAccount.id)) {
      setError("Choose two different accounts for a transfer.");
      return;
    }
    if (mode === "transfer" && destinationAccount?.currency_code !== sourceAccount.currency_code) {
      setError("Transfers must stay within one currency.");
      return;
    }
    if (mode !== "transfer" && !categoryId) {
      setError("Choose a category before saving.");
      return;
    }
    const recurrence = buildRecurrence();
    if (!recurrence) return;
    const currencyCode = sourceAccount.currency_code;
    const postings: MoneyRecurringPostingInput[] = mode === "transfer"
      ? [
          { account_id: sourceAccount.id, currency_code: currencyCode, amount: `-${normalizedAmount}` },
          { account_id: destinationAccount?.id, currency_code: currencyCode, amount: normalizedAmount },
        ]
      : [
          {
            account_id: sourceAccount.id,
            currency_code: currencyCode,
            amount: mode === "expense" ? `-${normalizedAmount}` : normalizedAmount,
          },
          {
            category_id: categoryId,
            currency_code: currencyCode,
            amount: mode === "expense" ? normalizedAmount : `-${normalizedAmount}`,
          },
        ];
    try {
      if (recurringTransactionId) {
        await saveMutation.mutateAsync({
          name: name.trim(),
          payee_id: payeeId || null,
          memo: memo.trim() || null,
          recurrence,
          postings,
        });
      } else {
        await saveMutation.mutateAsync({
          start_date: date,
          name: name.trim(),
          payee_id: payeeId || null,
          memo: memo.trim() || null,
          recurrence,
          postings,
        });
      }
      await invalidateMoneyQueries(queryClient);
      feedback.success({ title: recurringTransactionId ? "Recurring schedule updated." : "Recurring schedule created." });
      onSaved?.();
      onOpenChange(false);
    } catch (reason) {
      setError(describeMoneyError(reason));
    }
  }

  const title = recurringTransactionId ? (editing ? "Edit recurring schedule" : "Recurring schedule") : "Add recurring schedule";
  const description = recurringTransactionId
    ? "Update the future template while keeping posted occurrences intact."
    : "Set up one balanced movement that Cortex can post on its schedule.";
  const readOnlySchedule = recurringTransactionId && schedule && !scheduleMode;

  return (
    <>
      <Drawer open={open} onOpenChange={onOpenChange} swipeDirection="right">
        <DrawerContent className="min-h-[100svh] w-full max-w-xl gap-0 border-border bg-card p-0 text-card-foreground shadow-none sm:max-w-xl">
          <DrawerHeader className="border-b border-border/70 px-6 py-6 text-left sm:px-8">
            <div className="flex items-start justify-between gap-4">
              <div>
                <DrawerTitle className="text-xl font-semibold tracking-[-0.03em]">{title}</DrawerTitle>
                <DrawerDescription className="mt-2 max-w-md text-sm leading-6">{description}</DrawerDescription>
              </div>
              <DrawerClose render={<Button variant="ghost" size="icon-sm" aria-label="Close recurring schedule drawer" />}>
                <X aria-hidden="true" />
              </DrawerClose>
            </div>
          </DrawerHeader>

          {recurringTransactionId && recurringQuery.isPending ? (
            <div className="flex flex-1 items-center justify-center p-8 text-sm text-muted-foreground">Loading recurring schedule…</div>
          ) : recurringTransactionId && recurringQuery.isError ? (
            <div className="flex flex-1 flex-col items-center justify-center gap-3 p-8 text-center">
              <p role="alert" className="text-sm text-destructive">The recurring schedule could not be loaded.</p>
              <p className="max-w-sm text-sm leading-6 text-muted-foreground">{describeMoneyError(recurringQuery.error)}</p>
              <Button type="button" variant="outline" onClick={() => void recurringQuery.refetch()}>Try again</Button>
            </div>
          ) : readOnlySchedule ? (
            <ReadOnlyRecurringTemplate schedule={schedule} accounts={accounts} categories={categories} payees={payees} />
          ) : (
            <form onSubmit={handleSubmit} className="flex min-h-0 flex-1 flex-col">
              <div className="min-h-0 flex-1 space-y-6 overflow-y-auto px-6 py-6 sm:px-8">
                <div className="grid grid-cols-3 gap-1 rounded-lg border border-border/80 bg-background p-1" role="group" aria-label="Recurring transaction type">
                  {(["expense", "income", "transfer"] as RecurringEntryMode[]).map((item) => (
                    <Button
                      key={item}
                      type="button"
                      variant={mode === item ? "secondary" : "ghost"}
                      size="sm"
                      aria-pressed={mode === item}
                      onClick={() => {
                        setMode(item);
                        setCategoryId("");
                      }}
                    >
                      {item[0].toUpperCase() + item.slice(1)}
                    </Button>
                  ))}
                </div>

                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="flex flex-col gap-2 text-sm sm:col-span-2">
                    <Label htmlFor="recurring-name">Schedule name</Label>
                    <Input id="recurring-name" className="h-11" value={name} onChange={(event) => setName(event.target.value)} placeholder="e.g. Rent" maxLength={200} required />
                  </div>
                  <div className="flex flex-col gap-2 text-sm">
                    <Label htmlFor="recurring-start-date">{recurringTransactionId ? "Starts" : "Start date"}</Label>
                    <Input id="recurring-start-date" type="date" className="h-11" value={date} onChange={(event) => setDate(event.target.value)} disabled={Boolean(recurringTransactionId)} required />
                  </div>
                  <MoneySelectField
                    id="recurring-account"
                    label={mode === "transfer" ? "From account" : "Account"}
                    value={accountId}
                    selectedLabel={selectedAccount ? `${accountLabel(selectedAccount)} · ${selectedAccount.currency_code}` : undefined}
                    emptyLabel="Choose an account"
                    onValueChange={setAccountId}
                  >
                    {activeAccounts.map((account) => <SelectItem key={account.id} value={account.id}>{accountLabel(account)} · {account.currency_code}</SelectItem>)}
                  </MoneySelectField>
                </div>

                {mode === "transfer" ? (
                  <MoneySelectField
                    id="recurring-destination"
                    label="To account"
                    value={destinationAccountId}
                    selectedLabel={activeAccounts.find((account) => account.id === destinationAccountId)?.name}
                    emptyLabel="Choose a destination"
                    onValueChange={setDestinationAccountId}
                  >
                    {activeAccounts.map((account) => <SelectItem key={account.id} value={account.id}>{accountLabel(account)} · {account.currency_code}</SelectItem>)}
                  </MoneySelectField>
                ) : (
                  <MoneySelectField
                    id="recurring-category"
                    label="Category"
                    value={categoryId}
                    selectedLabel={modeCategories.find((category) => category.id === categoryId)?.name ?? resourceLabels[categoryId]}
                    emptyLabel="Choose a category"
                    onValueChange={(value) => handleResourceSelect("category", value)}
                  >
                    {modeCategories.map((category) => <SelectItem key={category.id} value={category.id}>{category.name}</SelectItem>)}
                    <SelectSeparator />
                    <SelectItem value="__create_category__">Create new {mode} category…</SelectItem>
                  </MoneySelectField>
                )}

                <div className="flex flex-col gap-2 text-sm">
                  <Label htmlFor="recurring-amount">Amount · {selectedCurrency}</Label>
                  <Input id="recurring-amount" className="h-11" inputMode="decimal" placeholder="0.00" value={amount} onChange={(event) => setAmount(event.target.value)} required />
                </div>

                <section className="space-y-4 rounded-lg border border-border/70 bg-background/60 p-4" aria-labelledby="recurring-rule-title">
                  <div className="flex items-start gap-3">
                    <span className="flex size-8 shrink-0 items-center justify-center rounded-md border border-border bg-card text-primary-strong">
                      <CalendarClock aria-hidden="true" className="size-4" />
                    </span>
                    <div>
                      <h2 id="recurring-rule-title" className="text-sm font-medium">When should it repeat?</h2>
                      <p className="mt-1 text-xs leading-5 text-muted-foreground">{recurrenceLabel({ timezone, frequency, interval: Number(interval) || 1, weekdays, month_day: Number(monthDay) || null, month: Number(yearMonth) || null, day: Number(yearDay) || null })}</p>
                    </div>
                  </div>
                  <div className="grid gap-4 sm:grid-cols-2">
                    <MoneySelectField id="recurring-frequency" label="Frequency" value={frequency} selectedLabel={frequency[0].toUpperCase() + frequency.slice(1)} onValueChange={(value) => setFrequency(value as MoneyRecurrenceFrequency)}>
                      <SelectItem value="weekly">Weekly</SelectItem>
                      <SelectItem value="monthly">Monthly</SelectItem>
                      <SelectItem value="yearly">Yearly</SelectItem>
                    </MoneySelectField>
                    <div className="flex flex-col gap-2 text-sm">
                      <Label htmlFor="recurring-interval">Repeat every</Label>
                      <div className="flex items-center gap-2">
                        <Input id="recurring-interval" className="h-11" inputMode="numeric" value={interval} onChange={(event) => setInterval(event.target.value.replace(/\D/g, "").slice(0, 3))} />
                        <span className="shrink-0 text-sm text-muted-foreground">{frequency === "weekly" ? "week(s)" : frequency === "monthly" ? "month(s)" : "year(s)"}</span>
                      </div>
                    </div>
                  </div>

                  {frequency === "weekly" ? (
                    <div className="space-y-2">
                      <Label>Repeat on</Label>
                      <div className="flex flex-wrap gap-2">
                        {recurrenceWeekdays.map((day) => {
                          const checked = weekdays.includes(day.value);
                          return (
                            <label key={day.value} className={cn("flex min-h-10 cursor-pointer items-center gap-2 rounded-md border px-3 text-sm transition-colors focus-within:ring-3 focus-within:ring-ring/40", checked ? "border-primary bg-primary/10" : "border-border bg-background hover:bg-muted/50")}>
                              <Checkbox checked={checked} onCheckedChange={(value) => toggleWeekday(day.value, value === true)} aria-label={day.label} />
                              <span>{day.short}<span className="sr-only">{day.label}</span></span>
                            </label>
                          );
                        })}
                      </div>
                    </div>
                  ) : null}

                  {frequency === "monthly" ? (
                    <div className="flex flex-col gap-2 text-sm">
                      <Label htmlFor="recurring-month-day">Day of month</Label>
                      <Input id="recurring-month-day" className="h-11" inputMode="numeric" value={monthDay} onChange={(event) => setMonthDay(event.target.value.replace(/\D/g, "").slice(0, 2))} placeholder="1–31" />
                    </div>
                  ) : null}

                  {frequency === "yearly" ? (
                    <div className="grid gap-4 sm:grid-cols-2">
                      <MoneySelectField id="recurring-year-month" label="Month" value={yearMonth} selectedLabel={yearMonth ? months[Number(yearMonth) - 1] : undefined} emptyLabel="Choose a month" onValueChange={setYearMonth}>
                        {months.map((month, index) => <SelectItem key={month} value={String(index + 1)}>{month}</SelectItem>)}
                      </MoneySelectField>
                      <div className="flex flex-col gap-2 text-sm">
                        <Label htmlFor="recurring-year-day">Day</Label>
                        <Input id="recurring-year-day" className="h-11" inputMode="numeric" value={yearDay} onChange={(event) => setYearDay(event.target.value.replace(/\D/g, "").slice(0, 2))} placeholder="1–31" />
                      </div>
                    </div>
                  ) : null}

                  <div className="grid gap-4 sm:grid-cols-2">
                    <MoneySelectField id="recurring-end-mode" label="Ends" value={endMode} selectedLabel={endMode === "none" ? "Never" : endMode === "date" ? "On a date" : "After occurrences"} onValueChange={(value) => setEndMode(value as EndMode)}>
                      <SelectItem value="none">Never</SelectItem>
                      <SelectItem value="date">On a date</SelectItem>
                      <SelectItem value="count">After occurrences</SelectItem>
                    </MoneySelectField>
                    {endMode === "date" ? (
                      <div className="flex flex-col gap-2 text-sm">
                        <Label htmlFor="recurring-until-date">End date</Label>
                        <Input id="recurring-until-date" type="date" className="h-11" value={untilDate} onChange={(event) => setUntilDate(event.target.value)} />
                      </div>
                    ) : null}
                    {endMode === "count" ? (
                      <div className="flex flex-col gap-2 text-sm">
                        <Label htmlFor="recurring-occurrence-count">Occurrences</Label>
                        <Input id="recurring-occurrence-count" className="h-11" inputMode="numeric" value={occurrenceCount} onChange={(event) => setOccurrenceCount(event.target.value.replace(/\D/g, "").slice(0, 6))} placeholder="e.g. 12" />
                      </div>
                    ) : null}
                  </div>
                  <div className="flex flex-col gap-2 text-sm">
                    <Label htmlFor="recurring-timezone">Timezone</Label>
                    <Input id="recurring-timezone" className="h-11" value={timezone} onChange={(event) => setTimezone(event.target.value)} placeholder="Asia/Manila" />
                    <p className="text-xs leading-5 text-muted-foreground">Dates follow this IANA timezone, so local calendar days stay stable across daylight-saving changes.</p>
                  </div>
                </section>

                <MoneySelectField
                  id="recurring-payee"
                  label={<>Payee <span className="font-normal text-muted-foreground">Optional</span></>}
                  value={payeeId}
                  selectedLabel={payees.find((payee) => payee.id === payeeId)?.name ?? resourceLabels[payeeId]}
                  emptyLabel="No payee"
                  onValueChange={(value) => handleResourceSelect("payee", value)}
                >
                  {payees.filter((payee) => !payee.archived_at).map((payee) => <SelectItem key={payee.id} value={payee.id}>{payee.name}</SelectItem>)}
                  <SelectSeparator />
                  <SelectItem value="__create_payee__">Create new payee…</SelectItem>
                </MoneySelectField>

                <div className="flex flex-col gap-2 text-sm">
                  <Label htmlFor="recurring-memo">Memo <span className="font-normal text-muted-foreground">Optional</span></Label>
                  <Textarea id="recurring-memo" rows={3} placeholder="Add useful context" value={memo} onChange={(event) => setMemo(event.target.value)} />
                </div>

                {error ? <p role="alert" className="rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">{error}</p> : null}
              </div>
              <DrawerFooter className="flex-row justify-end border-t border-border/70 bg-card px-6 py-4 sm:px-8">
                <DrawerClose type="button" render={<Button variant="outline" disabled={pending} />}>Cancel</DrawerClose>
                <Button type="submit" disabled={pending}>{pending ? "Saving…" : recurringTransactionId ? "Save changes" : "Create schedule"}</Button>
              </DrawerFooter>
            </form>
          )}
        </DrawerContent>
      </Drawer>
      <MoneyResourceCreateDialog
        kind={resourceDialogKind ?? resourceDialogDisplayKind}
        open={resourceDialogKind !== null}
        onOpenChange={(nextOpen) => {
          if (nextOpen) return;
          setResourceDialogKind(null);
          setResourceName("");
          setResourceError(undefined);
        }}
        name={resourceName}
        onNameChange={setResourceName}
        onSubmit={handleResourceSubmit}
        error={resourceError}
        pending={createPayeeMutation.isPending || createCategoryMutation.isPending}
      />
    </>
  );
}

"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  CalendarClock,
  ChevronDown,
  CircleAlert,
  Eye,
  LoaderCircle,
  Pause,
  Pencil,
  Play,
  Plus,
  Repeat2,
  Search,
  Square,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useFeedback } from "@/components/feedback";
import { Badge } from "@/components/ui/badge";
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
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { SelectItem } from "@/components/ui/select";
import { currentLocalDateInput } from "@/lib/date";
import { cn } from "@/lib/utils";
import {
  endMoneyRecurringTransaction,
  pauseMoneyRecurringTransaction,
  resumeMoneyRecurringTransaction,
  type MoneyAccount,
  type MoneyCategory,
  type MoneyPayee,
  type MoneyRecurrenceState,
  type MoneyRecurringTransaction,
} from "../api";
import { invalidateMoneyQueries, useMoneyRecurringTransactions } from "../hooks";
import { accountLabel, describeMoneyError, formatSignedMoney } from "../utils";
import { MoneySelectField } from "./money-select-field";
import { RecurringTransactionDrawer } from "./recurring-transaction-drawer";

type RecurringTransactionsSectionProps = {
  accounts: MoneyAccount[];
  payees: MoneyPayee[];
  categories: MoneyCategory[];
};

type StateFilter = "all" | MoneyRecurrenceState;

const recurrenceWeekdayLabels: Record<string, string> = {
  monday: "Monday",
  tuesday: "Tuesday",
  wednesday: "Wednesday",
  thursday: "Thursday",
  friday: "Friday",
  saturday: "Saturday",
  sunday: "Sunday",
};

const statusFilters: Array<{ value: StateFilter; label: string }> = [
  { value: "all", label: "All" },
  { value: "active", label: "Active" },
  { value: "paused", label: "Paused" },
  { value: "ended", label: "Ended" },
];

function dateLabel(value: string | null) {
  if (!value) return "None scheduled";
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(new Date(`${value}T00:00:00`));
}

function recurrenceLabel(schedule: MoneyRecurringTransaction) {
  const rule = schedule.recurrence;
  const interval = rule.interval === 1 ? "" : ` every ${rule.interval}`;
  if (rule.frequency === "weekly") {
    const days = rule.weekdays.map((day) => recurrenceWeekdayLabels[day]).join(", ");
    return `Weekly${interval}${days ? ` · ${days}` : ""}`;
  }
  if (rule.frequency === "monthly") return `Monthly${interval} · day ${rule.month_day ?? "—"}`;
  return `Yearly${interval} · ${rule.month ?? "—"}/${rule.day ?? "—"}`;
}

function statusLabel(state: MoneyRecurrenceState) {
  return state[0].toUpperCase() + state.slice(1);
}

function templateSummary(
  schedule: MoneyRecurringTransaction,
  accounts: MoneyAccount[],
  categories: MoneyCategory[],
) {
  const accountPostings = schedule.postings.filter((posting) => posting.account_id);
  const categoryPostings = schedule.postings.filter((posting) => posting.category_id);
  const accountById = new Map(accounts.map((account) => [account.id, account]));
  const categoryById = new Map(categories.map((category) => [category.id, category]));

  if (accountPostings.length === 2 && categoryPostings.length === 0) {
    const source = accountPostings.find((posting) => Number(posting.amount) < 0) ?? accountPostings[0];
    const destination = accountPostings.find((posting) => posting.id !== source.id);
    return {
      label: "Transfer",
      detail: `${source.account_id ? accountById.get(source.account_id)?.name ?? "Account" : "Account"} → ${destination?.account_id ? accountById.get(destination.account_id)?.name ?? "Account" : "Account"}`,
      amount: source.amount,
      currency: source.currency_code,
      guided: true,
    };
  }

  if (accountPostings.length === 1 && categoryPostings.length === 1) {
    const account = accountPostings[0].account_id ? accountById.get(accountPostings[0].account_id) : undefined;
    const category = categoryPostings[0].category_id ? categoryById.get(categoryPostings[0].category_id) : undefined;
    const guided = Boolean(account && category && (
      (category.kind === "expense" && Number(accountPostings[0].amount) < 0)
      || (category.kind === "income" && Number(accountPostings[0].amount) > 0)
    ));
    return {
      label: category?.kind === "income" ? "Income" : "Expense",
      detail: `${category?.name ?? "Category"} · ${account ? accountLabel(account) : "Account"}`,
      amount: accountPostings[0].amount,
      currency: accountPostings[0].currency_code,
      guided,
    };
  }

  return {
    label: "Split template",
    detail: `${schedule.postings.length} postings · advanced template`,
    amount: null,
    currency: schedule.postings[0]?.currency_code ?? "PHP",
    guided: false,
  };
}

function OccurrenceHistory({ schedule }: { schedule: MoneyRecurringTransaction }) {
  return (
    <div id={`recurring-occurrences-${schedule.id}`} className="mt-4 rounded-lg border border-border/70 bg-background/60 p-3">
      <div className="flex items-center justify-between gap-3">
        <p className="font-mono text-[0.62rem] uppercase tracking-[0.12em] text-muted-foreground">Occurrence history</p>
        <span className="text-xs text-muted-foreground">{schedule.posted_count} posted</span>
      </div>
      {schedule.occurrences.length ? (
        <ul className="mt-2 divide-y divide-border/60">
          {schedule.occurrences.map((occurrence) => (
            <li key={occurrence.id} className="flex items-center justify-between gap-3 py-2 text-sm">
              <span>Occurrence {occurrence.sequence_number}</span>
              <span className="text-right">
                <span className="block font-mono">{dateLabel(occurrence.due_date)}</span>
                <span className="block text-xs capitalize text-muted-foreground">{occurrence.status}</span>
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 text-sm text-muted-foreground">No occurrences have been scheduled yet.</p>
      )}
    </div>
  );
}

function RecurringScheduleRow({
  schedule,
  accounts,
  categories,
  expanded,
  pending,
  onToggle,
  onEdit,
  onPause,
  onResume,
  onEnd,
}: {
  schedule: MoneyRecurringTransaction;
  accounts: MoneyAccount[];
  categories: MoneyCategory[];
  expanded: boolean;
  pending: boolean;
  onToggle: () => void;
  onEdit: () => void;
  onPause: () => void;
  onResume: () => void;
  onEnd: () => void;
}) {
  const summary = templateSummary(schedule, accounts, categories);

  return (
    <li className="border-t border-border/70 first:border-t-0">
      <article className="px-4 py-4 sm:px-5">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
          <button
            type="button"
            aria-expanded={expanded}
            aria-controls={`recurring-occurrences-${schedule.id}`}
            onClick={onToggle}
            className="group flex min-w-0 flex-1 items-start gap-3 rounded-lg text-left outline-none focus-visible:ring-3 focus-visible:ring-ring/40"
          >
            <ChevronDown aria-hidden="true" className={cn("mt-0.5 size-4 shrink-0 text-muted-foreground transition-transform", expanded && "rotate-180")} />
            <span className="min-w-0 flex-1">
              <span className="flex flex-wrap items-center gap-2">
                <span className="truncate text-sm font-medium group-hover:text-primary-strong">{schedule.name}</span>
                <Badge variant={schedule.state === "active" ? "secondary" : "outline"} className="rounded-full text-[0.65rem]">{statusLabel(schedule.state)}</Badge>
              </span>
              <span className="mt-1 block truncate text-xs text-muted-foreground">{recurrenceLabel(schedule)} · {summary.label}</span>
            </span>
          </button>

          <div className="grid grid-cols-2 gap-x-6 gap-y-3 pl-7 text-sm sm:grid-cols-4 sm:pl-7 xl:min-w-[34rem] xl:pl-0">
            <div>
              <p className="text-xs text-muted-foreground">Next due</p>
              <p className="mt-1 font-mono font-medium">{dateLabel(schedule.next_occurrence_date)}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Template</p>
              <p className="mt-1 truncate font-medium" title={summary.detail}>{summary.detail}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Amount</p>
              <p className={cn("mt-1 font-mono font-medium", summary.amount && Number(summary.amount) > 0 ? "text-tag-sea-glass-foreground" : "text-foreground")}>
                {summary.amount ? formatSignedMoney(summary.amount, summary.currency) : "Multiple"}
              </p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Posted</p>
              <p className="mt-1 font-mono font-medium">{schedule.posted_count}</p>
            </div>
          </div>
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-2 pl-7" aria-label={`${schedule.name} actions`}>
          <Button type="button" variant="outline" size="sm" onClick={onEdit} disabled={pending} title={summary.guided ? "Edit schedule" : "View split template (read-only)"}>
            {summary.guided ? <Pencil aria-hidden="true" /> : <Eye aria-hidden="true" />}
            {summary.guided ? "Edit" : "View template"}
          </Button>
          {schedule.state === "active" ? (
            <Button type="button" variant="outline" size="sm" onClick={onPause} disabled={pending}>
              <Pause aria-hidden="true" />
              Pause
            </Button>
          ) : null}
          {schedule.state === "paused" ? (
            <Button type="button" variant="outline" size="sm" onClick={onResume} disabled={pending}>
              <Play aria-hidden="true" />
              Resume
            </Button>
          ) : null}
          {schedule.state !== "ended" ? (
            <Button type="button" variant="outline" size="sm" onClick={onEnd} disabled={pending}>
              <Square aria-hidden="true" />
              End schedule
            </Button>
          ) : null}
          {!summary.guided ? <span className="text-xs text-muted-foreground">Manage state here; edit posting shape through API/MCP.</span> : null}
        </div>

        {expanded ? <OccurrenceHistory schedule={schedule} /> : null}
      </article>
    </li>
  );
}

export function RecurringTransactionsSection({ accounts, payees, categories }: RecurringTransactionsSectionProps) {
  const queryClient = useQueryClient();
  const feedback = useFeedback();
  const [stateFilter, setStateFilter] = useState<StateFilter>("active");
  const [accountId, setAccountId] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerScheduleId, setDrawerScheduleId] = useState<string | null>(null);
  const [endTarget, setEndTarget] = useState<MoneyRecurringTransaction | null>(null);

  useEffect(() => {
    const timer = window.setTimeout(() => setSearch(searchInput.trim()), 250);
    return () => window.clearTimeout(timer);
  }, [searchInput]);

  const schedulesQuery = useMoneyRecurringTransactions({
    state: stateFilter === "all" ? undefined : stateFilter,
    accountId: accountId || undefined,
    search: search || undefined,
  });
  const schedules = schedulesQuery.data?.pages.flatMap((page) => page.items) ?? [];
  const activeAccounts = useMemo(() => accounts.filter((account) => !account.archived_at), [accounts]);

  const pauseMutation = useMutation({
    mutationFn: pauseMoneyRecurringTransaction,
    onSuccess: async () => {
      await invalidateMoneyQueries(queryClient);
      feedback.success({ title: "Recurring schedule paused." });
    },
    onError: (reason) => feedback.error({ title: "Schedule could not be paused.", description: describeMoneyError(reason) }),
  });
  const resumeMutation = useMutation({
    mutationFn: resumeMoneyRecurringTransaction,
    onSuccess: async () => {
      await invalidateMoneyQueries(queryClient);
      feedback.success({ title: "Recurring schedule resumed." });
    },
    onError: (reason) => feedback.error({ title: "Schedule could not be resumed.", description: describeMoneyError(reason) }),
  });
  const endMutation = useMutation({
    mutationFn: endMoneyRecurringTransaction,
    onSuccess: async () => {
      await invalidateMoneyQueries(queryClient);
      setEndTarget(null);
      feedback.success({ title: "Recurring schedule ended.", description: "Future scheduled occurrences were skipped." });
    },
    onError: (reason) => feedback.error({ title: "Schedule could not be ended.", description: describeMoneyError(reason) }),
  });
  const mutationPending = pauseMutation.isPending || resumeMutation.isPending || endMutation.isPending;

  function openCreate() {
    setDrawerScheduleId(null);
    setDrawerOpen(true);
  }

  function openEdit(schedule: MoneyRecurringTransaction) {
    setDrawerScheduleId(schedule.id);
    setDrawerOpen(true);
  }

  const filteredEmpty = Boolean(search || accountId || stateFilter !== "active");

  return (
    <section id="money-view-panel" role="tabpanel" aria-labelledby="money-view-recurring" tabIndex={0} className="space-y-5 outline-none focus-visible:ring-3 focus-visible:ring-ring/40">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <Repeat2 aria-hidden="true" className="size-4 text-primary-strong" />
            <p className="font-mono text-[0.64rem] uppercase tracking-[0.16em] text-muted-foreground">Scheduled movements</p>
          </div>
          <h2 className="mt-1 text-lg font-medium">Recurring transactions</h2>
          <p className="mt-1 max-w-2xl text-sm leading-6 text-muted-foreground">Keep the commitments that repeat visible, predictable, and separate from what has already posted.</p>
        </div>
        <Button type="button" size="lg" onClick={openCreate}>
          <Plus aria-hidden="true" />
          Add recurring
        </Button>
      </div>

      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex gap-1 overflow-x-auto rounded-lg border border-border/80 bg-background p-1" role="tablist" aria-label="Recurring schedule status">
          {statusFilters.map((filter) => (
            <Button key={filter.value} type="button" role="tab" aria-selected={stateFilter === filter.value} variant={stateFilter === filter.value ? "secondary" : "ghost"} size="sm" onClick={() => setStateFilter(filter.value)}>
              {filter.label}
            </Button>
          ))}
        </div>
        <div className="flex w-full flex-col gap-2 sm:flex-row sm:items-end lg:w-auto">
          <label className="relative min-w-0 flex-1 sm:min-w-64" htmlFor="recurring-search">
            <span className="sr-only">Search recurring transactions</span>
            <Search aria-hidden="true" className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input id="recurring-search" value={searchInput} onChange={(event) => setSearchInput(event.target.value)} placeholder="Search schedules…" className="h-10 pl-9" />
          </label>
          <MoneySelectField id="recurring-account-filter" label="Account" value={accountId} selectedLabel={activeAccounts.find((account) => account.id === accountId)?.name} emptyLabel="All accounts" onValueChange={setAccountId} size="compact" triggerClassName="min-w-40">
            {activeAccounts.map((account) => <SelectItem key={account.id} value={account.id}>{accountLabel(account)}</SelectItem>)}
          </MoneySelectField>
        </div>
      </div>

      {schedulesQuery.isError ? (
        <div role="alert" className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm">
          <span className="flex items-center gap-2 text-destructive"><CircleAlert aria-hidden="true" className="size-4" />Recurring schedules could not load. {describeMoneyError(schedulesQuery.error)}</span>
          <Button type="button" variant="outline" size="sm" onClick={() => void schedulesQuery.refetch()}>Try again</Button>
        </div>
      ) : null}

      <Card className="overflow-hidden rounded-xl border-border/80 p-0 shadow-none">
        {schedulesQuery.isPending ? (
          <div className="space-y-3 p-5" aria-label="Loading recurring schedules">
            <div className="h-20 animate-pulse rounded-lg bg-muted" />
            <div className="h-20 animate-pulse rounded-lg bg-muted" />
            <div className="h-20 animate-pulse rounded-lg bg-muted" />
          </div>
        ) : schedulesQuery.isSuccess && !schedules.length ? (
          <div className="flex flex-col items-center px-6 py-14 text-center">
            {filteredEmpty ? <Search aria-hidden="true" className="size-6 text-primary-strong" /> : <CalendarClock aria-hidden="true" className="size-6 text-primary-strong" />}
            <h3 className="mt-3 text-sm font-medium">{filteredEmpty ? "No schedules match this view." : "No recurring schedules yet."}</h3>
            <p className="mt-2 max-w-sm text-sm leading-6 text-muted-foreground">{filteredEmpty ? "Try another search, account, or status filter." : "Add a rent, salary, subscription, or transfer that repeats on a predictable calendar."}</p>
            {!filteredEmpty ? <Button type="button" className="mt-5" onClick={openCreate}><Plus aria-hidden="true" />Add your first schedule</Button> : null}
          </div>
        ) : schedules.length ? (
          <>
            <div className="hidden border-b border-border/70 bg-background px-5 py-2 font-mono text-[0.62rem] uppercase tracking-[0.1em] text-muted-foreground sm:block">Schedules are ordered by most recently changed.</div>
            <ul aria-label="Recurring transactions">
              {schedules.map((schedule) => (
                <RecurringScheduleRow
                  key={schedule.id}
                  schedule={schedule}
                  accounts={accounts}
                  categories={categories}
                  expanded={expandedId === schedule.id}
                  pending={mutationPending}
                  onToggle={() => setExpandedId((current) => current === schedule.id ? null : schedule.id)}
                  onEdit={() => openEdit(schedule)}
                  onPause={() => pauseMutation.mutate(schedule.id)}
                  onResume={() => resumeMutation.mutate(schedule.id)}
                  onEnd={() => setEndTarget(schedule)}
                />
              ))}
            </ul>
            {schedulesQuery.hasNextPage ? (
              <div className="border-t border-border/70 p-3">
                <Button type="button" variant="outline" className="w-full" disabled={schedulesQuery.isFetchingNextPage} onClick={() => void schedulesQuery.fetchNextPage()}>
                  {schedulesQuery.isFetchingNextPage ? <LoaderCircle aria-hidden="true" className="animate-spin" /> : null}
                  {schedulesQuery.isFetchingNextPage ? "Loading more…" : "Load more schedules"}
                </Button>
              </div>
            ) : null}
          </>
        ) : null}
      </Card>

      <RecurringTransactionDrawer
        open={drawerOpen}
        onOpenChange={(open) => {
          setDrawerOpen(open);
          if (!open) setDrawerScheduleId(null);
        }}
        recurringTransactionId={drawerScheduleId}
        defaultDate={currentLocalDateInput()}
        accounts={accounts}
        payees={payees}
        categories={categories}
      />

      <Dialog open={Boolean(endTarget)} onOpenChange={(open) => { if (!open) setEndTarget(null); }}>
        <DialogContent className="w-[min(28rem,calc(100vw-2rem))] rounded-xl border-border bg-card p-6 text-card-foreground shadow-none sm:max-w-none sm:p-7">
          <DialogHeader>
            <DialogTitle className="text-xl tracking-[-0.03em]">End recurring schedule?</DialogTitle>
            <DialogDescription className="mt-2 leading-6">
              {endTarget ? `${endTarget.name} will stop creating future transactions. Existing posted transactions remain in your ledger, and scheduled occurrences will be skipped.` : ""}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="mt-7 flex-row justify-end gap-2 border-0 bg-transparent p-0">
            <DialogClose render={<Button type="button" variant="outline" size="lg" disabled={endMutation.isPending} />}>Keep schedule</DialogClose>
            <Button type="button" variant="destructive" size="lg" disabled={!endTarget || endMutation.isPending} onClick={() => { if (endTarget) endMutation.mutate(endTarget.id); }}>
              {endMutation.isPending ? <LoaderCircle aria-hidden="true" className="animate-spin" /> : <Square aria-hidden="true" />}
              {endMutation.isPending ? "Ending…" : "End schedule"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  );
}

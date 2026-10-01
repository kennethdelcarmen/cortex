"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, CreditCard, ReceiptText, Repeat2, Search, SlidersHorizontal, X, type LucideIcon } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Popover,
  PopoverContent,
  PopoverDescription,
  PopoverHeader,
  PopoverTitle,
  PopoverTrigger,
} from "@/components/ui/popover";
import { SelectItem } from "@/components/ui/select";
import { WorkspaceRouteGuard, WorkspaceShell } from "@/features/workspace/components/workspace-shell";
import { useCurrentUser } from "@/features/auth/hooks";
import { currentLocalDateInput } from "@/lib/date";
import { cn } from "@/lib/utils";
import {
  cancelMoneyInstallmentPlan,
  moneySummaryQueryKey,
  getMoneySummary,
  type MoneyInstallmentPlan,
  type MoneyAccount,
  type MoneyCategory,
  type MoneyPayee,
  type MoneyTransaction,
} from "../api";
import { invalidateMoneyQueries, useMoneyCatalog, useMoneyInstallmentPlans, useMoneyTransactions } from "../hooks";
import { MoneyFloatingAction } from "./money-floating-action";
import { MoneySelectField } from "./money-select-field";
import { RecurringTransactionsSection } from "./recurring-transactions-section";
import { TransactionDrawer } from "./transaction-drawer";
import {
  accountLabel,
  currentPeriod,
  describeMoneyError,
  formatMoney,
  formatSignedMoney,
  periodLabel,
  periodOptions,
  periodRange,
  transactionAccountPostings,
  transactionCategoryPostings,
  transactionDisplayAmount,
  transactionMode,
} from "../utils";

type RangeMode = "month" | "custom" | "all";
type MoneyView = "ledger" | "recurring" | "installments";

type MoneyViewTab = {
  value: MoneyView;
  label: string;
  icon: LucideIcon;
  disabled?: boolean;
};

const moneyViewTabs: MoneyViewTab[] = [
  { value: "ledger", label: "Ledger", icon: ReceiptText },
  { value: "recurring", label: "Recurring", icon: Repeat2 },
  { value: "installments", label: "Installments", icon: CreditCard },
];

type ActiveFilter = {
  id: string;
  label: string;
  onRemove: () => void;
};

function TransactionRow({
  transaction,
  accounts,
  payees,
  categories,
  onOpen,
}: {
  transaction: MoneyTransaction;
  accounts: MoneyAccount[];
  payees: MoneyPayee[];
  categories: MoneyCategory[];
  onOpen: () => void;
}) {
  const accountById = new Map(accounts.map((account) => [account.id, account]));
  const categoryById = new Map(categories.map((category) => [category.id, category]));
  const payee = payees.find((item) => item.id === transaction.payee_id);
  const accountPostings = transactionAccountPostings(transaction);
  const categoryPosting = transactionCategoryPostings(transaction)[0];
  const mode = transactionMode(transaction, categories);
  const account = accountPostings[0]?.account_id ? accountById.get(accountPostings[0].account_id) : undefined;
  const category = categoryPosting?.category_id ? categoryById.get(categoryPosting.category_id) : undefined;
  const isCardPayment = mode === "transfer" && accountPostings.some((posting) => {
    const postingAccount = posting.account_id ? accountById.get(posting.account_id) : undefined;
    return postingAccount?.account_type === "credit_card";
  });
  const isInstallmentCharge = transaction.name.includes(" · Installment ");
  const currencyCode = accountPostings[0]?.currency_code ?? "PHP";
  const reconciliation = accountPostings.length === 0
    ? "—"
    : accountPostings.every((posting) => posting.reconciliation_state === "reconciled")
      ? "reconciled"
      : accountPostings.some((posting) => posting.reconciliation_state === "cleared")
        ? "cleared"
        : "uncleared";
  const transferLabel = accountPostings
    .map((posting) => posting.account_id ? accountById.get(posting.account_id)?.name : undefined)
    .filter(Boolean)
    .join(" → ");
  const supportingText = [
    payee?.name,
    transaction.memo,
    isInstallmentCharge
      ? "Installment charge"
      : mode === "transfer"
        ? isCardPayment ? "Card payment" : transferLabel || "Account transfer"
        : category?.name ?? "Uncategorized",
  ].filter(Boolean).join(" · ");

  return (
    <li>
      <button
        type="button"
        onClick={onOpen}
        className="group grid w-full gap-3 border-t border-border/70 px-4 py-4 text-left outline-none transition-colors hover:bg-muted/30 focus-visible:bg-muted/30 focus-visible:ring-3 focus-visible:ring-ring/40 sm:grid-cols-[7rem_minmax(0,1.3fr)_minmax(0,1fr)_7rem_8rem] sm:items-center sm:px-5"
      >
        <span className="font-mono text-xs text-muted-foreground">{transaction.transaction_date}</span>
        <span className="min-w-0">
          <span className="block truncate text-sm font-medium">{transaction.name}</span>
          <span className="mt-1 block truncate text-xs text-muted-foreground">{supportingText || "No additional context"}</span>
        </span>
        <span className="min-w-0 text-xs text-muted-foreground">
          <span className="block truncate">{isInstallmentCharge ? "Installment charge" : mode === "transfer" ? isCardPayment ? "Card payment" : transferLabel || "Transfer" : category?.name ?? "No category"}</span>
          <span className="mt-1 block truncate">{account ? accountLabel(account) : "Multiple accounts"}</span>
        </span>
        <span className="font-mono text-[0.65rem] uppercase tracking-[0.08em] text-muted-foreground">{reconciliation}</span>
        <span className={cn("font-mono text-sm font-medium sm:text-right", Number(transactionDisplayAmount(transaction)) > 0 ? "text-tag-sea-glass-foreground" : "text-foreground")}>
          {formatSignedMoney(transactionDisplayAmount(transaction), currencyCode)}
          {transaction.state === "voided" ? <span className="mt-1 block text-[0.6rem] uppercase tracking-[0.1em] text-destructive">Voided</span> : null}
        </span>
      </button>
    </li>
  );
}

function ActiveFilterChip({ filter }: { filter: ActiveFilter }) {
  return (
    <Badge variant="outline" className="h-7 gap-1 rounded-full bg-background px-2.5 font-normal text-muted-foreground">
      <span className="max-w-52 truncate">{filter.label}</span>
      <button
        type="button"
        aria-label={`Remove ${filter.label} filter`}
        className="rounded-full outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring"
        onClick={filter.onRemove}
      >
        <X aria-hidden="true" className="size-3.5" />
      </button>
    </Badge>
  );
}

function installmentDateLabel(value: string | null) {
  if (!value) return "None scheduled";
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(new Date(`${value}T00:00:00`));
}

function installmentStatusLabel(status: MoneyInstallmentPlan["status"]) {
  return status === "active" ? "Active" : status === "completed" ? "Completed" : "Cancelled";
}

function InstallmentPlansSection({
  plans,
  accounts,
  isPending,
  isError,
  error,
  onRetry,
}: {
  plans: MoneyInstallmentPlan[];
  accounts: MoneyAccount[];
  isPending: boolean;
  isError: boolean;
  error: unknown;
  onRetry: () => void;
}) {
  const queryClient = useQueryClient();
  const [expandedPlanId, setExpandedPlanId] = useState<string | null>(null);
  const cancelMutation = useMutation({
    mutationFn: cancelMoneyInstallmentPlan,
    onSuccess: () => invalidateMoneyQueries(queryClient),
  });
  const accountById = new Map(accounts.map((account) => [account.id, account]));

  return (
    <section aria-labelledby="installment-plans-title" className="overflow-hidden rounded-xl border border-border/80 bg-card shadow-none">
      <div className="flex flex-col gap-2 border-b border-border/70 px-4 py-4 sm:flex-row sm:items-end sm:justify-between sm:px-5">
        <div>
          <div className="flex items-center gap-2">
            <CreditCard aria-hidden="true" className="size-4 text-primary-strong" />
            <p className="font-mono text-[0.64rem] uppercase tracking-[0.16em] text-muted-foreground">Card commitments</p>
          </div>
          <h2 id="installment-plans-title" className="mt-1 text-lg font-medium">Installment plans</h2>
          <p className="mt-1 text-sm text-muted-foreground">Charges appear in the ledger as each statement closes. Payments are tracked separately.</p>
        </div>
        <span className="text-xs text-muted-foreground">{plans.length} plan{plans.length === 1 ? "" : "s"}</span>
      </div>
      {isPending ? <div className="space-y-3 p-5" aria-label="Loading installment plans"><div className="h-16 animate-pulse rounded-lg bg-muted" /><div className="h-16 animate-pulse rounded-lg bg-muted" /></div> : null}
      {isError ? (
        <div role="alert" className="p-6 text-center">
          <p className="text-sm text-destructive">Installment plans could not load.</p>
          <p className="mt-2 text-sm text-muted-foreground">{describeMoneyError(error)}</p>
          <Button type="button" variant="outline" size="sm" className="mt-4" onClick={onRetry}>Try again</Button>
        </div>
      ) : null}
      {!isPending && !isError && !plans.length ? (
        <div className="p-6 text-center">
          <CreditCard aria-hidden="true" className="mx-auto size-7 text-primary-strong" />
          <p className="mt-3 text-sm font-medium">No installment plans yet.</p>
          <p className="mt-2 text-sm text-muted-foreground">Choose Installment purchase when adding a credit-card transaction.</p>
        </div>
      ) : null}
      {plans.length ? (
        <div className="divide-y divide-border/70">
          {plans.map((plan) => {
            const account = accountById.get(plan.account_id);
            const expanded = expandedPlanId === plan.id;
            const canCancel = plan.status === "active" && plan.charged_count < plan.term_months;
            return (
              <article key={plan.id} className="px-4 py-4 sm:px-5">
                <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                  <button
                    type="button"
                    aria-expanded={expanded}
                    className="flex min-w-0 flex-1 items-start gap-3 text-left outline-none focus-visible:ring-3 focus-visible:ring-ring/40"
                    onClick={() => setExpandedPlanId(expanded ? null : plan.id)}
                  >
                    <ChevronDown aria-hidden="true" className={cn("mt-0.5 size-4 shrink-0 text-muted-foreground transition-transform", expanded && "rotate-180")} />
                    <span className="min-w-0">
                      <span className="flex flex-wrap items-center gap-2">
                        <span className="truncate text-sm font-medium">{plan.name}</span>
                        <Badge variant={plan.status === "active" ? "secondary" : "outline"} className="rounded-full text-[0.65rem]">{installmentStatusLabel(plan.status)}</Badge>
                      </span>
                      <span className="mt-1 block truncate text-xs text-muted-foreground">{account ? accountLabel(account) : "Unknown card"}</span>
                    </span>
                  </button>
                  {canCancel ? (
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      disabled={cancelMutation.isPending}
                      onClick={() => cancelMutation.mutate(plan.id)}
                    >
                      {cancelMutation.isPending && cancelMutation.variables === plan.id ? "Cancelling…" : "Cancel future charges"}
                    </Button>
                  ) : null}
                </div>
                <div className="mt-4 grid gap-3 text-sm sm:grid-cols-4">
                  <div><p className="text-xs text-muted-foreground">Charged months</p><p className="mt-1 font-mono font-medium">{plan.charged_count} of {plan.term_months}</p></div>
                  <div><p className="text-xs text-muted-foreground">Next statement charge</p><p className="mt-1 font-mono font-medium">{plan.next_charge_date ? `${installmentDateLabel(plan.next_charge_date)} · ${formatMoney(plan.next_charge_amount ?? "0", plan.currency_code)}` : "None scheduled"}</p></div>
                  <div><p className="text-xs text-muted-foreground">Remaining scheduled</p><p className="mt-1 font-mono font-medium">{formatMoney(plan.remaining_amount, plan.currency_code)}</p></div>
                  <div><p className="text-xs text-muted-foreground">Card</p><p className="mt-1 truncate font-medium">{account ? accountLabel(account) : "Unknown card"}</p></div>
                </div>
                {expanded ? (
                  <div className="mt-4 rounded-lg border border-border/70 bg-background/60 p-3">
                    <p className="font-mono text-[0.62rem] uppercase tracking-[0.12em] text-muted-foreground">Statement charge schedule</p>
                    <ul className="mt-2 divide-y divide-border/60">
                      {plan.occurrences.map((occurrence) => (
                        <li key={occurrence.id} className="flex items-center justify-between gap-3 py-2 text-sm">
                          <span>Installment {occurrence.sequence_number} of {plan.term_months}</span>
                          <span className="text-right"><span className="block font-mono">{formatMoney(occurrence.amount, plan.currency_code)}</span><span className="block text-xs text-muted-foreground">{installmentDateLabel(occurrence.charge_date)} · {occurrence.status}</span></span>
                        </li>
                      ))}
                    </ul>
                    {cancelMutation.isError && cancelMutation.variables === plan.id ? <p role="alert" className="mt-3 text-sm text-destructive">{describeMoneyError(cancelMutation.error)}</p> : null}
                  </div>
                ) : null}
              </article>
            );
          })}
        </div>
      ) : null}
    </section>
  );
}

function MoneyViewTabs({
  activeView,
  onViewChange,
}: {
  activeView: MoneyView;
  onViewChange: (view: MoneyView) => void;
}) {
  const tabRefs = useRef<Partial<Record<MoneyView, HTMLButtonElement | null>>>({});
  const enabledTabs = moneyViewTabs.filter((tab) => !tab.disabled);

  function focusTab(view: MoneyView) {
    const tab = moneyViewTabs.find((item) => item.value === view);
    if (!tab || tab.disabled) return;
    onViewChange(view);
    requestAnimationFrame(() => tabRefs.current[view]?.focus());
  }

  function handleKeyDown(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    let nextIndex: number | null = null;

    if (event.key === "ArrowRight" || event.key === "ArrowDown") {
      nextIndex = (index + 1) % enabledTabs.length;
    } else if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
      nextIndex = (index - 1 + enabledTabs.length) % enabledTabs.length;
    } else if (event.key === "Home") {
      nextIndex = 0;
    } else if (event.key === "End") {
      nextIndex = enabledTabs.length - 1;
    }

    if (nextIndex === null) return;

    event.preventDefault();
    focusTab(enabledTabs[nextIndex].value);
  }

  return (
    <div role="tablist" aria-label="Transaction views" aria-orientation="horizontal" className="flex gap-1 overflow-x-auto border-b border-border/70 pb-px">
      {moneyViewTabs.map((tab) => {
        const selected = tab.value === activeView;
        const Icon = tab.icon;
        const enabledIndex = enabledTabs.findIndex((item) => item.value === tab.value);

        return (
          <button
            key={tab.value}
            ref={(element) => {
              tabRefs.current[tab.value] = element;
            }}
            type="button"
            role="tab"
            id={`money-view-${tab.value}`}
            aria-selected={selected}
            aria-controls="money-view-panel"
            aria-disabled={tab.disabled || undefined}
            tabIndex={tab.disabled ? -1 : selected ? 0 : -1}
            disabled={tab.disabled}
            onClick={() => {
              if (!tab.disabled) onViewChange(tab.value);
            }}
            onKeyDown={(event) => {
              if (enabledIndex >= 0) handleKeyDown(event, enabledIndex);
            }}
            className={cn(
              "relative flex min-h-11 shrink-0 items-center gap-2 rounded-t-md px-3 text-sm font-medium text-muted-foreground outline-none transition-colors hover:bg-muted/60 hover:text-foreground focus-visible:z-10 focus-visible:ring-3 focus-visible:ring-ring/50 sm:px-4",
              selected && "text-foreground",
              tab.disabled && "cursor-not-allowed opacity-55 hover:bg-transparent hover:text-muted-foreground",
            )}
          >
            <Icon aria-hidden="true" className={cn("size-4", selected ? "text-primary-strong" : "text-muted-foreground")} />
            <span>{tab.label}</span>
            {tab.disabled ? <span className="rounded-full bg-muted px-1.5 py-0.5 font-mono text-[0.58rem] uppercase tracking-[0.08em] text-muted-foreground">Coming soon</span> : null}
            <span aria-hidden="true" className={cn("absolute inset-x-2 -bottom-px h-0.5 rounded-full bg-transparent transition-colors sm:inset-x-3", selected && "bg-primary")} />
          </button>
        );
      })}
    </div>
  );
}

function TransactionFilterPopover({
  rangeMode,
  setRangeMode,
  period,
  setPeriod,
  dateFrom,
  setDateFrom,
  dateTo,
  setDateTo,
  currencyCode,
  setCurrencyCode,
  accountId,
  setAccountId,
  payeeId,
  setPayeeId,
  categoryId,
  setCategoryId,
  reconciliationState,
  setReconciliationState,
  includeVoided,
  setIncludeVoided,
  currencyOptions,
  catalog,
  activeFilterCount,
}: {
  rangeMode: RangeMode;
  setRangeMode: (value: RangeMode) => void;
  period: string;
  setPeriod: (value: string) => void;
  dateFrom: string;
  setDateFrom: (value: string) => void;
  dateTo: string;
  setDateTo: (value: string) => void;
  currencyCode: string;
  setCurrencyCode: (value: string) => void;
  accountId: string;
  setAccountId: (value: string) => void;
  payeeId: string;
  setPayeeId: (value: string) => void;
  categoryId: string;
  setCategoryId: (value: string) => void;
  reconciliationState: string;
  setReconciliationState: (value: string) => void;
  includeVoided: boolean;
  setIncludeVoided: (value: boolean) => void;
  currencyOptions: string[];
  catalog: ReturnType<typeof useMoneyCatalog>;
  activeFilterCount: number;
}) {
  return (
    <Popover>
      <PopoverTrigger render={<Button type="button" variant="outline" className="h-10 gap-2" />}>
        <SlidersHorizontal aria-hidden="true" className="size-4" />
        <span>Filters</span>
        {activeFilterCount ? <Badge variant="secondary" className="rounded-full px-1.5 py-0 text-xs">{activeFilterCount}</Badge> : null}
      </PopoverTrigger>
      <PopoverContent align="end" className="w-[min(24rem,calc(100vw-2rem))] p-4">
        <PopoverHeader>
          <PopoverTitle>Refine ledger</PopoverTitle>
          <PopoverDescription>Choose the range and records shown in this view.</PopoverDescription>
        </PopoverHeader>
        <div className="grid gap-3 sm:grid-cols-2">
          <MoneySelectField id="transaction-range" label="Range" value={rangeMode} selectedLabel={rangeMode === "month" ? "By month" : rangeMode === "custom" ? "Custom range" : "All history"} onValueChange={(value) => setRangeMode(value as RangeMode)} size="compact">
            <SelectItem value="month">By month</SelectItem>
            <SelectItem value="custom">Custom range</SelectItem>
            <SelectItem value="all">All history</SelectItem>
          </MoneySelectField>
          {rangeMode === "month" ? (
            <MoneySelectField id="transaction-period" label="Month" value={period} selectedLabel={periodLabel(period)} onValueChange={(value) => { setPeriod(value); const range = periodRange(value); setDateFrom(range.start); setDateTo(range.end); }} size="compact">
              {periodOptions().map((option) => <SelectItem key={option.id} value={option.id}>{option.label}</SelectItem>)}
            </MoneySelectField>
          ) : null}
          {rangeMode === "custom" ? <>
            <div className="flex min-w-0 flex-col gap-2 text-sm"><Label htmlFor="transaction-date-from">From</Label><Input id="transaction-date-from" type="date" className="h-10" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} /></div>
            <div className="flex min-w-0 flex-col gap-2 text-sm"><Label htmlFor="transaction-date-to">To</Label><Input id="transaction-date-to" type="date" className="h-10" value={dateTo} onChange={(event) => setDateTo(event.target.value)} /></div>
          </> : null}
          <MoneySelectField id="transaction-currency" label="Currency" value={currencyCode} selectedLabel={currencyCode} onValueChange={setCurrencyCode} size="compact">
            {currencyOptions.map((currency) => <SelectItem key={currency} value={currency}>{currency}</SelectItem>)}
          </MoneySelectField>
          <MoneySelectField id="transaction-account-filter" label="Account" value={accountId} selectedLabel={catalog.accounts.find((account) => account.id === accountId)?.name} emptyLabel="All accounts" onValueChange={setAccountId} size="compact">
            {catalog.accounts.map((account) => <SelectItem key={account.id} value={account.id}>{account.name}</SelectItem>)}
          </MoneySelectField>
          <MoneySelectField id="transaction-payee-filter" label="Payee" value={payeeId} selectedLabel={catalog.payees.find((payee) => payee.id === payeeId)?.name} emptyLabel="All payees" onValueChange={setPayeeId} size="compact">
            {catalog.payees.map((payee) => <SelectItem key={payee.id} value={payee.id}>{payee.name}</SelectItem>)}
          </MoneySelectField>
          <MoneySelectField id="transaction-category-filter" label="Category" value={categoryId} selectedLabel={catalog.categories.find((category) => category.id === categoryId)?.name} emptyLabel="All categories" onValueChange={setCategoryId} size="compact">
            {catalog.categories.map((category) => <SelectItem key={category.id} value={category.id}>{category.name}</SelectItem>)}
          </MoneySelectField>
          <MoneySelectField id="transaction-reconciliation-filter" label="Reconciliation" value={reconciliationState} selectedLabel={reconciliationState ? reconciliationState[0].toUpperCase() + reconciliationState.slice(1) : undefined} emptyLabel="Any state" onValueChange={setReconciliationState} size="compact">
            <SelectItem value="uncleared">Uncleared</SelectItem>
            <SelectItem value="cleared">Cleared</SelectItem>
            <SelectItem value="reconciled">Reconciled</SelectItem>
          </MoneySelectField>
        </div>
        <label htmlFor="transaction-include-voided" className="flex min-h-10 items-center gap-2 text-sm">
          <Checkbox id="transaction-include-voided" checked={includeVoided} onCheckedChange={(checked) => setIncludeVoided(checked === true)} />
          <span>Include voided transactions</span>
        </label>
      </PopoverContent>
    </Popover>
  );
}

function TransactionsWorkspace() {
  const periodDefaults = useMemo(() => periodRange(currentPeriod()), []);
  const [period, setPeriod] = useState(currentPeriod);
  const [rangeMode, setRangeMode] = useState<RangeMode>("month");
  const [dateFrom, setDateFrom] = useState(periodDefaults.start);
  const [dateTo, setDateTo] = useState(periodDefaults.end);
  const [currencyCode, setCurrencyCode] = useState("PHP");
  const [accountId, setAccountId] = useState("");
  const [payeeId, setPayeeId] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [reconciliationState, setReconciliationState] = useState("");
  const [includeVoided, setIncludeVoided] = useState(false);
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerTransactionId, setDrawerTransactionId] = useState<string | null>(null);
  const [activeView, setActiveView] = useState<MoneyView>("ledger");
  const catalog = useMoneyCatalog();
  const installmentPlansQuery = useMoneyInstallmentPlans();

  useEffect(() => {
    const timer = window.setTimeout(() => setSearch(searchInput.trim()), 250);
    return () => window.clearTimeout(timer);
  }, [searchInput]);

  const filters = useMemo(() => ({
    dateFrom: rangeMode === "month" ? periodRange(period).start : rangeMode === "custom" ? dateFrom || undefined : undefined,
    dateTo: rangeMode === "month" ? periodRange(period).end : rangeMode === "custom" ? dateTo || undefined : undefined,
    accountId: accountId || undefined,
    payeeId: payeeId || undefined,
    categoryId: categoryId || undefined,
    currencyCode: currencyCode || undefined,
    reconciliationState: reconciliationState ? reconciliationState as "uncleared" | "cleared" | "reconciled" : undefined,
    includeVoided,
    search: search || undefined,
  }), [accountId, categoryId, currencyCode, dateFrom, dateTo, includeVoided, payeeId, period, rangeMode, reconciliationState, search]);
  const transactionsQuery = useMoneyTransactions(filters);
  const summaryQuery = useQuery({
    queryKey: [...moneySummaryQueryKey, period, currencyCode],
    queryFn: () => getMoneySummary(period, currencyCode),
  });
  const transactions = transactionsQuery.data?.pages.flatMap((page) => page.items) ?? [];
  const installmentPlans = installmentPlansQuery.data?.pages.flatMap((page) => page.items) ?? [];
  const currencyOptions = [...new Set(["PHP", ...catalog.accounts.map((account) => account.currency_code)])];
  const rangeLabel = rangeMode === "month" ? periodLabel(period) : rangeMode === "custom" ? `${dateFrom || "Start"}–${dateTo || "End"}` : "All history";

  function openCreate() {
    setDrawerTransactionId(null);
    setDrawerOpen(true);
  }

  function openTransaction(transactionId: string) {
    setDrawerTransactionId(transactionId);
    setDrawerOpen(true);
  }

  function clearFilters() {
    setRangeMode("month");
    const nextPeriod = currentPeriod();
    setPeriod(nextPeriod);
    const nextRange = periodRange(nextPeriod);
    setDateFrom(nextRange.start);
    setDateTo(nextRange.end);
    setCurrencyCode("PHP");
    setAccountId("");
    setPayeeId("");
    setCategoryId("");
    setReconciliationState("");
    setIncludeVoided(false);
    setSearchInput("");
    setSearch("");
  }

  const activeFilters = useMemo<ActiveFilter[]>(() => {
    const active: ActiveFilter[] = [];
    if (search) active.push({ id: "search", label: `Search: ${search}`, onRemove: () => { setSearchInput(""); setSearch(""); } });
    if (rangeMode !== "month") active.push({ id: "range", label: rangeMode === "custom" ? `Dates: ${rangeLabel}` : "All history", onRemove: () => setRangeMode("month") });
    if (rangeMode === "month" && period !== currentPeriod()) active.push({ id: "period", label: `Month: ${periodLabel(period)}`, onRemove: () => { const next = currentPeriod(); setPeriod(next); const range = periodRange(next); setDateFrom(range.start); setDateTo(range.end); } });
    if (currencyCode !== "PHP") active.push({ id: "currency", label: `Currency: ${currencyCode}`, onRemove: () => setCurrencyCode("PHP") });
    if (accountId) active.push({ id: "account", label: `Account: ${catalog.accounts.find((account) => account.id === accountId)?.name ?? "Selected"}`, onRemove: () => setAccountId("") });
    if (payeeId) active.push({ id: "payee", label: `Payee: ${catalog.payees.find((payee) => payee.id === payeeId)?.name ?? "Selected"}`, onRemove: () => setPayeeId("") });
    if (categoryId) active.push({ id: "category", label: `Category: ${catalog.categories.find((category) => category.id === categoryId)?.name ?? "Selected"}`, onRemove: () => setCategoryId("") });
    if (reconciliationState) active.push({ id: "reconciliation", label: `State: ${reconciliationState}`, onRemove: () => setReconciliationState("") });
    if (includeVoided) active.push({ id: "voided", label: "Including voided", onRemove: () => setIncludeVoided(false) });
    return active;
  }, [accountId, categoryId, catalog.accounts, catalog.categories, catalog.payees, currencyCode, includeVoided, payeeId, period, rangeLabel, rangeMode, reconciliationState, search]);

  return (
    <div className="space-y-8">
      <header className="flex flex-col gap-5 border-b border-border/70 pb-6 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="font-mono text-[0.66rem] uppercase tracking-[0.18em] text-muted-foreground">Money</p>
          <h1 className="mt-2 text-3xl font-semibold tracking-[-0.035em]">Transactions</h1>
          <p className="mt-3 max-w-xl text-sm leading-6 text-muted-foreground">Search the ledger by what happened, who it involved, or where the money moved.</p>
        </div>
      </header>

      <section aria-label="Transaction summary" className="grid gap-3 sm:grid-cols-3">
        {[
          ["Balance", summaryQuery.data?.total_balance, "Across active accounts"],
          ["Income", summaryQuery.data?.income_amount, `Recorded in ${periodLabel(period)}`],
          ["Spending", summaryQuery.data?.spending_amount, "Posted outflows"],
        ].map(([label, value, detail], index) => (
          <Card key={label} className={cn("relative rounded-xl border-border/80 p-4 shadow-none", index === 0 && "overflow-hidden")}>
            {index === 0 ? <span className="absolute inset-y-0 left-0 w-1 bg-primary/80" aria-hidden="true" /> : null}
            <p className="font-mono text-[0.64rem] uppercase tracking-[0.14em] text-muted-foreground">{label}</p>
            <p className="mt-3 text-xl font-semibold tracking-[-0.03em]">{value ? formatMoney(value, currencyCode) : "—"}</p>
            <p className="mt-1 text-xs text-muted-foreground">{detail}</p>
          </Card>
        ))}
      </section>

      {catalog.isError || summaryQuery.isError ? (
        <div role="alert" className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm">
          <span className="text-destructive">{catalog.isError ? "Money filters could not load." : describeMoneyError(summaryQuery.error)}</span>
          <Button type="button" variant="outline" size="sm" onClick={() => { if (catalog.isError) void catalog.refetch(); if (summaryQuery.isError) void summaryQuery.refetch(); }}>Try again</Button>
        </div>
      ) : null}

      <MoneyViewTabs activeView={activeView} onViewChange={setActiveView} />

      {activeView === "ledger" ? <section id="money-view-panel" role="tabpanel" aria-labelledby="money-view-ledger" aria-label="Ledger" tabIndex={0} className="overflow-hidden rounded-xl border border-border/80 bg-card shadow-none outline-none focus-visible:ring-3 focus-visible:ring-ring/40">
        <div className="space-y-4 px-4 py-4 sm:px-5">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <p className="font-mono text-[0.64rem] uppercase tracking-[0.16em] text-muted-foreground">Ledger</p>
                <span className="text-xs text-muted-foreground">{transactionsQuery.data ? `${transactions.length} visible` : "Loading"}</span>
              </div>
              <h2 id="transaction-list-title" className="mt-1 text-lg font-medium">{rangeLabel} · {currencyCode}</h2>
            </div>
            <div className="flex w-full flex-col gap-2 sm:flex-row lg:w-auto">
              <label className="relative min-w-0 flex-1 sm:min-w-72" htmlFor="transaction-search">
                <span className="sr-only">Search transactions</span>
                <Search aria-hidden="true" className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                <Input id="transaction-search" value={searchInput} onChange={(event) => setSearchInput(event.target.value)} placeholder="Search ledger…" className="h-10 pl-9" />
              </label>
              <TransactionFilterPopover
                rangeMode={rangeMode}
                setRangeMode={setRangeMode}
                period={period}
                setPeriod={setPeriod}
                dateFrom={dateFrom}
                setDateFrom={setDateFrom}
                dateTo={dateTo}
                setDateTo={setDateTo}
                currencyCode={currencyCode}
                setCurrencyCode={setCurrencyCode}
                accountId={accountId}
                setAccountId={setAccountId}
                payeeId={payeeId}
                setPayeeId={setPayeeId}
                categoryId={categoryId}
                setCategoryId={setCategoryId}
                reconciliationState={reconciliationState}
                setReconciliationState={setReconciliationState}
                includeVoided={includeVoided}
                setIncludeVoided={setIncludeVoided}
                currencyOptions={currencyOptions}
                catalog={catalog}
                activeFilterCount={activeFilters.length}
              />
            </div>
          </div>
          {activeFilters.length ? (
            <div className="flex flex-wrap items-center gap-2 border-t border-border/70 pt-3">
              <span className="text-xs text-muted-foreground">Refined by</span>
              {activeFilters.map((filter) => <ActiveFilterChip key={filter.id} filter={filter} />)}
              <Button type="button" variant="ghost" size="sm" className="h-7 px-2 text-xs" onClick={clearFilters}>Clear all</Button>
            </div>
          ) : null}
        </div>
        <div className="hidden border-y border-border/70 bg-background px-5 py-2 font-mono text-[0.62rem] uppercase tracking-[0.1em] text-muted-foreground sm:grid sm:grid-cols-[7rem_minmax(0,1.3fr)_minmax(0,1fr)_7rem_8rem] sm:gap-3"><span>Date</span><span>Transaction</span><span>Context</span><span>Reconciliation</span><span className="text-right">Amount</span></div>
        {transactionsQuery.isPending ? <div className="space-y-3 p-5" aria-label="Loading transactions"><div className="h-12 animate-pulse rounded-lg bg-muted" /><div className="h-12 animate-pulse rounded-lg bg-muted" /><div className="h-12 animate-pulse rounded-lg bg-muted" /></div> : null}
        {transactionsQuery.isError ? <div className="p-8 text-center"><ReceiptText aria-hidden="true" className="mx-auto size-7 text-destructive" /><h3 className="mt-3 text-sm font-medium">Transactions could not load.</h3><p className="mt-2 text-sm text-muted-foreground">{describeMoneyError(transactionsQuery.error)}</p><Button type="button" variant="outline" size="sm" className="mt-4" onClick={() => void transactionsQuery.refetch()}>Try again</Button></div> : null}
        {transactionsQuery.isSuccess && !transactions.length ? <div className="p-8 text-center"><ReceiptText aria-hidden="true" className="mx-auto size-7 text-primary-strong" /><h3 className="mt-3 text-sm font-medium">No transactions in this view.</h3><p className="mx-auto mt-2 max-w-sm text-sm leading-6 text-muted-foreground">Try another search or filter combination.</p></div> : null}
        {transactions.length ? <ul aria-label="Money transactions" className="divide-y divide-border/70">{transactions.map((transaction) => <TransactionRow key={transaction.id} transaction={transaction} accounts={catalog.accounts} payees={catalog.payees} categories={catalog.categories} onOpen={() => openTransaction(transaction.id)} />)}</ul> : null}
        {transactionsQuery.hasNextPage ? <div className="border-t border-border/70 p-3"><Button type="button" variant="outline" className="w-full" disabled={transactionsQuery.isFetchingNextPage} onClick={() => void transactionsQuery.fetchNextPage()}>{transactionsQuery.isFetchingNextPage ? "Loading more…" : "Load more transactions"}</Button></div> : null}
      </section> : null}

      {activeView === "installments" ? <section id="money-view-panel" role="tabpanel" aria-labelledby="money-view-installments" tabIndex={0} className="outline-none focus-visible:ring-3 focus-visible:ring-ring/40">
        <InstallmentPlansSection
          plans={installmentPlans}
          accounts={catalog.accounts}
          isPending={installmentPlansQuery.isPending}
          isError={installmentPlansQuery.isError}
          error={installmentPlansQuery.error}
          onRetry={() => void installmentPlansQuery.refetch()}
        />
      </section> : null}

      {activeView === "recurring" ? (
        <RecurringTransactionsSection
          accounts={catalog.accounts}
          payees={catalog.payees}
          categories={catalog.categories}
        />
      ) : null}

      <TransactionDrawer open={drawerOpen} onOpenChange={(open) => { setDrawerOpen(open); if (!open) setDrawerTransactionId(null); }} transactionId={drawerTransactionId} defaultDate={currentLocalDateInput()} defaultCurrencyCode={currencyCode} accounts={catalog.accounts} payees={catalog.payees} categories={catalog.categories} />
      {activeView !== "recurring" ? <MoneyFloatingAction onClick={openCreate} /> : null}
    </div>
  );
}

export function TransactionsRoute() {
  const currentUser = useCurrentUser();
  return <WorkspaceRouteGuard>{currentUser.data ? <WorkspaceShell email={currentUser.data.email}><TransactionsWorkspace /></WorkspaceShell> : null}</WorkspaceRouteGuard>;
}

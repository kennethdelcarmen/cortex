"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowDownLeft, ArrowUpRight, Building2, CalendarDays, CheckCircle2, CircleAlert, Landmark, ReceiptText, WalletCards } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { useCurrentUser } from "@/features/auth/hooks";
import { WorkspaceRouteGuard, WorkspaceShell } from "@/features/workspace/components/workspace-shell";
import { cn } from "@/lib/utils";
import {
  getMoneySummary,
  listMoneyBudgets,
  moneyBudgetsQueryKey,
  moneySummaryQueryKey,
  type MoneyAccount,
  type MoneyBudget,
  type MoneyCategory,
  type MoneySummary,
  type MoneyTransaction,
} from "../api";
import { useMoneyCatalog, useMoneyTransactions } from "../hooks";
import { MoneyFloatingAction } from "./money-floating-action";
import { MoneySelectField } from "./money-select-field";
import { TransactionDrawer } from "./transaction-drawer";
import {
  accountLabel,
  accountTypeLabel,
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

type BudgetFilter = "all" | "on_track" | "needs_attention";

function MetricCard({ label, value, detail, tone, icon: Icon, accent = false }: { label: string; value?: string; detail: string; tone: string; icon: typeof WalletCards; accent?: boolean }) {
  return <Card className={cn("relative min-w-0 rounded-xl border-border/80 p-5 shadow-none", accent && "overflow-hidden")}>
    {accent ? <span className="absolute inset-y-0 left-0 w-1 bg-primary/80" aria-hidden="true" /> : null}
    <div className="flex items-center justify-between gap-3"><span className={cn("font-mono text-[0.64rem] uppercase tracking-[0.14em]", tone)}>{label}</span><Icon aria-hidden="true" className={cn("size-4", tone)} /></div>
    <p className="mt-4 truncate text-2xl font-semibold tracking-[-0.035em]">{value ?? "—"}</p>
    <p className="mt-2 text-xs leading-5 text-muted-foreground">{detail}</p>
  </Card>;
}

function MoneySummary({ summary, currencyCode, period, pending }: { summary?: MoneySummary; currencyCode: string; period: string; pending: boolean }) {
  const values = [
    { label: "Total balance", value: summary ? formatMoney(summary.total_balance, currencyCode) : undefined, detail: "Across active accounts", tone: "text-primary-strong", icon: WalletCards, accent: true },
    { label: "Income", value: summary ? formatMoney(summary.income_amount, currencyCode) : undefined, detail: `Recorded in ${periodLabel(period)}`, tone: "text-tag-sea-glass-foreground", icon: ArrowDownLeft },
    { label: "Spending", value: summary ? formatMoney(summary.spending_amount, currencyCode) : undefined, detail: "Posted outflows", tone: "text-tag-amber-foreground", icon: ArrowUpRight },
    { label: "Budget left", value: summary ? formatMoney(summary.budget_remaining_amount, currencyCode) : undefined, detail: "Across planned categories", tone: summary && Number(summary.budget_remaining_amount) < 0 ? "text-destructive" : "text-tag-sea-glass-foreground", icon: CheckCircle2 },
  ];
  return <section aria-labelledby="money-snapshot-title" className="mt-7"><div className="mb-4 flex flex-wrap items-end justify-between gap-3"><div><p className="font-mono text-[0.66rem] uppercase tracking-[0.18em] text-muted-foreground">Monthly snapshot</p><h2 id="money-snapshot-title" className="mt-2 text-xl font-medium tracking-[-0.025em] sm:text-2xl">Make the month legible.</h2></div><p className="font-mono text-[0.65rem] uppercase tracking-[0.12em] text-muted-foreground">{currencyCode} · {periodLabel(period)}</p></div><div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">{values.map((metric) => <MetricCard key={metric.label} {...metric} value={pending ? undefined : metric.value} />)}</div></section>;
}

function EmptyState({ icon: Icon, title, description }: { icon: typeof WalletCards; title: string; description: string }) {
  return <div className="py-5"><Icon aria-hidden="true" className="size-5 text-primary-strong" /><h3 className="mt-3 text-sm font-medium">{title}</h3><p className="mt-1 max-w-sm text-sm leading-6 text-muted-foreground">{description}</p></div>;
}

function BudgetRow({ budget, category }: { budget: MoneyBudget; category?: MoneyCategory }) {
  const amount = Number(budget.amount);
  const spent = Number(budget.spent_amount);
  const remaining = amount - spent;
  const usage = amount > 0 ? Math.round((spent / amount) * 100) : 0;
  const attention = remaining < 0;
  const progress = Math.min(100, Math.max(0, usage));
  return <li className="border-t border-border/70 py-4 first:border-t-0 first:pt-0 last:pb-0"><div className="flex flex-wrap items-start justify-between gap-x-5 gap-y-2"><div className="min-w-0"><div className="flex items-center gap-2">{attention ? <CircleAlert aria-hidden="true" className="size-4 shrink-0 text-destructive" /> : <CheckCircle2 aria-hidden="true" className="size-4 shrink-0 text-tag-sea-glass-foreground" />}<h3 className="truncate text-sm font-medium">{category?.name ?? "Unknown category"}</h3></div><p className="mt-1 pl-6 text-xs text-muted-foreground">{attention ? "Needs attention" : "On track"} · {usage}% used</p></div><p className={cn("shrink-0 font-mono text-xs", attention ? "text-destructive" : "text-muted-foreground")}>{attention ? `${formatMoney(Math.abs(remaining), budget.currency_code)} over` : `${formatMoney(remaining, budget.currency_code)} left`}</p></div><div className="mt-3 h-2 overflow-hidden rounded-full bg-muted" role="progressbar" aria-label={`${category?.name ?? "Category"} budget usage`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={progress} aria-valuetext={`${usage}% used`}><span className={cn("block h-full rounded-full", attention ? "bg-destructive" : progress >= 85 ? "bg-tag-amber" : "bg-tag-sea-glass")} style={{ width: `${progress}%` }} /></div><div className="mt-2 flex justify-between gap-3 font-mono text-[0.64rem] uppercase tracking-[0.08em] text-muted-foreground"><span>{formatMoney(budget.spent_amount, budget.currency_code)} spent</span><span>{formatMoney(budget.amount, budget.currency_code)} planned</span></div></li>;
}

function BudgetPanel({ budgets, categories, pending }: { budgets: MoneyBudget[]; categories: MoneyCategory[]; pending: boolean }) {
  const [filter, setFilter] = useState<BudgetFilter>("all");
  const categoryById = new Map(categories.map((category) => [category.id, category]));
  const visibleBudgets = budgets.filter((budget) => filter === "all" || (filter === "needs_attention" ? Number(budget.spent_amount) > Number(budget.amount) : Number(budget.spent_amount) <= Number(budget.amount)));
  return <Card className="rounded-xl border-border/80 p-5 shadow-none sm:p-6"><div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between"><div><div className="flex items-center gap-2 text-primary-strong"><WalletCards aria-hidden="true" className="size-4" /><p className="font-mono text-[0.66rem] font-medium uppercase tracking-[0.16em]">Planned spending</p></div><h2 className="mt-3 text-xl font-medium tracking-[-0.025em]">Budget pulse</h2><p className="mt-2 max-w-xl text-sm leading-6 text-muted-foreground">See where the month is steady and where it needs a little attention.</p></div><div className="flex flex-wrap gap-1" role="group" aria-label="Filter budgets">{(["all", "on_track", "needs_attention"] as BudgetFilter[]).map((item) => <Button key={item} type="button" variant={filter === item ? "secondary" : "ghost"} size="sm" aria-pressed={filter === item} onClick={() => setFilter(item)} className="h-8 text-xs">{item === "all" ? "All" : item === "on_track" ? "On track" : "Needs attention"}</Button>)}</div></div><Separator className="my-5" />{pending ? <div className="space-y-3"><div className="h-12 animate-pulse rounded-lg bg-muted" /><div className="h-12 animate-pulse rounded-lg bg-muted" /></div> : visibleBudgets.length ? <ul aria-label={`${filter} budgets`}>{visibleBudgets.map((budget) => <BudgetRow key={budget.id} budget={budget} category={categoryById.get(budget.category_id)} />)}</ul> : <EmptyState icon={CheckCircle2} title="Nothing needs attention here." description="Every category is currently within its planned amount." />}</Card>;
}

function AccountsPanel({ accounts, pending }: { accounts: MoneyAccount[]; pending: boolean }) {
  return <Card className="rounded-xl border-border/80 p-5 shadow-none sm:p-6"><div className="flex items-start justify-between gap-3"><div><div className="flex items-center gap-2 text-primary-strong"><Landmark aria-hidden="true" className="size-4" /><p className="font-mono text-[0.66rem] font-medium uppercase tracking-[0.16em]">Where it lives</p></div><h2 className="mt-3 text-xl font-medium tracking-[-0.025em]">Accounts</h2></div><div className="flex flex-col items-end gap-2"><Badge variant="outline" className="font-mono text-[0.62rem] uppercase tracking-[0.1em]">{pending ? "…" : `${accounts.length} active`}</Badge><Link href="/money/accounts" className="rounded-sm text-xs font-medium text-primary-strong outline-none hover:underline focus-visible:ring-3 focus-visible:ring-ring/40">Manage</Link></div></div><div className="mt-5 divide-y divide-border/70 border-y border-border/70">{accounts.length ? accounts.map((account) => <div key={account.id} className="flex items-center gap-3 py-4 first:pt-3 last:pb-3"><span className="flex size-8 shrink-0 items-center justify-center rounded-md border border-border bg-background text-primary-strong">{account.account_type === "cash" ? <WalletCards aria-hidden="true" className="size-4" /> : <Building2 aria-hidden="true" className="size-4" />}</span><span className="min-w-0 flex-1"><span className="block truncate text-sm font-medium">{accountLabel(account)}</span><span className="mt-1 block truncate text-xs text-muted-foreground">{accountTypeLabel(account.account_type)} · {account.institution_name ?? "Local"}</span></span><span className="shrink-0 text-right"><span className="block font-mono text-sm font-medium">{formatMoney(account.balance, account.currency_code)}</span><span className="mt-1 block font-mono text-[0.62rem] uppercase tracking-[0.08em] text-muted-foreground">{account.currency_code}</span></span></div>) : <EmptyState icon={Landmark} title="No accounts yet." description="Create an account before recording a transaction." />}</div></Card>;
}

function ActivityPanel({ transactions, accounts, payees, categories, onOpen, pending }: { transactions: MoneyTransaction[]; accounts: MoneyAccount[]; payees: { id: string; name: string }[]; categories: MoneyCategory[]; onOpen: (id: string) => void; pending: boolean }) {
  const accountById = new Map(accounts.map((account) => [account.id, account]));
  const payeeById = new Map(payees.map((payee) => [payee.id, payee]));
  const categoryById = new Map(categories.map((category) => [category.id, category]));
 return <Card className="rounded-xl border-border/80 p-5 shadow-none sm:p-6"><div><div className="flex items-center gap-2 text-primary-strong"><ReceiptText aria-hidden="true" className="size-4" /><p className="font-mono text-[0.66rem] font-medium uppercase tracking-[0.16em]">Latest movement</p></div><h2 className="mt-3 text-xl font-medium tracking-[-0.025em]">Recent activity</h2></div><Separator className="my-5" />{pending ? <div className="space-y-3"><div className="h-12 animate-pulse rounded-lg bg-muted" /><div className="h-12 animate-pulse rounded-lg bg-muted" /></div> : transactions.length ? <ul aria-label="Recent money activity">{transactions.slice(0, 5).map((transaction) => { const accountPosting = transactionAccountPostings(transaction)[0]; const categoryPosting = transactionCategoryPostings(transaction)[0]; const account = accountPosting?.account_id ? accountById.get(accountPosting.account_id) : undefined; const category = categoryPosting?.category_id ? categoryById.get(categoryPosting.category_id) : undefined; const income = Number(transactionDisplayAmount(transaction)) > 0; const contextLabel = category?.name ?? (transactionMode(transaction, categories) === "transfer" ? "Transfer" : "Uncategorized"); return <li key={transaction.id}><button type="button" onClick={() => onOpen(transaction.id)} className="flex w-full items-center gap-3 border-t border-border/70 py-4 text-left outline-none transition-colors hover:bg-muted/30 focus-visible:ring-3 focus-visible:ring-ring/40 first:border-t-0 first:pt-0 last:pb-0"><span className={cn("flex size-8 shrink-0 items-center justify-center rounded-md border", income ? "border-tag-sea-glass/30 bg-tag-sea-glass/10 text-tag-sea-glass-foreground" : "border-border bg-background text-muted-foreground")}>{income ? <ArrowDownLeft aria-hidden="true" className="size-4" /> : <ReceiptText aria-hidden="true" className="size-4" />}</span><span className="min-w-0 flex-1"><span className="block truncate text-sm font-medium">{transaction.name}</span><span className="mt-1 block truncate text-xs text-muted-foreground">{[transaction.payee_id ? payeeById.get(transaction.payee_id)?.name : undefined, transaction.memo, contextLabel, account?.name ?? "Multiple accounts", transaction.transaction_date].filter(Boolean).join(" · ")}</span></span><span className={cn("shrink-0 font-mono text-sm font-medium", income ? "text-tag-sea-glass-foreground" : "text-foreground")}>{formatSignedMoney(transactionDisplayAmount(transaction), accountPosting?.currency_code ?? "PHP")}</span></button></li>; })}</ul> : <EmptyState icon={ReceiptText} title="No activity in this month." description="Posted income and spending will show up here as the month moves." />}</Card>;
}

function MoneyDashboard({ email }: { email: string }) {
  const [period, setPeriod] = useState(currentPeriod);
  const [currencyCode, setCurrencyCode] = useState("PHP");
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerTransactionId, setDrawerTransactionId] = useState<string | null>(null);
  const catalog = useMoneyCatalog();
  const range = periodRange(period);
  const summaryQuery = useQuery({ queryKey: [...moneySummaryQueryKey, period, currencyCode], queryFn: () => getMoneySummary(period, currencyCode) });
  const budgetsQuery = useQuery({ queryKey: [...moneyBudgetsQueryKey, period, currencyCode], queryFn: () => listMoneyBudgets({ period, currencyCode }) });
  const activityQuery = useMoneyTransactions({ dateFrom: range.start, dateTo: range.end, currencyCode });
  const transactions = activityQuery.data?.pages.flatMap((page) => page.items) ?? [];
  const currencyOptions = [...new Set(["PHP", ...catalog.accounts.map((account) => account.currency_code)])];

  function openCreate() { setDrawerTransactionId(null); setDrawerOpen(true); }
  function openTransaction(transactionId: string) { setDrawerTransactionId(transactionId); setDrawerOpen(true); }
  function retryLiveData() {
    void Promise.all([
      catalog.refetch(),
      summaryQuery.refetch(),
      budgetsQuery.refetch(),
      activityQuery.refetch(),
    ]);
  }

  return (
    <WorkspaceShell email={email}>
      <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_18rem] lg:gap-14">
        <div className="min-w-0">
          <header className="flex flex-col gap-5 border-b border-border/70 pb-6 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <p className="font-mono text-[0.66rem] uppercase tracking-[0.18em] text-muted-foreground">Money</p>
              <h1 className="mt-2 text-3xl font-semibold tracking-[-0.035em]">Overview</h1>
              <p className="mt-3 max-w-xl text-sm leading-6 text-muted-foreground">Keep the month close, then record the next movement without leaving the page.</p>
            </div>
            <div className="flex flex-wrap items-end gap-3">
              <label htmlFor="money-period" className="flex flex-col gap-2 font-mono text-[0.62rem] uppercase tracking-[0.14em] text-muted-foreground">
                View month
                <Select value={period} onValueChange={(value) => value && setPeriod(value)}>
                  <SelectTrigger id="money-period" aria-label="Choose money month" className="h-10 w-44 bg-background font-sans text-sm normal-case tracking-normal">
                    <CalendarDays aria-hidden="true" className="size-4 text-primary-strong" />
                    <SelectValue>{periodLabel(period)}</SelectValue>
                  </SelectTrigger>
                  <SelectContent>{periodOptions().map((option) => <SelectItem key={option.id} value={option.id}>{option.label}</SelectItem>)}</SelectContent>
                </Select>
              </label>
              <MoneySelectField
                id="money-currency"
                label="Currency"
                value={currencyCode}
                selectedLabel={currencyCode}
                onValueChange={setCurrencyCode}
                size="compact"
                triggerClassName="w-24"
              >
                {currencyOptions.map((currency) => <SelectItem key={currency} value={currency}>{currency}</SelectItem>)}
              </MoneySelectField>
            </div>
          </header>
          {catalog.isError || summaryQuery.isError || budgetsQuery.isError || activityQuery.isError ? <div role="alert" className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm"><span className="text-destructive">{catalog.isError ? "Money catalog could not load." : summaryQuery.isError ? describeMoneyError(summaryQuery.error) : "Some money activity could not load."}</span><Button type="button" variant="outline" size="sm" onClick={retryLiveData}>Try again</Button></div> : null}
          <MoneySummary summary={summaryQuery.data} currencyCode={currencyCode} period={period} pending={summaryQuery.isPending} />
          <section aria-labelledby="money-budget-section" className="mt-8">
            <div className="mb-4 flex flex-wrap items-end justify-between gap-3"><div><p className="font-mono text-[0.66rem] uppercase tracking-[0.18em] text-muted-foreground">Where the month is going</p><h2 id="money-budget-section" className="mt-2 text-xl font-medium tracking-[-0.025em] sm:text-2xl">Budget pulse</h2></div><div className="flex items-center gap-3"><span className="font-mono text-[0.65rem] uppercase tracking-[0.12em] text-muted-foreground">{budgetsQuery.data?.items.length ?? 0} categories</span><Link href="/money/budgets" className="rounded-sm text-xs font-medium text-primary-strong outline-none hover:underline focus-visible:ring-3 focus-visible:ring-ring/40">Manage budgets</Link></div></div>
            <BudgetPanel budgets={budgetsQuery.data?.items ?? []} categories={catalog.categories} pending={budgetsQuery.isPending || catalog.isPending} />
          </section>
          <section aria-labelledby="money-activity-section" className="mt-8">
            <div className="mb-4"><p className="font-mono text-[0.66rem] uppercase tracking-[0.18em] text-muted-foreground">Close to the surface</p><h2 id="money-activity-section" className="mt-2 text-xl font-medium tracking-[-0.025em] sm:text-2xl">Recent movement</h2></div>
            <ActivityPanel transactions={transactions} accounts={catalog.accounts} payees={catalog.payees} categories={catalog.categories} onOpen={openTransaction} pending={activityQuery.isPending} />
          </section>
        </div>
        <aside className="min-w-0 lg:pt-1" aria-label="Money context">
          <AccountsPanel accounts={catalog.accounts} pending={catalog.isPending} />
          <Card className="relative mt-6 overflow-hidden rounded-xl border-border/80 p-5 shadow-none sm:p-6">
            <span className="absolute inset-y-0 left-0 w-1 bg-primary/75" aria-hidden="true" />
            <div className="flex items-center gap-2 text-primary-strong"><CalendarDays aria-hidden="true" className="size-4" /><p className="font-mono text-[0.66rem] font-medium uppercase tracking-[0.16em]">Keep the signal close</p></div>
            <h2 className="mt-4 text-lg font-medium tracking-[-0.025em]">A quiet month is a useful month.</h2>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">Use Create transaction to capture a movement while the month is still in reach.</p>
          </Card>
        </aside>
      </div>
      <TransactionDrawer open={drawerOpen} onOpenChange={(open) => { setDrawerOpen(open); if (!open) setDrawerTransactionId(null); }} defaultDate={new Date().toISOString().slice(0, 10)} defaultCurrencyCode={currencyCode} transactionId={drawerTransactionId} accounts={catalog.accounts} payees={catalog.payees} categories={catalog.categories} />
      <MoneyFloatingAction onClick={openCreate} />
    </WorkspaceShell>
  );
}

export function MoneyRoute() {
  const currentUser = useCurrentUser();
  return <WorkspaceRouteGuard>{currentUser.data ? <MoneyDashboard email={currentUser.data.email} /> : null}</WorkspaceRouteGuard>;
}

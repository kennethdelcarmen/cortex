"use client";

import {
  ArrowDownLeft,
  ArrowUpRight,
  Building2,
  CalendarDays,
  CheckCircle2,
  CircleAlert,
  Landmark,
  ReceiptText,
  WalletCards,
} from "lucide-react";
import { useMemo, useState } from "react";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import {
  WorkspaceRouteGuard,
  WorkspaceShell,
} from "@/features/workspace/components/workspace-shell";
import { useCurrentUser } from "@/features/auth/hooks";
import { cn } from "@/lib/utils";
import {
  moneyPeriodOptions,
  moneyPeriods,
  type MoneyAccount,
  type MoneyBudget,
  type MoneyPeriod,
  type MoneyPeriodId,
  type MoneyTransaction,
} from "../money-data";

type BudgetFilter = "all" | "on_track" | "needs_attention";

const currencyFormatter = new Intl.NumberFormat("en-PH", {
  style: "currency",
  currency: "PHP",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

function formatMoney(amount: number) {
  return currencyFormatter.format(amount);
}

function formatSignedMoney(amount: number) {
  const sign = amount > 0 ? "+" : amount < 0 ? "−" : "";
  return `${sign}${formatMoney(Math.abs(amount))}`;
}

function budgetRemaining(budget: MoneyBudget) {
  return budget.amount - budget.spent;
}

function budgetProgress(budget: MoneyBudget) {
  return Math.min(100, budgetUsagePercent(budget));
}

function budgetUsagePercent(budget: MoneyBudget) {
  return Math.round((budget.spent / budget.amount) * 100);
}

function isBudgetNeedsAttention(budget: MoneyBudget) {
  return budget.spent > budget.amount;
}

function accountLabel(account: MoneyAccount) {
  return account.lastFour ? `${account.name} ··${account.lastFour}` : account.name;
}

function metricIcon(metric: "balance" | "income" | "spending" | "budget") {
  if (metric === "income") {
    return ArrowDownLeft;
  }

  if (metric === "spending") {
    return ArrowUpRight;
  }

  if (metric === "budget") {
    return CheckCircle2;
  }

  return WalletCards;
}

function MoneySummary({ period }: { period: MoneyPeriod }) {
  const budgetLeft = period.budgets.reduce(
    (remaining, budget) => remaining + budgetRemaining(budget),
    0,
  );
  const metrics = [
    {
      key: "balance" as const,
      label: "Total balance",
      value: period.balance,
      detail: "Across active accounts",
      tone: "text-primary-strong",
    },
    {
      key: "income" as const,
      label: "Income",
      value: period.income,
      detail: "Recorded this month",
      tone: "text-tag-sea-glass-foreground",
    },
    {
      key: "spending" as const,
      label: "Spending",
      value: period.spending,
      detail: "Posted outflows",
      tone: "text-tag-amber-foreground",
    },
    {
      key: "budget" as const,
      label: "Budget left",
      value: budgetLeft,
      detail: "Across planned categories",
      tone: budgetLeft >= 0 ? "text-tag-sea-glass-foreground" : "text-destructive",
    },
  ];

  return (
    <section aria-labelledby="money-snapshot-title" className="mt-7">
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="font-mono text-[0.66rem] uppercase tracking-[0.18em] text-muted-foreground">
            Monthly snapshot
          </p>
          <h2
            id="money-snapshot-title"
            className="mt-2 text-xl font-medium tracking-[-0.025em] sm:text-2xl"
          >
            Make the month legible.
          </h2>
        </div>
        <p className="font-mono text-[0.65rem] uppercase tracking-[0.12em] text-muted-foreground">
          PHP · {period.label}
        </p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {metrics.map((metric, index) => {
          const Icon = metricIcon(metric.key);

          return (
            <Card
              key={metric.key}
              className={cn(
                "relative min-w-0 rounded-xl border-border/80 p-5 shadow-none",
                index === 0 && "overflow-hidden",
              )}
            >
              {index === 0 ? (
                <span className="absolute inset-y-0 left-0 w-1 bg-primary/80" aria-hidden="true" />
              ) : null}
              <div className="flex items-center justify-between gap-3">
                <span className={cn("font-mono text-[0.64rem] uppercase tracking-[0.14em]", metric.tone)}>
                  {metric.label}
                </span>
                <Icon aria-hidden="true" className={cn("size-4", metric.tone)} />
              </div>
              <p className="mt-4 truncate text-2xl font-semibold tracking-[-0.035em]">
                {formatMoney(metric.value)}
              </p>
              <p className="mt-2 text-xs leading-5 text-muted-foreground">{metric.detail}</p>
            </Card>
          );
        })}
      </div>
    </section>
  );
}

function BudgetFilter({
  value,
  onChange,
}: {
  value: BudgetFilter;
  onChange: (value: BudgetFilter) => void;
}) {
  const options: Array<{ value: BudgetFilter; label: string }> = [
    { value: "all", label: "All" },
    { value: "on_track", label: "On track" },
    { value: "needs_attention", label: "Needs attention" },
  ];

  return (
    <div className="flex flex-wrap gap-1" role="group" aria-label="Filter budgets">
      {options.map((option) => (
        <Button
          key={option.value}
          type="button"
          variant={value === option.value ? "secondary" : "ghost"}
          size="sm"
          aria-pressed={value === option.value}
          onClick={() => onChange(option.value)}
          className="h-8 text-xs"
        >
          {option.label}
        </Button>
      ))}
    </div>
  );
}

function BudgetRow({ budget }: { budget: MoneyBudget }) {
  const attention = isBudgetNeedsAttention(budget);
  const remaining = budgetRemaining(budget);
  const progress = budgetProgress(budget);
  const usage = budgetUsagePercent(budget);

  return (
    <li className="border-t border-border/70 py-4 first:border-t-0 first:pt-0 last:pb-0">
      <div className="flex flex-wrap items-start justify-between gap-x-5 gap-y-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            {attention ? (
              <CircleAlert aria-hidden="true" className="size-4 shrink-0 text-destructive" />
            ) : (
              <CheckCircle2 aria-hidden="true" className="size-4 shrink-0 text-tag-sea-glass-foreground" />
            )}
            <h3 className="truncate text-sm font-medium">{budget.category}</h3>
          </div>
          <p className="mt-1 pl-6 text-xs text-muted-foreground">
            {attention ? "Needs attention" : "On track"} · {usage}% used
          </p>
        </div>
        <p className={cn("shrink-0 font-mono text-xs", attention ? "text-destructive" : "text-muted-foreground")}>
          {attention ? `${formatMoney(Math.abs(remaining))} over` : `${formatMoney(remaining)} left`}
        </p>
      </div>
      <div
        className="mt-3 h-2 overflow-hidden rounded-full bg-muted"
        role="progressbar"
        aria-label={`${budget.category} budget usage`}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={progress}
        aria-valuetext={`${usage}% used`}
      >
        <span
          className={cn(
            "block h-full rounded-full transition-[width] duration-300",
            attention ? "bg-destructive" : progress >= 85 ? "bg-tag-amber" : "bg-tag-sea-glass",
          )}
          style={{ width: `${progress}%` }}
        />
      </div>
      <div className="mt-2 flex justify-between gap-3 font-mono text-[0.64rem] uppercase tracking-[0.08em] text-muted-foreground">
        <span>{formatMoney(budget.spent)} spent</span>
        <span>{formatMoney(budget.amount)} planned</span>
      </div>
    </li>
  );
}

function BudgetPanel({ period }: { period: MoneyPeriod }) {
  const [filter, setFilter] = useState<BudgetFilter>("all");
  const budgets = period.budgets.filter((budget) => {
    if (filter === "needs_attention") {
      return isBudgetNeedsAttention(budget);
    }

    if (filter === "on_track") {
      return !isBudgetNeedsAttention(budget);
    }

    return true;
  });

  return (
    <Card className="rounded-xl border-border/80 p-5 shadow-none sm:p-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="flex items-center gap-2 text-primary-strong">
            <WalletCards aria-hidden="true" className="size-4" />
            <p className="font-mono text-[0.66rem] font-medium uppercase tracking-[0.16em]">
              Planned spending
            </p>
          </div>
          <h2 className="mt-3 text-xl font-medium tracking-[-0.025em]">Budget pulse</h2>
          <p className="mt-2 max-w-xl text-sm leading-6 text-muted-foreground">
            See where the month is steady and where it needs a little attention.
          </p>
        </div>
        <BudgetFilter value={filter} onChange={setFilter} />
      </div>

      <Separator className="my-5" />

      {budgets.length ? (
        <ul aria-label={`${filter} budgets`}>
          {budgets.map((budget) => (
            <BudgetRow key={budget.id} budget={budget} />
          ))}
        </ul>
      ) : (
        <EmptyState
          icon={CheckCircle2}
          title="Nothing needs attention here."
          description="Every category is currently within its planned amount."
        />
      )}
    </Card>
  );
}

function AccountsPanel({ accounts }: { accounts: MoneyAccount[] }) {
  return (
    <Card className="rounded-xl border-border/80 p-5 shadow-none sm:p-6">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 text-primary-strong">
            <Landmark aria-hidden="true" className="size-4" />
            <p className="font-mono text-[0.66rem] font-medium uppercase tracking-[0.16em]">
              Where it lives
            </p>
          </div>
          <h2 className="mt-3 text-xl font-medium tracking-[-0.025em]">Accounts</h2>
        </div>
        <Badge variant="outline" className="font-mono text-[0.62rem] uppercase tracking-[0.1em]">
          {accounts.length} active
        </Badge>
      </div>

      <div className="mt-5 divide-y divide-border/70 border-y border-border/70">
        {accounts.length ? (
          accounts.map((account) => (
            <div key={account.id} className="flex items-center gap-3 py-4 first:pt-3 last:pb-3">
              <span className="flex size-8 shrink-0 items-center justify-center rounded-md border border-border bg-background text-primary-strong">
                {account.type === "Cash" ? (
                  <WalletCards aria-hidden="true" className="size-4" />
                ) : (
                  <Building2 aria-hidden="true" className="size-4" />
                )}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium">{accountLabel(account)}</span>
                <span className="mt-1 block truncate text-xs text-muted-foreground">
                  {account.type} · {account.institution}
                </span>
              </span>
              <span className="shrink-0 text-right">
                <span className="block font-mono text-sm font-medium">{formatMoney(account.balance)}</span>
                <span className="mt-1 block font-mono text-[0.62rem] uppercase tracking-[0.08em] text-muted-foreground">
                  PHP
                </span>
              </span>
            </div>
          ))
        ) : (
          <EmptyState
            icon={Landmark}
            title="No accounts yet."
            description="Your active balances will appear here when accounts are connected."
          />
        )}
      </div>
    </Card>
  );
}

function ActivityRow({
  transaction,
  account,
}: {
  transaction: MoneyTransaction;
  account: MoneyAccount | undefined;
}) {
  const income = transaction.amount > 0;

  return (
    <li className="flex items-center gap-3 border-t border-border/70 py-4 first:border-t-0 first:pt-0 last:pb-0">
      <span
        className={cn(
          "flex size-8 shrink-0 items-center justify-center rounded-md border",
          income
            ? "border-tag-sea-glass/30 bg-tag-sea-glass/10 text-tag-sea-glass-foreground"
            : "border-border bg-background text-muted-foreground",
        )}
      >
        {income ? (
          <ArrowDownLeft aria-hidden="true" className="size-4" />
        ) : (
          <ReceiptText aria-hidden="true" className="size-4" />
        )}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm font-medium">{transaction.payee}</span>
        <span className="mt-1 block truncate text-xs text-muted-foreground">
          {transaction.category} · {account ? account.name : "Unknown account"} · {transaction.date}
        </span>
      </span>
      <span
        className={cn(
          "shrink-0 font-mono text-sm font-medium",
          income ? "text-tag-sea-glass-foreground" : "text-foreground",
        )}
      >
        {formatSignedMoney(transaction.amount)}
      </span>
    </li>
  );
}

function ActivityPanel({ period }: { period: MoneyPeriod }) {
  const [accountId, setAccountId] = useState("all");
  const accountById = useMemo(
    () => new Map(period.accounts.map((account) => [account.id, account])),
    [period.accounts],
  );
  const transactions = period.transactions.filter(
    (transaction) => accountId === "all" || transaction.accountId === accountId,
  );

  return (
    <Card className="rounded-xl border-border/80 p-5 shadow-none sm:p-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="flex items-center gap-2 text-primary-strong">
            <ReceiptText aria-hidden="true" className="size-4" />
            <p className="font-mono text-[0.66rem] font-medium uppercase tracking-[0.16em]">
              Latest movement
            </p>
          </div>
          <h2 className="mt-3 text-xl font-medium tracking-[-0.025em]">Recent activity</h2>
        </div>
        <Select value={accountId} onValueChange={(value) => setAccountId(value ?? "all")}>
          <SelectTrigger aria-label="Filter activity by account" className="h-9 w-full bg-background sm:w-48">
            <SelectValue>
              {accountId === "all"
                ? "All accounts"
                : accountById.get(accountId)?.name ?? "All accounts"}
            </SelectValue>
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All accounts</SelectItem>
            {period.accounts.map((account) => (
              <SelectItem key={account.id} value={account.id}>
                {account.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <Separator className="my-5" />

      {transactions.length ? (
        <ul aria-label="Recent money activity">
          {transactions.map((transaction) => (
            <ActivityRow
              key={transaction.id}
              transaction={transaction}
              account={accountById.get(transaction.accountId)}
            />
          ))}
        </ul>
      ) : (
        <EmptyState
          icon={ReceiptText}
          title="No activity in this account."
          description="Posted income and spending will show up here as the month moves."
        />
      )}
    </Card>
  );
}

function EmptyState({
  icon: Icon,
  title,
  description,
}: {
  icon: typeof WalletCards;
  title: string;
  description: string;
}) {
  return (
    <div className="py-5">
      <Icon aria-hidden="true" className="size-5 text-primary-strong" />
      <h3 className="mt-3 text-sm font-medium">{title}</h3>
      <p className="mt-1 max-w-sm text-sm leading-6 text-muted-foreground">{description}</p>
    </div>
  );
}

function MoneyDashboard({ email }: { email: string }) {
  const [periodId, setPeriodId] = useState<MoneyPeriodId>("2026-09");
  const period = moneyPeriods.find((item) => item.id === periodId) ?? moneyPeriods[0];

  return (
    <WorkspaceShell email={email}>
      <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_18rem] lg:gap-14">
        <div className="min-w-0">
          <section aria-labelledby="money-overview-title" className="mt-0">
            <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
              <div>
                <p className="font-mono text-[0.66rem] uppercase tracking-[0.18em] text-muted-foreground">
                  Money
                </p>
                <h1
                  id="money-overview-title"
                  className="mt-2 text-xl font-medium tracking-[-0.025em] sm:text-2xl"
                >
                  Overview
                </h1>
              </div>
              <label
                htmlFor="money-period"
                className="flex shrink-0 flex-col gap-2 font-mono text-[0.62rem] uppercase tracking-[0.14em] text-muted-foreground"
              >
                View month
                <Select
                  value={period.id}
                  onValueChange={(value) => {
                    if (value) {
                      setPeriodId(value as MoneyPeriodId);
                    }
                  }}
                >
                  <SelectTrigger id="money-period" aria-label="Choose money month" className="h-10 w-full bg-background font-sans text-sm normal-case tracking-normal sm:w-48">
                    <CalendarDays aria-hidden="true" className="size-4 text-primary-strong" />
                    <SelectValue>{period.label}</SelectValue>
                  </SelectTrigger>
                  <SelectContent>
                    {moneyPeriodOptions.map((option) => (
                      <SelectItem key={option.id} value={option.id}>
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </label>
            </div>
          </section>

          <MoneySummary period={period} />

          <section aria-labelledby="money-budget-section" className="mt-8">
            <div className="mb-4 flex items-end justify-between gap-3">
              <div>
                <p className="font-mono text-[0.66rem] uppercase tracking-[0.18em] text-muted-foreground">
                  Where the month is going
                </p>
                <h2 id="money-budget-section" className="mt-2 text-xl font-medium tracking-[-0.025em] sm:text-2xl">
                  Budget pulse
                </h2>
              </div>
              <span className="font-mono text-[0.65rem] uppercase tracking-[0.12em] text-muted-foreground">
                {period.budgets.length} categories
              </span>
            </div>
            <BudgetPanel period={period} />
          </section>

          <section aria-labelledby="money-activity-section" className="mt-8">
            <div className="mb-4">
              <p className="font-mono text-[0.66rem] uppercase tracking-[0.18em] text-muted-foreground">
                Close to the surface
              </p>
              <h2 id="money-activity-section" className="mt-2 text-xl font-medium tracking-[-0.025em] sm:text-2xl">
                Recent movement
              </h2>
            </div>
            <ActivityPanel period={period} />
          </section>
        </div>

        <aside className="min-w-0 lg:pt-1" aria-label="Money context">
          <AccountsPanel accounts={period.accounts} />
          <Card className="relative mt-6 overflow-hidden rounded-xl border-border/80 p-5 shadow-none sm:p-6">
            <span className="absolute inset-y-0 left-0 w-1 bg-primary/75" aria-hidden="true" />
            <div className="flex items-center gap-2 text-primary-strong">
              <CalendarDays aria-hidden="true" className="size-4" />
              <p className="font-mono text-[0.66rem] font-medium uppercase tracking-[0.16em]">
                Keep the signal close
              </p>
            </div>
            <h2 className="mt-4 text-lg font-medium tracking-[-0.025em]">A quiet month is a useful month.</h2>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">
              Money views will grow into accounts, budgets, and activity when those workflows are ready. For now, this overview keeps the important shape in reach.
            </p>
          </Card>
        </aside>
      </div>
    </WorkspaceShell>
  );
}

export function MoneyRoute() {
  const currentUser = useCurrentUser();

  return (
    <WorkspaceRouteGuard>
      {currentUser.data ? <MoneyDashboard email={currentUser.data.email} /> : null}
    </WorkspaceRouteGuard>
  );
}

"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowDownRight,
  CalendarDays,
  CheckCircle2,
  CircleAlert,
  LoaderCircle,
  Pencil,
  Plus,
  Trash2,
  WalletCards,
  X,
  type LucideIcon,
} from "lucide-react";
import { useEffect, useMemo, useState, type FormEvent } from "react";
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
import { Card } from "@/components/ui/card";
import { SelectItem, SelectSeparator } from "@/components/ui/select";
import { useCurrentUser } from "@/features/auth/hooks";
import { WorkspaceRouteGuard, WorkspaceShell } from "@/features/workspace/components/workspace-shell";
import { cn } from "@/lib/utils";
import {
  createMoneyCategory,
  deleteMoneyBudget,
  type MoneyBudget,
  type MoneyBudgetUpsertInput,
  type MoneyCategory,
  upsertMoneyBudget,
} from "../api";
import {
  categoriesForKind,
  invalidateMoneyQueries,
  invalidateMoneyBudgetQueries,
  useMoneyBudgets,
  useMoneyCatalog,
  useMoneySummary,
} from "../hooks";
import {
  currentPeriod,
  describeMoneyError,
  formatMoney,
  periodLabel,
} from "../utils";
import { MoneyResourceCreateDialog } from "./money-resource-create-dialog";
import { MoneySelectField } from "./money-select-field";

type BudgetFilter = "all" | "needs_attention" | "unplanned";

type BudgetRowData = {
  budget?: MoneyBudget;
  category?: MoneyCategory;
};

const amountPattern = /^(?:0|[1-9]\d*)(?:\.\d+)?$/;

function MetricCard({
  label,
  value,
  detail,
  tone,
  icon: Icon,
  accent = false,
}: {
  label: string;
  value?: string;
  detail: string;
  tone: string;
  icon: LucideIcon;
  accent?: boolean;
}) {
  return (
    <Card
      className={cn(
        "relative min-w-0 rounded-xl border-border/80 p-5 shadow-none",
        accent && "overflow-hidden",
      )}
    >
      {accent ? <span className="absolute inset-y-0 left-0 w-1 bg-primary/80" aria-hidden="true" /> : null}
      <div className="flex items-center justify-between gap-3">
        <span className={cn("font-mono text-[0.64rem] uppercase tracking-[0.14em]", tone)}>{label}</span>
        <Icon aria-hidden="true" className={cn("size-4", tone)} />
      </div>
      <p className="mt-4 truncate text-2xl font-semibold tracking-[-0.035em]">{value ?? "—"}</p>
      <p className="mt-2 text-xs leading-5 text-muted-foreground">{detail}</p>
    </Card>
  );
}

function BudgetProgress({ budget, categoryName }: { budget: MoneyBudget; categoryName: string }) {
  const amount = Number(budget.amount);
  const spent = Number(budget.spent_amount);
  const remaining = amount - spent;
  const attention = spent > amount;
  const usage = amount > 0 ? Math.round((spent / amount) * 100) : spent > 0 ? 100 : 0;
  const progress = Math.min(100, Math.max(0, usage));
  const progressText = amount > 0 ? `${usage}% used` : spent > 0 ? "Over zero budget" : "No spend yet";

  return (
    <div className="min-w-0 flex-1">
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1">
        <span className="text-xs text-muted-foreground">{progressText}</span>
        <span className={cn("font-mono text-xs", attention ? "text-destructive" : "text-muted-foreground")}>
          {attention ? `${formatMoney(Math.abs(remaining), budget.currency_code)} over` : `${formatMoney(remaining, budget.currency_code)} left`}
        </span>
      </div>
      <div
        className="mt-2 h-2 overflow-hidden rounded-full bg-muted"
        role="progressbar"
        aria-label={`${categoryName} budget usage`}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={progress}
        aria-valuetext={progressText}
      >
        <span
          className={cn(
            "block h-full rounded-full",
            attention ? "bg-destructive" : progress >= 85 ? "bg-tag-amber" : "bg-tag-sea-glass",
          )}
          style={{ width: `${progress}%` }}
        />
      </div>
      <div className="mt-2 flex flex-wrap justify-between gap-2 font-mono text-[0.64rem] uppercase tracking-[0.08em] text-muted-foreground">
        <span>{formatMoney(budget.spent_amount, budget.currency_code)} spent</span>
        <span>{formatMoney(budget.amount, budget.currency_code)} planned</span>
      </div>
    </div>
  );
}

function BudgetRow({
  row,
  onEdit,
  onDelete,
  onAdd,
  pending,
}: {
  row: BudgetRowData;
  onEdit: (budget: MoneyBudget) => void;
  onDelete: (budget: MoneyBudget) => void;
  onAdd: (categoryId: string) => void;
  pending: boolean;
}) {
  const categoryName = row.category?.name ?? "Unknown category";

  return (
    <li className="border-t border-border/70 first:border-t-0">
      <div className="flex flex-col gap-4 px-4 py-4 sm:px-5 sm:py-5 lg:flex-row lg:items-center">
        <div className="flex min-w-0 flex-1 items-start gap-3">
          <span
            className={cn(
              "mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-lg border",
              row.budget ? "border-border bg-background text-primary-strong" : "border-dashed border-primary/40 bg-primary/5 text-primary-strong",
            )}
          >
            {row.budget ? <WalletCards aria-hidden="true" className="size-4" /> : <Plus aria-hidden="true" className="size-4" />}
          </span>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="truncate text-sm font-medium">{categoryName}</h3>
              {row.budget ? (
                <Badge variant="outline" className="font-mono text-[0.58rem] uppercase tracking-[0.08em]">
                  Planned
                </Badge>
              ) : (
                <Badge variant="outline" className="border-primary/30 font-mono text-[0.58rem] uppercase tracking-[0.08em] text-primary-strong">
                  Not planned
                </Badge>
              )}
            </div>
            <p className="mt-1 text-xs leading-5 text-muted-foreground">
              {row.budget ? "This category has a monthly spending limit." : "Add an amount to start tracking this category."}
            </p>
          </div>
        </div>

        {row.budget ? (
          <div className="flex min-w-0 flex-1 items-center gap-4 lg:max-w-[34rem]">
            <BudgetProgress budget={row.budget} categoryName={categoryName} />
            <div className="flex shrink-0 gap-2" aria-label={`${categoryName} budget actions`}>
              <Button type="button" variant="outline" size="sm" onClick={() => onEdit(row.budget!)} disabled={pending}>
                <Pencil aria-hidden="true" />
                <span className="hidden sm:inline">Edit</span>
                <span className="sr-only sm:hidden">Edit {categoryName}</span>
              </Button>
              <Button type="button" variant="outline" size="sm" onClick={() => onDelete(row.budget!)} disabled={pending}>
                <Trash2 aria-hidden="true" />
                <span className="hidden sm:inline">Delete</span>
                <span className="sr-only sm:hidden">Delete {categoryName}</span>
              </Button>
            </div>
          </div>
        ) : (
          <div className="flex shrink-0 items-center justify-between gap-3 lg:min-w-52 lg:justify-end">
            <span className="font-mono text-xs uppercase tracking-[0.1em] text-muted-foreground">No plan set</span>
            <Button type="button" size="sm" onClick={() => row.category && onAdd(row.category.id)} disabled={pending || !row.category}>
              <Plus aria-hidden="true" />
              Add budget
            </Button>
          </div>
        )}
      </div>
    </li>
  );
}

function BudgetLedger({
  rows,
  pending,
  filter,
  onFilterChange,
  onEdit,
  onDelete,
  onAdd,
  onAddBudget,
  hasNextPage,
  isFetchingNextPage,
  onLoadMore,
}: {
  rows: BudgetRowData[];
  pending: boolean;
  filter: BudgetFilter;
  onFilterChange: (filter: BudgetFilter) => void;
  onEdit: (budget: MoneyBudget) => void;
  onDelete: (budget: MoneyBudget) => void;
  onAdd: (categoryId: string) => void;
  onAddBudget: () => void;
  hasNextPage: boolean;
  isFetchingNextPage: boolean;
  onLoadMore: () => void;
}) {
  const visibleRows = rows.filter((row) => {
    if (filter === "unplanned") return !row.budget;
    if (filter === "needs_attention") {
      return row.budget ? Number(row.budget.spent_amount) > Number(row.budget.amount) : false;
    }
    return true;
  });

  return (
    <Card className="overflow-hidden rounded-xl border-border/80 p-0 shadow-none">
      <div className="flex flex-col gap-4 border-b border-border/70 px-5 py-5 sm:flex-row sm:items-start sm:justify-between sm:px-6">
        <div>
          <div className="flex items-center gap-2 text-primary-strong">
            <WalletCards aria-hidden="true" className="size-4" />
            <p className="font-mono text-[0.66rem] font-medium uppercase tracking-[0.16em]">Monthly ledger</p>
          </div>
          <h2 className="mt-3 text-xl font-medium tracking-[-0.025em]">Where the month is going</h2>
          <p className="mt-2 max-w-xl text-sm leading-6 text-muted-foreground">
            Give every expense category a visible place, whether it has a limit yet or not.
          </p>
        </div>
        <Button type="button" onClick={onAddBudget}>
          <Plus aria-hidden="true" />
          Add budget
        </Button>
      </div>

      <div className="flex flex-wrap gap-1 border-b border-border/70 bg-background px-5 py-3 sm:px-6" role="group" aria-label="Filter budget categories">
        {(["all", "needs_attention", "unplanned"] as BudgetFilter[]).map((item) => (
          <Button
            key={item}
            type="button"
            variant={filter === item ? "secondary" : "ghost"}
            size="sm"
            aria-pressed={filter === item}
            onClick={() => onFilterChange(item)}
            className="h-8 text-xs"
          >
            {item === "all" ? "All" : item === "needs_attention" ? "Needs attention" : "Unplanned"}
          </Button>
        ))}
      </div>

      {pending ? (
        <div className="space-y-3 p-5" aria-label="Loading budgets">
          {["one", "two", "three"].map((item) => <div key={item} className="h-20 animate-pulse rounded-lg bg-muted" />)}
        </div>
      ) : visibleRows.length ? (
        <>
          <ul aria-label="Budget categories">
            {visibleRows.map((row) => (
              <BudgetRow
                key={row.budget?.id ?? row.category?.id}
                row={row}
                pending={pending}
                onEdit={onEdit}
                onDelete={onDelete}
                onAdd={onAdd}
              />
            ))}
          </ul>
          {hasNextPage ? (
            <div className="border-t border-border/70 p-4 text-center">
              <Button type="button" variant="outline" onClick={onLoadMore} disabled={isFetchingNextPage}>
                {isFetchingNextPage ? <LoaderCircle aria-hidden="true" className="animate-spin" /> : null}
                {isFetchingNextPage ? "Loading more…" : "Load more budgets"}
              </Button>
            </div>
          ) : null}
        </>
      ) : rows.length ? (
        <div className="flex flex-col items-center px-6 py-14 text-center">
          <CheckCircle2 aria-hidden="true" className="size-5 text-primary-strong" />
          <h3 className="mt-3 text-sm font-medium">Nothing in this view.</h3>
          <p className="mt-1 max-w-sm text-sm leading-6 text-muted-foreground">Try another budget filter to see the rest of the month.</p>
        </div>
      ) : (
        <div className="flex flex-col items-center px-6 py-14 text-center">
          <WalletCards aria-hidden="true" className="size-5 text-primary-strong" />
          <h3 className="mt-3 text-sm font-medium">No expense categories yet.</h3>
          <p className="mt-1 max-w-sm text-sm leading-6 text-muted-foreground">
            Open “Add budget” to create an expense category and set its first monthly limit in one flow.
          </p>
        </div>
      )}
    </Card>
  );
}

function BudgetDrawer({
  open,
  onOpenChange,
  budget,
  initialCategoryId,
  period,
  currencyCode,
  categories,
  pending,
  onSave,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  budget: MoneyBudget | null;
  initialCategoryId: string;
  period: string;
  currencyCode: string;
  categories: MoneyCategory[];
  pending: boolean;
  onSave: (categoryId: string, payload: MoneyBudgetUpsertInput) => Promise<void>;
}) {
  const queryClient = useQueryClient();
  const feedback = useFeedback();
  const [categoryId, setCategoryId] = useState("");
  const [amount, setAmount] = useState("");
  const [error, setError] = useState<string>();
  const [categoryDialogOpen, setCategoryDialogOpen] = useState(false);
  const [categoryName, setCategoryName] = useState("");
  const [categoryError, setCategoryError] = useState<string>();
  const [categoryLabels, setCategoryLabels] = useState<Record<string, string>>({});
  const editing = Boolean(budget);
  const availableCategories = useMemo(
    () => categories.filter((category) => category.id === budget?.category_id || category.id === initialCategoryId || !budget),
    [budget, categories, initialCategoryId],
  );
  const createCategoryMutation = useMutation({ mutationFn: createMoneyCategory });
  const formPending = pending || createCategoryMutation.isPending;

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    queueMicrotask(() => {
      if (cancelled) return;
      setError(undefined);
      setCategoryDialogOpen(false);
      setCategoryName("");
      setCategoryError(undefined);
      setCategoryId(budget?.category_id ?? initialCategoryId);
      setAmount(budget?.amount ?? "");
    });
    return () => {
      cancelled = true;
    };
  }, [budget, initialCategoryId, open]);

  function handleCategorySelect(value: string) {
    if (value === "__create_category__") {
      setCategoryDialogOpen(true);
      setCategoryName("");
      setCategoryError(undefined);
      return;
    }
    setCategoryId(value);
  }

  async function handleCategorySubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const name = categoryName.trim();
    if (!name) return;
    setCategoryError(undefined);

    try {
      const created = await createCategoryMutation.mutateAsync({ name, kind: "expense" });
      await invalidateMoneyQueries(queryClient);
      setCategoryLabels((current) => ({ ...current, [created.id]: created.name }));
      setCategoryId(created.id);
      setCategoryDialogOpen(false);
      setCategoryName("");
      feedback.success({ title: "Category created." });
    } catch (reason) {
      setCategoryError(describeMoneyError(reason));
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(undefined);
    const normalizedAmount = amount.trim();
    const maxFractionDigits = currencyCode === "JPY" || currencyCode === "KRW" ? 0 : 2;
    const decimalDigits = normalizedAmount.includes(".") ? normalizedAmount.split(".")[1]?.length ?? 0 : 0;

    if (!categoryId) {
      setError("Choose an expense category before saving.");
      return;
    }
    if (!amountPattern.test(normalizedAmount)) {
      setError("Enter a non-negative amount, such as 0 or 125.50.");
      return;
    }
    if (decimalDigits > maxFractionDigits) {
      setError(`Use no more than ${maxFractionDigits} decimal places for ${currencyCode}.`);
      return;
    }

    try {
      await onSave(categoryId, { amount: normalizedAmount });
      onOpenChange(false);
    } catch (reason) {
      setError(describeMoneyError(reason));
    }
  }

  return (
    <>
      <Drawer open={open} onOpenChange={onOpenChange} swipeDirection="right">
      <DrawerContent className="min-h-[100svh] w-full max-w-xl gap-0 border-border bg-card p-0 text-card-foreground shadow-none sm:max-w-xl">
        <DrawerHeader className="border-b border-border/70 px-6 py-6 text-left sm:px-8">
          <div className="flex items-start justify-between gap-4">
            <div>
              <DrawerTitle className="text-xl font-semibold tracking-[-0.03em]">{editing ? "Edit budget" : "Add budget"}</DrawerTitle>
              <DrawerDescription className="mt-2 max-w-md text-sm leading-6">
                Set a monthly limit for one expense category. Spending is calculated from posted transactions.
              </DrawerDescription>
            </div>
            <DrawerClose render={<Button variant="ghost" size="icon-sm" aria-label="Close budget drawer" />}>
              <X aria-hidden="true" />
            </DrawerClose>
          </div>
        </DrawerHeader>

        <form onSubmit={handleSubmit} className="flex min-h-0 flex-1 flex-col">
          <div className="min-h-0 flex-1 space-y-6 overflow-y-auto px-6 py-6 sm:px-8">
            {error ? <div role="alert" className="rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm leading-5 text-destructive">{error}</div> : null}

            <div className="grid gap-4 sm:grid-cols-2">
              <div className="flex flex-col gap-2 text-sm sm:col-span-2">
                <MoneySelectField
                  id="budget-category"
                  label="Expense category"
                  value={categoryId}
                  selectedLabel={categories.find((category) => category.id === categoryId)?.name ?? categoryLabels[categoryId]}
                  emptyLabel="Choose a category"
                  onValueChange={handleCategorySelect}
                  disabled={editing || formPending}
                >
                  {availableCategories.map((category) => <SelectItem key={category.id} value={category.id}>{category.name}</SelectItem>)}
                  {!editing ? <><SelectSeparator /><SelectItem value="__create_category__">Create new expense category…</SelectItem></> : null}
                </MoneySelectField>
                {editing ? <p className="text-xs leading-5 text-muted-foreground">Category is fixed after creation.</p> : null}
              </div>

              <div className="flex flex-col gap-2 text-sm">
                <Label htmlFor="budget-amount">Monthly limit · {currencyCode}</Label>
                <Input
                  id="budget-amount"
                  className="h-11"
                  value={amount}
                  onChange={(event) => setAmount(event.target.value)}
                  placeholder={currencyCode === "JPY" || currencyCode === "KRW" ? "0" : "0.00"}
                  inputMode="decimal"
                  aria-invalid={Boolean(error)}
                  disabled={formPending}
                  autoFocus
                  required
                />
              </div>

              <dl className="rounded-lg border border-border/70 bg-background/60 p-3 text-sm">
                <div>
                  <dt className="text-xs text-muted-foreground">Budget month</dt>
                  <dd className="mt-1 font-medium">{periodLabel(period)}</dd>
                </div>
                <div className="mt-3">
                  <dt className="text-xs text-muted-foreground">Currency</dt>
                  <dd className="mt-1 font-mono font-medium">{currencyCode}</dd>
                </div>
              </dl>
            </div>

            {!availableCategories.length ? (
              <div className="rounded-lg border border-border/70 bg-background/60 px-4 py-3 text-sm leading-6 text-muted-foreground">
                Create a new expense category from the selector above to add another monthly plan.
              </div>
            ) : null}
          </div>

          <DrawerFooter className="border-t border-border/70 bg-card px-6 py-4 sm:flex-row sm:justify-end sm:px-8">
            <DrawerClose render={<Button type="button" variant="outline" size="lg" disabled={formPending} />}>Cancel</DrawerClose>
            <Button type="submit" size="lg" disabled={formPending || !categoryId || !amount.trim()}>
              {pending ? "Saving…" : editing ? "Save changes" : "Add budget"}
            </Button>
          </DrawerFooter>
        </form>
      </DrawerContent>
      </Drawer>
      <MoneyResourceCreateDialog
        kind="category"
        open={categoryDialogOpen}
        onOpenChange={(nextOpen) => {
          setCategoryDialogOpen(nextOpen);
          if (!nextOpen) {
            setCategoryName("");
            setCategoryError(undefined);
          }
        }}
        name={categoryName}
        onNameChange={setCategoryName}
        onSubmit={handleCategorySubmit}
        error={categoryError}
        pending={createCategoryMutation.isPending}
        description="Add an expense category without leaving this budget."
      />
    </>
  );
}

function BudgetWorkspace({ email }: { email: string }) {
  const queryClient = useQueryClient();
  const feedback = useFeedback();
  const [period, setPeriod] = useState(currentPeriod());
  const [currencyCode, setCurrencyCode] = useState("PHP");
  const [filter, setFilter] = useState<BudgetFilter>("all");
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editingBudget, setEditingBudget] = useState<MoneyBudget | null>(null);
  const [initialCategoryId, setInitialCategoryId] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<MoneyBudget | null>(null);
  const catalog = useMoneyCatalog();
  const budgetsQuery = useMoneyBudgets(period, currencyCode);
  const summaryQuery = useMoneySummary(period, currencyCode);
  const budgets = useMemo(() => budgetsQuery.data?.pages.flatMap((page) => page.items) ?? [], [budgetsQuery.data?.pages]);
  const expenseCategories = useMemo(() => categoriesForKind(catalog.categories, "expense"), [catalog.categories]);
  const categoryById = useMemo(() => new Map(catalog.categories.map((category) => [category.id, category])), [catalog.categories]);
  const budgetCategoryIds = useMemo(() => new Set(budgets.map((budget) => budget.category_id)), [budgets]);
  const budgetFormCategories = useMemo(
    () => expenseCategories.filter((category) => !budgetCategoryIds.has(category.id) || category.id === editingBudget?.category_id),
    [budgetCategoryIds, editingBudget?.category_id, expenseCategories],
  );
  const rows = useMemo<BudgetRowData[]>(() => {
    const configured = budgets
      .map((budget) => ({ budget, category: categoryById.get(budget.category_id) }))
      .sort((left, right) => (left.category?.name ?? "").localeCompare(right.category?.name ?? ""));
    const unplanned = expenseCategories
      .filter((category) => !budgetCategoryIds.has(category.id))
      .sort((left, right) => left.name.localeCompare(right.name))
      .map((category) => ({ category }));
    return [...configured, ...unplanned];
  }, [budgetCategoryIds, budgets, categoryById, expenseCategories]);
  const currencyOptions = [...new Set(["PHP", ...catalog.accounts.map((account) => account.currency_code)])];
  const unplannedCount = rows.filter((row) => !row.budget).length;
  const pagePending = catalog.isPending || budgetsQuery.isPending || summaryQuery.isPending;

  const saveMutation = useMutation({
    mutationFn: ({ categoryId, payload }: { categoryId: string; payload: MoneyBudgetUpsertInput }) =>
      upsertMoneyBudget(period, categoryId, currencyCode, payload),
    onSuccess: async (budget) => {
      await invalidateMoneyBudgetQueries(queryClient);
      setEditingBudget(null);
      setInitialCategoryId("");
      feedback.success({ title: "Budget saved.", description: `${formatMoney(budget.amount, budget.currency_code)} planned for ${periodLabel(budget.period)}.` });
    },
    onError: (reason) => feedback.error({ title: "Budget could not be saved.", description: describeMoneyError(reason) }),
  });

  const deleteMutation = useMutation({
    mutationFn: deleteMoneyBudget,
    onSuccess: async () => {
      await invalidateMoneyBudgetQueries(queryClient);
      setDeleteTarget(null);
      feedback.success({ title: "Budget deleted.", description: "The category is now unplanned for this month." });
    },
    onError: (reason) => feedback.error({ title: "Budget could not be deleted.", description: describeMoneyError(reason) }),
  });

  function openCreate(categoryId = "") {
    const defaultCategoryId = categoryId || expenseCategories.find((category) => !budgetCategoryIds.has(category.id))?.id || "";
    setEditingBudget(null);
    setInitialCategoryId(defaultCategoryId);
    setDrawerOpen(true);
  }

  function openEdit(budget: MoneyBudget) {
    setEditingBudget(budget);
    setInitialCategoryId("");
    setDrawerOpen(true);
  }

  async function saveBudget(categoryId: string, payload: MoneyBudgetUpsertInput) {
    await saveMutation.mutateAsync({ categoryId, payload });
  }

  function retryLiveData() {
    void Promise.all([catalog.refetch(), budgetsQuery.refetch(), summaryQuery.refetch()]);
  }

  return (
    <WorkspaceShell email={email}>
      <div className="max-w-6xl">
        {catalog.isError || budgetsQuery.isError || summaryQuery.isError ? (
          <div role="alert" className="mt-5 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm">
            <span className="flex items-center gap-2 text-destructive"><CircleAlert aria-hidden="true" className="size-4" />{catalog.isError ? "Money categories could not load." : summaryQuery.isError ? describeMoneyError(summaryQuery.error) : describeMoneyError(budgetsQuery.error)}</span>
            <Button type="button" variant="outline" size="sm" onClick={retryLiveData}>Try again</Button>
          </div>
        ) : null}

        <section aria-labelledby="budget-summary-title" className="mt-7">
          <div className="mb-4 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <p className="font-mono text-[0.66rem] uppercase tracking-[0.18em] text-muted-foreground">Monthly snapshot</p>
              <h2 id="budget-summary-title" className="mt-2 text-xl font-medium tracking-[-0.025em] sm:text-2xl">A clearer number to live with.</h2>
            </div>
            <div className="flex flex-wrap items-end gap-3">
              <label htmlFor="budget-period" className="flex flex-col gap-2 font-mono text-[0.62rem] uppercase tracking-[0.14em] text-muted-foreground">
                View month
                <div className="relative">
                  <CalendarDays aria-hidden="true" className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-primary-strong" />
                  <Input id="budget-period" type="month" className="h-10 w-44 bg-background pl-9 font-sans text-sm normal-case tracking-normal" value={period} onChange={(event) => setPeriod(event.target.value || currentPeriod())} />
                </div>
              </label>
              <MoneySelectField
                id="budget-currency"
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
          </div>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <MetricCard label="Planned" value={pagePending ? undefined : summaryQuery.data ? formatMoney(summaryQuery.data.budget_amount, currencyCode) : undefined} detail="Across saved category limits" tone="text-primary-strong" icon={WalletCards} accent />
            <MetricCard label="Budget spent" value={pagePending ? undefined : summaryQuery.data ? formatMoney(summaryQuery.data.budget_spent_amount, currencyCode) : undefined} detail="Posted spending in planned categories" tone="text-tag-amber-foreground" icon={ArrowDownRight} />
            <MetricCard label="Remaining" value={pagePending ? undefined : summaryQuery.data ? formatMoney(summaryQuery.data.budget_remaining_amount, currencyCode) : undefined} detail="Before planned categories go over" tone={summaryQuery.data && Number(summaryQuery.data.budget_remaining_amount) < 0 ? "text-destructive" : "text-tag-sea-glass-foreground"} icon={CheckCircle2} />
            <MetricCard label="Unplanned" value={pagePending ? undefined : String(unplannedCount)} detail="Active expense categories without a limit" tone={unplannedCount ? "text-tag-amber-foreground" : "text-tag-sea-glass-foreground"} icon={unplannedCount ? CircleAlert : CheckCircle2} />
          </div>
        </section>

        <section aria-labelledby="budget-ledger-title" className="mt-8">
          <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
            <div>
              <p className="font-mono text-[0.66rem] uppercase tracking-[0.18em] text-muted-foreground">Categories in view</p>
              <h2 id="budget-ledger-title" className="mt-2 text-xl font-medium tracking-[-0.025em] sm:text-2xl">Plan the parts that move.</h2>
            </div>
            <span className="font-mono text-[0.65rem] uppercase tracking-[0.12em] text-muted-foreground">{pagePending ? "Loading" : `${rows.length} categories`}</span>
          </div>
          <BudgetLedger
            rows={rows}
            pending={pagePending}
            filter={filter}
            onFilterChange={setFilter}
            onEdit={openEdit}
            onDelete={setDeleteTarget}
            onAdd={openCreate}
            onAddBudget={() => openCreate()}
            hasNextPage={Boolean(budgetsQuery.hasNextPage)}
            isFetchingNextPage={budgetsQuery.isFetchingNextPage}
            onLoadMore={() => void budgetsQuery.fetchNextPage()}
          />
        </section>
      </div>

      <BudgetDrawer
        open={drawerOpen}
        onOpenChange={(open) => {
          setDrawerOpen(open);
          if (!open) {
            setEditingBudget(null);
            setInitialCategoryId("");
          }
        }}
        budget={editingBudget}
        initialCategoryId={initialCategoryId}
        period={period}
        currencyCode={currencyCode}
        categories={budgetFormCategories}
        pending={saveMutation.isPending}
        onSave={saveBudget}
      />

      <Dialog open={Boolean(deleteTarget)} onOpenChange={(open) => { if (!open) setDeleteTarget(null); }}>
        <DialogContent className="w-[min(28rem,calc(100vw-2rem))] rounded-xl border-border bg-card p-6 text-card-foreground shadow-none sm:max-w-none sm:p-7">
          <DialogHeader>
            <DialogTitle className="text-xl tracking-[-0.03em]">Delete budget?</DialogTitle>
            <DialogDescription className="mt-2 leading-6">
              {deleteTarget ? `The ${categoryById.get(deleteTarget.category_id)?.name ?? "selected"} budget for ${periodLabel(deleteTarget.period)} will be removed. Its transactions and category remain intact.` : ""}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="mt-7 flex-row justify-end gap-2 border-0 bg-transparent p-0">
            <DialogClose render={<Button type="button" variant="outline" size="lg" disabled={deleteMutation.isPending} />}>Cancel</DialogClose>
            <Button type="button" variant="destructive" size="lg" disabled={!deleteTarget || deleteMutation.isPending} onClick={() => { if (deleteTarget) deleteMutation.mutate(deleteTarget.id); }}>
              {deleteMutation.isPending ? <LoaderCircle aria-hidden="true" className="animate-spin" /> : <Trash2 aria-hidden="true" />}
              {deleteMutation.isPending ? "Deleting…" : "Delete budget"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </WorkspaceShell>
  );
}

export function BudgetsRoute() {
  const currentUser = useCurrentUser();
  return <WorkspaceRouteGuard>{currentUser.data ? <BudgetWorkspace email={currentUser.data.email} /> : null}</WorkspaceRouteGuard>;
}

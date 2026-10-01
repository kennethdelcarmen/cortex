import { z } from "zod";
import { apiFetch } from "@/lib/api/client";

export const moneyAccountTypeSchema = z.enum([
  "checking",
  "savings",
  "cash",
  "credit_card",
  "loan",
  "investment",
  "other",
]);
export const moneyAccountTypeOptions = moneyAccountTypeSchema.options;
export const moneyCurrencyCodes = [
  "USD",
  "EUR",
  "GBP",
  "CHF",
  "CAD",
  "AUD",
  "SGD",
  "HKD",
  "CNY",
  "INR",
  "PHP",
  "JPY",
  "KRW",
] as const;
export const moneyCategoryKindSchema = z.enum(["income", "expense"]);
export const moneyTransactionStateSchema = z.enum(["posted", "voided"]);
export const moneyReconciliationStateSchema = z.enum([
  "uncleared",
  "cleared",
  "reconciled",
]);
export const moneyInstallmentPlanStateSchema = z.enum(["active", "completed", "cancelled"]);
export const moneyInstallmentOccurrenceStateSchema = z.enum([
  "scheduled",
  "charged",
  "cancelled",
]);
export const moneyRecurrenceFrequencySchema = z.enum(["weekly", "monthly", "yearly"]);
export const moneyRecurrenceStateSchema = z.enum(["active", "paused", "ended"]);
export const moneyRecurrenceWeekdaySchema = z.enum([
  "monday",
  "tuesday",
  "wednesday",
  "thursday",
  "friday",
  "saturday",
  "sunday",
]);
export const moneyRecurringOccurrenceStateSchema = z.enum([
  "scheduled",
  "posted",
  "skipped",
]);

export const moneyAccountSchema = z.object({
  id: z.string().min(1),
  name: z.string().min(1),
  account_type: moneyAccountTypeSchema,
  institution_name: z.string().nullable(),
  last_four: z.string().length(4).nullable(),
  currency_code: z.string().length(3),
  opening_balance: z.string().min(1),
  balance: z.string().min(1),
  credit_limit: z.string().nullable(),
  amount_owed: z.string().nullable(),
  available_credit: z.string().nullable(),
  statement_close_day: z.number().int().nullable(),
  payment_due_day: z.number().int().nullable(),
  next_statement_close_date: z.string().nullable(),
  next_payment_due_date: z.string().nullable(),
  created_at: z.string().min(1),
  updated_at: z.string().min(1),
  archived_at: z.string().nullable(),
});

export const moneyPayeeSchema = z.object({
  id: z.string().min(1),
  name: z.string().min(1),
  created_at: z.string().min(1),
  updated_at: z.string().min(1),
  archived_at: z.string().nullable(),
});

export const moneyCategorySchema = z.object({
  id: z.string().min(1),
  name: z.string().min(1),
  kind: moneyCategoryKindSchema,
  created_at: z.string().min(1),
  updated_at: z.string().min(1),
  archived_at: z.string().nullable(),
});

export const moneyBudgetSchema = z.object({
  id: z.string().min(1),
  category_id: z.string().min(1),
  period: z.string().regex(/^\d{4}-(0[1-9]|1[0-2])$/),
  currency_code: z.string().length(3),
  amount: z.string().min(1),
  spent_amount: z.string().min(1),
  created_at: z.string().min(1),
  updated_at: z.string().min(1),
});

export const moneyPostingSchema = z.object({
  id: z.string().min(1),
  account_id: z.string().min(1).nullable(),
  category_id: z.string().min(1).nullable(),
  currency_code: z.string().length(3),
  amount: z.string().min(1),
  reconciliation_state: moneyReconciliationStateSchema,
  cleared_at: z.string().nullable(),
  reconciled_at: z.string().nullable(),
});

export const moneyTransactionSchema = z.object({
  id: z.string().min(1),
  transaction_date: z.string().min(1),
  name: z.string().min(1),
  payee_id: z.string().min(1).nullable(),
  memo: z.string().nullable(),
  state: moneyTransactionStateSchema,
  reversal_of_id: z.string().min(1).nullable(),
  postings: z.array(moneyPostingSchema),
  created_at: z.string().min(1),
  updated_at: z.string().min(1),
  voided_at: z.string().nullable(),
});

export const moneySummarySchema = z.object({
  period: z.string().regex(/^\d{4}-(0[1-9]|1[0-2])$/),
  currency_code: z.string().length(3),
  total_balance: z.string().min(1),
  income_amount: z.string().min(1),
  spending_amount: z.string().min(1),
  budget_amount: z.string().min(1),
  budget_spent_amount: z.string().min(1),
  budget_remaining_amount: z.string().min(1),
});

export const moneyInstallmentOccurrenceSchema = z.object({
  id: z.string().min(1),
  sequence_number: z.number().int().positive(),
  charge_date: z.string().min(1),
  amount: z.string().min(1),
  status: moneyInstallmentOccurrenceStateSchema,
  transaction_id: z.string().nullable(),
  charged_at: z.string().nullable(),
});

export const moneyInstallmentPlanSchema = z.object({
  id: z.string().min(1),
  account_id: z.string().min(1),
  payee_id: z.string().nullable(),
  category_id: z.string().min(1),
  currency_code: z.string().length(3),
  purchase_date: z.string().min(1),
  name: z.string().min(1),
  memo: z.string().nullable(),
  total_amount: z.string().min(1),
  fee_amount: z.string().min(1),
  term_months: z.number().int().positive(),
  status: moneyInstallmentPlanStateSchema,
  charged_count: z.number().int().nonnegative(),
  next_charge_date: z.string().nullable(),
  next_charge_amount: z.string().nullable(),
  remaining_amount: z.string().min(1),
  occurrences: z.array(moneyInstallmentOccurrenceSchema),
  created_at: z.string().min(1),
  updated_at: z.string().min(1),
});

export const moneyInstallmentProcessSchema = z.object({
  processed_count: z.number().int().nonnegative(),
});

export const moneyRecurrenceSchema = z.object({
  timezone: z.string().min(1),
  frequency: moneyRecurrenceFrequencySchema,
  interval: z.number().int().positive(),
  weekdays: z.array(moneyRecurrenceWeekdaySchema),
  month_day: z.number().int().min(1).max(31).nullable(),
  month: z.number().int().min(1).max(12).nullable(),
  day: z.number().int().min(1).max(31).nullable(),
  until_date: z.string().nullable(),
  occurrence_count: z.number().int().positive().nullable(),
});

export const moneyRecurringPostingSchema = z.object({
  id: z.string().min(1),
  account_id: z.string().min(1).nullable(),
  category_id: z.string().min(1).nullable(),
  currency_code: z.string().length(3),
  amount: z.string().min(1),
});

export const moneyRecurringOccurrenceSchema = z.object({
  id: z.string().min(1),
  sequence_number: z.number().int().positive(),
  due_date: z.string().min(1),
  status: moneyRecurringOccurrenceStateSchema,
  transaction_id: z.string().nullable(),
  processed_at: z.string().nullable(),
});

export const moneyRecurringTransactionSchema = z.object({
  id: z.string().min(1),
  start_date: z.string().min(1),
  name: z.string().min(1),
  payee_id: z.string().min(1).nullable(),
  memo: z.string().nullable(),
  recurrence: moneyRecurrenceSchema,
  state: moneyRecurrenceStateSchema,
  next_occurrence_date: z.string().nullable(),
  next_occurrence_number: z.number().int().positive().nullable(),
  posted_count: z.number().int().nonnegative(),
  postings: z.array(moneyRecurringPostingSchema),
  occurrences: z.array(moneyRecurringOccurrenceSchema),
  created_at: z.string().min(1),
  updated_at: z.string().min(1),
  paused_at: z.string().nullable(),
  ended_at: z.string().nullable(),
});

const listResponse = <T extends z.ZodType>(itemSchema: T) =>
  z.object({
    items: z.array(itemSchema),
    next_cursor: z.string().nullable(),
  });

const moneyAccountListSchema = listResponse(moneyAccountSchema);
const moneyPayeeListSchema = listResponse(moneyPayeeSchema);
const moneyCategoryListSchema = listResponse(moneyCategorySchema);
const moneyBudgetListSchema = listResponse(moneyBudgetSchema);
const moneyTransactionListSchema = listResponse(moneyTransactionSchema);
const moneyInstallmentPlanListSchema = listResponse(moneyInstallmentPlanSchema);
const moneyRecurringTransactionListSchema = listResponse(moneyRecurringTransactionSchema);

export type MoneyAccount = z.infer<typeof moneyAccountSchema>;
export type MoneyPayee = z.infer<typeof moneyPayeeSchema>;
export type MoneyCategory = z.infer<typeof moneyCategorySchema>;
export type MoneyBudget = z.infer<typeof moneyBudgetSchema>;
export type MoneyPosting = z.infer<typeof moneyPostingSchema>;
export type MoneyTransaction = z.infer<typeof moneyTransactionSchema>;
export type MoneySummary = z.infer<typeof moneySummarySchema>;
export type MoneyAccountType = z.infer<typeof moneyAccountTypeSchema>;
export type MoneyCategoryKind = z.infer<typeof moneyCategoryKindSchema>;
export type MoneyReconciliationState = z.infer<typeof moneyReconciliationStateSchema>;
export type MoneyTransactionListPage = z.infer<typeof moneyTransactionListSchema>;
export type MoneyInstallmentPlan = z.infer<typeof moneyInstallmentPlanSchema>;
export type MoneyInstallmentOccurrence = z.infer<typeof moneyInstallmentOccurrenceSchema>;
export type MoneyInstallmentPlanState = z.infer<typeof moneyInstallmentPlanStateSchema>;
export type MoneyRecurrence = z.infer<typeof moneyRecurrenceSchema>;
export type MoneyRecurrenceFrequency = z.infer<typeof moneyRecurrenceFrequencySchema>;
export type MoneyRecurrenceState = z.infer<typeof moneyRecurrenceStateSchema>;
export type MoneyRecurrenceWeekday = z.infer<typeof moneyRecurrenceWeekdaySchema>;
export type MoneyRecurringOccurrence = z.infer<typeof moneyRecurringOccurrenceSchema>;
export type MoneyRecurringPosting = z.infer<typeof moneyRecurringPostingSchema>;
export type MoneyRecurringTransaction = z.infer<typeof moneyRecurringTransactionSchema>;
export type MoneyRecurringTransactionListPage = z.infer<typeof moneyRecurringTransactionListSchema>;

export type MoneyAccountCreateInput = {
  name: string;
  account_type: MoneyAccountType;
  institution_name?: string | null;
  last_four?: string | null;
  currency_code: string;
  opening_balance: string;
  credit_limit?: string | null;
  statement_close_day?: number | null;
  payment_due_day?: number | null;
};

export type MoneyAccountUpdateInput = {
  name?: string;
  institution_name?: string | null;
  last_four?: string | null;
  credit_limit?: string | null;
  statement_close_day?: number | null;
  payment_due_day?: number | null;
};

export type MoneyInstallmentPlanCreateInput = {
  account_id: string;
  currency_code: string;
  purchase_date: string;
  name: string;
  payee_id?: string | null;
  category_id: string;
  memo?: string | null;
  total_amount: string;
  fee_amount: string;
  term_months: number;
};

export type MoneyPostingInput = {
  account_id?: string;
  category_id?: string;
  currency_code: string;
  amount: string;
};

export type MoneyTransactionInput = {
  transaction_date: string;
  name: string;
  payee_id?: string | null;
  memo?: string | null;
  postings: MoneyPostingInput[];
};

export type MoneyTransactionUpdateInput = Partial<MoneyTransactionInput>;

export type MoneyBudgetUpsertInput = {
  amount: string;
};

export type MoneyRecurrenceInput = {
  timezone: string;
  frequency: MoneyRecurrenceFrequency;
  interval: number;
  weekdays?: MoneyRecurrenceWeekday[];
  month_day?: number | null;
  month?: number | null;
  day?: number | null;
  until_date?: string | null;
  occurrence_count?: number | null;
};

export type MoneyRecurringPostingInput = {
  account_id?: string;
  category_id?: string;
  currency_code: string;
  amount: string;
};

export type MoneyRecurringTransactionCreateInput = {
  start_date: string;
  name: string;
  payee_id?: string | null;
  memo?: string | null;
  recurrence: MoneyRecurrenceInput;
  postings: MoneyRecurringPostingInput[];
};

export type MoneyRecurringTransactionUpdateInput = {
  name?: string;
  payee_id?: string | null;
  memo?: string | null;
  recurrence?: MoneyRecurrenceInput;
  postings?: MoneyRecurringPostingInput[];
};

export type MoneyTransactionFilters = {
  dateFrom?: string;
  dateTo?: string;
  search?: string;
  accountId?: string;
  payeeId?: string;
  categoryId?: string;
  currencyCode?: string;
  reconciliationState?: MoneyReconciliationState;
  includeVoided?: boolean;
};

export const moneyQueryKey = ["money"] as const;
export const moneyAccountsQueryKey = [...moneyQueryKey, "accounts"] as const;
export const moneyPayeesQueryKey = [...moneyQueryKey, "payees"] as const;
export const moneyCategoriesQueryKey = [...moneyQueryKey, "categories"] as const;
export const moneyBudgetsQueryKey = [...moneyQueryKey, "budgets"] as const;
export const moneyTransactionsQueryKey = [...moneyQueryKey, "transactions"] as const;
export const moneySummaryQueryKey = [...moneyQueryKey, "summary"] as const;
export const moneyInstallmentPlansQueryKey = [...moneyQueryKey, "installment-plans"] as const;
export const moneyRecurringTransactionsQueryKey = [...moneyQueryKey, "recurring-transactions"] as const;

function addListParams(
  params: URLSearchParams,
  options: {
    cursor?: string;
    limit?: number;
    search?: string;
    includeArchived?: boolean;
    archivedOnly?: boolean;
  },
) {
  params.set("limit", String(options.limit ?? 100));
  if (options.cursor) params.set("cursor", options.cursor);
  if (options.search) params.set("search", options.search);
  if (options.includeArchived) params.set("include_archived", "true");
  if (options.archivedOnly) params.set("archived_only", "true");
}

export function listMoneyAccounts(options: {
  cursor?: string;
  limit?: number;
  search?: string;
  includeArchived?: boolean;
  archivedOnly?: boolean;
} = {}) {
  const params = new URLSearchParams();
  addListParams(params, options);
  return apiFetch(`/api/v1/money/accounts?${params}`, {}, moneyAccountListSchema);
}

export function listMoneyPayees(options: {
  cursor?: string;
  limit?: number;
  search?: string;
  includeArchived?: boolean;
} = {}) {
  const params = new URLSearchParams();
  addListParams(params, options);
  return apiFetch(`/api/v1/money/payees?${params}`, {}, moneyPayeeListSchema);
}

export function listMoneyCategories(options: {
  cursor?: string;
  limit?: number;
  search?: string;
  kind?: MoneyCategoryKind;
  includeArchived?: boolean;
} = {}) {
  const params = new URLSearchParams();
  addListParams(params, options);
  if (options.kind) params.set("kind", options.kind);
  return apiFetch(`/api/v1/money/categories?${params}`, {}, moneyCategoryListSchema);
}

export function listMoneyBudgets(options: {
  period?: string;
  currencyCode?: string;
  cursor?: string;
  limit?: number;
} = {}) {
  const params = new URLSearchParams();
  params.set("limit", String(options.limit ?? 100));
  if (options.period) params.set("period", options.period);
  if (options.currencyCode) params.set("currency_code", options.currencyCode);
  if (options.cursor) params.set("cursor", options.cursor);
  return apiFetch(`/api/v1/money/budgets?${params}`, {}, moneyBudgetListSchema);
}

function buildTransactionPath(filters: MoneyTransactionFilters, cursor?: string) {
  const params = new URLSearchParams();
  params.set("limit", "50");
  if (filters.dateFrom) params.set("date_from", filters.dateFrom);
  if (filters.dateTo) params.set("date_to", filters.dateTo);
  if (filters.search?.trim()) params.set("search", filters.search.trim());
  if (filters.accountId) params.set("account_id", filters.accountId);
  if (filters.payeeId) params.set("payee_id", filters.payeeId);
  if (filters.categoryId) params.set("category_id", filters.categoryId);
  if (filters.currencyCode) params.set("currency_code", filters.currencyCode);
  if (filters.reconciliationState) {
    params.set("reconciliation_state", filters.reconciliationState);
  }
  if (filters.includeVoided) params.set("include_voided", "true");
  if (cursor) params.set("cursor", cursor);
  return `/api/v1/money/transactions?${params}`;
}

export function listMoneyTransactions(filters: MoneyTransactionFilters, cursor?: string) {
  return apiFetch(
    buildTransactionPath(filters, cursor),
    {},
    moneyTransactionListSchema,
  );
}

export function getMoneySummary(period: string, currencyCode = "PHP") {
  const params = new URLSearchParams({ period, currency_code: currencyCode });
  return apiFetch(`/api/v1/money/summary?${params}`, {}, moneySummarySchema);
}

export function listMoneyInstallmentPlans(options: {
  accountId?: string;
  status?: MoneyInstallmentPlanState;
  cursor?: string;
  limit?: number;
} = {}) {
  const params = new URLSearchParams();
  params.set("limit", String(options.limit ?? 100));
  if (options.accountId) params.set("account_id", options.accountId);
  if (options.status) params.set("status", options.status);
  if (options.cursor) params.set("cursor", options.cursor);
  return apiFetch(`/api/v1/money/installment-plans?${params}`, {}, moneyInstallmentPlanListSchema);
}

export function getMoneyInstallmentPlan(planId: string) {
  return apiFetch(
    `/api/v1/money/installment-plans/${encodeURIComponent(planId)}`,
    {},
    moneyInstallmentPlanSchema,
  );
}

export function createMoneyInstallmentPlan(payload: MoneyInstallmentPlanCreateInput) {
  return apiFetch(
    "/api/v1/money/installment-plans",
    { method: "POST", body: JSON.stringify(payload) },
    moneyInstallmentPlanSchema,
  );
}

export function cancelMoneyInstallmentPlan(planId: string) {
  return apiFetch(
    `/api/v1/money/installment-plans/${encodeURIComponent(planId)}/cancel`,
    { method: "POST" },
    moneyInstallmentPlanSchema,
  );
}

export function processDueMoneyInstallments() {
  return apiFetch(
    "/api/v1/money/installment-plans/process-due",
    { method: "POST" },
    moneyInstallmentProcessSchema,
  );
}

export function listMoneyRecurringTransactions(options: {
  state?: MoneyRecurrenceState;
  accountId?: string;
  search?: string;
  cursor?: string;
  limit?: number;
} = {}) {
  const params = new URLSearchParams();
  params.set("limit", String(options.limit ?? 50));
  if (options.state) params.set("state", options.state);
  if (options.accountId) params.set("account_id", options.accountId);
  if (options.search?.trim()) params.set("search", options.search.trim());
  if (options.cursor) params.set("cursor", options.cursor);
  return apiFetch(
    `/api/v1/money/recurring-transactions?${params}`,
    {},
    moneyRecurringTransactionListSchema,
  );
}

export function getMoneyRecurringTransaction(recurringTransactionId: string) {
  return apiFetch(
    `/api/v1/money/recurring-transactions/${encodeURIComponent(recurringTransactionId)}`,
    {},
    moneyRecurringTransactionSchema,
  );
}

export function createMoneyRecurringTransaction(payload: MoneyRecurringTransactionCreateInput) {
  return apiFetch(
    "/api/v1/money/recurring-transactions",
    { method: "POST", body: JSON.stringify(payload) },
    moneyRecurringTransactionSchema,
  );
}

export function updateMoneyRecurringTransaction(
  recurringTransactionId: string,
  payload: MoneyRecurringTransactionUpdateInput,
) {
  return apiFetch(
    `/api/v1/money/recurring-transactions/${encodeURIComponent(recurringTransactionId)}`,
    { method: "PATCH", body: JSON.stringify(payload) },
    moneyRecurringTransactionSchema,
  );
}

function mutateMoneyRecurringTransaction(
  recurringTransactionId: string,
  action: "pause" | "resume" | "end",
) {
  return apiFetch(
    `/api/v1/money/recurring-transactions/${encodeURIComponent(recurringTransactionId)}/${action}`,
    { method: "POST" },
    moneyRecurringTransactionSchema,
  );
}

export function pauseMoneyRecurringTransaction(recurringTransactionId: string) {
  return mutateMoneyRecurringTransaction(recurringTransactionId, "pause");
}

export function resumeMoneyRecurringTransaction(recurringTransactionId: string) {
  return mutateMoneyRecurringTransaction(recurringTransactionId, "resume");
}

export function endMoneyRecurringTransaction(recurringTransactionId: string) {
  return mutateMoneyRecurringTransaction(recurringTransactionId, "end");
}

export function upsertMoneyBudget(
  period: string,
  categoryId: string,
  currencyCode: string,
  payload: MoneyBudgetUpsertInput,
) {
  return apiFetch(
    `/api/v1/money/budgets/${encodeURIComponent(period)}/${encodeURIComponent(categoryId)}/${encodeURIComponent(currencyCode)}`,
    { method: "PUT", body: JSON.stringify(payload) },
    moneyBudgetSchema,
  );
}

export function deleteMoneyBudget(budgetId: string) {
  return apiFetch<void>(
    `/api/v1/money/budgets/${encodeURIComponent(budgetId)}`,
    { method: "DELETE" },
  );
}

export function getMoneyAccount(accountId: string) {
  return apiFetch(
    `/api/v1/money/accounts/${encodeURIComponent(accountId)}`,
    {},
    moneyAccountSchema,
  );
}

export function createMoneyAccount(payload: MoneyAccountCreateInput) {
  return apiFetch(
    "/api/v1/money/accounts",
    { method: "POST", body: JSON.stringify(payload) },
    moneyAccountSchema,
  );
}

export function updateMoneyAccount(
  accountId: string,
  payload: MoneyAccountUpdateInput,
) {
  return apiFetch(
    `/api/v1/money/accounts/${encodeURIComponent(accountId)}`,
    { method: "PATCH", body: JSON.stringify(payload) },
    moneyAccountSchema,
  );
}

export function archiveMoneyAccount(accountId: string) {
  return apiFetch(
    `/api/v1/money/accounts/${encodeURIComponent(accountId)}/archive`,
    { method: "POST" },
    moneyAccountSchema,
  );
}

export function restoreMoneyAccount(accountId: string) {
  return apiFetch(
    `/api/v1/money/accounts/${encodeURIComponent(accountId)}/restore`,
    { method: "POST" },
    moneyAccountSchema,
  );
}

export function getMoneyTransaction(transactionId: string) {
  return apiFetch(
    `/api/v1/money/transactions/${encodeURIComponent(transactionId)}`,
    {},
    moneyTransactionSchema,
  );
}

export function createMoneyTransaction(payload: MoneyTransactionInput) {
  return apiFetch(
    "/api/v1/money/transactions",
    { method: "POST", body: JSON.stringify(payload) },
    moneyTransactionSchema,
  );
}

export function updateMoneyTransaction(
  transactionId: string,
  payload: MoneyTransactionUpdateInput,
) {
  return apiFetch(
    `/api/v1/money/transactions/${encodeURIComponent(transactionId)}`,
    { method: "PATCH", body: JSON.stringify(payload) },
    moneyTransactionSchema,
  );
}

function mutateMoneyPosting(
  transactionId: string,
  postingId: string,
  action: "clear" | "reconcile",
) {
  return apiFetch(
    `/api/v1/money/transactions/${encodeURIComponent(transactionId)}/postings/${encodeURIComponent(postingId)}/${action}`,
    { method: "POST" },
    moneyTransactionSchema,
  );
}

export function clearMoneyPosting(transactionId: string, postingId: string) {
  return mutateMoneyPosting(transactionId, postingId, "clear");
}

export function reconcileMoneyPosting(transactionId: string, postingId: string) {
  return mutateMoneyPosting(transactionId, postingId, "reconcile");
}

export function reverseMoneyTransaction(
  transactionId: string,
  payload?: { transaction_date?: string; memo?: string | null },
) {
  return apiFetch(
    `/api/v1/money/transactions/${encodeURIComponent(transactionId)}/reverse`,
    { method: "POST", body: payload ? JSON.stringify(payload) : undefined },
    moneyTransactionSchema,
  );
}

export function createMoneyPayee(payload: { name: string }) {
  return apiFetch(
    "/api/v1/money/payees",
    { method: "POST", body: JSON.stringify(payload) },
    moneyPayeeSchema,
  );
}

export function createMoneyCategory(payload: {
  name: string;
  kind: MoneyCategoryKind;
}) {
  return apiFetch(
    "/api/v1/money/categories",
    { method: "POST", body: JSON.stringify(payload) },
    moneyCategorySchema,
  );
}

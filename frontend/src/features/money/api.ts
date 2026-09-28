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
export const moneyCategoryKindSchema = z.enum(["income", "expense"]);
export const moneyTransactionStateSchema = z.enum(["posted", "voided"]);
export const moneyReconciliationStateSchema = z.enum([
  "uncleared",
  "cleared",
  "reconciled",
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

function addListParams(
  params: URLSearchParams,
  options: { cursor?: string; limit?: number; search?: string; includeArchived?: boolean },
) {
  params.set("limit", String(options.limit ?? 100));
  if (options.cursor) params.set("cursor", options.cursor);
  if (options.search) params.set("search", options.search);
  if (options.includeArchived) params.set("include_archived", "true");
}

export function listMoneyAccounts(options: {
  cursor?: string;
  limit?: number;
  search?: string;
  includeArchived?: boolean;
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

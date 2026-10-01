"use client";

import { useInfiniteQuery, useQuery, type QueryClient } from "@tanstack/react-query";
import {
  listMoneyAccounts,
  listMoneyBudgets,
  listMoneyCategories,
  listMoneyPayees,
  listMoneyTransactions,
  listMoneyInstallmentPlans,
  listMoneyRecurringTransactions,
  getMoneySummary,
  type MoneyCategory,
  type MoneyRecurrenceState,
  type MoneyTransactionFilters,
} from "./api";
import {
  moneyAccountsQueryKey,
  moneyBudgetsQueryKey,
  moneyCategoriesQueryKey,
  moneyPayeesQueryKey,
  moneySummaryQueryKey,
  moneyTransactionsQueryKey,
  moneyInstallmentPlansQueryKey,
  moneyRecurringTransactionsQueryKey,
} from "./api";

function flattenPages<T>(pages: Array<{ items: T[] }> | undefined) {
  return pages?.flatMap((page) => page.items) ?? [];
}

export function useMoneyCatalog() {
  const accountsQuery = useInfiniteQuery({
    queryKey: moneyAccountsQueryKey,
    queryFn: ({ pageParam }: { pageParam: string }) => listMoneyAccounts({ cursor: pageParam }),
    initialPageParam: "",
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
  const payeesQuery = useInfiniteQuery({
    queryKey: moneyPayeesQueryKey,
    queryFn: ({ pageParam }: { pageParam: string }) => listMoneyPayees({ cursor: pageParam }),
    initialPageParam: "",
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
  const categoriesQuery = useInfiniteQuery({
    queryKey: moneyCategoriesQueryKey,
    queryFn: ({ pageParam }: { pageParam: string }) => listMoneyCategories({ cursor: pageParam }),
    initialPageParam: "",
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });

  const accounts = flattenPages(accountsQuery.data?.pages);
  const payees = flattenPages(payeesQuery.data?.pages);
  const categories = flattenPages(categoriesQuery.data?.pages);

  const loadAll = async () => {
    await Promise.all([
      accountsQuery.hasNextPage ? accountsQuery.fetchNextPage() : Promise.resolve(),
      payeesQuery.hasNextPage ? payeesQuery.fetchNextPage() : Promise.resolve(),
      categoriesQuery.hasNextPage ? categoriesQuery.fetchNextPage() : Promise.resolve(),
    ]);
  };

  return {
    accounts,
    payees,
    categories,
    isPending: accountsQuery.isPending || payeesQuery.isPending || categoriesQuery.isPending,
    isError: accountsQuery.isError || payeesQuery.isError || categoriesQuery.isError,
    error: accountsQuery.error ?? payeesQuery.error ?? categoriesQuery.error,
    refetch: () => Promise.all([
      accountsQuery.refetch(),
      payeesQuery.refetch(),
      categoriesQuery.refetch(),
    ]),
    loadAll,
  };
}

export function useMoneyAccounts(options: {
  archivedOnly?: boolean;
  search?: string;
} = {}) {
  const archivedOnly = options.archivedOnly ?? false;
  const search = options.search?.trim() ?? "";

  return useInfiniteQuery({
    queryKey: [...moneyAccountsQueryKey, "list", { archivedOnly, search }],
    queryFn: ({ pageParam }: { pageParam: string }) =>
      listMoneyAccounts({
        archivedOnly,
        cursor: pageParam,
        limit: 50,
        search: search || undefined,
      }),
    initialPageParam: "",
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
}

export function useMoneyTransactions(filters: MoneyTransactionFilters) {
  return useInfiniteQuery({
    queryKey: [...moneyTransactionsQueryKey, "list", filters],
    queryFn: ({ pageParam }: { pageParam: string }) => listMoneyTransactions(filters, pageParam),
    initialPageParam: "",
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
}

export function useMoneyBudgets(period: string, currencyCode: string) {
  return useInfiniteQuery({
    queryKey: [...moneyBudgetsQueryKey, "list", { period, currencyCode }],
    queryFn: ({ pageParam }: { pageParam: string }) =>
      listMoneyBudgets({ period, currencyCode, cursor: pageParam, limit: 50 }),
    initialPageParam: "",
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
}

export function useMoneyInstallmentPlans(accountId?: string) {
  return useInfiniteQuery({
    queryKey: [...moneyInstallmentPlansQueryKey, "list", { accountId }],
    queryFn: ({ pageParam }: { pageParam: string }) =>
      listMoneyInstallmentPlans({ accountId, cursor: pageParam, limit: 100 }),
    initialPageParam: "",
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
}

export function useMoneyRecurringTransactions(options: {
  state?: MoneyRecurrenceState;
  accountId?: string;
  search?: string;
} = {}) {
  const search = options.search?.trim() ?? "";

  return useInfiniteQuery({
    queryKey: [
      ...moneyRecurringTransactionsQueryKey,
      "list",
      { state: options.state, accountId: options.accountId, search },
    ],
    queryFn: ({ pageParam }: { pageParam: string }) =>
      listMoneyRecurringTransactions({
        state: options.state,
        accountId: options.accountId,
        search: search || undefined,
        cursor: pageParam,
        limit: 50,
      }),
    initialPageParam: "",
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
}

export function useMoneySummary(period: string, currencyCode: string) {
  return useQuery({
    queryKey: [...moneySummaryQueryKey, period, currencyCode],
    queryFn: () => getMoneySummary(period, currencyCode),
  });
}

export function categoriesForKind(categories: MoneyCategory[], kind: "income" | "expense") {
  return categories.filter((category) => category.kind === kind && !category.archived_at);
}

export function invalidateMoneyQueries(queryClient: QueryClient) {
  return Promise.all([
    queryClient.invalidateQueries({ queryKey: moneyAccountsQueryKey }),
    queryClient.invalidateQueries({ queryKey: moneyPayeesQueryKey }),
    queryClient.invalidateQueries({ queryKey: moneyCategoriesQueryKey }),
    queryClient.invalidateQueries({ queryKey: moneyTransactionsQueryKey }),
    queryClient.invalidateQueries({ queryKey: moneyBudgetsQueryKey }),
    queryClient.invalidateQueries({ queryKey: moneySummaryQueryKey }),
    queryClient.invalidateQueries({ queryKey: moneyInstallmentPlansQueryKey }),
    queryClient.invalidateQueries({ queryKey: moneyRecurringTransactionsQueryKey }),
  ]);
}

export function invalidateMoneyBudgetQueries(queryClient: QueryClient) {
  return Promise.all([
    queryClient.invalidateQueries({ queryKey: moneyBudgetsQueryKey }),
    queryClient.invalidateQueries({ queryKey: moneySummaryQueryKey }),
  ]);
}

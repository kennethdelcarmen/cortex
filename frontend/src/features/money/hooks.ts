"use client";

import { useInfiniteQuery, type QueryClient } from "@tanstack/react-query";
import {
  listMoneyAccounts,
  listMoneyCategories,
  listMoneyPayees,
  listMoneyTransactions,
  type MoneyCategory,
  type MoneyTransactionFilters,
} from "./api";
import {
  moneyAccountsQueryKey,
  moneyBudgetsQueryKey,
  moneyCategoriesQueryKey,
  moneyPayeesQueryKey,
  moneySummaryQueryKey,
  moneyTransactionsQueryKey,
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
  ]);
}

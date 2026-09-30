"use client";

import { useQuery, type QueryClient } from "@tanstack/react-query";
import { getHomeSummary, homeQueryKey } from "./api";

export function useHomeSummary(timezone: string, period: string, currencyCode = "PHP") {
  return useQuery({
    queryKey: [...homeQueryKey, timezone, period, currencyCode],
    queryFn: () => getHomeSummary(timezone, period, currencyCode),
  });
}

export function invalidateHomeQueries(queryClient: QueryClient) {
  return queryClient.invalidateQueries({ queryKey: homeQueryKey });
}

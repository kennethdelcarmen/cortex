"use client";

import { useQuery } from "@tanstack/react-query";
import { authQueryKey, getCurrentUser } from "./api";

export function useCurrentUser() {
  return useQuery({
    queryKey: authQueryKey,
    queryFn: getCurrentUser,
    retry: false,
  });
}

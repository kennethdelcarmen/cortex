"use client";

import { useQueryClient } from "@tanstack/react-query";
import {
  activityLogQueryKey,
  tryAppendActivityLog,
  type ActivityLogWriteInput,
} from "./api";

export function useActivityLogger() {
  const queryClient = useQueryClient();

  return async (payload: ActivityLogWriteInput) => {
    const recorded = await tryAppendActivityLog(payload);

    if (recorded) {
      void queryClient.invalidateQueries({ queryKey: activityLogQueryKey });
    }

    return recorded;
  };
}

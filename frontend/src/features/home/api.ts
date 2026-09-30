import { z } from "zod";
import { apiFetch } from "@/lib/api/client";

const homeTaskSchema = z.object({
  id: z.string().min(1),
  title: z.string().min(1),
  status: z.enum(["backlog", "todo", "in_progress"]),
  priority: z.enum(["none", "low", "medium", "high"]),
  start_at: z.string().nullable(),
  due_at: z.string().nullable(),
  overdue: z.boolean(),
});

const homeNotesSchema = z.object({
  count: z.number().int().nonnegative(),
  items: z.array(z.object({
    id: z.string().min(1),
    title: z.string().nullable(),
    journal_date: z.string().nullable(),
    updated_at: z.string().min(1),
    preview: z.string(),
  })),
});

const homeMovementSchema = z.object({
  id: z.string().min(1),
  transaction_date: z.string().min(1),
  name: z.string().min(1),
  direction: z.enum(["income", "expense", "transfer"]),
  amount: z.string().min(1),
  currency_code: z.string().length(3),
});

const homeMoneySchema = z.object({
  period: z.string().regex(/^\d{4}-(0[1-9]|1[0-2])$/),
  currency_code: z.string().length(3),
  total_balance: z.string().min(1),
  income_amount: z.string().min(1),
  spending_amount: z.string().min(1),
  budget_amount: z.string().min(1),
  budget_spent_amount: z.string().min(1),
  budget_remaining_amount: z.string().min(1),
  movements: z.array(homeMovementSchema),
});

const homeActivitySchema = z.object({
  id: z.string().min(1),
  user_id: z.string().min(1),
  event_type: z.string().min(1),
  entity_type: z.string().nullable(),
  entity_id: z.string().nullable(),
  metadata: z.record(z.string(), z.unknown()),
  created_at: z.string().min(1),
});

const homeSummarySchema = z.object({
  period: z.string().regex(/^\d{4}-(0[1-9]|1[0-2])$/),
  currency_code: z.string().length(3),
  tasks: z.object({
    counts: z.object({
      today: z.number().int().nonnegative(),
      upcoming: z.number().int().nonnegative(),
      overdue: z.number().int().nonnegative(),
      high_priority: z.number().int().nonnegative(),
    }),
    items: z.array(homeTaskSchema),
  }),
  notes: homeNotesSchema,
  money: homeMoneySchema,
  activity: z.array(homeActivitySchema),
});

export type HomeTask = z.infer<typeof homeTaskSchema>;
export type HomeSummary = z.infer<typeof homeSummarySchema>;
export type HomeActivity = z.infer<typeof homeActivitySchema>;

export const homeQueryKey = ["home", "summary"] as const;

export function getHomeSummary(timezone: string, period: string, currencyCode = "PHP") {
  const params = new URLSearchParams({
    timezone,
    period,
    currency_code: currencyCode,
  });

  return apiFetch(
    `/api/v1/home/summary?${params.toString()}`,
    {},
    homeSummarySchema,
  );
}

import { BudgetsRoute } from "@/features/money/components/budgets-page";

export const metadata = {
  title: "Budgets · Money · Cortex",
  description: "Plan monthly category spending in Cortex.",
};

export default function BudgetsPage() {
  return <BudgetsRoute />;
}

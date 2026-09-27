import { MoneyRoute } from "@/features/money/components/money-page";

export const metadata = {
  title: "Money · Cortex",
  description: "The cash flow and budgets workspace for Cortex.",
};

export default function MoneyPage() {
  return <MoneyRoute />;
}

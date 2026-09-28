import { TransactionsRoute } from "@/features/money/components/transactions-page";

export const metadata = {
  title: "Transactions · Money · Cortex",
  description: "Review and record money transactions in Cortex.",
};

export default function TransactionsPage() {
  return <TransactionsRoute />;
}

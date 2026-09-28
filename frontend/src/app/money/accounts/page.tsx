import { AccountsRoute } from "@/features/money/components/accounts-page";

export const metadata = {
  title: "Accounts · Money · Cortex",
  description: "Manage the accounts that hold your money in Cortex.",
};

export default function AccountsPage() {
  return <AccountsRoute />;
}

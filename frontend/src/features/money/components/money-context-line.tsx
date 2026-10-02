import {
  ArrowLeftRight,
  Building2,
  CreditCard,
  ReceiptText,
  Tag,
  Tags,
  WalletCards,
  type LucideIcon,
} from "lucide-react";
import type { MoneyAccount } from "../api";

export type MoneyContextKind = "category" | "split" | "transfer" | "installment";

export function MoneyContextLine({ icon: Icon, label }: { icon: LucideIcon; label: string }) {
  return (
    <span className="flex min-w-0 items-center gap-1.5">
      <Icon aria-hidden="true" className="size-3.5 shrink-0 text-primary-strong" />
      <span className="truncate">{label}</span>
    </span>
  );
}

export function moneyCategoryContextIcon(kind: MoneyContextKind): LucideIcon {
  if (kind === "installment") return ReceiptText;
  if (kind === "split") return Tags;
  if (kind === "transfer") return ArrowLeftRight;
  return Tag;
}

export function moneyAccountContextIcon(account?: MoneyAccount): LucideIcon {
  if (account?.account_type === "credit_card") return CreditCard;
  if (account?.account_type === "cash") return WalletCards;
  return Building2;
}

import { ApiError } from "@/lib/api/client";
import type {
  MoneyAccount,
  MoneyCategory,
  MoneyTransaction,
} from "./api";

export type TransactionMode = "expense" | "income" | "transfer";

const currencyFractionDigits: Record<string, number> = {
  JPY: 0,
  KRW: 0,
};

export function currentPeriod() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

export function periodRange(period: string) {
  const [year, month] = period.split("-").map(Number);
  const start = `${period}-01`;
  const lastDay = new Date(year, month, 0).getDate();
  return { start, end: `${period}-${String(lastDay).padStart(2, "0")}` };
}

export function periodLabel(period: string) {
  const [year, month] = period.split("-").map(Number);
  return new Intl.DateTimeFormat(undefined, { month: "long", year: "numeric" }).format(
    new Date(year, month - 1, 1),
  );
}

export function periodOptions(count = 12) {
  const now = new Date();
  return Array.from({ length: count }, (_, index) => {
    const date = new Date(now.getFullYear(), now.getMonth() - index, 1);
    const id = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}`;
    return { id, label: periodLabel(id) };
  });
}

export function formatMoney(amount: string | number, currencyCode = "PHP") {
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency: currencyCode,
    minimumFractionDigits: currencyFractionDigits[currencyCode] ?? 2,
    maximumFractionDigits: currencyFractionDigits[currencyCode] ?? 2,
  }).format(typeof amount === "number" ? amount : Number(amount));
}

export function formatSignedMoney(amount: string | number, currencyCode = "PHP") {
  const numericAmount = typeof amount === "number" ? amount : Number(amount);
  const sign = numericAmount > 0 ? "+" : numericAmount < 0 ? "−" : "";
  return `${sign}${formatMoney(Math.abs(numericAmount), currencyCode)}`;
}

export function formatAmountInput(value: string, currencyCode: string) {
  const numericValue = Number(value);
  if (!Number.isFinite(numericValue) || numericValue <= 0) return "";
  return numericValue.toFixed(currencyFractionDigits[currencyCode] ?? 2);
}

export function accountLabel(account: MoneyAccount) {
  return account.last_four ? `${account.name} ··${account.last_four}` : account.name;
}

export function accountTypeLabel(value: MoneyAccount["account_type"]) {
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function describeMoneyError(error: unknown) {
  if (error instanceof ApiError) return error.message;
  return "The money request could not be completed. Try again.";
}

export function transactionAccountPostings(transaction: MoneyTransaction) {
  return transaction.postings.filter((posting) => posting.account_id);
}

export function transactionCategoryPostings(transaction: MoneyTransaction) {
  return transaction.postings.filter((posting) => posting.category_id);
}

export function transactionDisplayAmount(transaction: MoneyTransaction) {
  const accounts = transactionAccountPostings(transaction);
  return accounts.find((posting) => Number(posting.amount) < 0)?.amount ?? accounts[0]?.amount ?? "0";
}

export function transactionMode(
  transaction: MoneyTransaction,
  categories: MoneyCategory[],
): TransactionMode | null {
  const accounts = transactionAccountPostings(transaction);
  const categoryPostings = transactionCategoryPostings(transaction);
  if (accounts.length === 2 && categoryPostings.length === 0) return "transfer";
  if (accounts.length !== 1 || categoryPostings.length !== 1) return null;
  const category = categories.find((item) => item.id === categoryPostings[0].category_id);
  if (!category) return null;
  if (category.kind === "expense" && Number(accounts[0].amount) < 0) return "expense";
  if (category.kind === "income" && Number(accounts[0].amount) > 0) return "income";
  return null;
}

export function describeTransactionMode(mode: TransactionMode) {
  return mode === "expense" ? "Expense" : mode === "income" ? "Income" : "Transfer";
}

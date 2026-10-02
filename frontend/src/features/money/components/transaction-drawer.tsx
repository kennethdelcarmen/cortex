"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDownLeft, ArrowLeftRight, ArrowUpRight, Ban, Check, CreditCard, GitFork, Pencil, RotateCcw, Undo2, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { useFeedback } from "@/components/feedback";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Drawer, DrawerClose, DrawerContent, DrawerDescription, DrawerFooter, DrawerHeader, DrawerTitle } from "@/components/ui/drawer";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { SelectItem, SelectSeparator } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { currentLocalDateInput } from "@/lib/date";
import { cn } from "@/lib/utils";
import {
  clearMoneyPosting,
  createMoneyInstallmentPlan,
  createMoneyCategory,
  createMoneyPayee,
  createMoneyTransaction,
  getMoneyTransaction,
  moneyTransactionsQueryKey,
  reconcileMoneyPosting,
  restoreMoneyTransaction,
  reverseMoneyTransaction,
  updateMoneyTransaction,
  voidMoneyTransaction,
  type MoneyAccount,
  type MoneyCategory,
  type MoneyPayee,
  type MoneyTransaction,
  type MoneyTransactionInput,
} from "../api";
import { categoriesForKind, invalidateMoneyQueries } from "../hooks";
import {
  accountLabel,
  describeMoneyError,
  describeTransactionMode,
  formatAmountInput,
  formatMinorUnits,
  formatSignedMoney,
  isSplitTransaction,
  parseMoneyMinorUnits,
  splitDirection,
  transactionAccountPostings,
  transactionCategoryPostings,
  transactionMode,
  type SplitDirection,
  type TransactionMode,
} from "../utils";
import { MoneyResourceCreateDialog, type MoneyResourceKind } from "./money-resource-create-dialog";
import { MoneySelectField } from "./money-select-field";
import { createSplitRows, SplitTransactionEditor, type SplitTransactionRow } from "./split-transaction-editor";

type TransactionDrawerProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSaved?: () => void;
  transactionId?: string | null;
  defaultDate?: string;
  defaultCurrencyCode?: string;
  accounts: MoneyAccount[];
  payees: MoneyPayee[];
  categories: MoneyCategory[];
};

type EntryMode = TransactionMode | "installment" | "split";

const amountPattern = /^-?(?:0|[1-9]\d*)(?:\.\d+)?$/;

function transactionDraft(transaction: MoneyTransaction, categories: MoneyCategory[]) {
  if (isSplitTransaction(transaction)) {
    const accountPosting = transactionAccountPostings(transaction)[0];
    const direction = splitDirection(transaction);
    if (!accountPosting || !direction) return null;
    return {
      mode: "split" as const,
      date: transaction.transaction_date,
      name: transaction.name,
      payeeId: transaction.payee_id ?? "",
      memo: transaction.memo ?? "",
      amount: formatAmountInput(Math.abs(Number(accountPosting.amount)).toString(), accountPosting.currency_code),
      accountId: accountPosting.account_id ?? "",
      destinationAccountId: "",
      categoryId: "",
      currencyCode: accountPosting.currency_code,
      splitDirection: direction,
      splitRows: transactionCategoryPostings(transaction)
        .slice()
        .sort((left, right) => left.position - right.position)
        .map((posting, index) => ({
          id: posting.id || `split-row-${index}`,
          categoryId: posting.category_id ?? "",
          label: posting.label ?? "",
          amount: formatAmountInput(Math.abs(Number(posting.amount)).toString(), posting.currency_code),
        })),
    };
  }

  const mode = transactionMode(transaction, categories);
  const accounts = transactionAccountPostings(transaction);
  const categoriesForTransaction = transactionCategoryPostings(transaction);
  const negativeAccount = accounts.find((posting) => Number(posting.amount) < 0);
  const positiveAccount = accounts.find((posting) => Number(posting.amount) > 0);
  const amountPosting = negativeAccount ?? positiveAccount;

  if (!mode || !amountPosting) return null;

  return {
    mode,
    date: transaction.transaction_date,
    name: transaction.name,
    payeeId: transaction.payee_id ?? "",
    memo: transaction.memo ?? "",
    amount: formatAmountInput(Math.abs(Number(amountPosting.amount)).toString(), amountPosting.currency_code),
    accountId: mode === "income" ? positiveAccount?.account_id ?? "" : negativeAccount?.account_id ?? "",
    destinationAccountId: mode === "transfer" ? positiveAccount?.account_id ?? "" : "",
    categoryId: categoriesForTransaction[0]?.category_id ?? "",
    currencyCode: amountPosting.currency_code,
  };
}

export function TransactionDrawer({
  open,
  onOpenChange,
  onSaved,
  transactionId,
  defaultDate,
  defaultCurrencyCode = "PHP",
  accounts,
  payees,
  categories,
}: TransactionDrawerProps) {
  const queryClient = useQueryClient();
  const feedback = useFeedback();
  const [editing, setEditing] = useState(!transactionId);
  const [mode, setMode] = useState<EntryMode>("expense");
  const [date, setDate] = useState(defaultDate ?? currentLocalDateInput());
  const [name, setName] = useState("");
  const [payeeId, setPayeeId] = useState("");
  const [memo, setMemo] = useState("");
  const [amount, setAmount] = useState("");
  const [accountId, setAccountId] = useState("");
  const [destinationAccountId, setDestinationAccountId] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [splitDirectionValue, setSplitDirectionValue] = useState<SplitDirection>("expense");
  const [splitRows, setSplitRows] = useState<SplitTransactionRow[]>(() => createSplitRows());
  const [termMonths, setTermMonths] = useState("12");
  const [feeAmount, setFeeAmount] = useState("0");
  const [error, setError] = useState<string>();
  const [resourceDialogKind, setResourceDialogKind] = useState<MoneyResourceKind | null>(null);
  const [resourceDialogDisplayKind, setResourceDialogDisplayKind] = useState<MoneyResourceKind>("payee");
  const [splitCategoryRowIndex, setSplitCategoryRowIndex] = useState<number | null>(null);
  const [resourceName, setResourceName] = useState("");
  const [resourceError, setResourceError] = useState<string>();
  const [resourceLabels, setResourceLabels] = useState<Record<string, string>>({});
  const [confirmation, setConfirmation] = useState<"void" | "reverse" | null>(null);
  const initializedSessionRef = useRef<string | null>(null);
  const transactionQuery = useQuery({
    queryKey: [...moneyTransactionsQueryKey, transactionId],
    queryFn: () => getMoneyTransaction(transactionId ?? ""),
    enabled: open && Boolean(transactionId),
  });
  const transaction = transactionQuery.data;
  const activeAccounts = useMemo(() => accounts.filter((account) => !account.archived_at), [accounts]);
  const selectedAccount = activeAccounts.find((account) => account.id === accountId);
  const selectedCurrency = selectedAccount?.currency_code ?? defaultCurrencyCode;
  const modeCategories = mode === "transfer" || mode === "split"
    ? []
    : categoriesForKind(categories, mode === "income" ? "income" : "expense");
  const supportedEdit = transaction
    ? transactionMode(transaction, categories) !== null || isSplitTransaction(transaction)
    : false;
  const hasReconciledAccountPosting = transaction
    ? transactionAccountPostings(transaction).some((posting) => posting.reconciliation_state === "reconciled")
    : false;
  const canVoid = transaction
    ? transaction.state === "posted"
      && transaction.reversal_of_id === null
      && !hasReconciledAccountPosting
    : false;
  const canRestore = transaction
    ? transaction.state === "voided" && transaction.void_reason === "manual"
    : false;

  useEffect(() => {
    if (!open) {
      initializedSessionRef.current = null;
      return;
    }
    if (transactionId && !transaction) return;
    const sessionKey = transactionId ? `${transactionId}:${transaction?.updated_at ?? ""}` : "new";
    if (initializedSessionRef.current === sessionKey) return;
    initializedSessionRef.current = sessionKey;
    let cancelled = false;
    queueMicrotask(() => {
      if (cancelled) return;
      setError(undefined);
      setResourceDialogKind(null);
      setSplitCategoryRowIndex(null);
      setResourceName("");
      setResourceError(undefined);
      setResourceLabels({});
      if (transactionId && transaction) {
        const draft = transactionDraft(transaction, categories);
        setEditing(false);
        if (!draft) return;
        setMode(draft.mode);
        setDate(draft.date);
        setName(draft.name);
        setPayeeId(draft.payeeId);
        setMemo(draft.memo);
        setAmount(draft.amount);
        setAccountId(draft.accountId);
        setDestinationAccountId(draft.destinationAccountId);
        setCategoryId(draft.categoryId);
        if (draft.mode === "split") {
          setSplitDirectionValue(draft.splitDirection);
          setSplitRows(draft.splitRows);
        } else {
          setSplitDirectionValue("expense");
          setSplitRows(createSplitRows());
        }
        return;
      }
      if (!transactionId) {
        setEditing(true);
        setMode("expense");
        setDate(defaultDate ?? currentLocalDateInput());
        setName("");
        setPayeeId("");
        setMemo("");
        setAmount("");
        setAccountId(activeAccounts[0]?.id ?? "");
        setDestinationAccountId(activeAccounts[1]?.id ?? "");
        setCategoryId(categoriesForKind(categories, "expense")[0]?.id ?? "");
        setSplitDirectionValue("expense");
        setSplitRows(createSplitRows());
      }
    });
    return () => {
      cancelled = true;
    };
  }, [activeAccounts, categories, defaultDate, open, transaction, transactionId]);

  const createPayeeMutation = useMutation({ mutationFn: createMoneyPayee });
  const createCategoryMutation = useMutation({ mutationFn: createMoneyCategory });
  const saveMutation = useMutation({
    mutationFn: async (payload: MoneyTransactionInput) => {
      if (transactionId) return updateMoneyTransaction(transactionId, payload);
      return createMoneyTransaction(payload);
    },
  });
  const installmentMutation = useMutation({ mutationFn: createMoneyInstallmentPlan });
  const postingMutation = useMutation({
    mutationFn: ({ action, postingId }: { action: "clear" | "reconcile"; postingId: string }) =>
      action === "clear"
        ? clearMoneyPosting(transactionId ?? "", postingId)
        : reconcileMoneyPosting(transactionId ?? "", postingId),
  });
  const reverseMutation = useMutation({ mutationFn: () => reverseMoneyTransaction(transactionId ?? "") });
  const voidMutation = useMutation({ mutationFn: () => voidMoneyTransaction(transactionId ?? "") });
  const restoreMutation = useMutation({ mutationFn: () => restoreMoneyTransaction(transactionId ?? "") });

  const pending = saveMutation.isPending || installmentMutation.isPending || createPayeeMutation.isPending || createCategoryMutation.isPending;
  const confirmationPending = voidMutation.isPending || reverseMutation.isPending;

  function handleSplitCategoryCreate(rowIndex: number) {
    setSplitCategoryRowIndex(rowIndex);
    setResourceDialogDisplayKind("category");
    setResourceDialogKind("category");
    setResourceName("");
    setResourceError(undefined);
  }

  function handleResourceSelect(kind: MoneyResourceKind, value: string) {
    const createValue = kind === "payee" ? "__create_payee__" : "__create_category__";
    if (value === createValue) {
      setResourceDialogDisplayKind(kind);
      setResourceDialogKind(kind);
      setSplitCategoryRowIndex(null);
      setResourceName("");
      setResourceError(undefined);
      return;
    }
    if (kind === "payee") setPayeeId(value);
    else setCategoryId(value);
  }

  async function handleResourceSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!resourceDialogKind || !resourceName.trim()) return;
    setResourceError(undefined);
    const name = resourceName.trim();
    try {
      const categoryKind = mode === "split" ? splitDirectionValue : mode === "income" ? "income" : "expense";
      const created = resourceDialogKind === "payee"
        ? await createPayeeMutation.mutateAsync({ name })
        : await createCategoryMutation.mutateAsync({ name, kind: categoryKind });
      await invalidateMoneyQueries(queryClient);
      setResourceLabels((current) => ({ ...current, [created.id]: name }));
      if (resourceDialogKind === "payee") setPayeeId(created.id);
      else if (mode === "split" && splitCategoryRowIndex !== null) {
        setSplitRows((current) => current.map((row, index) => index === splitCategoryRowIndex ? { ...row, categoryId: created.id } : row));
      } else setCategoryId(created.id);
      setResourceDialogKind(null);
      setSplitCategoryRowIndex(null);
      setResourceName("");
      feedback.success({ title: `${resourceDialogKind === "payee" ? "Payee" : "Category"} created.` });
    } catch (reason) {
      setResourceError(describeMoneyError(reason));
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(undefined);
    const sourceAccount = activeAccounts.find((account) => account.id === accountId);
    const destinationAccount = activeAccounts.find((account) => account.id === destinationAccountId);
    const normalizedAmount = formatAmountInput(amount, sourceAccount?.currency_code ?? selectedCurrency);

    if (!date || !name.trim() || !sourceAccount || !normalizedAmount) {
      setError("Enter a transaction name, choose an account and date, and provide a positive amount before saving.");
      return;
    }
    if (mode === "transfer" && (!destinationAccount || destinationAccount.id === sourceAccount.id)) {
      setError("Choose two different accounts for a transfer.");
      return;
    }
    if (mode === "transfer" && destinationAccount?.currency_code !== sourceAccount.currency_code) {
      setError("Transfers must stay within one currency.");
      return;
    }
    if (mode !== "transfer" && mode !== "split" && !categoryId) {
      setError("Choose a category before saving.");
      return;
    }
    if (mode === "installment" && sourceAccount?.account_type !== "credit_card") {
      setError("Installment purchases must use a credit-card account.");
      return;
    }
    if (mode === "installment" && (!/^\d+$/.test(termMonths) || Number(termMonths) < 1 || Number(termMonths) > 120)) {
      setError("Choose an installment term between 1 and 120 months.");
      return;
    }
    if (mode === "installment" && !amountPattern.test(feeAmount.trim())) {
      setError("Enter a valid installment fee, such as 0 or 500.00.");
      return;
    }

    try {
      const currencyCode = sourceAccount.currency_code;
      if (mode === "installment") {
        await installmentMutation.mutateAsync({
          account_id: sourceAccount.id,
          currency_code: currencyCode,
          purchase_date: date,
          name: name.trim(),
          payee_id: payeeId || null,
          category_id: categoryId,
          memo: memo.trim() || null,
          total_amount: normalizedAmount,
          fee_amount: feeAmount.trim() || "0",
          term_months: Number(termMonths),
        });
        await invalidateMoneyQueries(queryClient);
        feedback.success({ title: "Installment purchase scheduled.", description: "The card will be charged at each statement close." });
        onSaved?.();
        onOpenChange(false);
        return;
      }
      let postings: MoneyTransactionInput["postings"];
      if (mode === "split") {
        const totalMinor = parseMoneyMinorUnits(normalizedAmount, currencyCode);
        if (totalMinor === null || totalMinor <= 0) {
          setError("Enter a valid positive total amount.");
          return;
        }
        if (splitRows.length < 2) {
          setError("Add at least two category rows to create a split.");
          return;
        }
        const rowValues = splitRows.map((row) => ({
          ...row,
          label: row.label.trim(),
          amountMinor: parseMoneyMinorUnits(row.amount, currencyCode),
        }));
        if (rowValues.some((row) => !row.categoryId || !row.label || row.amountMinor === null || row.amountMinor <= 0)) {
          setError("Choose a category, enter a label, and provide a positive amount for every split row.");
          return;
        }
        const allocatedMinor = rowValues.reduce((sum, row) => sum + (row.amountMinor ?? 0), 0);
        if (allocatedMinor !== totalMinor) {
          setError("Split category amounts must add up exactly to the total amount.");
          return;
        }
        const accountAmount = splitDirectionValue === "expense" ? `-${normalizedAmount}` : normalizedAmount;
        const categorySign = splitDirectionValue === "expense" ? "" : "-";
        postings = [
          { account_id: sourceAccount.id, currency_code: currencyCode, amount: accountAmount },
          ...rowValues.map((row) => ({
            category_id: row.categoryId,
            currency_code: currencyCode,
            amount: `${categorySign}${formatMinorUnits(row.amountMinor ?? 0, currencyCode)}`,
            label: row.label,
          })),
        ];
      } else {
        postings = mode === "transfer"
        ? [
            { account_id: sourceAccount.id, currency_code: currencyCode, amount: `-${normalizedAmount}` },
            { account_id: destinationAccount?.id, currency_code: currencyCode, amount: normalizedAmount },
          ]
        : [
            {
              account_id: sourceAccount.id,
              currency_code: currencyCode,
              amount: mode === "expense" ? `-${normalizedAmount}` : normalizedAmount,
            },
            {
              category_id: categoryId,
              currency_code: currencyCode,
              amount: mode === "expense" ? normalizedAmount : `-${normalizedAmount}`,
            },
          ];
      }
      await saveMutation.mutateAsync({
        transaction_date: date,
        name: name.trim(),
        payee_id: payeeId || null,
        memo: memo.trim() || null,
        postings,
      });
      await invalidateMoneyQueries(queryClient);
      feedback.success({ title: transactionId ? "Transaction updated." : "Transaction recorded." });
      onSaved?.();
      onOpenChange(false);
    } catch (reason) {
      setError(describeMoneyError(reason));
    }
  }

  async function handlePostingAction(action: "clear" | "reconcile", postingId: string) {
    try {
      await postingMutation.mutateAsync({ action, postingId });
      await invalidateMoneyQueries(queryClient);
      await transactionQuery.refetch();
      feedback.success({ title: action === "clear" ? "Posting cleared." : "Posting reconciled." });
    } catch (reason) {
      feedback.error({ title: "Posting could not be updated.", description: describeMoneyError(reason) });
    }
  }

  async function handleReverse() {
    try {
      await reverseMutation.mutateAsync();
      await invalidateMoneyQueries(queryClient);
      await transactionQuery.refetch();
      setConfirmation(null);
      feedback.success({ title: "Transaction reversed.", description: "The original entry is now voided." });
    } catch (reason) {
      feedback.error({ title: "Transaction could not be reversed.", description: describeMoneyError(reason) });
    }
  }

  async function handleVoid() {
    try {
      await voidMutation.mutateAsync();
      await invalidateMoneyQueries(queryClient);
      await transactionQuery.refetch();
      setConfirmation(null);
      feedback.success({ title: "Transaction voided.", description: "The entry is hidden from the normal ledger view." });
    } catch (reason) {
      feedback.error({ title: "Transaction could not be voided.", description: describeMoneyError(reason) });
    }
  }

  async function handleRestore() {
    try {
      await restoreMutation.mutateAsync();
      await invalidateMoneyQueries(queryClient);
      await transactionQuery.refetch();
      feedback.success({ title: "Transaction restored.", description: "The entry is posted in the ledger again." });
    } catch (reason) {
      feedback.error({ title: "Transaction could not be restored.", description: describeMoneyError(reason) });
    }
  }

  function handleDrawerOpenChange(nextOpen: boolean) {
    if (!nextOpen) setConfirmation(null);
    onOpenChange(nextOpen);
  }

  function handleConfirmationConfirm() {
    if (confirmation === "void") void handleVoid();
    if (confirmation === "reverse") void handleReverse();
  }

  const title = transactionId ? (editing ? "Edit transaction" : "Transaction details") : "Add transaction";
  const description = transactionId
    ? "Review the ledger entry and its account-side reconciliation state."
    : "Record one balanced movement without manually building ledger postings.";

  return (
    <>
      <Drawer open={open} onOpenChange={handleDrawerOpenChange} swipeDirection="right">
        <DrawerContent className="min-h-[100svh] w-full max-w-xl gap-0 border-border bg-card p-0 text-card-foreground shadow-none sm:max-w-xl">
        <DrawerHeader className="border-b border-border/70 px-6 py-6 text-left sm:px-8">
          <div className="flex items-start justify-between gap-4">
            <div>
              <DrawerTitle className="text-xl font-semibold tracking-[-0.03em]">{title}</DrawerTitle>
              <DrawerDescription className="mt-2 max-w-md text-sm leading-6">{description}</DrawerDescription>
            </div>
            <DrawerClose render={<Button variant="ghost" size="icon-sm" aria-label="Close transaction drawer" />}>
              <X aria-hidden="true" />
            </DrawerClose>
          </div>
        </DrawerHeader>

        {transactionId && transactionQuery.isPending ? (
          <div className="flex flex-1 items-center justify-center p-8 text-sm text-muted-foreground">Loading transaction…</div>
        ) : transactionId && transactionQuery.isError ? (
          <div className="flex flex-1 flex-col items-center justify-center gap-3 p-8 text-center">
            <p role="alert" className="text-sm text-destructive">The transaction could not be loaded.</p>
            <p className="max-w-sm text-sm leading-6 text-muted-foreground">{describeMoneyError(transactionQuery.error)}</p>
            <Button type="button" variant="outline" onClick={() => void transactionQuery.refetch()}>Try again</Button>
          </div>
        ) : transactionId && transaction && !editing ? (
          <TransactionDetail
            transaction={transaction}
            accounts={accounts}
            categories={categories}
            payees={payees}
            canEdit={supportedEdit && !hasReconciledAccountPosting && transaction.state === "posted"}
            canReverse={transaction.state === "posted" && hasReconciledAccountPosting}
            canVoid={canVoid}
            canRestore={canRestore}
            guidedShapeSupported={supportedEdit}
            pending={postingMutation.isPending || reverseMutation.isPending || voidMutation.isPending || restoreMutation.isPending}
            onEdit={() => setEditing(true)}
            onPostingAction={handlePostingAction}
            onReverse={() => setConfirmation("reverse")}
            onVoid={() => setConfirmation("void")}
            onRestore={handleRestore}
          />
        ) : (
          <form onSubmit={handleSubmit} className="flex min-h-0 flex-1 flex-col">
            <div className="min-h-0 flex-1 space-y-6 overflow-y-auto px-6 py-6 sm:px-8">
              <div className="grid grid-cols-5 gap-1 rounded-lg border border-border/80 bg-background p-1" role="group" aria-label="Transaction type">
                {(["expense", "income", "transfer", "split", "installment"] as EntryMode[]).map((item) => {
                  const Icon = item === "expense" ? ArrowUpRight : item === "income" ? ArrowDownLeft : item === "transfer" ? ArrowLeftRight : item === "split" ? GitFork : CreditCard;
                  return (
                    <Button
                      key={item}
                      type="button"
                      variant={mode === item ? "secondary" : "ghost"}
                      size="sm"
                      aria-pressed={mode === item}
                      onClick={() => {
                        setMode(item);
                        if (item !== "split") setCategoryId("");
                        if (item === "split" && splitRows.length < 2) setSplitRows(createSplitRows());
                      }}
                    >
                      <Icon aria-hidden="true" />
                      {item === "installment" ? "Installment" : item === "split" ? "Split" : describeTransactionMode(item)}
                    </Button>
                  );
                })}
              </div>

              <div className="grid gap-4 sm:grid-cols-2">
                <div className="flex flex-col gap-2 text-sm sm:col-span-2">
                  <Label htmlFor="transaction-name">Transaction name</Label>
                  <Input id="transaction-name" className="h-11" value={name} onChange={(event) => setName(event.target.value)} placeholder="e.g. Weekly groceries" maxLength={200} required />
                </div>
                <div className="flex flex-col gap-2 text-sm">
                  <Label htmlFor="transaction-date">Date</Label>
                  <Input id="transaction-date" type="date" className="h-11" value={date} onChange={(event) => setDate(event.target.value)} required />
                </div>
                <MoneySelectField
                  id="transaction-account"
                  label={mode === "transfer" ? "From account" : "Account"}
                  value={accountId}
                  selectedLabel={selectedAccount ? `${accountLabel(selectedAccount)} · ${selectedAccount.currency_code}` : undefined}
                  emptyLabel="Choose an account"
                  onValueChange={setAccountId}
                >
                  {activeAccounts.map((account) => <SelectItem key={account.id} value={account.id}>{accountLabel(account)} · {account.currency_code}</SelectItem>)}
                </MoneySelectField>
              </div>

              {mode === "split" ? (
                <SplitTransactionEditor
                  direction={splitDirectionValue}
                  onDirectionChange={(nextDirection) => {
                    setSplitDirectionValue(nextDirection);
                    setSplitRows((current) => current.map((row) => ({ ...row, categoryId: "" })));
                  }}
                  totalAmount={amount}
                  onTotalAmountChange={setAmount}
                  rows={splitRows}
                  onRowsChange={setSplitRows}
                  categories={categories}
                  currencyCode={selectedCurrency}
                  resourceLabels={resourceLabels}
                  onCreateCategory={handleSplitCategoryCreate}
                  disabled={pending}
                />
              ) : mode === "transfer" ? (
                <MoneySelectField
                  id="transaction-destination"
                  label="To account"
                  value={destinationAccountId}
                  selectedLabel={(() => { const destination = activeAccounts.find((account) => account.id === destinationAccountId); return destination ? `${accountLabel(destination)} · ${destination.currency_code}` : undefined; })()}
                  emptyLabel="Choose a destination"
                  onValueChange={setDestinationAccountId}
                >
                  {activeAccounts.map((account) => <SelectItem key={account.id} value={account.id}>{accountLabel(account)} · {account.currency_code}</SelectItem>)}
                </MoneySelectField>
              ) : (
                <div className="grid gap-4 sm:grid-cols-2">
                  <MoneySelectField
                    id="transaction-category"
                    label="Category"
                    value={categoryId}
                    selectedLabel={modeCategories.find((category) => category.id === categoryId)?.name ?? resourceLabels[categoryId]}
                    emptyLabel="Choose a category"
                    onValueChange={(value) => handleResourceSelect("category", value)}
                  >
                    {modeCategories.map((category) => <SelectItem key={category.id} value={category.id}>{category.name}</SelectItem>)}
                    <SelectSeparator />
                    <SelectItem value="__create_category__">Create new {mode} category…</SelectItem>
                  </MoneySelectField>
                  <div className="flex flex-col gap-2 text-sm">
                    <Label htmlFor="transaction-amount">Amount · {selectedCurrency}</Label>
                  <Input id="transaction-amount" className="h-11" inputMode="decimal" placeholder="0.00" value={amount} onChange={(event) => setAmount(event.target.value)} required />
                  </div>
                  {mode === "installment" ? (
                    <>
                      <div className="flex flex-col gap-2 text-sm">
                        <Label htmlFor="installment-term">Term in months</Label>
                        <Input id="installment-term" className="h-11" inputMode="numeric" value={termMonths} onChange={(event) => setTermMonths(event.target.value.replace(/\D/g, "").slice(0, 3))} placeholder="12" required />
                      </div>
                      <div className="flex flex-col gap-2 text-sm">
                        <Label htmlFor="installment-fee">Fees included · {selectedCurrency}</Label>
                        <Input id="installment-fee" className="h-11" inputMode="decimal" value={feeAmount} onChange={(event) => setFeeAmount(event.target.value)} placeholder="0.00" required />
                      </div>
                      <p className="text-xs leading-5 text-muted-foreground sm:col-span-2">This records a purchase commitment. The card is charged one installment at each statement close; paying the card bill is tracked separately.</p>
                    </>
                  ) : null}
                </div>
              )}

              {mode === "transfer" ? (
                <div className="flex flex-col gap-2 text-sm">
                  <Label htmlFor="transaction-transfer-amount">Amount · {selectedCurrency}</Label>
                  <Input id="transaction-transfer-amount" className="h-11" inputMode="decimal" placeholder="0.00" value={amount} onChange={(event) => setAmount(event.target.value)} required />
                </div>
              ) : null}

              <MoneySelectField
                id="transaction-payee"
                label={<>Payee <span className="font-normal text-muted-foreground">Optional</span></>}
                value={payeeId}
                selectedLabel={payees.find((payee) => payee.id === payeeId)?.name ?? resourceLabels[payeeId]}
                emptyLabel="No payee"
                onValueChange={(value) => handleResourceSelect("payee", value)}
              >
                {payees.filter((payee) => !payee.archived_at).map((payee) => <SelectItem key={payee.id} value={payee.id}>{payee.name}</SelectItem>)}
                <SelectSeparator />
                <SelectItem value="__create_payee__">Create new payee…</SelectItem>
              </MoneySelectField>

              <div className="flex flex-col gap-2 text-sm">
                <Label htmlFor="transaction-memo">Memo <span className="font-normal text-muted-foreground">Optional</span></Label>
                <Textarea id="transaction-memo" rows={3} placeholder="Add useful context" value={memo} onChange={(event) => setMemo(event.target.value)} />
              </div>

              {error ? <p role="alert" className="rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">{error}</p> : null}
            </div>
            <DrawerFooter className="flex-row justify-end border-t border-border/70 bg-card px-6 py-4 sm:px-8">
              <DrawerClose type="button" render={<Button variant="outline" disabled={pending} />}>Cancel</DrawerClose>
              <Button type="submit" disabled={pending}>{pending ? "Saving…" : transactionId ? "Save changes" : "Record transaction"}</Button>
            </DrawerFooter>
          </form>
        )}
        </DrawerContent>
      </Drawer>
      <MoneyResourceCreateDialog
        kind={resourceDialogKind ?? resourceDialogDisplayKind}
        open={resourceDialogKind !== null}
        onOpenChange={(nextOpen) => {
          if (nextOpen) return;
          setResourceDialogKind(null);
          setSplitCategoryRowIndex(null);
          setResourceName("");
          setResourceError(undefined);
        }}
        name={resourceName}
        onNameChange={setResourceName}
        onSubmit={handleResourceSubmit}
        error={resourceError}
        pending={createPayeeMutation.isPending || createCategoryMutation.isPending}
      />
      <Dialog
        open={confirmation !== null}
        onOpenChange={(nextOpen) => {
          if (!nextOpen && !confirmationPending) setConfirmation(null);
        }}
      >
        <DialogContent
          showCloseButton={false}
          className="w-[min(28rem,calc(100vw-2rem))] rounded-xl border-border bg-card p-6 text-card-foreground shadow-none sm:max-w-none sm:p-7"
        >
          <DialogHeader>
            <DialogTitle className="text-xl font-semibold tracking-[-0.025em]">
              {confirmation === "void" ? "Void this transaction?" : "Reverse this transaction?"}
            </DialogTitle>
            <DialogDescription className="mt-3 text-sm leading-6 text-muted-foreground">
              {confirmation === "void"
                ? "This hides the entry from the normal ledger and derived totals. You can restore it later from Include voided transactions."
                : "This creates an offsetting entry and voids the original reconciled transaction."}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="mt-7 flex-row justify-end gap-2 border-0 bg-transparent p-0">
            <DialogClose
              type="button"
              render={<Button variant="outline" size="lg" disabled={confirmationPending} />}
            >
              Cancel
            </DialogClose>
            <Button
              type="button"
              variant="destructive"
              size="lg"
              onClick={handleConfirmationConfirm}
              disabled={confirmationPending}
            >
              {confirmationPending
                ? confirmation === "void" ? "Voiding…" : "Reversing…"
                : confirmation === "void" ? "Void transaction" : "Reverse transaction"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

function TransactionDetail({
  transaction,
  accounts,
  categories,
  payees,
  canEdit,
  canReverse,
  canVoid,
  canRestore,
  guidedShapeSupported,
  pending,
  onEdit,
  onPostingAction,
  onReverse,
  onVoid,
  onRestore,
}: {
  transaction: MoneyTransaction;
  accounts: MoneyAccount[];
  categories: MoneyCategory[];
  payees: MoneyPayee[];
  canEdit: boolean;
  canReverse: boolean;
  canVoid: boolean;
  canRestore: boolean;
  guidedShapeSupported: boolean;
  pending: boolean;
  onEdit: () => void;
  onPostingAction: (action: "clear" | "reconcile", postingId: string) => Promise<void>;
  onReverse: () => void;
  onVoid: () => void;
  onRestore: () => Promise<void>;
}) {
  const accountById = new Map(accounts.map((account) => [account.id, account]));
  const categoryById = new Map(categories.map((category) => [category.id, category]));
  const payee = payees.find((item) => item.id === transaction.payee_id);
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="min-h-0 flex-1 space-y-6 overflow-y-auto px-6 py-6 sm:px-8">
        <div>
          <p className="font-mono text-[0.65rem] uppercase tracking-[0.14em] text-muted-foreground">{transaction.transaction_date} · {transaction.state}</p>
          <h2 className="mt-2 text-xl font-semibold tracking-[-0.025em]">{transaction.name}</h2>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">{[payee?.name, transaction.memo].filter(Boolean).join(" · ") || "No additional context"}</p>
        </div>
        <div className="space-y-3" aria-label="Transaction postings">
          {transaction.postings.map((posting) => {
            const account = posting.account_id ? accountById.get(posting.account_id) : undefined;
            const category = posting.category_id ? categoryById.get(posting.category_id) : undefined;
            const label = account
              ? accountLabel(account)
              : [posting.label, category?.name].filter(Boolean).join(" · ") || "Unknown posting";
            const isAccountPosting = Boolean(posting.account_id);
            return (
              <div key={posting.id} className="rounded-lg border border-border/70 bg-background p-4">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <p className="text-sm font-medium">{label}</p>
            <p className="mt-1 text-xs text-muted-foreground">{isAccountPosting ? "Account side" : `${category?.kind ?? "Category"} side`} · {posting.currency_code}{posting.label ? " · Split label" : ""}</p>
                  </div>
                  <p className={cn("font-mono text-sm font-medium", Number(posting.amount) > 0 ? "text-tag-sea-glass-foreground" : "text-foreground")}>{formatSignedMoney(posting.amount, posting.currency_code)}</p>
                </div>
                {isAccountPosting ? (
                  <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
                    <span className="inline-flex items-center gap-1.5"><span className={cn("size-1.5 rounded-full", posting.reconciliation_state === "reconciled" ? "bg-tag-sea-glass" : posting.reconciliation_state === "cleared" ? "bg-tag-amber" : "bg-muted-foreground/50")} aria-hidden="true" />{posting.reconciliation_state}</span>
                    {transaction.state === "posted" ? (
                      <span className="flex gap-1">
                        {posting.reconciliation_state === "uncleared" ? <Button type="button" variant="outline" size="xs" disabled={pending} onClick={() => void onPostingAction("clear", posting.id)}>Clear</Button> : null}
                        {posting.reconciliation_state === "cleared" ? <Button type="button" variant="outline" size="xs" disabled={pending} onClick={() => void onPostingAction("reconcile", posting.id)}>Reconcile</Button> : null}
                        {posting.reconciliation_state === "reconciled" ? <span className="inline-flex items-center gap-1 font-medium text-tag-sea-glass-foreground"><Check aria-hidden="true" className="size-3.5" /> Locked</span> : null}
                      </span>
                    ) : null}
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
        {transaction.reversal_of_id ? <p className="rounded-lg border border-border/70 bg-background px-3 py-2 text-sm text-muted-foreground">This is a reversal entry for an earlier transaction.</p> : null}
      </div>
      <DrawerFooter className="flex-row justify-between border-t border-border/70 bg-card px-6 py-4 sm:px-8">
        <div className="flex gap-2">
          {canEdit ? <Button type="button" variant="outline" onClick={onEdit}><Pencil aria-hidden="true" />Edit</Button> : null}
          {canVoid ? <Button type="button" variant="destructive" disabled={pending} onClick={onVoid}><Ban aria-hidden="true" />Void</Button> : null}
          {canRestore ? <Button type="button" variant="outline" disabled={pending} onClick={() => void onRestore()}><Undo2 aria-hidden="true" />Restore</Button> : null}
          {canReverse ? <Button type="button" variant="destructive" disabled={pending} onClick={onReverse}><RotateCcw aria-hidden="true" />Reverse</Button> : null}
        </div>
        {!guidedShapeSupported ? <span className="self-center text-xs text-muted-foreground">Read-only detail for an unsupported transaction shape.</span> : null}
        {guidedShapeSupported && !canEdit && transaction.state === "posted" && !canReverse && !canVoid ? <span className="self-center text-xs text-muted-foreground">Reconcile an account posting to enable reversal.</span> : null}
      </DrawerFooter>
    </div>
  );
}

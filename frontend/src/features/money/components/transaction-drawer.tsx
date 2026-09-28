"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDownLeft, ArrowLeftRight, ArrowUpRight, Check, Pencil, RotateCcw, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { useFeedback } from "@/components/feedback";
import { Button } from "@/components/ui/button";
import { Drawer, DrawerClose, DrawerContent, DrawerDescription, DrawerFooter, DrawerHeader, DrawerTitle } from "@/components/ui/drawer";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { SelectItem, SelectSeparator } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import {
  clearMoneyPosting,
  createMoneyCategory,
  createMoneyPayee,
  createMoneyTransaction,
  getMoneyTransaction,
  moneyTransactionsQueryKey,
  reconcileMoneyPosting,
  reverseMoneyTransaction,
  updateMoneyTransaction,
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
  formatSignedMoney,
  transactionAccountPostings,
  transactionCategoryPostings,
  transactionMode,
  type TransactionMode,
} from "../utils";
import { MoneyResourceCreateDialog, type MoneyResourceKind } from "./money-resource-create-dialog";
import { MoneySelectField } from "./money-select-field";

type TransactionDrawerProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  transactionId?: string | null;
  defaultDate?: string;
  defaultCurrencyCode?: string;
  accounts: MoneyAccount[];
  payees: MoneyPayee[];
  categories: MoneyCategory[];
};

function transactionDraft(transaction: MoneyTransaction, categories: MoneyCategory[]) {
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
  const [mode, setMode] = useState<TransactionMode>("expense");
  const [date, setDate] = useState(defaultDate ?? new Date().toISOString().slice(0, 10));
  const [name, setName] = useState("");
  const [payeeId, setPayeeId] = useState("");
  const [memo, setMemo] = useState("");
  const [amount, setAmount] = useState("");
  const [accountId, setAccountId] = useState("");
  const [destinationAccountId, setDestinationAccountId] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [error, setError] = useState<string>();
  const [resourceDialogKind, setResourceDialogKind] = useState<MoneyResourceKind | null>(null);
  const [resourceDialogDisplayKind, setResourceDialogDisplayKind] = useState<MoneyResourceKind>("payee");
  const [resourceName, setResourceName] = useState("");
  const [resourceError, setResourceError] = useState<string>();
  const [resourceLabels, setResourceLabels] = useState<Record<string, string>>({});
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
  const modeCategories = mode === "transfer" ? [] : categoriesForKind(categories, mode);
  const supportedEdit = transaction ? transactionMode(transaction, categories) !== null : false;
  const hasReconciledAccountPosting = transaction
    ? transactionAccountPostings(transaction).some((posting) => posting.reconciliation_state === "reconciled")
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
        return;
      }
      if (!transactionId) {
        setEditing(true);
        setMode("expense");
        setDate(defaultDate ?? new Date().toISOString().slice(0, 10));
        setName("");
        setPayeeId("");
        setMemo("");
        setAmount("");
        setAccountId(activeAccounts[0]?.id ?? "");
        setDestinationAccountId(activeAccounts[1]?.id ?? "");
        setCategoryId(categoriesForKind(categories, "expense")[0]?.id ?? "");
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
  const postingMutation = useMutation({
    mutationFn: ({ action, postingId }: { action: "clear" | "reconcile"; postingId: string }) =>
      action === "clear"
        ? clearMoneyPosting(transactionId ?? "", postingId)
        : reconcileMoneyPosting(transactionId ?? "", postingId),
  });
  const reverseMutation = useMutation({ mutationFn: () => reverseMoneyTransaction(transactionId ?? "") });

  const pending = saveMutation.isPending || createPayeeMutation.isPending || createCategoryMutation.isPending;

  function handleResourceSelect(kind: MoneyResourceKind, value: string) {
    const createValue = kind === "payee" ? "__create_payee__" : "__create_category__";
    if (value === createValue) {
      setResourceDialogDisplayKind(kind);
      setResourceDialogKind(kind);
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
      const created = resourceDialogKind === "payee"
        ? await createPayeeMutation.mutateAsync({ name })
        : await createCategoryMutation.mutateAsync({ name, kind: mode as "income" | "expense" });
      await invalidateMoneyQueries(queryClient);
      setResourceLabels((current) => ({ ...current, [created.id]: name }));
      if (resourceDialogKind === "payee") setPayeeId(created.id);
      else setCategoryId(created.id);
      setResourceDialogKind(null);
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
    if (mode !== "transfer" && !categoryId) {
      setError("Choose a category before saving.");
      return;
    }

    try {
      const currencyCode = sourceAccount.currency_code;
      const postings = mode === "transfer"
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
      await saveMutation.mutateAsync({
        transaction_date: date,
        name: name.trim(),
        payee_id: payeeId || null,
        memo: memo.trim() || null,
        postings,
      });
      await invalidateMoneyQueries(queryClient);
      feedback.success({ title: transactionId ? "Transaction updated." : "Transaction recorded." });
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
      feedback.success({ title: "Transaction reversed.", description: "The original entry is now voided." });
    } catch (reason) {
      feedback.error({ title: "Transaction could not be reversed.", description: describeMoneyError(reason) });
    }
  }

  const title = transactionId ? (editing ? "Edit transaction" : "Transaction details") : "Add transaction";
  const description = transactionId
    ? "Review the ledger entry and its account-side reconciliation state."
    : "Record one balanced movement without manually building ledger postings.";

  return (
    <>
      <Drawer open={open} onOpenChange={onOpenChange} swipeDirection="right">
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
            guidedShapeSupported={supportedEdit}
            pending={postingMutation.isPending || reverseMutation.isPending}
            onEdit={() => setEditing(true)}
            onPostingAction={handlePostingAction}
            onReverse={handleReverse}
          />
        ) : (
          <form onSubmit={handleSubmit} className="flex min-h-0 flex-1 flex-col">
            <div className="min-h-0 flex-1 space-y-6 overflow-y-auto px-6 py-6 sm:px-8">
              <div className="grid grid-cols-3 gap-1 rounded-lg border border-border/80 bg-background p-1" role="group" aria-label="Transaction type">
                {(["expense", "income", "transfer"] as TransactionMode[]).map((item) => {
                  const Icon = item === "expense" ? ArrowUpRight : item === "income" ? ArrowDownLeft : ArrowLeftRight;
                  return (
                    <Button
                      key={item}
                      type="button"
                      variant={mode === item ? "secondary" : "ghost"}
                      size="sm"
                      aria-pressed={mode === item}
                      onClick={() => {
                        setMode(item);
                        setCategoryId("");
                      }}
                    >
                      <Icon aria-hidden="true" />
                      {describeTransactionMode(item)}
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

              {mode === "transfer" ? (
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
          setResourceName("");
          setResourceError(undefined);
        }}
        name={resourceName}
        onNameChange={setResourceName}
        onSubmit={handleResourceSubmit}
        error={resourceError}
        pending={createPayeeMutation.isPending || createCategoryMutation.isPending}
      />
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
  guidedShapeSupported,
  pending,
  onEdit,
  onPostingAction,
  onReverse,
}: {
  transaction: MoneyTransaction;
  accounts: MoneyAccount[];
  categories: MoneyCategory[];
  payees: MoneyPayee[];
  canEdit: boolean;
  canReverse: boolean;
  guidedShapeSupported: boolean;
  pending: boolean;
  onEdit: () => void;
  onPostingAction: (action: "clear" | "reconcile", postingId: string) => Promise<void>;
  onReverse: () => Promise<void>;
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
            const label = account ? accountLabel(account) : category?.name ?? "Unknown posting";
            const isAccountPosting = Boolean(posting.account_id);
            return (
              <div key={posting.id} className="rounded-lg border border-border/70 bg-background p-4">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <p className="text-sm font-medium">{label}</p>
                    <p className="mt-1 text-xs text-muted-foreground">{isAccountPosting ? "Account side" : `${category?.kind ?? "Category"} side`} · {posting.currency_code}</p>
                  </div>
                  <p className={cn("font-mono text-sm font-medium", Number(posting.amount) > 0 ? "text-tag-sea-glass-foreground" : "text-foreground")}>{formatSignedMoney(posting.amount, posting.currency_code)}</p>
                </div>
                <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
                  <span className="inline-flex items-center gap-1.5"><span className={cn("size-1.5 rounded-full", posting.reconciliation_state === "reconciled" ? "bg-tag-sea-glass" : posting.reconciliation_state === "cleared" ? "bg-tag-amber" : "bg-muted-foreground/50")} aria-hidden="true" />{posting.reconciliation_state}</span>
                  {isAccountPosting && transaction.state === "posted" ? (
                    <span className="flex gap-1">
                      {posting.reconciliation_state === "uncleared" ? <Button type="button" variant="outline" size="xs" disabled={pending} onClick={() => void onPostingAction("clear", posting.id)}>Clear</Button> : null}
                      {posting.reconciliation_state === "cleared" ? <Button type="button" variant="outline" size="xs" disabled={pending} onClick={() => void onPostingAction("reconcile", posting.id)}>Reconcile</Button> : null}
                      {posting.reconciliation_state === "reconciled" ? <span className="inline-flex items-center gap-1 font-medium text-tag-sea-glass-foreground"><Check aria-hidden="true" className="size-3.5" /> Locked</span> : null}
                    </span>
                  ) : null}
                </div>
              </div>
            );
          })}
        </div>
        {transaction.reversal_of_id ? <p className="rounded-lg border border-border/70 bg-background px-3 py-2 text-sm text-muted-foreground">This is a reversal entry for an earlier transaction.</p> : null}
      </div>
      <DrawerFooter className="flex-row justify-between border-t border-border/70 bg-card px-6 py-4 sm:px-8">
        <div className="flex gap-2">
          {canEdit ? <Button type="button" variant="outline" onClick={onEdit}><Pencil aria-hidden="true" />Edit</Button> : null}
          {canReverse ? <Button type="button" variant="destructive" disabled={pending} onClick={() => { if (window.confirm("Reverse this reconciled transaction? The original entry will be voided.")) void onReverse(); }}><RotateCcw aria-hidden="true" />Reverse</Button> : null}
        </div>
        {!guidedShapeSupported ? <span className="self-center text-xs text-muted-foreground">Read-only detail for a split or externally-created transaction.</span> : null}
        {guidedShapeSupported && !canEdit && transaction.state === "posted" && !canReverse ? <span className="self-center text-xs text-muted-foreground">Reconcile an account posting to enable reversal.</span> : null}
      </DrawerFooter>
    </div>
  );
}

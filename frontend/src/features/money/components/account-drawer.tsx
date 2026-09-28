"use client";

import { useEffect, useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import {
  Drawer,
  DrawerClose,
  DrawerContent,
  DrawerDescription,
  DrawerFooter,
  DrawerHeader,
  DrawerTitle,
} from "@/components/ui/drawer";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  moneyAccountTypeOptions,
  moneyCurrencyCodes,
  type MoneyAccount,
  type MoneyAccountCreateInput,
  type MoneyAccountType,
  type MoneyAccountUpdateInput,
} from "../api";
import { accountLabel, accountTypeLabel, describeMoneyError, formatMoney } from "../utils";

type AccountDrawerProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  account: MoneyAccount | null;
  pending?: boolean;
  onSave: (
    accountId: string | null,
    payload: MoneyAccountCreateInput | MoneyAccountUpdateInput,
  ) => Promise<void>;
};

const amountPattern = /^-?(?:0|[1-9]\d*)(?:\.\d+)?$/;

export function AccountDrawer({
  open,
  onOpenChange,
  account,
  pending = false,
  onSave,
}: AccountDrawerProps) {
  const [name, setName] = useState("");
  const [accountType, setAccountType] = useState<MoneyAccountType>("checking");
  const [institutionName, setInstitutionName] = useState("");
  const [lastFour, setLastFour] = useState("");
  const [currencyCode, setCurrencyCode] = useState("PHP");
  const [openingBalance, setOpeningBalance] = useState("0");
  const [error, setError] = useState<string>();

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    queueMicrotask(() => {
      if (cancelled) return;
      setError(undefined);
      setName(account?.name ?? "");
      setAccountType(account?.account_type ?? "checking");
      setInstitutionName(account?.institution_name ?? "");
      setLastFour(account?.last_four ?? "");
      setCurrencyCode(account?.currency_code ?? "PHP");
      setOpeningBalance(account?.opening_balance ?? "0");
    });
    return () => {
      cancelled = true;
    };
  }, [account, open]);

  const editing = Boolean(account);
  const title = editing ? "Edit account" : "Add account";
  const description = editing
    ? "Update the account details you use to recognize it in your ledger."
    : "Add an account so balances and transactions have a place to live.";

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(undefined);

    const normalizedName = name.trim();
    const normalizedInstitution = institutionName.trim();
    const normalizedLastFour = lastFour.trim();
    const normalizedOpeningBalance = openingBalance.trim();

    if (!normalizedName) {
      setError("Enter an account name before saving.");
      return;
    }
    if (normalizedLastFour && !/^\d{4}$/.test(normalizedLastFour)) {
      setError("The last four digits must contain exactly four numbers.");
      return;
    }
    if (!editing && !amountPattern.test(normalizedOpeningBalance)) {
      setError("Enter a valid opening balance, such as 0 or -125.50.");
      return;
    }

    const payload: MoneyAccountCreateInput | MoneyAccountUpdateInput = editing
      ? {
          name: normalizedName,
          institution_name: normalizedInstitution || null,
          last_four: normalizedLastFour || null,
        }
      : {
          name: normalizedName,
          account_type: accountType,
          institution_name: normalizedInstitution || null,
          last_four: normalizedLastFour || null,
          currency_code: currencyCode,
          opening_balance: normalizedOpeningBalance,
        };

    try {
      await onSave(account?.id ?? null, payload);
      onOpenChange(false);
    } catch (reason) {
      setError(describeMoneyError(reason));
    }
  }

  return (
    <Drawer open={open} onOpenChange={onOpenChange} swipeDirection="right">
      <DrawerContent className="min-h-[100svh] w-full max-w-xl gap-0 border-border bg-card p-0 text-card-foreground shadow-none sm:max-w-xl">
        <DrawerHeader className="border-b border-border/70 px-6 py-6 text-left sm:px-8">
          <div className="flex items-start justify-between gap-4">
            <div>
              <DrawerTitle className="text-xl font-semibold tracking-[-0.03em]">{title}</DrawerTitle>
              <DrawerDescription className="mt-2 max-w-md text-sm leading-6">{description}</DrawerDescription>
            </div>
            <DrawerClose render={<Button variant="ghost" size="icon-sm" aria-label="Close account drawer" />}>
              <span aria-hidden="true">×</span>
            </DrawerClose>
          </div>
        </DrawerHeader>

        <form onSubmit={handleSubmit} className="flex min-h-0 flex-1 flex-col">
          <div className="min-h-0 flex-1 space-y-6 overflow-y-auto px-6 py-6 sm:px-8">
            {error ? (
              <div role="alert" className="rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm leading-5 text-destructive">
                {error}
              </div>
            ) : null}

            <div className="grid gap-4 sm:grid-cols-2">
              <div className="flex flex-col gap-2 text-sm sm:col-span-2">
                <Label htmlFor="account-name">Account name</Label>
                <Input
                  id="account-name"
                  className="h-11"
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  placeholder="e.g. Main checking"
                  maxLength={200}
                  required
                  disabled={pending}
                  autoFocus
                />
              </div>

              <div className="flex flex-col gap-2 text-sm">
                <Label htmlFor="account-type">Account type</Label>
                <Select
                  value={accountType}
                  onValueChange={(value) => value && setAccountType(value as MoneyAccountType)}
                  disabled={editing || pending}
                >
                  <SelectTrigger id="account-type" className="h-11 w-full bg-background">
                    <SelectValue>{accountTypeLabel(accountType)}</SelectValue>
                  </SelectTrigger>
                  <SelectContent>
                    {moneyAccountTypeOptions.map((option) => (
                      <SelectItem key={option} value={option}>{accountTypeLabel(option)}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {editing ? <p className="text-xs leading-5 text-muted-foreground">Type is fixed after creation.</p> : null}
              </div>

              <div className="flex flex-col gap-2 text-sm">
                <Label htmlFor="account-currency">Currency</Label>
                <Select value={currencyCode} onValueChange={(value) => value && setCurrencyCode(value)} disabled={editing || pending}>
                  <SelectTrigger id="account-currency" className="h-11 w-full bg-background">
                    <SelectValue>{currencyCode}</SelectValue>
                  </SelectTrigger>
                  <SelectContent>
                    {moneyCurrencyCodes.map((code) => <SelectItem key={code} value={code}>{code}</SelectItem>)}
                  </SelectContent>
                </Select>
                {editing ? <p className="text-xs leading-5 text-muted-foreground">Currency is fixed after creation.</p> : null}
              </div>

              <div className="flex flex-col gap-2 text-sm sm:col-span-2">
                <Label htmlFor="account-institution">Institution <span className="text-muted-foreground">(optional)</span></Label>
                <Input
                  id="account-institution"
                  className="h-11"
                  value={institutionName}
                  onChange={(event) => setInstitutionName(event.target.value)}
                  placeholder="e.g. Local bank"
                  maxLength={200}
                  disabled={pending}
                />
              </div>

              <div className="flex flex-col gap-2 text-sm">
                <Label htmlFor="account-last-four">Last four digits <span className="text-muted-foreground">(optional)</span></Label>
                <Input
                  id="account-last-four"
                  className="h-11"
                  value={lastFour}
                  onChange={(event) => setLastFour(event.target.value.replace(/\D/g, "").slice(0, 4))}
                  placeholder="1234"
                  inputMode="numeric"
                  maxLength={4}
                  disabled={pending}
                />
              </div>

              {!editing ? (
                <div className="flex flex-col gap-2 text-sm">
                  <Label htmlFor="account-opening-balance">Opening balance · {currencyCode}</Label>
                  <Input
                    id="account-opening-balance"
                    className="h-11"
                    value={openingBalance}
                    onChange={(event) => setOpeningBalance(event.target.value)}
                    placeholder="0.00"
                    inputMode="decimal"
                    disabled={pending}
                  />
                </div>
              ) : null}
            </div>

            {editing && account ? (
              <dl className="grid gap-3 rounded-lg border border-border/70 bg-background/60 p-4 text-sm sm:grid-cols-2">
                <div>
                  <dt className="text-xs text-muted-foreground">Current balance</dt>
                  <dd className="mt-1 font-mono font-medium">{formatMoney(account.balance, account.currency_code)}</dd>
                </div>
                <div>
                  <dt className="text-xs text-muted-foreground">Opening balance</dt>
                  <dd className="mt-1 font-mono font-medium">{formatMoney(account.opening_balance, account.currency_code)}</dd>
                </div>
                <div>
                  <dt className="text-xs text-muted-foreground">Account</dt>
                  <dd className="mt-1">{accountLabel(account)}</dd>
                </div>
                <div>
                  <dt className="text-xs text-muted-foreground">Balance changes</dt>
                  <dd className="mt-1 text-muted-foreground">Recorded through transactions</dd>
                </div>
              </dl>
            ) : null}
          </div>

          <DrawerFooter className="border-t border-border/70 bg-card px-6 py-4 sm:flex-row sm:justify-end sm:px-8">
            <DrawerClose render={<Button type="button" variant="outline" size="lg" disabled={pending} />}>Cancel</DrawerClose>
            <Button type="submit" size="lg" disabled={pending || !name.trim()}>
              {pending ? "Saving…" : editing ? "Save changes" : "Create account"}
            </Button>
          </DrawerFooter>
        </form>
      </DrawerContent>
    </Drawer>
  );
}

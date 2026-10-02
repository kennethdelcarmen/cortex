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
import { FieldError } from "@/components/ui/field";
import { fieldDescribedBy, FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
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

type AccountErrorField =
  | "name"
  | "lastFour"
  | "openingBalance"
  | "creditLimit"
  | "statementCloseDay"
  | "paymentDueDay";

type AccountFieldErrors = Partial<Record<AccountErrorField, string>>;

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
  const [creditLimit, setCreditLimit] = useState("");
  const [statementCloseDay, setStatementCloseDay] = useState("");
  const [paymentDueDay, setPaymentDueDay] = useState("");
  const [formError, setFormError] = useState<string>();
  const [fieldErrors, setFieldErrors] = useState<AccountFieldErrors>({});

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    queueMicrotask(() => {
      if (cancelled) return;
      setFormError(undefined);
      setFieldErrors({});
      setName(account?.name ?? "");
      setAccountType(account?.account_type ?? "checking");
      setInstitutionName(account?.institution_name ?? "");
      setLastFour(account?.last_four ?? "");
      setCurrencyCode(account?.currency_code ?? "PHP");
      setOpeningBalance(account?.opening_balance ?? "0");
      setCreditLimit(account?.credit_limit ?? "");
      setStatementCloseDay(account?.statement_close_day?.toString() ?? "");
      setPaymentDueDay(account?.payment_due_day?.toString() ?? "");
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
    setFormError(undefined);
    setFieldErrors({});

    const normalizedName = name.trim();
    const normalizedInstitution = institutionName.trim();
    const normalizedLastFour = lastFour.trim();
    const normalizedOpeningBalance = openingBalance.trim();
    const normalizedCreditLimit = creditLimit.trim();
    const normalizedStatementCloseDay = statementCloseDay.trim();
    const normalizedPaymentDueDay = paymentDueDay.trim();

    const nextFieldErrors: AccountFieldErrors = {};
    if (!normalizedName) nextFieldErrors.name = "Enter an account name before saving.";
    if (normalizedLastFour && !/^\d{4}$/.test(normalizedLastFour)) {
      nextFieldErrors.lastFour = "The last four digits must contain exactly four numbers.";
    }
    if (!editing && !amountPattern.test(normalizedOpeningBalance)) {
      nextFieldErrors.openingBalance = "Enter a valid opening amount, such as 0 or 125.50.";
    }
    if (accountType === "credit_card") {
      if (!amountPattern.test(normalizedCreditLimit) || Number(normalizedCreditLimit) <= 0) {
        nextFieldErrors.creditLimit = "Enter a positive credit limit for this card.";
      }
      if (!/^(?:[1-9]|[12]\d|3[01])$/.test(normalizedStatementCloseDay)) {
        nextFieldErrors.statementCloseDay = "Statement closing day must be between 1 and 31.";
      }
      if (!/^(?:[1-9]|[12]\d|3[01])$/.test(normalizedPaymentDueDay)) {
        nextFieldErrors.paymentDueDay = "Payment due day must be between 1 and 31.";
      }
    }

    if (Object.keys(nextFieldErrors).length) {
      setFieldErrors(nextFieldErrors);
      const firstInvalidField = [
        "name",
        "lastFour",
        "openingBalance",
        "creditLimit",
        "statementCloseDay",
        "paymentDueDay",
      ].find((field) => nextFieldErrors[field as AccountErrorField]);
      if (firstInvalidField) {
        window.requestAnimationFrame(() => document.getElementById(`account-${firstInvalidField.replace(/[A-Z]/g, (letter) => `-${letter.toLowerCase()}`)}`)?.focus());
      }
      return;
    }

    const payload: MoneyAccountCreateInput | MoneyAccountUpdateInput = editing
      ? {
          name: normalizedName,
          institution_name: normalizedInstitution || null,
          last_four: normalizedLastFour || null,
          ...(accountType === "credit_card" ? {
            credit_limit: normalizedCreditLimit,
            statement_close_day: Number(normalizedStatementCloseDay),
            payment_due_day: Number(normalizedPaymentDueDay),
          } : {}),
        }
      : {
          name: normalizedName,
          account_type: accountType,
          institution_name: normalizedInstitution || null,
          last_four: normalizedLastFour || null,
          currency_code: currencyCode,
          opening_balance: normalizedOpeningBalance,
          ...(accountType === "credit_card" ? {
            credit_limit: normalizedCreditLimit,
            statement_close_day: Number(normalizedStatementCloseDay),
            payment_due_day: Number(normalizedPaymentDueDay),
          } : {}),
        };

    try {
      await onSave(account?.id ?? null, payload);
      onOpenChange(false);
    } catch (reason) {
      setFormError(describeMoneyError(reason));
    }
  }

  function clearFieldError(field: AccountErrorField) {
    setFormError(undefined);
    setFieldErrors((current) => {
      if (!current[field]) return current;
      const next = { ...current };
      delete next[field];
      return next;
    });
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

        <form onSubmit={handleSubmit} noValidate className="flex min-h-0 flex-1 flex-col" aria-describedby={formError ? "account-form-error" : undefined}>
          <div className="min-h-0 flex-1 space-y-6 overflow-y-auto px-6 py-6 sm:px-8">
            {formError ? (
              <FieldError id="account-form-error" aria-live="polite" className="rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 leading-5">
                {formError}
              </FieldError>
            ) : null}

            <div className="grid gap-4 sm:grid-cols-2">
              <FormField id="account-name" label="Account name" error={fieldErrors.name} className="sm:col-span-2">
                <Input
                  id="account-name"
                  className="h-11"
                  value={name}
                  onChange={(event) => { setName(event.target.value); clearFieldError("name"); }}
                  placeholder="e.g. Main checking"
                  maxLength={200}
                  required
                  disabled={pending}
                  autoFocus
                  aria-invalid={Boolean(fieldErrors.name) || undefined}
                  aria-describedby={fieldDescribedBy("account-name", undefined, fieldErrors.name)}
                />
              </FormField>

              <FormField id="account-type" label="Account type">
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
              </FormField>

              <FormField id="account-currency" label="Currency">
                <Select value={currencyCode} onValueChange={(value) => value && setCurrencyCode(value)} disabled={editing || pending}>
                  <SelectTrigger id="account-currency" className="h-11 w-full bg-background">
                    <SelectValue>{currencyCode}</SelectValue>
                  </SelectTrigger>
                  <SelectContent>
                    {moneyCurrencyCodes.map((code) => <SelectItem key={code} value={code}>{code}</SelectItem>)}
                  </SelectContent>
                </Select>
                {editing ? <p className="text-xs leading-5 text-muted-foreground">Currency is fixed after creation.</p> : null}
              </FormField>

              <FormField id="account-institution" label={<>Institution <span className="text-muted-foreground">(optional)</span></>} className="sm:col-span-2">
                <Input
                  id="account-institution"
                  className="h-11"
                  value={institutionName}
                  onChange={(event) => setInstitutionName(event.target.value)}
                  placeholder="e.g. Local bank"
                  maxLength={200}
                  disabled={pending}
                />
              </FormField>

              <FormField id="account-last-four" label={<>Last four digits <span className="text-muted-foreground">(optional)</span></>} error={fieldErrors.lastFour}>
                <Input
                  id="account-last-four"
                  className="h-11"
                  value={lastFour}
                  onChange={(event) => { setLastFour(event.target.value.replace(/\D/g, "").slice(0, 4)); clearFieldError("lastFour"); }}
                  placeholder="1234"
                  inputMode="numeric"
                  maxLength={4}
                  disabled={pending}
                  aria-invalid={Boolean(fieldErrors.lastFour) || undefined}
                  aria-describedby={fieldDescribedBy("account-last-four", undefined, fieldErrors.lastFour)}
                />
              </FormField>

              {!editing && accountType !== "credit_card" ? (
                <FormField id="account-opening-balance" label={`Opening balance · ${currencyCode}`} error={fieldErrors.openingBalance}>
                  <Input
                    id="account-opening-balance"
                    className="h-11"
                    value={openingBalance}
                    onChange={(event) => { setOpeningBalance(event.target.value); clearFieldError("openingBalance"); }}
                    placeholder="0.00"
                    inputMode="decimal"
                    disabled={pending}
                    aria-invalid={Boolean(fieldErrors.openingBalance) || undefined}
                    aria-describedby={fieldDescribedBy("account-opening-balance", undefined, fieldErrors.openingBalance)}
                  />
                </FormField>
              ) : null}

              {accountType === "credit_card" ? (
                <>
                  <FormField id="account-credit-limit" label={`Credit limit · ${currencyCode}`} error={fieldErrors.creditLimit}>
                    <Input
                      id="account-credit-limit"
                      className="h-11"
                      value={creditLimit}
                      onChange={(event) => { setCreditLimit(event.target.value); clearFieldError("creditLimit"); }}
                      placeholder="100000.00"
                      inputMode="decimal"
                      disabled={pending}
                      aria-invalid={Boolean(fieldErrors.creditLimit) || undefined}
                      aria-describedby={fieldDescribedBy("account-credit-limit", undefined, fieldErrors.creditLimit)}
                    />
                  </FormField>
                  {!editing ? (
                    <FormField id="account-opening-balance" label={`Amount owed · ${currencyCode}`} error={fieldErrors.openingBalance}>
                      <Input
                        id="account-opening-balance"
                        className="h-11"
                        value={openingBalance}
                        onChange={(event) => { setOpeningBalance(event.target.value); clearFieldError("openingBalance"); }}
                        placeholder="0.00"
                        inputMode="decimal"
                        disabled={pending}
                        aria-invalid={Boolean(fieldErrors.openingBalance) || undefined}
                        aria-describedby={fieldDescribedBy("account-opening-balance", undefined, fieldErrors.openingBalance)}
                      />
                    </FormField>
                  ) : null}
                  <FormField id="account-statement-close-day" label="Statement closes on day" error={fieldErrors.statementCloseDay}>
                    <Input
                      id="account-statement-close-day"
                      className="h-11"
                      value={statementCloseDay}
                      onChange={(event) => { setStatementCloseDay(event.target.value.replace(/\D/g, "").slice(0, 2)); clearFieldError("statementCloseDay"); }}
                      placeholder="15"
                      inputMode="numeric"
                      maxLength={2}
                      disabled={pending}
                      aria-invalid={Boolean(fieldErrors.statementCloseDay) || undefined}
                      aria-describedby={fieldDescribedBy("account-statement-close-day", undefined, fieldErrors.statementCloseDay)}
                    />
                  </FormField>
                  <FormField id="account-payment-due-day" label="Payment due on day" error={fieldErrors.paymentDueDay}>
                    <Input
                      id="account-payment-due-day"
                      className="h-11"
                      value={paymentDueDay}
                      onChange={(event) => { setPaymentDueDay(event.target.value.replace(/\D/g, "").slice(0, 2)); clearFieldError("paymentDueDay"); }}
                      placeholder="5"
                      inputMode="numeric"
                      maxLength={2}
                      disabled={pending}
                      aria-invalid={Boolean(fieldErrors.paymentDueDay) || undefined}
                      aria-describedby={fieldDescribedBy("account-payment-due-day", undefined, fieldErrors.paymentDueDay)}
                    />
                  </FormField>
                </>
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
                {account.account_type === "credit_card" ? (
                  <>
                    <div>
                      <dt className="text-xs text-muted-foreground">Amount owed</dt>
                      <dd className="mt-1 font-mono font-medium">{account.amount_owed ? formatMoney(account.amount_owed, account.currency_code) : "Not configured"}</dd>
                    </div>
                    <div>
                      <dt className="text-xs text-muted-foreground">Available credit</dt>
                      <dd className="mt-1 font-mono font-medium">{account.available_credit ? formatMoney(account.available_credit, account.currency_code) : "Not configured"}</dd>
                    </div>
                  </>
                ) : null}
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
            <Button type="submit" size="lg" disabled={pending}>
              {pending ? "Saving…" : editing ? "Save changes" : "Create account"}
            </Button>
          </DrawerFooter>
        </form>
      </DrawerContent>
    </Drawer>
  );
}

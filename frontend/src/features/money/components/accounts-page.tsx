"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Building2, Landmark, LoaderCircle, RotateCcw, Search, Trash2, WalletCards } from "lucide-react";
import { useEffect, useState } from "react";
import { useFeedback } from "@/components/feedback";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useCurrentUser } from "@/features/auth/hooks";
import { WorkspaceRouteGuard, WorkspaceShell } from "@/features/workspace/components/workspace-shell";
import { cn } from "@/lib/utils";
import {
  archiveMoneyAccount,
  createMoneyAccount,
  restoreMoneyAccount,
  updateMoneyAccount,
  type MoneyAccount,
  type MoneyAccountCreateInput,
  type MoneyAccountUpdateInput,
} from "../api";
import { invalidateMoneyQueries, useMoneyAccounts } from "../hooks";
import { accountLabel, accountTypeLabel, describeMoneyError, formatMoney } from "../utils";
import { AccountDrawer } from "./account-drawer";

type AccountView = "active" | "archived";

function AccountEmptyState({
  view,
  search,
  onCreate,
}: {
  view: AccountView;
  search: string;
  onCreate: () => void;
}) {
  if (search) {
    return (
      <div className="flex flex-col items-center px-6 py-14 text-center">
        <Search aria-hidden="true" className="size-5 text-primary-strong" />
        <h3 className="mt-3 text-sm font-medium">No accounts match that search.</h3>
        <p className="mt-1 max-w-sm text-sm leading-6 text-muted-foreground">Try a different name or institution.</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center px-6 py-14 text-center">
      <Landmark aria-hidden="true" className="size-5 text-primary-strong" />
      <h3 className="mt-3 text-sm font-medium">
        {view === "active" ? "No accounts yet." : "No archived accounts."}
      </h3>
      <p className="mt-1 max-w-sm text-sm leading-6 text-muted-foreground">
        {view === "active"
          ? "Create an account before recording a transaction."
          : "Archived accounts will stay here until you restore them."}
      </p>
      {view === "active" ? (
        <Button type="button" className="mt-5" onClick={onCreate}>
          Add your first account
        </Button>
      ) : null}
    </div>
  );
}

function AccountRow({
  account,
  archived,
  pending,
  onEdit,
  onArchive,
  onRestore,
}: {
  account: MoneyAccount;
  archived: boolean;
  pending: boolean;
  onEdit: () => void;
  onArchive: () => void;
  onRestore: () => void;
}) {
  const Icon = account.account_type === "cash" ? WalletCards : Building2;
  const summary = (
    <>
      <span className="flex size-10 shrink-0 items-center justify-center rounded-lg border border-border bg-background text-primary-strong">
        <Icon aria-hidden="true" className="size-4" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex flex-wrap items-center gap-2">
          <span className="truncate text-sm font-medium group-hover:text-primary-strong">{accountLabel(account)}</span>
          {archived ? <Badge variant="outline" className="font-mono text-[0.58rem] uppercase tracking-[0.08em]">Archived</Badge> : null}
        </span>
        <span className="mt-1 block truncate text-xs text-muted-foreground">
          {accountTypeLabel(account.account_type)} · {account.institution_name ?? "Local"}
        </span>
      </span>
      <span className="shrink-0 text-right">
        <span className={cn("block font-mono text-sm font-medium", archived && "text-muted-foreground")}>
          {formatMoney(account.balance, account.currency_code)}
        </span>
        <span className="mt-1 block font-mono text-[0.62rem] uppercase tracking-[0.08em] text-muted-foreground">
          {account.currency_code}
        </span>
      </span>
    </>
  );

  return (
    <li className="border-t border-border/70 first:border-t-0">
      <div className="flex flex-col gap-4 px-4 py-4 sm:flex-row sm:items-center sm:px-5">
        {archived ? (
          <div className="flex min-w-0 flex-1 items-center gap-3 rounded-lg text-left">{summary}</div>
        ) : (
          <button
            type="button"
            onClick={onEdit}
            className="group flex min-w-0 flex-1 items-center gap-3 rounded-lg text-left outline-none focus-visible:ring-3 focus-visible:ring-ring/40"
            aria-label={`Edit ${accountLabel(account)}`}
          >
            {summary}
          </button>
        )}

        <div className="flex shrink-0 gap-2 pl-[3.25rem] sm:pl-0" aria-label={`${accountLabel(account)} actions`}>
          {archived ? (
            <Button type="button" variant="outline" size="sm" onClick={onRestore} disabled={pending}>
              {pending ? <LoaderCircle aria-hidden="true" className="animate-spin" /> : <RotateCcw aria-hidden="true" />}
              Restore
            </Button>
          ) : (
            <>
              <Button type="button" variant="outline" size="sm" onClick={onEdit} disabled={pending}>
                Edit
              </Button>
              <Button type="button" variant="outline" size="sm" onClick={onArchive} disabled={pending}>
                <Trash2 aria-hidden="true" />
                Archive
              </Button>
            </>
          )}
        </div>
      </div>
    </li>
  );
}

function AccountsWorkspace({ email }: { email: string }) {
  const queryClient = useQueryClient();
  const feedback = useFeedback();
  const [view, setView] = useState<AccountView>("active");
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editingAccount, setEditingAccount] = useState<MoneyAccount | null>(null);
  const [archiveTarget, setArchiveTarget] = useState<MoneyAccount | null>(null);
  const accountsQuery = useMoneyAccounts({ archivedOnly: view === "archived", search });
  const accounts = accountsQuery.data?.pages.flatMap((page) => page.items) ?? [];

  useEffect(() => {
    const timeout = window.setTimeout(() => setSearch(searchInput.trim()), 300);
    return () => window.clearTimeout(timeout);
  }, [searchInput]);

  const saveMutation = useMutation({
    mutationFn: async ({
      accountId,
      payload,
    }: {
      accountId: string | null;
      payload: MoneyAccountCreateInput | MoneyAccountUpdateInput;
    }) => {
      if (accountId) return updateMoneyAccount(accountId, payload as MoneyAccountUpdateInput);
      return createMoneyAccount(payload as MoneyAccountCreateInput);
    },
    onSuccess: async (account, variables) => {
      await invalidateMoneyQueries(queryClient);
      feedback.success({ title: variables.accountId ? `${account.name} updated.` : `${account.name} created.` });
    },
  });

  const archiveMutation = useMutation({
    mutationFn: archiveMoneyAccount,
    onSuccess: async (account) => {
      await invalidateMoneyQueries(queryClient);
      setArchiveTarget(null);
      feedback.success({ title: `${account.name} archived.` });
    },
    onError: (reason) => feedback.error({ title: "Account could not be archived.", description: describeMoneyError(reason) }),
  });

  const restoreMutation = useMutation({
    mutationFn: restoreMoneyAccount,
    onSuccess: async (account) => {
      await invalidateMoneyQueries(queryClient);
      feedback.success({ title: `${account.name} restored.` });
    },
    onError: (reason) => feedback.error({ title: "Account could not be restored.", description: describeMoneyError(reason) }),
  });

  const mutationPending = saveMutation.isPending || archiveMutation.isPending || restoreMutation.isPending;

  function openCreate() {
    setEditingAccount(null);
    setDrawerOpen(true);
  }

  function openEdit(account: MoneyAccount) {
    setEditingAccount(account);
    setDrawerOpen(true);
  }

  async function saveAccount(
    accountId: string | null,
    payload: MoneyAccountCreateInput | MoneyAccountUpdateInput,
  ) {
    await saveMutation.mutateAsync({ accountId, payload });
  }

  function changeView(nextView: AccountView) {
    setView(nextView);
    setSearchInput("");
    setSearch("");
  }

  return (
    <WorkspaceShell email={email}>
      <div className="max-w-5xl">
        <header className="flex flex-col gap-5 border-b border-border/70 pb-6 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="font-mono text-[0.66rem] uppercase tracking-[0.18em] text-muted-foreground">Money · Accounts</p>
            <h1 className="mt-2 text-3xl font-semibold tracking-[-0.035em]">Where your money lives.</h1>
            <p className="mt-3 max-w-xl text-sm leading-6 text-muted-foreground">
              Keep account names and balances recognizable, while transactions continue to carry the movement.
            </p>
          </div>
          <Button type="button" size="lg" onClick={openCreate}>
            Add account
          </Button>
        </header>

        {accountsQuery.isError ? (
          <div role="alert" className="mt-5 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm">
            <span className="text-destructive">Accounts could not load. {describeMoneyError(accountsQuery.error)}</span>
            <Button type="button" variant="outline" size="sm" onClick={() => void accountsQuery.refetch()}>Try again</Button>
          </div>
        ) : null}

        <section aria-labelledby="accounts-list-title" className="mt-8">
          <div className="mb-4 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <p className="font-mono text-[0.66rem] uppercase tracking-[0.18em] text-muted-foreground">Account catalog</p>
              <div className="mt-2 flex flex-wrap items-center gap-3">
                <h2 id="accounts-list-title" className="text-xl font-medium tracking-[-0.025em] sm:text-2xl">
                  {view === "active" ? "Active accounts" : "Archived accounts"}
                </h2>
                <Badge variant="outline" className="font-mono text-[0.62rem] uppercase tracking-[0.1em]">
                  {accountsQuery.isPending ? "…" : `${accounts.length} loaded`}
                </Badge>
              </div>
            </div>

            <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
              <div className="relative min-w-0 sm:w-64">
                <label htmlFor="account-search" className="sr-only">Search accounts</label>
                <Search aria-hidden="true" className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  id="account-search"
                  className="h-10 bg-background pl-9"
                  value={searchInput}
                  onChange={(event) => setSearchInput(event.target.value)}
                  placeholder="Search accounts"
                />
              </div>
              <div className="flex gap-1 rounded-lg border border-border/80 bg-background p-1" role="tablist" aria-label="Account status">
                {(["active", "archived"] as AccountView[]).map((item) => (
                  <Button
                    key={item}
                    type="button"
                    role="tab"
                    aria-selected={view === item}
                    aria-controls="accounts-panel"
                    variant={view === item ? "secondary" : "ghost"}
                    size="sm"
                    onClick={() => changeView(item)}
                    className="capitalize"
                  >
                    {item}
                  </Button>
                ))}
              </div>
            </div>
          </div>

          <Card id="accounts-panel" role="tabpanel" className="overflow-hidden rounded-xl border-border/80 p-0 shadow-none">
            {accountsQuery.isPending ? (
              <div className="space-y-3 p-5" aria-label="Loading accounts">
                {["one", "two", "three"].map((item) => <div key={item} className="h-16 animate-pulse rounded-lg bg-muted" />)}
              </div>
            ) : accounts.length ? (
              <>
                <ul aria-label={`${view} accounts`}>
                  {accounts.map((account) => (
                    <AccountRow
                      key={account.id}
                      account={account}
                      archived={view === "archived"}
                      pending={mutationPending}
                      onEdit={() => openEdit(account)}
                      onArchive={() => setArchiveTarget(account)}
                      onRestore={() => restoreMutation.mutate(account.id)}
                    />
                  ))}
                </ul>
                {accountsQuery.hasNextPage ? (
                  <div className="border-t border-border/70 p-4 text-center">
                    <Button type="button" variant="outline" onClick={() => void accountsQuery.fetchNextPage()} disabled={accountsQuery.isFetchingNextPage}>
                      {accountsQuery.isFetchingNextPage ? <LoaderCircle aria-hidden="true" className="animate-spin" /> : null}
                      {accountsQuery.isFetchingNextPage ? "Loading more…" : "Load more"}
                    </Button>
                  </div>
                ) : null}
              </>
            ) : (
              <AccountEmptyState view={view} search={search} onCreate={openCreate} />
            )}
          </Card>
        </section>
      </div>

      <AccountDrawer
        open={drawerOpen}
        account={editingAccount}
        pending={saveMutation.isPending}
        onOpenChange={(open) => {
          setDrawerOpen(open);
          if (!open) setEditingAccount(null);
        }}
        onSave={saveAccount}
      />

      <Dialog open={Boolean(archiveTarget)} onOpenChange={(open) => { if (!open) setArchiveTarget(null); }}>
        <DialogContent className="w-[min(28rem,calc(100vw-2rem))] rounded-xl border-border bg-card p-6 text-card-foreground shadow-none sm:max-w-none sm:p-7">
          <DialogHeader>
            <DialogTitle className="text-xl tracking-[-0.03em]">Archive account?</DialogTitle>
            <DialogDescription className="mt-2 leading-6">
              {archiveTarget ? `${accountLabel(archiveTarget)} will leave your active account list. Its transactions and balance remain intact, and you can restore it later.` : ""}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="mt-7 flex-row justify-end gap-2 border-0 bg-transparent p-0">
            <DialogClose render={<Button type="button" variant="outline" size="lg" disabled={archiveMutation.isPending} />}>Cancel</DialogClose>
            <Button
              type="button"
              variant="destructive"
              size="lg"
              disabled={!archiveTarget || archiveMutation.isPending}
              onClick={() => { if (archiveTarget) archiveMutation.mutate(archiveTarget.id); }}
            >
              {archiveMutation.isPending ? "Archiving…" : "Archive account"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </WorkspaceShell>
  );
}

export function AccountsRoute() {
  const currentUser = useCurrentUser();
  return <WorkspaceRouteGuard>{currentUser.data ? <AccountsWorkspace email={currentUser.data.email} /> : null}</WorkspaceRouteGuard>;
}

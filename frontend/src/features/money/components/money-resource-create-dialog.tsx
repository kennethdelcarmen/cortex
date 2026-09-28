"use client";

import type { FormEvent } from "react";
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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export type MoneyResourceKind = "payee" | "category";

type MoneyResourceCreateDialogProps = {
  kind: MoneyResourceKind;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  name: string;
  onNameChange: (name: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  error?: string;
  pending?: boolean;
};

function resourceLabel(kind: MoneyResourceKind) {
  return kind === "payee" ? "payee" : "category";
}

export function MoneyResourceCreateDialog({
  kind,
  open,
  onOpenChange,
  name,
  onNameChange,
  onSubmit,
  error,
  pending = false,
}: MoneyResourceCreateDialogProps) {
  const label = resourceLabel(kind);
  const fieldId = `money-create-${kind}-name`;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="w-[min(28rem,calc(100vw-2rem))] rounded-xl border-border bg-card p-6 text-card-foreground shadow-none sm:max-w-none sm:p-7">
        <form onSubmit={onSubmit}>
          <DialogHeader>
            <DialogTitle className="text-xl tracking-[-0.03em]">Create {label}</DialogTitle>
            <DialogDescription className="mt-2 leading-6">
              Add a {label} without leaving this transaction.
            </DialogDescription>
          </DialogHeader>

          <div className="mt-6 space-y-2">
            <Label htmlFor={fieldId}>Name</Label>
            <Input
              id={fieldId}
              className="h-11"
              value={name}
              onChange={(event) => onNameChange(event.target.value)}
              placeholder={`Enter ${label} name`}
              autoFocus
              disabled={pending}
              aria-invalid={Boolean(error)}
            />
            {error ? <p role="alert" className="text-sm leading-5 text-destructive">{error}</p> : null}
          </div>

          <DialogFooter className="mt-7 -mx-6 -mb-6 rounded-b-xl border-t border-border/70 bg-card px-6 py-4 sm:-mx-7 sm:-mb-7 sm:px-7">
            <DialogClose type="button" render={<Button variant="outline" size="lg" disabled={pending} />}>
              Cancel
            </DialogClose>
            <Button type="submit" size="lg" disabled={pending || !name.trim()}>
              {pending ? "Creating…" : `Create ${label}`}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

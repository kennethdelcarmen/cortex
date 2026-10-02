"use client";

import { ArrowDownLeft, ArrowUpRight, Plus, Trash2 } from "lucide-react";
import type { Dispatch, SetStateAction } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { SelectItem, SelectSeparator } from "@/components/ui/select";
import { cn } from "@/lib/utils";
import type { MoneyCategory } from "../api";
import { categoriesForKind } from "../hooks";
import {
  formatMoney,
  formatMinorUnits,
  formatSignedMoney,
  parseMoneyMinorUnits,
  type SplitDirection,
} from "../utils";
import { MoneySelectField } from "./money-select-field";

export type SplitTransactionRow = {
  id: string;
  categoryId: string;
  label: string;
  amount: string;
};

type SplitTransactionEditorProps = {
  direction: SplitDirection;
  onDirectionChange: (direction: SplitDirection) => void;
  totalAmount: string;
  onTotalAmountChange: (value: string) => void;
  rows: SplitTransactionRow[];
  onRowsChange: Dispatch<SetStateAction<SplitTransactionRow[]>>;
  categories: MoneyCategory[];
  currencyCode: string;
  resourceLabels: Record<string, string>;
  onCreateCategory: (rowIndex: number) => void;
  disabled?: boolean;
};

function newRow(index: number): SplitTransactionRow {
  return { id: `split-row-${Date.now()}-${index}`, categoryId: "", label: "", amount: "" };
}

export function createSplitRows(count = 2) {
  return Array.from({ length: count }, (_, index) => newRow(index));
}

export function SplitTransactionEditor({
  direction,
  onDirectionChange,
  totalAmount,
  onTotalAmountChange,
  rows,
  onRowsChange,
  categories,
  currencyCode,
  resourceLabels,
  onCreateCategory,
  disabled = false,
}: SplitTransactionEditorProps) {
  const availableCategories = categoriesForKind(categories, direction);
  const totalMinor = parseMoneyMinorUnits(totalAmount, currencyCode);
  const allocatedMinor = rows.reduce((total, row) => {
    const value = parseMoneyMinorUnits(row.amount, currencyCode);
    return total + (value ?? 0);
  }, 0);
  const remainingMinor = totalMinor === null ? null : totalMinor - allocatedMinor;
  const rowsValid = rows.every((row) => (
    Boolean(row.categoryId)
      && Boolean(row.label.trim())
      && (parseMoneyMinorUnits(row.amount, currencyCode) ?? 0) > 0
  ));
  const balanced = totalMinor !== null && totalMinor > 0 && rowsValid && remainingMinor === 0;

  function updateRow(rowId: string, update: Partial<SplitTransactionRow>) {
    onRowsChange((current) => current.map((row) => row.id === rowId ? { ...row, ...update } : row));
  }

  function addRow() {
    if (rows.length >= 99) return;
    onRowsChange((current) => [...current, newRow(current.length)]);
  }

  function removeRow(rowId: string) {
    if (rows.length <= 2) return;
    onRowsChange((current) => current.filter((row) => row.id !== rowId));
  }

  return (
    <section aria-labelledby="split-editor-title" className="space-y-4 rounded-lg border border-border/80 bg-background/60 p-4 sm:p-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p id="split-editor-title" className="font-mono text-[0.64rem] uppercase tracking-[0.14em] text-muted-foreground">Split allocation</p>
          <p className="mt-1 text-sm leading-6 text-muted-foreground">Allocate the account total across labelled categories.</p>
        </div>
        <div className="grid grid-cols-2 gap-1 rounded-md border border-border/70 bg-card p-1" role="group" aria-label="Split direction">
          <Button
            type="button"
            size="sm"
            variant={direction === "expense" ? "secondary" : "ghost"}
            aria-pressed={direction === "expense"}
            disabled={disabled}
            onClick={() => onDirectionChange("expense")}
          >
            <ArrowUpRight aria-hidden="true" /> Expense
          </Button>
          <Button
            type="button"
            size="sm"
            variant={direction === "income" ? "secondary" : "ghost"}
            aria-pressed={direction === "income"}
            disabled={disabled}
            onClick={() => onDirectionChange("income")}
          >
            <ArrowDownLeft aria-hidden="true" /> Income
          </Button>
        </div>
      </div>

      <div className="flex flex-col gap-2 text-sm">
        <Label htmlFor="split-total-amount">Total amount · {currencyCode}</Label>
        <Input
          id="split-total-amount"
          className="h-11 bg-background"
          inputMode="decimal"
          placeholder="0.00"
          value={totalAmount}
          onChange={(event) => onTotalAmountChange(event.target.value)}
          disabled={disabled}
          required
        />
      </div>

      <div className="space-y-3" aria-label="Split category rows">
        {rows.map((row, index) => (
          <div key={row.id} className="space-y-3 rounded-lg border border-border/70 bg-card p-3 sm:p-4">
            <div className="flex items-center justify-between gap-3">
              <p className="font-mono text-[0.62rem] uppercase tracking-[0.12em] text-muted-foreground">Category {index + 1}</p>
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                aria-label={`Remove category ${index + 1}`}
                disabled={disabled || rows.length <= 2}
                onClick={() => removeRow(row.id)}
              >
                <Trash2 aria-hidden="true" />
              </Button>
            </div>
            <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_minmax(8rem,0.7fr)]">
              <MoneySelectField
                id={`split-category-${row.id}`}
                label="Category"
                value={row.categoryId}
                selectedLabel={availableCategories.find((category) => category.id === row.categoryId)?.name ?? resourceLabels[row.categoryId]}
                emptyLabel="Choose a category"
                onValueChange={(value) => {
                  if (value === "__create_category__") {
                    onCreateCategory(index);
                    return;
                  }
                  updateRow(row.id, { categoryId: value });
                }}
                disabled={disabled}
              >
                {availableCategories.map((category) => <SelectItem key={category.id} value={category.id}>{category.name}</SelectItem>)}
                <SelectSeparator />
                <SelectItem value="__create_category__">Create new {direction} category…</SelectItem>
              </MoneySelectField>
              <div className="flex flex-col gap-2 text-sm">
                <Label htmlFor={`split-amount-${row.id}`}>Amount · {currencyCode}</Label>
                <Input
                  id={`split-amount-${row.id}`}
                  className="h-11 bg-background"
                  inputMode="decimal"
                  placeholder="0.00"
                  value={row.amount}
                  onChange={(event) => updateRow(row.id, { amount: event.target.value })}
                  disabled={disabled}
                  required
                />
              </div>
            </div>
            <div className="flex flex-col gap-2 text-sm">
              <Label htmlFor={`split-label-${row.id}`}>Label</Label>
              <Input
                id={`split-label-${row.id}`}
                className="h-10 bg-background"
                value={row.label}
                onChange={(event) => updateRow(row.id, { label: event.target.value })}
                placeholder={direction === "expense" ? "e.g. Fresh food" : "e.g. Consulting"}
                maxLength={200}
                disabled={disabled}
                required
              />
            </div>
          </div>
        ))}
      </div>

      <Button type="button" variant="outline" className="w-full" disabled={disabled || rows.length >= 99} onClick={addRow}>
        <Plus aria-hidden="true" /> Add category
      </Button>

      <div className="grid gap-2 rounded-lg border border-border/70 bg-card p-3 text-sm sm:grid-cols-3" aria-live="polite">
        <div>
          <p className="text-xs text-muted-foreground">Total</p>
          <p className="mt-1 font-mono font-medium">{totalMinor === null ? "—" : formatMoney(formatMinorUnits(totalMinor, currencyCode), currencyCode)}</p>
        </div>
        <div>
          <p className="text-xs text-muted-foreground">Allocated</p>
          <p className="mt-1 font-mono font-medium">{formatMoney(formatMinorUnits(allocatedMinor, currencyCode), currencyCode)}</p>
        </div>
        <div>
          <p className="text-xs text-muted-foreground">Remaining</p>
          <p className={cn("mt-1 font-mono font-medium", remainingMinor !== null && remainingMinor !== 0 && "text-destructive", balanced && "text-tag-sea-glass-foreground")}>
            {remainingMinor === null ? "—" : remainingMinor === 0 ? "Balanced" : formatSignedMoney(formatMinorUnits(remainingMinor, currencyCode), currencyCode)}
          </p>
        </div>
      </div>
    </section>
  );
}

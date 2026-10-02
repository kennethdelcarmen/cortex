"use client";

import type { ReactNode } from "react";
import { fieldDescribedBy, FormField } from "@/components/ui/form-field";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";

const emptyValue = "__money_empty__";

type MoneySelectFieldProps = {
  id: string;
  label: ReactNode;
  value: string;
  selectedLabel?: ReactNode;
  onValueChange: (value: string) => void;
  children: ReactNode;
  emptyLabel?: string;
  className?: string;
  triggerClassName?: string;
  disabled?: boolean;
  size?: "default" | "compact";
  hint?: string;
  error?: string;
};

export function MoneySelectField({
  id,
  label,
  value,
  selectedLabel,
  onValueChange,
  children,
  emptyLabel,
  className,
  triggerClassName,
  disabled,
  size = "default",
  hint,
  error,
}: MoneySelectFieldProps) {
  const triggerSize = size === "compact" ? "h-10 min-h-10" : "h-11 min-h-11";

  return (
    <FormField id={id} label={label} hint={hint} error={error} className={cn("min-w-0", className)}>
      <Select
        value={value || null}
        onValueChange={(nextValue) => onValueChange(!nextValue || nextValue === emptyValue ? "" : nextValue)}
        disabled={disabled}
      >
        <SelectTrigger
          id={id}
          className={cn(triggerSize, "w-full bg-background", triggerClassName)}
          aria-invalid={Boolean(error) || undefined}
          aria-describedby={fieldDescribedBy(id, hint, error)}
        >
          <SelectValue placeholder={emptyLabel}>{value ? selectedLabel ?? value : undefined}</SelectValue>
        </SelectTrigger>
        <SelectContent>
          {emptyLabel ? <SelectItem value={emptyValue}>{emptyLabel}</SelectItem> : null}
          {children}
        </SelectContent>
      </Select>
    </FormField>
  );
}

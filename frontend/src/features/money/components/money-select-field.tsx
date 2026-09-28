"use client";

import type { ReactNode } from "react";
import { Label } from "@/components/ui/label";
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
}: MoneySelectFieldProps) {
  const triggerSize = size === "compact" ? "h-10 min-h-10" : "h-11 min-h-11";

  return (
    <div className={cn("flex min-w-0 flex-col gap-2 text-sm", className)}>
      <Label htmlFor={id}>{label}</Label>
      <Select
        value={value || null}
        onValueChange={(nextValue) => onValueChange(!nextValue || nextValue === emptyValue ? "" : nextValue)}
        disabled={disabled}
      >
        <SelectTrigger id={id} className={cn(triggerSize, "w-full bg-background", triggerClassName)}>
          <SelectValue placeholder={emptyLabel}>{value ? selectedLabel ?? value : undefined}</SelectValue>
        </SelectTrigger>
        <SelectContent>
          {emptyLabel ? <SelectItem value={emptyValue}>{emptyLabel}</SelectItem> : null}
          {children}
        </SelectContent>
      </Select>
    </div>
  );
}

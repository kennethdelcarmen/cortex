import type { InputHTMLAttributes, ReactNode } from "react";
import {
  Field,
  FieldDescription,
  FieldError,
  FieldLabel,
} from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

export const inputClassName =
  "mt-2 h-11 bg-background/70 text-foreground shadow-sm";

type FormFieldProps = {
  id: string;
  label: ReactNode;
  hint?: string;
  error?: string;
  className?: string;
  children: ReactNode;
};

export function fieldDescribedBy(
  id: string,
  hint?: string,
  error?: string,
): string | undefined {
  const hintId = hint ? id + "-hint" : undefined;
  const errorId = error ? id + "-error" : undefined;
  return [hintId, errorId].filter(Boolean).join(" ") || undefined;
}

export function FormField({ id, label, hint, error, className, children }: FormFieldProps) {
  const hintId = hint ? id + "-hint" : undefined;
  const errorId = error ? id + "-error" : undefined;

  return (
    <Field data-invalid={error ? true : undefined} className={cn("gap-1.5", className)}>
      <FieldLabel htmlFor={id} className="text-sm text-foreground">
        {label}
      </FieldLabel>
      {hint ? (
        <FieldDescription id={hintId} className="text-xs leading-5">
          {hint}
        </FieldDescription>
      ) : null}
      <div>{children}</div>
      {error ? (
        <FieldError id={errorId} className="text-xs leading-5">
          {error}
        </FieldError>
      ) : null}
    </Field>
  );
}

type TextFieldProps = InputHTMLAttributes<HTMLInputElement> & {
  id: string;
  label: string;
  hint?: string;
  error?: string;
};

export function TextField({
  id,
  label,
  hint,
  error,
  className,
  ...props
}: TextFieldProps) {
  return (
    <FormField id={id} label={label} hint={hint} error={error}>
      <Input
        id={id}
        className={inputClassName + (className ? " " + className : "")}
        aria-invalid={Boolean(error) || undefined}
        aria-describedby={fieldDescribedBy(id, hint, error)}
        {...props}
      />
    </FormField>
  );
}

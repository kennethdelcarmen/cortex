import type { InputHTMLAttributes, ReactNode } from "react";

export const inputClassName =
  "mt-2 flex h-11 w-full rounded-lg border border-input bg-background/70 px-3 text-sm text-foreground shadow-sm outline-none transition-colors placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/25 disabled:cursor-not-allowed disabled:opacity-60 aria-[invalid=true]:border-destructive aria-[invalid=true]:ring-3 aria-[invalid=true]:ring-destructive/15";

type FormFieldProps = {
  id: string;
  label: string;
  hint?: string;
  error?: string;
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

export function FormField({ id, label, hint, error, children }: FormFieldProps) {
  const hintId = hint ? id + "-hint" : undefined;
  const errorId = error ? id + "-error" : undefined;

  return (
    <div>
      <label htmlFor={id} className="text-sm font-medium text-foreground">
        {label}
      </label>
      {hint ? (
        <p id={hintId} className="mt-1 text-xs leading-5 text-muted-foreground">
          {hint}
        </p>
      ) : null}
      <div>{children}</div>
      {error ? (
        <p id={errorId} role="alert" className="mt-2 text-xs leading-5 text-destructive">
          {error}
        </p>
      ) : null}
    </div>
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
      <input
        id={id}
        className={inputClassName + (className ? " " + className : "")}
        aria-invalid={Boolean(error) || undefined}
        aria-describedby={fieldDescribedBy(id, hint, error)}
        {...props}
      />
    </FormField>
  );
}

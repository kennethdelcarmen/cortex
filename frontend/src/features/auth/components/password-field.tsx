"use client";

import { Eye, EyeOff } from "lucide-react";
import { useState } from "react";
import type { InputHTMLAttributes } from "react";
import { Button } from "@/components/ui/button";
import { fieldDescribedBy, FormField, inputClassName } from "./form-field";

type PasswordFieldProps = InputHTMLAttributes<HTMLInputElement> & {
  id: string;
  label: string;
  hint?: string;
  error?: string;
};

export function PasswordField({
  id,
  label,
  hint,
  error,
  className,
  ...props
}: PasswordFieldProps) {
  const [visible, setVisible] = useState(false);

  return (
    <FormField id={id} label={label} hint={hint} error={error}>
      <div className="relative">
        <input
          {...props}
          id={id}
          type={visible ? "text" : "password"}
          className={inputClassName + " pr-12" + (className ? " " + className : "")}
          aria-invalid={Boolean(error) || undefined}
          aria-describedby={fieldDescribedBy(id, hint, error)}
        />
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          className="absolute right-1.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
          aria-label={visible ? "Hide " + label.toLowerCase() : "Show " + label.toLowerCase()}
          aria-pressed={visible}
          onClick={() => setVisible((current) => !current)}
        >
          {visible ? <EyeOff aria-hidden="true" /> : <Eye aria-hidden="true" />}
        </Button>
      </div>
    </FormField>
  );
}

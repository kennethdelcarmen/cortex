"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { z } from "zod";
import { useFeedback } from "@/components/feedback";
import { Button } from "@/components/ui/button";
import { FieldError } from "@/components/ui/field";
import { useActivityLogger } from "@/features/activity/hooks";
import { Input } from "@/components/ui/input";
import { ApiError } from "@/lib/api/client";
import { authQueryKey, describeAuthError, login } from "../api";
import { fieldDescribedBy, FormField, inputClassName } from "./form-field";
import { PasswordField } from "./password-field";

const loginFormSchema = z.object({
  email: z.string().trim().email("Enter a valid email address."),
  password: z.string().min(1, "Enter your password."),
});

export function LoginForm() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const feedback = useFeedback();
  const logActivity = useActivityLogger();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [errors, setErrors] = useState<{ email?: string; password?: string }>({});
  const [formError, setFormError] = useState<string>();

  const mutation = useMutation({
    mutationFn: login,
    onSuccess: async (user) => {
      await logActivity({ event_type: "auth.logged_in" });
      queryClient.setQueryData(authQueryKey, user);
      setPassword("");
      router.replace("/");
    },
    onError: (error) => {
      setPassword("");
      if (error instanceof ApiError && error.code === "invalid_credentials") {
        setFormError(describeAuthError(error));
      } else {
        feedback.error({
          title: "Sign in failed",
          description: describeAuthError(error),
        });
      }
    },
  });

  function submit() {
    setFormError(undefined);
    const result = loginFormSchema.safeParse({ email, password });

    if (!result.success) {
      const nextErrors: { email?: string; password?: string } = {};
      for (const issue of result.error.issues) {
        const field = issue.path[0];
        if (field === "email" || field === "password") {
          nextErrors[field] = issue.message;
        }
      }
      setErrors(nextErrors);
      return;
    }

    setErrors({});
    mutation.mutate(result.data);
  }

  return (
    <form
      className="space-y-5"
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
      noValidate
    >
      {formError ? (
        <FieldError id="login-form-error" aria-live="polite">
          {formError}
        </FieldError>
      ) : null}
      <FormField id="login-email" label="Owner email" error={errors.email}>
        <Input
          id="login-email"
          name="email"
          type="email"
          className={inputClassName}
          autoComplete="email"
          autoFocus
          value={email}
          aria-describedby={fieldDescribedBy("login-email", undefined, errors.email)}
          onChange={(event) => {
            setEmail(event.target.value);
            setErrors((current) => ({ ...current, email: undefined }));
            setFormError(undefined);
          }}
          aria-invalid={Boolean(errors.email) || undefined}
          disabled={mutation.isPending}
        />
      </FormField>
      <PasswordField
        id="login-password"
        name="password"
        label="Password"
        autoComplete="current-password"
        value={password}
        onChange={(event) => {
          setPassword(event.target.value);
          setErrors((current) => ({ ...current, password: undefined }));
          setFormError(undefined);
        }}
        error={errors.password}
        disabled={mutation.isPending}
      />
      <Button type="submit" size="lg" className="w-full" disabled={mutation.isPending}>
        {mutation.isPending ? "Signing in…" : "Sign in"}
      </Button>
      <p className="text-center text-xs leading-5 text-muted-foreground">
        Need to initialize this installation?{" "}
        <Link
          href="/setup"
          className="font-medium text-primary underline-offset-4 hover:underline focus-visible:rounded-sm focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/40"
        >
          Set up Cortex
        </Link>
      </p>
    </form>
  );
}

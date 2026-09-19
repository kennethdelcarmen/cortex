"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, Check } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { z } from "zod";
import { BlockingErrorDialog, useFeedback } from "@/components/feedback";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useActivityLogger } from "@/features/activity/hooks";
import { ApiError } from "@/lib/api/client";
import {
  authQueryKey,
  describeAuthError,
  setupOwner,
  verifySetupSecret,
} from "../api";
import { fieldDescribedBy, FormField, inputClassName } from "./form-field";
import { PasswordField } from "./password-field";

type SetupBlockingError = {
  title: string;
  description: string;
  actionLabel: string;
  onAction: () => void;
};

const ownerDetailsSchema = z
  .object({
    email: z.string().trim().email("Enter a valid email address."),
    password: z
      .string()
      .min(12, "Use at least 12 characters.")
      .max(128, "Use 128 characters or fewer."),
    confirmation: z.string(),
  })
  .superRefine((value, context) => {
    if (value.password !== value.confirmation) {
      context.addIssue({
        code: "custom",
        path: ["confirmation"],
        message: "Passwords must match.",
      });
    }
  });

export function SetupWizard() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const feedback = useFeedback();
  const logActivity = useActivityLogger();
  const [step, setStep] = useState<1 | 2>(1);
  const [setupSecret, setSetupSecret] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [secretError, setSecretError] = useState<string>();
  const [errors, setErrors] = useState<{
    email?: string;
    password?: string;
    confirmation?: string;
  }>({});
  const [blockingError, setBlockingError] = useState<SetupBlockingError>();

  const secretMutation = useMutation({
    mutationFn: verifySetupSecret,
    onSuccess: () => {
      setSecretError(undefined);
      setBlockingError(undefined);
      setStep(2);
    },
    onError: (error) => {
      if (error instanceof ApiError && error.code === "invalid_setup_secret") {
        setSecretError(describeAuthError(error));
        return;
      }

      setSecretError(undefined);
      if (error instanceof ApiError && error.code === "auth_already_initialized") {
        setBlockingError({
          title: "This installation is already initialized.",
          description: "The owner account already exists. Sign in to continue.",
          actionLabel: "Sign in instead",
          onAction: () => router.replace("/login"),
        });
        return;
      }

      if (error instanceof ApiError && error.code === "setup_not_configured") {
        setBlockingError({
          title: "Setup is unavailable.",
          description: describeAuthError(error),
          actionLabel: "Try again",
          onAction: () => secretMutation.mutate(setupSecret),
        });
        return;
      }

      feedback.error({
        title: "Setup check failed",
        description: describeAuthError(error),
      });
    },
  });

  const mutation = useMutation({
    mutationFn: setupOwner,
    onSuccess: async (user) => {
      await logActivity({ event_type: "auth.setup_completed" });
      queryClient.setQueryData(authQueryKey, user);
      setSetupSecret("");
      setPassword("");
      setConfirmation("");
      router.replace("/");
    },
    onError: (error) => {
      setPassword("");
      setConfirmation("");
      if (error instanceof ApiError && error.code === "auth_already_initialized") {
        setBlockingError({
          title: "This installation is already initialized.",
          description: "The owner account already exists. Sign in to continue.",
          actionLabel: "Sign in instead",
          onAction: () => router.replace("/login"),
        });
        return;
      }

      if (error instanceof ApiError && error.code === "setup_not_configured") {
        setBlockingError({
          title: "Setup is unavailable.",
          description: describeAuthError(error),
          actionLabel: "Return to access step",
          onAction: () => {
            setStep(1);
            setBlockingError(undefined);
          },
        });
        return;
      }

      feedback.error({
        title: "Owner account could not be created",
        description: describeAuthError(error),
      });
    },
  });

  function continueToOwnerDetails() {
    setSecretError(undefined);
    setBlockingError(undefined);
    if (!setupSecret) {
      setSecretError("Enter the setup secret configured for this installation.");
      return;
    }
    secretMutation.mutate(setupSecret);
  }

  function submitOwnerDetails() {
    setBlockingError(undefined);
    const result = ownerDetailsSchema.safeParse({ email, password, confirmation });

    if (!result.success) {
      const nextErrors: {
        email?: string;
        password?: string;
        confirmation?: string;
      } = {};
      for (const issue of result.error.issues) {
        const field = issue.path[0];
        if (field === "email" || field === "password" || field === "confirmation") {
          nextErrors[field] = issue.message;
        }
      }
      setErrors(nextErrors);
      return;
    }

    setErrors({});
    mutation.mutate({
      email: result.data.email,
      password: result.data.password,
      setupSecret,
    });
  }

  return (
    <div className="space-y-7">
      <div
        className="flex items-center justify-between gap-4"
        role="group"
        aria-label="Setup progress"
      >
        <div className="flex items-center gap-2 text-xs font-medium text-foreground">
          <span className="flex size-6 items-center justify-center rounded-full bg-primary font-mono text-[0.68rem] text-primary-foreground">
            {step === 1 ? "1" : <Check aria-hidden="true" className="size-3.5" />}
          </span>
          <span className={step === 1 ? "" : "text-muted-foreground"}>Access</span>
        </div>
        <div className="h-px flex-1 bg-border" aria-hidden="true" />
        <div className="flex items-center gap-2 text-xs font-medium">
          <span
            className={
              "flex size-6 items-center justify-center rounded-full font-mono text-[0.68rem] " +
              (step === 2
                ? "bg-primary text-primary-foreground"
                : "border border-border text-muted-foreground")
            }
          >
            2
          </span>
          <span className={step === 2 ? "text-foreground" : "text-muted-foreground"}>
            Owner
          </span>
        </div>
      </div>

      {blockingError ? (
        <BlockingErrorDialog
          open
          title={blockingError.title}
          description={blockingError.description}
          action={{
            label: blockingError.actionLabel,
            onClick: blockingError.onAction,
            pending: secretMutation.isPending || mutation.isPending,
            pendingLabel: "Working…",
          }}
        />
      ) : null}

      {step === 1 ? (
        <form
          className="space-y-6"
          onSubmit={(event) => {
            event.preventDefault();
            continueToOwnerDetails();
          }}
          noValidate
        >
          <div>
            <h2 className="text-xl font-medium tracking-[-0.02em] text-foreground">
              Connect this installation
            </h2>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">
              Enter the one-time secret supplied when the local Cortex service was started.
              It stays in this tab until setup is complete.
            </p>
          </div>
          <FormField
            id="setup-secret"
            label="Setup secret"
            hint="This is the value of CORTEX_SETUP_SECRET, not your owner password."
            error={secretError}
          >
            <Input
              id="setup-secret"
              name="setup-secret"
              type="password"
              className={inputClassName}
              autoComplete="off"
              autoFocus
              value={setupSecret}
              aria-invalid={Boolean(secretError) || undefined}
              aria-describedby={fieldDescribedBy(
                "setup-secret",
                "This is the value of CORTEX_SETUP_SECRET, not your owner password.",
                secretError,
              )}
              onChange={(event) => {
                setSetupSecret(event.target.value);
                setSecretError(undefined);
              }}
              disabled={secretMutation.isPending}
            />
          </FormField>
          <Button
            type="submit"
            size="lg"
            className="w-full"
            disabled={secretMutation.isPending}
          >
            {secretMutation.isPending ? (
              "Checking…"
            ) : (
              <>
                Continue <ArrowRight data-icon="inline-end" aria-hidden="true" />
              </>
            )}
          </Button>
          <p className="text-center text-xs leading-5 text-muted-foreground">
            Already initialized?{" "}
            <Link
              href="/login"
              className="font-medium text-primary-strong underline-offset-4 hover:underline focus-visible:rounded-sm focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/40"
            >
              Sign in instead
            </Link>
          </p>
        </form>
      ) : (
        <form
          className="space-y-5"
          onSubmit={(event) => {
            event.preventDefault();
            submitOwnerDetails();
          }}
          noValidate
        >
          <div>
            <h2 className="text-xl font-medium tracking-[-0.02em] text-foreground">
              Create the owner account
            </h2>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">
              This account controls the local workspace. Use a password you can keep secure.
            </p>
          </div>
          <FormField id="setup-email" label="Owner email" error={errors.email}>
            <Input
              id="setup-email"
              name="email"
              type="email"
              className={inputClassName}
              autoComplete="email"
              autoFocus
              value={email}
              aria-invalid={Boolean(errors.email) || undefined}
              aria-describedby={fieldDescribedBy("setup-email", undefined, errors.email)}
              onChange={(event) => {
                setEmail(event.target.value);
                setErrors((current) => ({ ...current, email: undefined }));
              }}
              disabled={mutation.isPending}
            />
          </FormField>
          <PasswordField
            id="setup-password"
            name="password"
            label="Password"
            hint="At least 12 characters."
            autoComplete="new-password"
            value={password}
            onChange={(event) => {
              setPassword(event.target.value);
              setErrors((current) => ({ ...current, password: undefined }));
            }}
            error={errors.password}
            disabled={mutation.isPending}
          />
          <PasswordField
            id="setup-confirmation"
            name="confirmation"
            label="Confirm password"
            autoComplete="new-password"
            value={confirmation}
            onChange={(event) => {
              setConfirmation(event.target.value);
              setErrors((current) => ({ ...current, confirmation: undefined }));
            }}
            error={errors.confirmation}
            disabled={mutation.isPending}
          />
          <div className="grid gap-3 sm:grid-cols-[auto_1fr]">
            <Button
              type="button"
              variant="outline"
              size="lg"
              onClick={() => {
                setStep(1);
                setErrors({});
                setBlockingError(undefined);
              }}
              disabled={mutation.isPending}
            >
              <ArrowLeft aria-hidden="true" />
              Back
            </Button>
            <Button type="submit" size="lg" disabled={mutation.isPending}>
              {mutation.isPending ? "Creating owner…" : "Create owner"}
            </Button>
          </div>
        </form>
      )}
    </div>
  );
}

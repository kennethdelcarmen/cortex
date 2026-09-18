"use client";

import { Toast } from "@base-ui/react/toast";
import { AlertCircle, CheckCircle2, X } from "lucide-react";
import type { ReactNode } from "react";
import { useCallback, useMemo } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

type FeedbackAction = {
  label: string;
  onClick: () => void;
};

type FeedbackToastOptions = {
  title: string;
  description?: string;
  action?: FeedbackAction;
  timeout?: number;
};

type FeedbackToastData = {
  action?: FeedbackAction;
};

function FeedbackToastList() {
  const toastManager = Toast.useToastManager<FeedbackToastData>();

  return toastManager.toasts.map((toast) => {
    const isError = toast.type === "error";

    return (
      <Toast.Root
        key={toast.id}
        toast={toast}
        className={cn(
          "pointer-events-auto grid grid-cols-[auto_minmax(0,1fr)_auto] items-start gap-3 rounded-lg border bg-card p-4 text-card-foreground shadow-[0_18px_50px_-28px_color-mix(in_oklab,var(--foreground)_55%,transparent)] outline-none transition-[transform,opacity] duration-200",
          "data-[type=success]:border-primary/30 data-[type=success]:bg-primary/8",
          "data-[type=error]:border-destructive/35 data-[type=error]:bg-destructive/10",
        )}
      >
        {isError ? (
          <AlertCircle aria-hidden="true" className="mt-0.5 size-4 text-destructive" />
        ) : (
          <CheckCircle2 aria-hidden="true" className="mt-0.5 size-4 text-primary" />
        )}
        <Toast.Content className="min-w-0">
          <Toast.Title className="text-sm font-medium" />
          {toast.description ? (
            <Toast.Description className="mt-1 text-sm leading-5 text-muted-foreground" />
          ) : null}
        </Toast.Content>
        <div className="flex items-start gap-1">
          {toast.data?.action ? (
            <Toast.Action
              type="button"
              className="rounded-md px-2 py-1 text-xs font-medium text-primary outline-none hover:bg-primary/10 focus-visible:ring-3 focus-visible:ring-ring/40"
              onClick={() => {
                toast.data?.action?.onClick();
                toastManager.close(toast.id);
              }}
            >
              {toast.data.action.label}
            </Toast.Action>
          ) : null}
          <Toast.Close
            aria-label="Dismiss notification"
            render={<Button variant="ghost" size="icon-sm" />}
          >
            <X aria-hidden="true" />
          </Toast.Close>
        </div>
      </Toast.Root>
    );
  });
}

export function FeedbackProvider({ children }: { children: ReactNode }) {
  return (
    <Toast.Provider limit={3} timeout={5000}>
      {children}
      <Toast.Portal>
        <Toast.Viewport className="pointer-events-none fixed inset-x-4 bottom-[calc(env(safe-area-inset-bottom)+5rem)] z-[100] mx-auto flex w-auto max-w-md flex-col gap-3 outline-none sm:inset-x-auto sm:right-6 sm:bottom-6 sm:w-[min(24rem,calc(100vw-3rem))]">
          <FeedbackToastList />
        </Toast.Viewport>
      </Toast.Portal>
    </Toast.Provider>
  );
}

export function useFeedback() {
  const toastManager = Toast.useToastManager<FeedbackToastData>();

  const addToast = useCallback(
    (type: "success" | "error", options: FeedbackToastOptions) => {
      return toastManager.add({
        title: options.title,
        description: options.description,
        type,
        priority: "low",
        timeout: options.timeout ?? (type === "error" ? 7000 : 4000),
        data: options.action ? { action: options.action } : undefined,
      });
    },
    [toastManager],
  );

  const success = useCallback(
    (options: FeedbackToastOptions) => addToast("success", options),
    [addToast],
  );
  const error = useCallback(
    (options: FeedbackToastOptions) => addToast("error", options),
    [addToast],
  );

  return useMemo(() => ({ success, error }), [error, success]);
}

type BlockingErrorAction = {
  label: string;
  onClick: () => void;
  pending?: boolean;
  pendingLabel?: string;
};

type BlockingErrorDialogProps = {
  open: boolean;
  title: string;
  description: string;
  action: BlockingErrorAction;
  secondaryAction?: Omit<BlockingErrorAction, "pending" | "pendingLabel">;
};

export function BlockingErrorDialog({
  open,
  title,
  description,
  action,
  secondaryAction,
}: BlockingErrorDialogProps) {
  return (
    <Dialog open={open} onOpenChange={() => undefined}>
      <DialogContent
        showCloseButton={false}
        className="w-[min(28rem,calc(100vw-2rem))] rounded-xl border-destructive/30 bg-card p-6 text-card-foreground shadow-[0_24px_80px_-35px_color-mix(in_oklab,var(--destructive)_55%,transparent)] sm:max-w-none sm:p-7"
      >
        <DialogHeader>
          <div className="flex items-start gap-3">
            <AlertCircle aria-hidden="true" className="mt-0.5 size-5 shrink-0 text-destructive" />
            <div>
              <DialogTitle className="text-xl font-semibold tracking-[-0.025em]">
                {title}
              </DialogTitle>
              <DialogDescription className="mt-3 text-sm leading-6 text-muted-foreground">
                {description}
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>
        <DialogFooter className="mt-2 flex-row justify-end gap-2 border-0 bg-transparent p-0">
          {secondaryAction ? (
            <Button type="button" variant="outline" onClick={secondaryAction.onClick}>
              {secondaryAction.label}
            </Button>
          ) : null}
          <Button
            type="button"
            onClick={action.onClick}
            disabled={action.pending}
          >
            {action.pending ? action.pendingLabel ?? "Working…" : action.label}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

"use client";

import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";

export function MoneyFloatingAction({ onClick }: { onClick: () => void }) {
  return (
    <Button
      type="button"
      size="icon-lg"
      aria-label="Create transaction"
      title="Create transaction"
      onClick={onClick}
      className="fixed right-4 bottom-[calc(env(safe-area-inset-bottom)+5.25rem)] z-30 size-12 rounded-full border-primary/30 bg-primary text-primary-foreground shadow-[0_14px_35px_-16px_color-mix(in_oklab,var(--primary)_70%,transparent)] hover:bg-primary/85 focus-visible:ring-4 lg:right-8 lg:bottom-8 motion-reduce:transition-none motion-reduce:active:translate-y-0"
    >
      <Plus aria-hidden="true" />
    </Button>
  );
}


"use client";

import { Menu } from "@base-ui/react/menu";
import { Plus } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { captureOptions } from "../workspace-config";

type CaptureMenuProps = {
  compact?: boolean;
};

export function CaptureMenu({ compact = false }: CaptureMenuProps) {
  return (
    <Menu.Root>
      <Menu.Trigger
        type="button"
        aria-label={compact ? "Add to Cortex" : undefined}
        className={buttonVariants({
          size: compact ? "icon" : "lg",
          className: cn(
            "h-10 border-primary/20 shadow-[0_8px_24px_-16px_color-mix(in_oklab,var(--primary)_70%,transparent)]",
            compact && "size-10",
          ),
        })}
      >
        <Plus aria-hidden="true" />
        {!compact ? <span>Add</span> : null}
      </Menu.Trigger>
      <Menu.Portal>
        <Menu.Positioner side="bottom" align="end" sideOffset={8} className="z-50">
          <Menu.Popup
            aria-label="Capture something"
            className="w-[min(18rem,calc(100vw-2rem))] rounded-xl border border-border bg-card p-2 text-card-foreground shadow-[0_24px_60px_-28px_color-mix(in_oklab,var(--foreground)_45%,transparent)] outline-none data-[open]:animate-in data-[open]:fade-in-0 data-[open]:zoom-in-95"
          >
            <div className="px-3 py-2">
              <p className="font-mono text-[0.65rem] font-medium uppercase tracking-[0.18em] text-muted-foreground">
                Capture
              </p>
              <p className="mt-1 text-sm leading-5 text-foreground">
                Keep the next thing close.
              </p>
            </div>
            <div className="my-1 h-px bg-border/70" />
            <div role="group" aria-label="Capture options">
              {captureOptions.map((option) => {
                const Icon = option.icon;

                return (
                  <Menu.Item
                    key={option.key}
                    disabled
                    closeOnClick={false}
                    className="flex min-h-12 w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-sm text-muted-foreground opacity-75 outline-none data-[highlighted]:bg-muted"
                  >
                    <span className="flex size-8 shrink-0 items-center justify-center rounded-md border border-border bg-background text-primary">
                      <Icon aria-hidden="true" className="size-4" />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block font-medium text-foreground">{option.label}</span>
                      <span className="block truncate text-xs leading-5">{option.description}</span>
                    </span>
                    <span className="shrink-0 font-mono text-[0.6rem] uppercase tracking-[0.12em] text-muted-foreground">
                      Coming next
                    </span>
                  </Menu.Item>
                );
              })}
            </div>
          </Menu.Popup>
        </Menu.Positioner>
      </Menu.Portal>
    </Menu.Root>
  );
}

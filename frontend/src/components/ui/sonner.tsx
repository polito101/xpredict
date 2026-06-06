/**
 * shadcn/ui Sonner toast provider.
 *
 * Adapted from https://ui.shadcn.com/docs/components/sonner. The canonical
 * shadcn version reads the active theme via `next-themes` `useTheme()`. This
 * project is dark-first with no `next-themes` provider, so we hardcode
 * `theme="dark"` and paint the toast surfaces with the design-system tokens
 * (popover / muted / brand). The player BET flow deliberately uses inline alerts
 * rather than toasts; toasts are used by the admin flows.
 *
 * sonner provides `role="status"` + `aria-live="polite"` automatically
 * (UI-SPEC §Accessibility — toast notifications).
 */
"use client";

import { Toaster as Sonner, type ToasterProps } from "sonner";

const Toaster = ({ ...props }: ToasterProps) => {
  return (
    <Sonner
      theme="dark"
      className="toaster group"
      toastOptions={{
        classNames: {
          toast:
            "group toast group-[.toaster]:bg-popover group-[.toaster]:text-popover-foreground group-[.toaster]:border-border group-[.toaster]:shadow-pop group-[.toaster]:rounded-xl",
          description: "group-[.toast]:text-muted-foreground",
          actionButton:
            "group-[.toast]:bg-brand-primary group-[.toast]:text-brand-primary-foreground",
          cancelButton:
            "group-[.toast]:bg-muted group-[.toast]:text-muted-foreground",
        },
      }}
      {...props}
    />
  );
};

export { Toaster };

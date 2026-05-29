/**
 * shadcn/ui Sonner toast provider.
 *
 * Adapted from https://ui.shadcn.com/docs/components/sonner. The canonical
 * shadcn version reads the active theme via `next-themes` `useTheme()`. This
 * project uses CSS-only dark mode (`@media (prefers-color-scheme: dark)` in
 * globals.css — see UI-SPEC §Dark Mode: "No manual toggle"), so there is no
 * `next-themes` provider to read from. We therefore hardcode `theme="system"`,
 * which lets sonner follow the OS color scheme to match the rest of the app.
 *
 * sonner provides `role="status"` + `aria-live="polite"` automatically
 * (UI-SPEC §Accessibility — toast notifications).
 */
"use client";

import { Toaster as Sonner, type ToasterProps } from "sonner";

const Toaster = ({ ...props }: ToasterProps) => {
  return (
    <Sonner
      theme="system"
      className="toaster group"
      toastOptions={{
        classNames: {
          toast:
            "group toast group-[.toaster]:bg-white group-[.toaster]:text-zinc-950 group-[.toaster]:border-zinc-200 group-[.toaster]:shadow-lg dark:group-[.toaster]:bg-zinc-950 dark:group-[.toaster]:text-zinc-50 dark:group-[.toaster]:border-zinc-800",
          description:
            "group-[.toast]:text-zinc-500 dark:group-[.toast]:text-zinc-400",
          actionButton:
            "group-[.toast]:bg-zinc-900 group-[.toast]:text-zinc-50 dark:group-[.toast]:bg-zinc-50 dark:group-[.toast]:text-zinc-900",
          cancelButton:
            "group-[.toast]:bg-zinc-100 group-[.toast]:text-zinc-500 dark:group-[.toast]:bg-zinc-800 dark:group-[.toast]:text-zinc-400",
        },
      }}
      {...props}
    />
  );
};

export { Toaster };

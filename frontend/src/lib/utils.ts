/**
 * shadcn/ui canonical helper. Combines clsx (conditional class names) +
 * tailwind-merge (deduplicates conflicting Tailwind utility classes,
 * keeping the LAST one — so `cn("px-2", condition && "px-4")` resolves
 * to `px-4` instead of leaving both and letting CSS specificity decide).
 *
 * This file is copied verbatim by `pnpm dlx shadcn@latest add` — when
 * adding more shadcn primitives later, this helper is the import target.
 */
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

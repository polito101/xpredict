/**
 * shadcn/ui Textarea primitive — canonical implementation.
 * Mirrors https://ui.shadcn.com/docs/components/textarea (verbatim except the
 * `@/lib/utils` import alias). Used for the mandatory ban reason input.
 */
import * as React from "react";

import { cn } from "@/lib/utils";

const Textarea = React.forwardRef<
  HTMLTextAreaElement,
  React.ComponentProps<"textarea">
>(({ className, ...props }, ref) => {
  return (
    <textarea
      className={cn(
        "flex min-h-[80px] w-full rounded-xl border border-input bg-muted/60 px-3.5 py-2 text-sm text-foreground ring-offset-background transition-colors placeholder:text-subtle-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:border-brand-primary/50 disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
      ref={ref}
      {...props}
    />
  );
});
Textarea.displayName = "Textarea";

export { Textarea };

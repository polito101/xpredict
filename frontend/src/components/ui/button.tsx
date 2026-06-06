/**
 * shadcn/ui Button primitive — copied from the canonical shadcn registry
 * (https://ui.shadcn.com/docs/components/button). Modified only to import
 * `cn` from "@/lib/utils" matching the path alias in tsconfig.json.
 *
 * Visual style is the "new-york" default. The primary (default) variant and the
 * focus ring consume the operator brand token (--brand-primary, v1.1 Fase A) so a
 * palette change re-skins every CTA, with the label color derived for contrast
 * (--brand-primary-foreground). secondary/ghost/outline stay neutral zinc and
 * destructive stays semantic red.
 */
import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-xl text-sm font-medium ring-offset-background transition-[color,background-color,box-shadow,transform,filter] active:scale-[0.97] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 disabled:active:scale-100",
  {
    variants: {
      variant: {
        default:
          "bg-brand-primary text-brand-primary-foreground shadow-sm hover:brightness-110",
        destructive: "bg-red-500 text-zinc-50 hover:bg-red-500/90",
        outline:
          "border border-input bg-transparent text-foreground hover:bg-muted",
        secondary: "bg-muted text-foreground hover:bg-muted/70",
        ghost: "text-muted-foreground hover:bg-muted hover:text-foreground",
        link: "text-brand-primary underline-offset-4 hover:underline",
      },
      size: {
        default: "h-10 px-4 py-2",
        sm: "h-9 rounded-md px-3",
        lg: "h-11 rounded-md px-8",
        icon: "h-10 w-10",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    );
  },
);
Button.displayName = "Button";

export { Button, buttonVariants };

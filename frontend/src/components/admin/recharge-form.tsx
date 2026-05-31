/**
 * Plan 08-03 — Wallet recharge form (calls the Phase 3 recharge primitive).
 *
 * Inline card form: Amount ($ prefix) + Reason (required). Validation via
 * react-hook-form + zod. Submit POSTs through `rechargeWallet`, which attaches a
 * fresh `Idempotency-Key` (UUID v4, generated per submission via
 * `crypto.randomUUID()`) — double-submit mitigation T-08-11. On success: toast
 * "Wallet recharged successfully" and `onRecharged()` so the parent refreshes
 * the balance + transaction table. The whole form is DISABLED when the user is
 * banned (greyed out + tooltip "Cannot recharge a banned user"); the backend is
 * authoritative and returns 403 for a banned target regardless.
 *
 * MONEY DISCIPLINE (CLAUDE.md hard constraint): the amount is kept and sent as a
 * STRING — validated with a decimal regex + a sign check on the integer/decimal
 * digit groups, never `parseFloat` / `Number()`. The raw trimmed string is what
 * reaches the backend, which parses it as Decimal authoritatively.
 */
"use client";

import * as React from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { rechargeWallet } from "@/lib/admin-api";

/**
 * Positive decimal (string) validator — no float coercion. Accepts an optional
 * leading "+", then digits with an optional fractional part, and rejects a
 * zero magnitude ("0", "0.0", "00.000", …) so amount must be > 0.
 */
function isPositiveDecimalString(raw: string): boolean {
  const v = raw.trim().replace(/^\+/, "");
  if (!/^\d+(\.\d+)?$/.test(v)) return false;
  // Reject zero magnitude without parsing to a number.
  return /[1-9]/.test(v.replace(".", ""));
}

const RechargeSchema = z.object({
  amount: z
    .string()
    .min(1, "Amount is required")
    .refine(
      (v) => /^\+?\d+(\.\d+)?$/.test(v.trim()),
      "Amount must be a valid number",
    )
    .refine(isPositiveDecimalString, "Amount must be greater than zero"),
  reason: z.string().trim().min(1, "Reason is required"),
});

type RechargeValues = z.infer<typeof RechargeSchema>;

export function RechargeForm({
  userId,
  banned,
  onRecharged,
}: {
  userId: string;
  banned: boolean;
  onRecharged: () => void;
}) {
  const [submitting, setSubmitting] = React.useState(false);

  const form = useForm<RechargeValues>({
    resolver: zodResolver(RechargeSchema),
    defaultValues: { amount: "", reason: "" },
    mode: "onSubmit",
  });

  const onSubmit = form.handleSubmit(async (values) => {
    if (banned || submitting) return;
    setSubmitting(true);
    try {
      // Fresh UUID v4 per submission — a retry of the SAME logical submit would
      // reuse this key, but each user-initiated submit gets a new one.
      const idempotencyKey = crypto.randomUUID();
      await rechargeWallet(
        userId,
        values.amount.trim(),
        values.reason.trim(),
        idempotencyKey,
      );
      toast.success("Wallet recharged successfully");
      form.reset({ amount: "", reason: "" });
      onRecharged();
    } catch {
      toast.error("Failed to recharge wallet. Please try again.");
    } finally {
      setSubmitting(false);
    }
  });

  const formBody = (
    <Form {...form}>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void onSubmit(e);
        }}
        className="flex flex-col gap-4 sm:flex-row sm:items-start"
        noValidate
        aria-disabled={banned}
      >
        <FormField
          control={form.control}
          name="amount"
          render={({ field }) => (
            <FormItem className="sm:w-40">
              <FormLabel>Amount ($)</FormLabel>
              <FormControl>
                <div className="relative">
                  <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-sm text-zinc-400">
                    $
                  </span>
                  <Input
                    type="text"
                    inputMode="decimal"
                    placeholder="0.0000"
                    className="pl-7 tabular-nums"
                    disabled={banned || submitting}
                    {...field}
                  />
                </div>
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <FormField
          control={form.control}
          name="reason"
          render={({ field }) => (
            <FormItem className="flex-1">
              <FormLabel>Reason (required)</FormLabel>
              <FormControl>
                <Input
                  type="text"
                  placeholder="Enter the reason for this recharge..."
                  disabled={banned || submitting}
                  {...field}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <Button
          type="submit"
          disabled={banned || submitting}
          className="sm:mt-[1.625rem]"
        >
          {submitting && (
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          )}
          Recharge
        </Button>
      </form>
    </Form>
  );

  if (!banned) return formBody;

  // Banned: grey the form out and surface the disabled reason on hover.
  return (
    <TooltipProvider delayDuration={200}>
      <Tooltip>
        <TooltipTrigger asChild>
          <div className="cursor-not-allowed opacity-50">{formBody}</div>
        </TooltipTrigger>
        <TooltipContent>Cannot recharge a banned user</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

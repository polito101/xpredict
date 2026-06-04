/**
 * Plan 12-06 — Force-settle market dialog (ADM-06).
 *
 * Clone of `ban-confirm-dialog.tsx` with ONE structural addition: a YES/NO
 * outcome `<Select>` ABOVE the mandatory justification `Textarea` (same shape
 * as resolve-market-dialog; UI-SPEC §Surface 3 / 12-RESEARCH Pattern 4). Used to
 * override a STUCK Polymarket-mirrored market when its automated resolution has
 * not arrived. Two-step + mandatory justification: the button reveals the dialog
 * (step 1: propose outcome + justify), the `destructive` "Confirm force-settle"
 * submits (step 2). The dialog STAYS OPEN during submit (double-click guard +
 * a11y), shows a `Loader2` spinner, toasts on success, and the parent refetches
 * via `onForceSettled()`.
 *
 * Calls `forceSettle(id, {winning_outcome_id, justification})` — the 12-02
 * wrapper that targets the BARE `/admin/markets/{id}/force-settle` prefix (NOT
 * `/api/v1`; the two-prefix landmine is locked by admin-markets-api.test.ts).
 * Justification is validated `trim().length >= 1` client-side (matching backend
 * `min_length=1`, threat T-12-18) before the call; an empty value shows the
 * `role="alert"` error and never calls the wrapper. A 401/403 thrown by the
 * wrapper maps to the session-expired toast (UI-SPEC §Toast).
 */
"use client";

import * as React from "react";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { forceSettle } from "@/lib/admin-markets-api";
import type { OutcomeRead } from "@/lib/admin-markets-types";
import { isSessionExpiredError } from "@/components/admin/settlement-dialog-utils";

export function ForceSettleDialog({
  open,
  onOpenChange,
  marketId,
  outcomes,
  onForceSettled,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  marketId: string;
  outcomes: OutcomeRead[];
  onForceSettled: () => void;
}) {
  const [winningOutcomeId, setWinningOutcomeId] = React.useState("");
  const [justification, setJustification] = React.useState("");
  const [submitting, setSubmitting] = React.useState(false);
  const [validationError, setValidationError] = React.useState<string | null>(
    null,
  );
  const outcomeId = React.useId();
  const justificationId = React.useId();

  // Reset BOTH the outcome and the justification whenever the dialog opens.
  React.useEffect(() => {
    if (open) {
      setWinningOutcomeId("");
      setJustification("");
      setValidationError(null);
      setSubmitting(false);
    }
  }, [open]);

  async function handleConfirm() {
    if (!winningOutcomeId) {
      setValidationError("Select the winning outcome.");
      return;
    }
    if (justification.trim().length < 1) {
      setValidationError("A justification is required.");
      return;
    }
    setValidationError(null);
    setSubmitting(true);
    try {
      await forceSettle(marketId, {
        winning_outcome_id: winningOutcomeId,
        justification: justification.trim(),
      });
      toast.success("Market force-settled.");
      onForceSettled();
      onOpenChange(false);
    } catch (err) {
      if (isSessionExpiredError(err)) {
        toast.error("Your session expired. Please sign in again.");
      } else {
        toast.error("Couldn't force-settle the market. Please try again.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !submitting && onOpenChange(o)}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Force-settle market</DialogTitle>
          <DialogDescription>
            Manually settle this Polymarket-mirrored market to the winning
            outcome when its automated resolution has not arrived. This pays out
            winning positions through the ledger and cannot be undone without a
            reversal.
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <Label htmlFor={outcomeId}>Winning outcome</Label>
            <Select
              value={winningOutcomeId}
              onValueChange={(v) => {
                setWinningOutcomeId(v);
                if (validationError) setValidationError(null);
              }}
              disabled={submitting}
            >
              <SelectTrigger id={outcomeId} aria-label="Winning outcome">
                <SelectValue placeholder="Select the winning outcome" />
              </SelectTrigger>
              <SelectContent>
                {outcomes.map((o) => (
                  <SelectItem key={o.id} value={o.id}>
                    {o.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="flex flex-col gap-2">
            <Label htmlFor={justificationId}>Justification (required)</Label>
            <Textarea
              id={justificationId}
              value={justification}
              onChange={(e) => {
                setJustification(e.target.value);
                if (validationError) setValidationError(null);
              }}
              placeholder="Explain why this market is being force-settled to the selected outcome..."
              disabled={submitting}
              aria-invalid={!!validationError}
            />
            {validationError && (
              <p role="alert" className="text-sm font-medium text-red-500">
                {validationError}
              </p>
            )}
          </div>
        </div>

        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={submitting}
          >
            Cancel
          </Button>
          <Button
            type="button"
            variant="destructive"
            onClick={() => void handleConfirm()}
            disabled={submitting}
          >
            {submitting && (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            )}
            Confirm force-settle
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

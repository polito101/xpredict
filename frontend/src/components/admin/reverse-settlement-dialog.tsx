/**
 * Plan 12-06 — Reverse settlement dialog (STL-07).
 *
 * Clone of `ban-confirm-dialog.tsx` with NO structural addition (justification
 * ONLY — no outcome Select). Two-step + mandatory justification: the button
 * reveals the dialog (step 1: justify), the `destructive` "Confirm reversal"
 * submits (step 2). The dialog STAYS OPEN during submit (double-click guard +
 * a11y), shows a `Loader2` spinner, toasts on success, and the parent refetches
 * via `onReversed()`.
 *
 * Calls `reverseSettlement(id, {justification})` — the 12-02 wrapper that
 * targets the BARE `/admin/markets/{id}/reverse` prefix (NOT `/api/v1`; the
 * two-prefix landmine is locked by admin-markets-api.test.ts). Justification is
 * validated `trim().length >= 1` client-side (matching backend `min_length=1`,
 * threat T-12-18) before the call; an empty value shows the `role="alert"`
 * error and never calls the wrapper. A 401/403 thrown by the wrapper maps to
 * the session-expired toast (UI-SPEC §Toast).
 *
 * REVERSE COPY GUARD (Pitfall 5 / threat T-12-21): the body copy explicitly
 * does NOT promise re-resolution — re-resolving after a reversal collides on
 * reused settlement idempotency keys (a known, deferred v1 limitation). The
 * §Reverse copy guard body is used verbatim from 12-UI-SPEC.
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
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { reverseSettlement } from "@/lib/admin-markets-api";
import { isSessionExpiredError } from "@/components/admin/settlement-dialog-utils";

export function ReverseSettlementDialog({
  open,
  onOpenChange,
  marketId,
  onReversed,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  marketId: string;
  onReversed: () => void;
}) {
  const [justification, setJustification] = React.useState("");
  const [submitting, setSubmitting] = React.useState(false);
  const [validationError, setValidationError] = React.useState<string | null>(
    null,
  );
  const justificationId = React.useId();

  // Reset the justification whenever the dialog opens.
  React.useEffect(() => {
    if (open) {
      setJustification("");
      setValidationError(null);
      setSubmitting(false);
    }
  }, [open]);

  async function handleConfirm() {
    if (justification.trim().length < 1) {
      setValidationError("A justification is required.");
      return;
    }
    setValidationError(null);
    setSubmitting(true);
    try {
      await reverseSettlement(marketId, {
        justification: justification.trim(),
      });
      toast.success("Settlement reversed.");
      onReversed();
      onOpenChange(false);
    } catch (err) {
      if (isSessionExpiredError(err)) {
        toast.error("Your session expired. Please sign in again.");
      } else {
        toast.error("Couldn't reverse the settlement. Please try again.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !submitting && onOpenChange(o)}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Reverse settlement</DialogTitle>
          {/* §Reverse copy guard (Pitfall 5): set the audit/correction expectation;
              do NOT promise a clean re-resolution. */}
          <DialogDescription>
            Reverse this settlement. This posts compensating ledger entries that
            return every affected player to their pre-settlement balance and
            writes an audit entry. It does not re-open the market for a clean
            re-resolution.
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-2">
          <Label htmlFor={justificationId}>Justification (required)</Label>
          <Textarea
            id={justificationId}
            value={justification}
            onChange={(e) => {
              setJustification(e.target.value);
              if (validationError) setValidationError(null);
            }}
            placeholder="Explain why this settlement is being reversed..."
            disabled={submitting}
            aria-invalid={!!validationError}
          />
          {validationError && (
            <p role="alert" className="text-sm font-medium text-red-500">
              {validationError}
            </p>
          )}
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
            Confirm reversal
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/**
 * Plan 12-06 — Resolve market dialog (STL-02 / ADM-05).
 *
 * Clone of `ban-confirm-dialog.tsx` with ONE structural addition: a YES/NO
 * outcome `<Select>` ABOVE the mandatory justification `Textarea` (UI-SPEC
 * §Surface 3 / 12-RESEARCH Pattern 4). Two-step + mandatory justification:
 * the button reveals the dialog (step 1: propose outcome + justify), the
 * `destructive` "Confirm resolve" submits (step 2). The dialog STAYS OPEN during
 * submit (double-click guard + a11y), shows a `Loader2` spinner, toasts on
 * success, and the parent refetches via `onResolved()`.
 *
 * Calls `resolveMarket(id, {winning_outcome_id, justification})` — the 12-02
 * wrapper that targets the BARE `/admin/markets/{id}/resolve` prefix (NOT
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
import { resolveMarket } from "@/lib/admin-markets-api";
import type { OutcomeRead } from "@/lib/admin-markets-types";
import { isSessionExpiredError } from "@/components/admin/settlement-dialog-utils";

export function ResolveMarketDialog({
  open,
  onOpenChange,
  marketId,
  outcomes,
  onResolved,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  marketId: string;
  outcomes: OutcomeRead[];
  onResolved: () => void;
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
      await resolveMarket(marketId, {
        winning_outcome_id: winningOutcomeId,
        justification: justification.trim(),
      });
      toast.success("Market resolved.");
      onResolved();
      onOpenChange(false);
    } catch (err) {
      if (isSessionExpiredError(err)) {
        toast.error("Your session expired. Please sign in again.");
      } else {
        toast.error("Couldn't resolve the market. Please try again.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !submitting && onOpenChange(o)}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Resolve market</DialogTitle>
          <DialogDescription>
            Settle this market to the winning outcome. This pays out winning
            positions through the ledger and cannot be undone without a reversal.
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
              placeholder="Explain why this market resolves to the selected outcome..."
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
            Confirm resolve
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

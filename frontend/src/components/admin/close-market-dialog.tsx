/**
 * Plan 12-06 — Close market dialog (ADM-04).
 *
 * Clone of `ban-confirm-dialog.tsx` with the reason field DROPPED — the close
 * endpoint (`POST /api/v1/admin/markets/{id}/close`) takes NO body. Two-step
 * confirm: the button reveals the dialog (step 1: read the consequence copy),
 * the `destructive` "Close market" submits (step 2). The dialog STAYS OPEN
 * during submit (double-click guard + a11y), shows a `Loader2` spinner, toasts
 * on success, and the parent refetches via `onClosed()`.
 *
 * Calls `closeMarket(id)` — the 12-02 CRUD wrapper. Unlike the settlement
 * actions this is an early-stop, not a settlement: it stops the market from
 * accepting new bets while players keep their open positions until resolution.
 * A 401/403 thrown by the wrapper maps to the session-expired toast
 * (UI-SPEC §Toast).
 *
 * NOTE: there is NO justification field here (the API takes none) — the
 * consequence copy in the body is the entire confirmation surface.
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
import { closeMarket } from "@/lib/admin-markets-api";
import { isSessionExpiredError } from "@/components/admin/settlement-dialog-utils";

export function CloseMarketDialog({
  open,
  onOpenChange,
  marketId,
  onClosed,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  marketId: string;
  onClosed: () => void;
}) {
  const [submitting, setSubmitting] = React.useState(false);

  // Reset transient state whenever the dialog opens.
  React.useEffect(() => {
    if (open) {
      setSubmitting(false);
    }
  }, [open]);

  async function handleConfirm() {
    setSubmitting(true);
    try {
      await closeMarket(marketId);
      toast.success("Market closed. It's no longer accepting bets.");
      onClosed();
      onOpenChange(false);
    } catch (err) {
      if (isSessionExpiredError(err)) {
        toast.error("Your session expired. Please sign in again.");
      } else {
        toast.error("Couldn't close the market. Please try again.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !submitting && onOpenChange(o)}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Close market</DialogTitle>
          <DialogDescription>
            This stops the market from accepting new bets. Players keep their
            open positions until resolution.
          </DialogDescription>
        </DialogHeader>

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
            Close market
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

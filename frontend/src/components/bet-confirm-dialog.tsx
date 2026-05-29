/**
 * Plan 09-04 — Bet confirmation modal (MKT-03 / BET-04 / Phase 5 SC#3).
 *
 * The destructive-style guard for placing a bet (financially committing — play
 * money locks with no cash-out, so the confirm modal IS the irreversible-action
 * gate per the UI-SPEC). Built on the hand-copied shadcn `Dialog` (Plan 03).
 *
 * Shows the three labeled rows from the UI-SPEC Copywriting Contract:
 *   Stake          → {stake} PLAY_USD
 *   Current odds   → {yes}% YES / {no}% NO
 *   Expected payout → {payout} PLAY_USD
 * footer note "Odds may move before your bet is placed." and the
 * "Confirm bet" / "Cancel" buttons. Only "Confirm bet" invokes `onConfirm`
 * (which fires `placeBetAction` in the parent). The dialog is fully
 * controlled by the parent (`open` / `onOpenChange`).
 */
"use client";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

const CURRENCY = "PLAY_USD";

interface BetConfirmDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Stake string exactly as the player entered it (money-as-string, SP-1). */
  stake: string;
  /** Rounded YES / NO percentages for display (already computed by parent). */
  yesPct: number;
  noPct: number;
  /** Expected-payout display string (computed by parent — SP-1). */
  payout: string;
  /** Fires `placeBetAction`; parent keeps the pending state. */
  onConfirm: () => void;
  /** Disables the confirm button while the action is in flight. */
  pending?: boolean;
}

export function BetConfirmDialog({
  open,
  onOpenChange,
  stake,
  yesPct,
  noPct,
  payout,
  onConfirm,
  pending = false,
}: BetConfirmDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Confirm your bet</DialogTitle>
          <DialogDescription>
            Review your stake, the current odds, and the expected payout before
            placing this bet.
          </DialogDescription>
        </DialogHeader>

        <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-2 text-sm">
          <dt className="text-zinc-500">Stake</dt>
          <dd className="text-right font-normal">
            {stake} {CURRENCY}
          </dd>

          <dt className="text-zinc-500">Current odds</dt>
          <dd className="text-right font-normal">
            {yesPct}% YES / {noPct}% NO
          </dd>

          <dt className="text-zinc-500">Expected payout</dt>
          <dd className="text-right font-normal">
            {payout} {CURRENCY}
          </dd>
        </dl>

        <p className="text-xs text-zinc-500">
          Odds may move before your bet is placed.
        </p>

        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={pending}
          >
            Cancel
          </Button>
          <Button type="button" onClick={onConfirm} disabled={pending}>
            {pending ? "Placing bet…" : "Confirm bet"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

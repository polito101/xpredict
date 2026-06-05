/**
 * Plan 17-04 — Resolve event dialog (EVA-03).
 *
 * Clone of `resolve-market-dialog.tsx`, adapted to the backend's SERVER-driven
 * two-step confirm: open → operator picks the winning outcome + justification →
 * "Preview impact" calls `resolveEvent({confirm:false})` (non-mutating) and
 * renders the projected `{winners}/{losers}/projected_status` → the destructive
 * "Confirm resolve" calls `resolveEvent({confirm:true})` to execute. Editing the
 * outcome or justification clears the preview, so the confirm always matches
 * what was previewed. Justification is mandatory (`trim().length >= 1`).
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
import { resolveEvent } from "@/lib/admin-events-api";
import { isSessionExpiredError } from "@/components/admin/settlement-dialog-utils";
import type { EventActionResponse } from "@/lib/admin-events-types";

export interface ResolveOutcomeOption {
  label: string;
  yes_outcome_id: string | null;
}

export function ResolveEventDialog({
  open,
  onOpenChange,
  groupId,
  outcomes,
  onResolved,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  groupId: string;
  outcomes: ResolveOutcomeOption[];
  onResolved: () => void;
}) {
  const [winningOutcomeId, setWinningOutcomeId] = React.useState("");
  const [justification, setJustification] = React.useState("");
  const [preview, setPreview] = React.useState<EventActionResponse | null>(null);
  const [submitting, setSubmitting] = React.useState(false);
  const [validationError, setValidationError] = React.useState<string | null>(
    null,
  );
  const outcomeId = React.useId();
  const justificationId = React.useId();

  React.useEffect(() => {
    if (open) {
      setWinningOutcomeId("");
      setJustification("");
      setPreview(null);
      setValidationError(null);
      setSubmitting(false);
    }
  }, [open]);

  function mapError(err: unknown) {
    if (isSessionExpiredError(err)) {
      toast.error("Your session expired. Please sign in again.");
    } else if (err instanceof Error && /\b409\b/.test(err.message)) {
      toast.error("Mirrored events are read-only and can't be resolved here.");
    } else {
      toast.error("Couldn't resolve the event. Please try again.");
    }
  }

  async function handlePreview() {
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
      const res = await resolveEvent(groupId, {
        winning_outcome_id: winningOutcomeId,
        justification: justification.trim(),
        confirm: false,
      });
      setPreview(res);
    } catch (err) {
      mapError(err);
    } finally {
      setSubmitting(false);
    }
  }

  async function handleConfirm() {
    setSubmitting(true);
    try {
      await resolveEvent(groupId, {
        winning_outcome_id: winningOutcomeId,
        justification: justification.trim(),
        confirm: true,
      });
      toast.success("Event resolved.");
      onResolved();
      onOpenChange(false);
    } catch (err) {
      mapError(err);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !submitting && onOpenChange(o)}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Resolve event</DialogTitle>
          <DialogDescription>
            Settle this event to the winning outcome. Each outcome settles through
            the ledger; this cannot be undone without a reversal.
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <Label htmlFor={outcomeId}>Winning outcome</Label>
            <Select
              value={winningOutcomeId}
              onValueChange={(v) => {
                setWinningOutcomeId(v);
                setPreview(null);
                if (validationError) setValidationError(null);
              }}
              disabled={submitting}
            >
              <SelectTrigger id={outcomeId} aria-label="Winning outcome">
                <SelectValue placeholder="Select the winning outcome" />
              </SelectTrigger>
              <SelectContent>
                {outcomes
                  .filter((o) => o.yes_outcome_id)
                  .map((o) => (
                    <SelectItem
                      key={o.yes_outcome_id as string}
                      value={o.yes_outcome_id as string}
                    >
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
                setPreview(null);
                if (validationError) setValidationError(null);
              }}
              placeholder="Explain why this event resolves to the selected outcome..."
              disabled={submitting}
              aria-invalid={!!validationError}
            />
            {validationError && (
              <p role="alert" className="text-sm font-medium text-red-500">
                {validationError}
              </p>
            )}
          </div>

          {preview && (
            <div
              className="rounded-md bg-zinc-50 p-3 text-sm dark:bg-zinc-800"
              role="status"
            >
              <p className="font-medium">Projected impact</p>
              <p className="text-zinc-600 dark:text-zinc-400">
                {preview.winners ?? 0} winning, {preview.losers ?? 0} losing
                positions → {preview.projected_status}
              </p>
            </div>
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
          {preview ? (
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
          ) : (
            <Button
              type="button"
              onClick={() => void handlePreview()}
              disabled={submitting}
            >
              {submitting && (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              )}
              Preview impact
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

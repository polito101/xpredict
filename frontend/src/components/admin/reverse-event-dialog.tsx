/**
 * Plan 17-04 — Reverse event dialog (EVA-05).
 *
 * Justification-only clone using the SERVER two-step: "Preview impact" calls
 * `reverseEvent({confirm:false})` and shows how many settled outcomes will be
 * reversed; the destructive "Confirm reversal" calls `reverseEvent({confirm:true})`.
 *
 * REVERSE COPY GUARD: the body sets the audit/correction expectation and does
 * NOT promise a clean re-resolution (re-resolving after a reversal collides on
 * reused settlement idempotency keys — a known, deferred limitation).
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
import { reverseEvent } from "@/lib/admin-events-api";
import { isSessionExpiredError } from "@/components/admin/settlement-dialog-utils";
import type { EventActionResponse } from "@/lib/admin-events-types";

export function ReverseEventDialog({
  open,
  onOpenChange,
  groupId,
  onReversed,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  groupId: string;
  onReversed: () => void;
}) {
  const [justification, setJustification] = React.useState("");
  const [preview, setPreview] = React.useState<EventActionResponse | null>(null);
  const [submitting, setSubmitting] = React.useState(false);
  const [validationError, setValidationError] = React.useState<string | null>(
    null,
  );
  const justificationId = React.useId();

  React.useEffect(() => {
    if (open) {
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
      toast.error("Mirrored events are read-only and can't be reversed here.");
    } else {
      toast.error("Couldn't reverse the event. Please try again.");
    }
  }

  async function handlePreview() {
    if (justification.trim().length < 1) {
      setValidationError("A justification is required.");
      return;
    }
    setValidationError(null);
    setSubmitting(true);
    try {
      setPreview(
        await reverseEvent(groupId, {
          justification: justification.trim(),
          confirm: false,
        }),
      );
    } catch (err) {
      mapError(err);
    } finally {
      setSubmitting(false);
    }
  }

  async function handleConfirm() {
    setSubmitting(true);
    try {
      await reverseEvent(groupId, {
        justification: justification.trim(),
        confirm: true,
      });
      toast.success("Event settlement reversed.");
      onReversed();
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
          <DialogTitle>Reverse event settlement</DialogTitle>
          <DialogDescription>
            Reverse this event&apos;s settlement. This posts compensating ledger
            entries that return every affected player to their pre-settlement
            balance and writes an audit entry. It does not re-open the event for a
            clean re-resolution.
          </DialogDescription>
        </DialogHeader>

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
            placeholder="Explain why this settlement is being reversed..."
            disabled={submitting}
            aria-invalid={!!validationError}
          />
          {validationError && (
            <p role="alert" className="text-sm font-medium text-red-500">
              {validationError}
            </p>
          )}
          {preview && (
            <div
              className="mt-2 rounded-md bg-zinc-50 p-3 text-sm dark:bg-zinc-800"
              role="status"
            >
              <p className="font-medium">Projected impact</p>
              <p className="text-zinc-600 dark:text-zinc-400">
                {preview.settled_children_to_reverse ?? 0} settled outcomes will
                be reversed → {preview.projected_status}
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
              Confirm reversal
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

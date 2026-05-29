/**
 * Plan 08-03 — Ban confirmation dialog (ADU-04, D-01/D-04).
 *
 * shadcn Dialog with a MANDATORY reason Textarea (backend min_length=1,
 * extra="forbid" — see <backend_contracts>). Validated client-side before
 * submit; the "Confirm ban" button is `destructive` and shows a spinner while
 * the request is in flight (the dialog stays open during submission to prevent
 * double-click — UI-SPEC §Interaction Contract). On success: toast "User has
 * been banned", dialog closes, and the parent refetches via `onBanned(updated)`
 * with the returned UserDetail. Copywriting verbatim from UI-SPEC.
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
import { banUser } from "@/lib/admin-api";
import type { UserDetail } from "@/lib/admin-types";

export function BanConfirmDialog({
  open,
  onOpenChange,
  userId,
  onBanned,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  userId: string;
  onBanned: (updated: UserDetail) => void;
}) {
  const [reason, setReason] = React.useState("");
  const [submitting, setSubmitting] = React.useState(false);
  const [validationError, setValidationError] = React.useState<string | null>(
    null,
  );
  const reasonId = React.useId();

  // Reset transient state whenever the dialog is opened.
  React.useEffect(() => {
    if (open) {
      setReason("");
      setValidationError(null);
      setSubmitting(false);
    }
  }, [open]);

  async function handleConfirm() {
    if (reason.trim().length < 1) {
      setValidationError("A reason is required to ban a user");
      return;
    }
    setValidationError(null);
    setSubmitting(true);
    try {
      const updated = await banUser(userId, reason.trim());
      toast.success("User has been banned");
      onBanned(updated);
      onOpenChange(false);
    } catch {
      toast.error("Failed to ban user. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !submitting && onOpenChange(o)}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Ban user</DialogTitle>
          <DialogDescription>
            This will suspend the user&apos;s account. They will be unable to log
            in or place bets. Their wallet balance will be frozen.
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-2">
          <Label htmlFor={reasonId}>Reason (required)</Label>
          <Textarea
            id={reasonId}
            value={reason}
            onChange={(e) => {
              setReason(e.target.value);
              if (validationError) setValidationError(null);
            }}
            placeholder="Enter the reason for banning this user..."
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
            Confirm ban
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

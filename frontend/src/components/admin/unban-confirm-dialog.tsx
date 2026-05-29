/**
 * Plan 08-03 — Unban confirmation dialog (ADU-05, D-01/D-04).
 *
 * Same pattern as BanConfirmDialog but the reason is OPTIONAL (backend accepts
 * `reason?: string | null`, extra="forbid"; `unbanUser` sends it only when
 * non-empty). "Confirm unban" button uses the `default` variant. On success:
 * toast "User has been unbanned", dialog closes, parent refetches via
 * `onUnbanned(updated)`. Copywriting verbatim from UI-SPEC.
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
import { unbanUser } from "@/lib/admin-api";
import type { UserDetail } from "@/lib/admin-types";

export function UnbanConfirmDialog({
  open,
  onOpenChange,
  userId,
  onUnbanned,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  userId: string;
  onUnbanned: (updated: UserDetail) => void;
}) {
  const [reason, setReason] = React.useState("");
  const [submitting, setSubmitting] = React.useState(false);
  const reasonId = React.useId();

  React.useEffect(() => {
    if (open) {
      setReason("");
      setSubmitting(false);
    }
  }, [open]);

  async function handleConfirm() {
    setSubmitting(true);
    try {
      const trimmed = reason.trim();
      const updated = await unbanUser(
        userId,
        trimmed.length > 0 ? trimmed : undefined,
      );
      toast.success("User has been unbanned");
      onUnbanned(updated);
      onOpenChange(false);
    } catch {
      toast.error("Failed to unban user. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !submitting && onOpenChange(o)}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Unban user</DialogTitle>
          <DialogDescription>
            This will restore the user&apos;s account access. Their wallet
            balance will be restored as-is.
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-2">
          <Label htmlFor={reasonId}>Reason (optional)</Label>
          <Textarea
            id={reasonId}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Enter a reason for unbanning..."
            disabled={submitting}
          />
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
            variant="default"
            onClick={() => void handleConfirm()}
            disabled={submitting}
          >
            {submitting && (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            )}
            Confirm unban
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

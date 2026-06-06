/**
 * Plan 17-04 — Admin event detail client island (the action host).
 *
 * Clone of `market-detail-actions.tsx`: hosts the edit `EventForm` + the
 * status-gated Resolve / Void / Reverse dialogs, refreshing the Server Component
 * (`router.refresh()`) after any mutation. Gating is off the DERIVED event
 * status; mirrored (Polymarket) events are read-only (no mutate actions — they
 * settle via the upstream resolution).
 */
"use client";

import * as React from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { EventForm, type EventFormValues } from "@/components/admin/event-form";
import { ResolveEventDialog } from "@/components/admin/resolve-event-dialog";
import { VoidEventDialog } from "@/components/admin/void-event-dialog";
import { ReverseEventDialog } from "@/components/admin/reverse-event-dialog";
import type { EventDetail } from "@/lib/catalog";

/** Reshape an ISO timestamp to the `datetime-local` input value (local time). */
function toDatetimeLocal(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return (
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}` +
    `T${pad(d.getHours())}:${pad(d.getMinutes())}`
  );
}

export function EventDetailAdminActions({ event }: { event: EventDetail }) {
  const router = useRouter();
  const [resolveOpen, setResolveOpen] = React.useState(false);
  const [voidOpen, setVoidOpen] = React.useState(false);
  const [reverseOpen, setReverseOpen] = React.useState(false);

  const refresh = React.useCallback(() => router.refresh(), [router]);

  const isHouse = event.source === "HOUSE";
  const { status } = event;
  const canResolve =
    isHouse && (status === "open" || status === "partially_resolved");
  // Void (settle every outcome NO) only fits a fully-open event; a
  // partially-resolved one already has settled children that can't be re-settled.
  const canVoid = isHouse && status === "open";
  const canReverse =
    isHouse && (status === "resolved" || status === "partially_resolved");

  const initialValues: EventFormValues = {
    title: event.title,
    category: event.category ?? "",
    deadline: toDatetimeLocal(event.deadline),
    resolution_criteria: "",
    outcomes: event.outcomes.map((o) => ({
      label: o.label,
      initial_odds: o.yes_price,
    })),
  };

  const resolveOptions = event.outcomes.map((o) => ({
    label: o.label,
    yes_outcome_id: o.yes_outcome_id,
  }));

  if (!isHouse) {
    return (
      <div className="rounded-md border border-zinc-200 bg-zinc-50 p-4 text-sm text-zinc-600 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-400">
        This is a mirrored (Polymarket) event and is read-only. It settles
        automatically via the upstream resolution.
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-8">
      {(canResolve || canVoid || canReverse) && (
        <div className="flex flex-wrap items-center gap-3">
          {canResolve && (
            <Button
              type="button"
              variant="destructive"
              onClick={() => setResolveOpen(true)}
            >
              Resolve
            </Button>
          )}
          {canVoid && (
            <Button
              type="button"
              variant="destructive"
              onClick={() => setVoidOpen(true)}
            >
              Void
            </Button>
          )}
          {canReverse && (
            <Button
              type="button"
              variant="destructive"
              onClick={() => setReverseOpen(true)}
            >
              Reverse settlement
            </Button>
          )}
        </div>
      )}

      <EventForm mode="edit" groupId={event.id} initialValues={initialValues} />

      <ResolveEventDialog
        open={resolveOpen}
        onOpenChange={setResolveOpen}
        groupId={event.id}
        outcomes={resolveOptions}
        onResolved={refresh}
      />
      <VoidEventDialog
        open={voidOpen}
        onOpenChange={setVoidOpen}
        groupId={event.id}
        onVoided={refresh}
      />
      <ReverseEventDialog
        open={reverseOpen}
        onOpenChange={setReverseOpen}
        groupId={event.id}
        onReversed={refresh}
      />
    </div>
  );
}

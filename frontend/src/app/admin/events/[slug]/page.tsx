/**
 * Plan 17-04 — Admin event manage page.
 *
 * Loads the event via the PUBLIC `fetchEvent(slug)` (its `id` IS the group_id;
 * `outcomes[].yes_outcome_id` feeds the resolve dialog) and hands it to the
 * `EventDetailAdminActions` island (edit form + status-gated resolve/void/reverse
 * dialogs). Mirrors the admin market detail shell.
 */
import Link from "next/link";
import { ArrowLeft } from "lucide-react";

import { EventDetailAdminActions } from "@/components/admin/event-detail-admin-actions";
import { EventStatusBadge } from "@/components/event/event-status-badge";
import { SourceBadge } from "@/components/source-badge";
import { fetchEvent, type EventDetail } from "@/lib/catalog";

export const dynamic = "force-dynamic";

export default async function AdminEventDetailPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;

  let event: EventDetail | null = null;
  try {
    event = await fetchEvent(slug);
  } catch {
    event = null;
  }

  return (
    <div className="mx-auto max-w-6xl px-6 py-12">
      <Link
        href="/admin/events"
        className="mb-8 inline-flex items-center gap-1.5 text-sm text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-50"
      >
        <ArrowLeft className="h-4 w-4" aria-hidden="true" />
        Back to events
      </Link>

      {event ? (
        <>
          <header className="mb-8 flex flex-wrap items-center gap-3">
            <h1 className="text-3xl font-semibold tracking-tight">
              {event.title}
            </h1>
            <SourceBadge source={event.source} sourceUrl={null} />
            <EventStatusBadge status={event.status} />
          </header>
          <EventDetailAdminActions event={event} />
        </>
      ) : (
        <div className="py-12 text-center">
          <p className="text-sm font-medium text-red-700 dark:text-red-400">
            Event not found
          </p>
          <p className="mt-1 text-sm text-zinc-500">
            This event doesn&apos;t exist or could not be loaded.
          </p>
        </div>
      )}
    </div>
  );
}

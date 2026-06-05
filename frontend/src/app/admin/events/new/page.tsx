/**
 * Plan 17-04 — Admin "create event" page. Renders the EventForm in create mode.
 */
import { EventForm } from "@/components/admin/event-form";

export default function AdminNewEventPage() {
  return (
    <div className="mx-auto max-w-6xl px-6 py-12">
      <h1 className="mb-8 text-xl font-semibold tracking-tight">Create event</h1>
      <EventForm mode="create" />
    </div>
  );
}

/**
 * Plan 17-04 — Admin events list page.
 *
 * No admin list endpoint exists in the Phase-16 contract; house events surface
 * in the PUBLIC catalog, so this Server Component reads `fetchCatalog()` and
 * filters to `type:"event" && source:"HOUSE"`. Degrades to empty on failure.
 * A top-right "Create event" links to the create route; rows link to the manage
 * page by slug.
 */
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { fetchCatalog, type CatalogItem } from "@/lib/catalog";

export const dynamic = "force-dynamic";

export default async function AdminEventsPage() {
  let events: CatalogItem[] = [];
  try {
    const items = await fetchCatalog({ sort: "newest" });
    events = items.filter((i) => i.type === "event" && i.source === "HOUSE");
  } catch {
    events = [];
  }

  return (
    <div className="mx-auto max-w-6xl px-6 py-12">
      <div className="mb-8 flex items-center justify-between gap-4">
        <h1 className="text-xl font-semibold tracking-tight">Events</h1>
        <Button asChild>
          <Link href="/admin/events/new">Create event</Link>
        </Button>
      </div>

      {events.length === 0 ? (
        <p className="py-12 text-center text-sm text-muted-foreground">
          No house events yet.
        </p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead className="bg-surface text-left text-xs uppercase tracking-wide text-muted-foreground">
              <tr>
                <th className="px-4 py-3 font-medium">Title</th>
                <th className="px-4 py-3 font-medium">Category</th>
                <th className="px-4 py-3 font-medium">Outcomes</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {events.map((e) => (
                <tr
                  key={e.id}
                  className="border-t border-border transition-colors hover:bg-surface"
                >
                  <td className="px-4 py-3 font-medium">{e.title}</td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {e.category ?? "—"}
                  </td>
                  <td className="px-4 py-3 tabular-nums">{e.outcomes.length}</td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {e.status}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <Link
                      href={`/admin/events/${e.slug}`}
                      className="text-sm font-medium text-foreground underline"
                    >
                      Manage
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

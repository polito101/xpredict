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
        <p className="py-12 text-center text-sm text-zinc-500">
          No house events yet.
        </p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-zinc-200 dark:border-zinc-800">
          <table className="w-full text-sm">
            <thead className="bg-zinc-50 text-left text-xs uppercase tracking-wide text-zinc-500 dark:bg-zinc-900">
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
                  className="border-t border-zinc-100 dark:border-zinc-800"
                >
                  <td className="px-4 py-3 font-medium">{e.title}</td>
                  <td className="px-4 py-3 text-zinc-600 dark:text-zinc-400">
                    {e.category ?? "—"}
                  </td>
                  <td className="px-4 py-3 tabular-nums">{e.outcomes.length}</td>
                  <td className="px-4 py-3 text-zinc-600 dark:text-zinc-400">
                    {e.status}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <Link
                      href={`/admin/events/${e.slug}`}
                      className="text-sm font-medium text-zinc-900 underline dark:text-zinc-50"
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

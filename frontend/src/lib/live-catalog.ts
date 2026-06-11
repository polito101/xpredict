/**
 * Live-bets multi-table catalog (live multi-table plan, 2026-06-11).
 *
 * SERVER-ONLY: parses the `LIVEBETS_TABLES` env var (no `NEXT_PUBLIC_` prefix,
 * so it is read at request time on the server and never baked into the client
 * bundle — table changes need an env edit + container recreate, NOT a rebuild).
 *
 * Shape: JSON array of `{ slug, label, tableId }`:
 *   [{"slug":"cars","label":"Cars","tableId":"<uuid>"},
 *    {"slug":"birds","label":"Birds","tableId":"<uuid>"}]
 *
 * Contract: malformed input NEVER throws. Bad JSON / non-array → empty catalog
 * (the `/live` page then falls back to the single-default-table flow, exactly
 * the pre-catalog behavior). Malformed entries and duplicate slugs are dropped
 * with a console.warn (first occurrence of a slug wins).
 */

export interface LiveCatalogEntry {
  /** URL segment for /live/[slug] — lowercase, [a-z0-9-], 1..32 chars. */
  slug: string;
  /** Human label: picker card title AND the widget HUD `counter-label`. */
  label: string;
  /** live-bets table UUID, forwarded to LB-A `POST /api/live/session`. */
  tableId: string;
  /** Optional picker card subtitle (≤80 chars); absent → shared default copy. */
  tagline?: string;
}

const SLUG_RE = /^[a-z0-9-]{1,32}$/;

export function getLiveCatalog(): LiveCatalogEntry[] {
  const raw = process.env.LIVEBETS_TABLES;
  if (!raw) return [];

  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    console.warn("LIVEBETS_TABLES is not valid JSON — ignoring the catalog.");
    return [];
  }
  if (!Array.isArray(parsed)) {
    console.warn("LIVEBETS_TABLES must be a JSON array — ignoring the catalog.");
    return [];
  }

  const entries: LiveCatalogEntry[] = [];
  const seen = new Set<string>();
  for (const item of parsed) {
    const o = item as Record<string, unknown> | null;
    const slug = typeof o?.slug === "string" ? o.slug : "";
    const label = typeof o?.label === "string" ? o.label.trim() : "";
    const tableId = typeof o?.tableId === "string" ? o.tableId.trim() : "";
    if (!SLUG_RE.test(slug) || !label || label.length > 40 || !tableId || seen.has(slug)) {
      console.warn(`LIVEBETS_TABLES: dropping malformed/duplicate entry ${JSON.stringify(item)}`);
      continue;
    }
    seen.add(slug);
    // Optional picker tagline: a malformed one drops silently to the picker's
    // shared default copy — it must never invalidate the entry itself.
    const tagline =
      typeof o?.tagline === "string" && o.tagline.trim() && o.tagline.trim().length <= 80
        ? o.tagline.trim()
        : undefined;
    entries.push(tagline ? { slug, label, tableId, tagline } : { slug, label, tableId });
  }
  return entries;
}

export function findLiveTable(slug: string): LiveCatalogEntry | undefined {
  return getLiveCatalog().find((e) => e.slug === slug);
}

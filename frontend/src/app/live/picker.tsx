/**
 * Visual multi-table picker for `/live` (catalog configured): one hero card per
 * live table, linking to `/live/[slug]`.
 *
 * Each card is a full-bleed REAL frame from that table's camera (convention:
 * `public/live/<slug>.jpg`, checked server-side with `fs.existsSync` — this is
 * a Server Component) under a dark gradient, with a pulsing LIVE badge, the
 * catalog label in display type, and the catalog `tagline` (or a shared
 * default). Slugs without a frame asset fall back to a brand gradient — never
 * a broken <img>.
 *
 * Chrome + balance stay on this page: there is no widget here, so the balance
 * header is NOT a duplicate (same rationale as the empty state). The images
 * are pre-compressed stills served from /public — `unoptimized` skips the
 * Next image optimizer (nothing to gain on a one-off 70 KB JPG) and keeps the
 * raw `/live/<slug>.jpg` src.
 */
import fs from "node:fs";
import path from "node:path";
import Image from "next/image";
import Link from "next/link";

import type { LiveCatalogEntry } from "@/lib/live-catalog";

import { BalanceHeader, LiveShell } from "./shared";

const DEFAULT_TAGLINE =
  "Multiplayer live table — join the round and bet in real time.";

/** Convention: a hero frame for a table lives at `public/live/<slug>.jpg`. */
function hasCardImage(slug: string): boolean {
  try {
    return fs.existsSync(
      path.join(process.cwd(), "public", "live", `${slug}.jpg`),
    );
  } catch {
    return false;
  }
}

export function LiveCatalogPicker({
  entries,
  balance,
}: {
  entries: LiveCatalogEntry[];
  balance: string | null;
}) {
  return (
    <LiveShell>
      {balance !== null && <BalanceHeader balance={balance} />}
      <div className="grid gap-6 sm:grid-cols-2">
        {entries.map((e) => (
          <Link
            key={e.slug}
            href={`/live/${e.slug}`}
            data-testid={`live-card-${e.slug}`}
            className="group relative block overflow-hidden rounded-2xl border border-border shadow-lg transition-shadow duration-300 hover:shadow-2xl focus-visible:outline-2 focus-visible:outline-offset-2"
          >
            <div className="relative aspect-[16/10]">
              {hasCardImage(e.slug) ? (
                <Image
                  src={`/live/${e.slug}.jpg`}
                  alt=""
                  fill
                  unoptimized
                  className="object-cover transition-transform duration-500 group-hover:scale-105"
                />
              ) : (
                <div
                  data-testid="live-card-fallback"
                  aria-hidden
                  className="absolute inset-0 bg-gradient-to-br from-[--brand-primary] via-background to-background opacity-70"
                />
              )}
              {/* Readability scrim — the text sits on real video frames. */}
              <div
                aria-hidden
                className="absolute inset-0 bg-gradient-to-t from-black/85 via-black/25 to-black/10"
              />
              <span
                data-testid="live-badge"
                className="absolute left-4 top-4 inline-flex items-center gap-1.5 rounded-full bg-black/55 px-3 py-1 text-xs font-semibold uppercase tracking-widest text-white backdrop-blur-sm"
              >
                <span aria-hidden className="relative flex h-2 w-2">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-red-500 opacity-75" />
                  <span className="relative inline-flex h-2 w-2 rounded-full bg-red-500" />
                </span>
                Live
              </span>
              <div className="absolute inset-x-0 bottom-0 p-5 sm:p-6">
                <h2 className="font-display text-3xl font-semibold tracking-tight text-white sm:text-4xl">
                  {e.label}
                </h2>
                <p className="mt-1.5 max-w-[40ch] text-sm leading-relaxed text-white/75">
                  {e.tagline ?? DEFAULT_TAGLINE}
                </p>
                <span className="mt-3 inline-flex translate-y-1 items-center gap-1.5 text-sm font-semibold text-white opacity-0 transition duration-300 group-hover:translate-y-0 group-hover:opacity-100 group-focus-visible:translate-y-0 group-focus-visible:opacity-100">
                  Join the table <span aria-hidden>→</span>
                </span>
              </div>
            </div>
          </Link>
        ))}
      </div>
    </LiveShell>
  );
}

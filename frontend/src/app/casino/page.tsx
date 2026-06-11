/**
 * Casino (demo) — SlotsLaunch demo-slots surface (quick task 260611-u0q).
 *
 * An async Server Component (behind auth — the edge middleware gates `/casino`):
 * fetches the catalog server-side (`cache:"no-store"`, fresh per render) and renders
 * either a thumbnail grid (active) or a friendly "not available yet" empty state
 * (inactive OR empty). It NEVER shows an error or a blank/zero grid for the inactive
 * case — a degraded state must read as intentional (v1.1 Fase C error contract).
 *
 * The SlotsLaunch subscription is not active today, so the default render is the
 * empty state; the grid lights up with ZERO code changes once the free plan is
 * activated (the backend simply starts returning `status:"active"`).
 *
 * Token safety: the page only ever receives backend-composed `iframe_url`s — the raw
 * token never reaches the client bundle (T-u0q-02).
 */
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { fetchCasinoGames } from "@/lib/casino";

import { CasinoGrid } from "./casino-grid";

const PAGE_SHELL = "w-full max-w-6xl mx-auto px-4 sm:px-6 py-10";

export default async function CasinoPage() {
  const catalog = await fetchCasinoGames();
  const isAvailable = catalog.status === "active" && catalog.games.length > 0;

  return (
    <main className={PAGE_SHELL}>
      <header className="mb-8 flex flex-col gap-1">
        <h1 className="font-display text-3xl font-semibold tracking-tight">
          Casino
        </h1>
        <p className="text-sm text-muted-foreground">
          Demo slots — play-money games, just for the demo.
        </p>
      </header>

      {isAvailable ? (
        <CasinoGrid games={catalog.games} />
      ) : (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg font-semibold">
              Casino demo not available yet
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm leading-relaxed text-muted-foreground">
              The demo slots aren&apos;t live in this environment yet. Once the
              demo catalog is enabled, the games will appear here — ready to play
              in a fullscreen launcher.
            </p>
          </CardContent>
        </Card>
      )}
    </main>
  );
}

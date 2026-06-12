/**
 * CasinoGrid — responsive thumbnail grid of demo slots (quick task 260611-u0q).
 *
 * Client Component: owns the selected-game state. Each tile shows the `thumb`
 * (plain `<img>` with `object-cover`; a name-initial placeholder when `thumb` is
 * null) + name + provider. Clicking a tile opens the `GameLauncher` for THAT game
 * ONLY — the grid itself renders NO iframe, so a game's upstream quota request is
 * spent exclusively on an explicit click (T-u0q-03, never preload/autoplay).
 *
 * `next/image` is deliberately NOT used: thumb URLs come from the SlotsLaunch CDN
 * (arbitrary remote hosts) and the app has no `images.remotePatterns` allow-list,
 * so a plain `<img>` is the robust choice (and the plan explicitly permits it).
 */
"use client";

import { useState } from "react";

import type { CasinoGame } from "@/lib/casino";
import { cn } from "@/lib/utils";

import { GameLauncher } from "./game-launcher";

const FOCUS_RING =
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background";

export function CasinoGrid({ games }: { games: CasinoGame[] }) {
  const [selected, setSelected] = useState<CasinoGame | null>(null);

  return (
    <>
      <ul className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
        {games.map((game) => (
          <li key={game.id}>
            <button
              type="button"
              onClick={() => setSelected(game)}
              className={cn(
                "group flex w-full flex-col overflow-hidden rounded-2xl border border-border bg-card text-left transition-colors hover:border-border-strong",
                FOCUS_RING,
              )}
            >
              <div className="relative aspect-[4/3] w-full overflow-hidden bg-muted">
                {game.thumb ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={game.thumb}
                    alt={game.name}
                    loading="lazy"
                    className="h-full w-full object-cover transition-transform duration-200 group-hover:scale-105"
                  />
                ) : (
                  <span className="grid h-full w-full place-items-center bg-gradient-brand text-2xl font-semibold text-brand-primary-foreground">
                    {game.name.charAt(0).toUpperCase() || "?"}
                  </span>
                )}
              </div>
              <div className="flex flex-col gap-0.5 p-3">
                <span className="truncate text-sm font-medium text-foreground">
                  {game.name}
                </span>
                {game.provider && (
                  <span className="truncate text-xs text-muted-foreground">
                    {game.provider}
                  </span>
                )}
              </div>
            </button>
          </li>
        ))}
      </ul>

      {selected && (
        <GameLauncher game={selected} onClose={() => setSelected(null)} />
      )}
    </>
  );
}

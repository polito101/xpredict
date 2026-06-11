/**
 * GameLauncher — fullscreen iframe launcher for one SlotsLaunch demo slot.
 *
 * Mirrors `LiveFullscreenHost` (`live/shared.tsx`): a `fixed inset-0 z-50` black
 * overlay that covers the SiteFrame chrome, with a close affordance (X) that clears
 * the selection. A SINGLE `<iframe src={game.iframe_url}>` fills the overlay; the
 * grid never renders an iframe, so a game's quota request is spent ONLY on an
 * explicit click (T-u0q-03).
 *
 * The iframe `src` is the backend-composed URL (it carries the domain-bound token —
 * SlotsLaunch's documented model; the frontend never sees the raw env var). The
 * token is domain-bound to the live deploy domain, so from localhost the iframe may
 * 403. An `onError` handler + a visible fallback message turn that into a graceful
 * "couldn't load here" state, NOT a broken frame — this is expected, not a bug
 * (CONTEXT / must-have #4).
 */
"use client";

import { useState } from "react";
import { X } from "lucide-react";

import type { CasinoGame } from "@/lib/casino";

export function GameLauncher({
  game,
  onClose,
}: {
  game: CasinoGame;
  onClose: () => void;
}) {
  const [failed, setFailed] = useState(false);

  return (
    <div
      data-testid="casino-launcher"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black"
      role="dialog"
      aria-modal="true"
      aria-label={`${game.name} demo`}
    >
      <button
        type="button"
        onClick={onClose}
        aria-label="Close game"
        className="absolute right-4 top-4 z-10 grid h-11 w-11 place-items-center rounded-full border border-white/20 bg-black/50 text-white transition-colors hover:bg-black/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/60"
      >
        <X className="h-5 w-5" />
      </button>

      {failed ? (
        <div
          role="status"
          className="mx-auto flex max-w-md flex-col items-center px-6 text-center text-white"
        >
          <h2 className="text-lg font-semibold">
            This demo game couldn&apos;t load here
          </h2>
          <p className="mt-2 text-sm text-white/70">
            It may be restricted to the live domain. Try again on the deployed
            site.
          </p>
        </div>
      ) : (
        <iframe
          src={game.iframe_url}
          title={game.name}
          allow="fullscreen; autoplay"
          allowFullScreen
          onError={() => setFailed(true)}
          className="h-full w-full border-0"
        />
      )}
    </div>
  );
}

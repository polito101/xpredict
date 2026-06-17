/**
 * LiveOrientationGate — the live widget runs in a hard-16:9 fullscreen stage
 * (see `LiveFullscreenHost`). In portrait that stage letterboxes to a thin band
 * with huge black bars top/bottom, so below landscape we show a "rotate your
 * device" prompt instead — and we DON'T render the widget (the children) until
 * the viewport is landscape, so portrait never mounts the socket / external
 * widget script for a view the player can't use.
 *
 * Orientation is read via `useSyncExternalStore` over `matchMedia` — the React-
 * idiomatic way to subscribe to a browser store (no setState-in-effect). SSR and
 * the first hydration render assume landscape; since the host is a black overlay
 * either way there's no chrome flash, and portrait resolves to the prompt right
 * after hydration. When `matchMedia` is unavailable (e.g. jsdom) we assume
 * landscape so the widget still mounts.
 */
"use client";

import { useSyncExternalStore } from "react";
import { RotateCw } from "lucide-react";

const PORTRAIT_QUERY = "(orientation: portrait)";

function subscribe(onChange: () => void): () => void {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
    return () => {};
  }
  const mq = window.matchMedia(PORTRAIT_QUERY);
  mq.addEventListener("change", onChange);
  return () => mq.removeEventListener("change", onChange);
}

function getSnapshot(): boolean {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
    return false; // orientation unknowable → assume landscape so the widget mounts
  }
  return window.matchMedia(PORTRAIT_QUERY).matches;
}

// SSR + first hydration render can't know the device orientation, so assume
// landscape (the host is black either way → no chrome flash).
function getServerSnapshot(): boolean {
  return false;
}

export function LiveOrientationGate({
  children,
}: {
  children: React.ReactNode;
}) {
  const isPortrait = useSyncExternalStore(
    subscribe,
    getSnapshot,
    getServerSnapshot,
  );

  if (isPortrait) return <LiveRotatePrompt />;
  return <>{children}</>;
}

function LiveRotatePrompt() {
  return (
    <main
      data-testid="live-rotate-prompt"
      className="fixed inset-0 z-50 flex flex-col items-center justify-center gap-5 bg-black px-8 text-center"
    >
      <RotateCw
        className="h-12 w-12 text-muted-foreground"
        aria-hidden="true"
      />
      <div className="flex flex-col gap-1.5">
        <p className="font-display text-xl font-semibold text-foreground">
          Rotate your device
        </p>
        <p className="max-w-xs text-sm leading-relaxed text-muted-foreground">
          Live runs in landscape — turn your device sideways to play.
        </p>
      </div>
    </main>
  );
}

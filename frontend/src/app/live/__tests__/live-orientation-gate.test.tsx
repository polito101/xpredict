/**
 * LiveOrientationGate tests — the /live fullscreen widget runs in a hard-16:9
 * stage that letterboxes badly in portrait, so the gate swaps to a "rotate"
 * prompt below landscape and (critically) does NOT mount the children there.
 *
 * jsdom has no real `matchMedia`, so each test installs a stub; the no-stub case
 * asserts the defensive "assume landscape" fallback.
 */
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";

import { LiveOrientationGate } from "../live-orientation-gate";

function mockOrientation(portrait: boolean) {
  window.matchMedia = vi.fn().mockReturnValue({
    matches: portrait,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  } as unknown as MediaQueryList) as unknown as typeof window.matchMedia;
}

afterEach(() => {
  vi.restoreAllMocks();
  // @ts-expect-error — reset the per-test matchMedia stub
  delete window.matchMedia;
});

describe("LiveOrientationGate", () => {
  it("shows the rotate prompt and does NOT mount children in portrait", () => {
    mockOrientation(true);
    render(
      <LiveOrientationGate>
        <div data-testid="live-widget">widget</div>
      </LiveOrientationGate>,
    );
    expect(screen.queryByTestId("live-rotate-prompt")).not.toBeNull();
    expect(screen.queryByText("Rotate your device")).not.toBeNull();
    // The widget must not mount in portrait (no wasted socket / script load).
    expect(screen.queryByTestId("live-widget")).toBeNull();
  });

  it("mounts children and hides the prompt in landscape", () => {
    mockOrientation(false);
    render(
      <LiveOrientationGate>
        <div data-testid="live-widget">widget</div>
      </LiveOrientationGate>,
    );
    expect(screen.queryByTestId("live-widget")).not.toBeNull();
    expect(screen.queryByTestId("live-rotate-prompt")).toBeNull();
  });

  it("assumes landscape (mounts children) when matchMedia is unavailable", () => {
    // No matchMedia stub installed → defensive fallback path.
    render(
      <LiveOrientationGate>
        <div data-testid="live-widget">widget</div>
      </LiveOrientationGate>,
    );
    expect(screen.queryByTestId("live-widget")).not.toBeNull();
    expect(screen.queryByTestId("live-rotate-prompt")).toBeNull();
  });
});

/**
 * XParticles smoke tests. jsdom has no real canvas/matchMedia/ResizeObserver,
 * so all three are stubbed; assertions target lifecycle behavior (loop vs
 * static frame, cleanup), not pixels.
 */
import { cleanup, render } from "@testing-library/react";
import {
  afterEach,
  beforeEach,
  describe,
  expect,
  it,
  vi,
  type MockInstance,
} from "vitest";

import { XParticles } from "./x-particles";

type MqListener = (e: { matches: boolean }) => void;

function makeFakeCtx() {
  return {
    setTransform: vi.fn(),
    clearRect: vi.fn(),
    beginPath: vi.fn(),
    moveTo: vi.fn(),
    lineTo: vi.fn(),
    stroke: vi.fn(),
    arc: vi.fn(),
    fill: vi.fn(),
    strokeStyle: "",
    fillStyle: "",
    lineWidth: 1,
  };
}

function stubMatchMedia(reduced: boolean) {
  const addEventListener = vi.fn<(t: string, l: MqListener) => void>();
  const removeEventListener = vi.fn();
  window.matchMedia = vi.fn().mockReturnValue({
    matches: reduced,
    addEventListener,
    removeEventListener,
  } as unknown as MediaQueryList) as unknown as typeof window.matchMedia;
  return { addEventListener, removeEventListener };
}

class FakeResizeObserver {
  observe = vi.fn();
  disconnect = vi.fn();
}

describe("XParticles", () => {
  let fakeCtx: ReturnType<typeof makeFakeCtx>;
  let rafSpy: MockInstance<typeof window.requestAnimationFrame>;
  let cafSpy: MockInstance<typeof window.cancelAnimationFrame>;

  beforeEach(() => {
    fakeCtx = makeFakeCtx();
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(
      fakeCtx as unknown as CanvasRenderingContext2D,
    );
    rafSpy = vi.spyOn(window, "requestAnimationFrame").mockReturnValue(1);
    cafSpy = vi.spyOn(window, "cancelAnimationFrame").mockImplementation(() => {});
    vi.stubGlobal("ResizeObserver", FakeResizeObserver);
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("mounts an aria-hidden canvas and starts the animation loop", () => {
    stubMatchMedia(false);
    const { container } = render(<XParticles />);
    const canvas = container.querySelector("canvas");
    expect(canvas).not.toBeNull();
    expect(container.firstElementChild).toHaveAttribute("aria-hidden", "true");
    expect(rafSpy).toHaveBeenCalled();
  });

  it("draws a single static frame (no loop) under prefers-reduced-motion", () => {
    stubMatchMedia(true);
    render(<XParticles />);
    expect(rafSpy).not.toHaveBeenCalled();
    expect(fakeCtx.clearRect).toHaveBeenCalledTimes(1);
  });

  it("cleans up rAF and media-query listener on unmount", () => {
    const mq = stubMatchMedia(false);
    const { unmount } = render(<XParticles />);
    unmount();
    expect(cafSpy).toHaveBeenCalled();
    expect(mq.removeEventListener).toHaveBeenCalled();
  });
});

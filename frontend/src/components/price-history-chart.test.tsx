/**
 * Plan 09-03 Task 3 -- PriceHistoryChart tests.
 *
 * The headline assertion is the **react-is sentinel**: with >=2 points the
 * Recharts <LineChart> must render an SVG `path` element. If `react-is` were
 * mismatched against React 19 (RESEARCH Pitfall 1), Recharts renders nothing
 * and this test goes red — so a green `path` assertion proves the pnpm
 * override collapsed react-is to the installed React version.
 *
 * Recharts' <ResponsiveContainer> measures its parent via ResizeObserver,
 * which jsdom does not implement and which reports 0x0 dimensions. We stub
 * ResizeObserver and force a non-zero element box so the container can size
 * and actually paint the SVG (the standard documented way to test Recharts
 * under jsdom). This is a real render assertion, not a mock of the chart.
 */

import { describe, it, expect, vi, beforeAll } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

beforeAll(() => {
  // jsdom has no ResizeObserver — Recharts ResponsiveContainer needs one and
  // measures its parent through it. Fire the callback with a non-zero box on
  // observe() so ResponsiveContainer resolves width/height > 0 and actually
  // paints the SVG (otherwise it stays at -1x-1 and logs a warning).
  class ResizeObserverStub {
    private cb: ResizeObserverCallback;
    constructor(cb: ResizeObserverCallback) {
      this.cb = cb;
    }
    observe(el: Element) {
      this.cb(
        [{ contentRect: { width: 640, height: 256 } } as ResizeObserverEntry],
        this as unknown as ResizeObserver,
      );
    }
    unobserve() {}
    disconnect() {}
  }
  vi.stubGlobal("ResizeObserver", ResizeObserverStub);

  Object.defineProperty(HTMLElement.prototype, "getBoundingClientRect", {
    configurable: true,
    value: () => ({
      width: 640,
      height: 256,
      top: 0,
      left: 0,
      right: 640,
      bottom: 256,
      x: 0,
      y: 0,
      toJSON: () => {},
    }),
  });
});

import { PriceHistoryChart } from "@/components/price-history-chart";
import type { PricePoint } from "@/lib/api";

const threePoints: PricePoint[] = [
  { ts: "2026-05-27T00:00:00Z", probability: "0.42" },
  { ts: "2026-05-28T00:00:00Z", probability: "0.55" },
  { ts: "2026-05-29T00:00:00Z", probability: "0.61" },
];

describe("<PriceHistoryChart />", () => {
  it("renders an SVG path for >=2 points (react-is sentinel — chart not blank)", () => {
    const { container } = render(
      <PriceHistoryChart
        points={threePoints}
        window="7d"
        onWindowChange={() => {}}
      />,
    );
    // The emerald YES line is an SVG <path>. If react-is were mismatched
    // against React 19, Recharts renders nothing and querySelector returns
    // null — so a non-null path proves the pnpm override is in effect.
    const path = container.querySelector("svg path");
    expect(path).not.toBeNull();
    // And it is specifically the Recharts line curve, not an incidental icon.
    expect(
      container.querySelector("path.recharts-line-curve"),
    ).not.toBeNull();
  });

  it("renders the empty-state copy for <2 points", () => {
    render(
      <PriceHistoryChart
        points={[threePoints[0]]}
        window="7d"
        onWindowChange={() => {}}
      />,
    );
    expect(
      screen.getByText("Not enough price history yet"),
    ).toBeInTheDocument();
  });

  it("renders the 24h / 7d / 30d toggle with 7d active by default", () => {
    render(
      <PriceHistoryChart
        points={threePoints}
        window="7d"
        onWindowChange={() => {}}
      />,
    );
    expect(screen.getByRole("button", { name: "24h" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "7d" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "30d" })).toBeInTheDocument();
    // The active window button is marked aria-pressed=true.
    expect(screen.getByRole("button", { name: "7d" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("calls onWindowChange when a different window is clicked", async () => {
    const onWindowChange = vi.fn();
    render(
      <PriceHistoryChart
        points={threePoints}
        window="7d"
        onWindowChange={onWindowChange}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: "30d" }));
    expect(onWindowChange).toHaveBeenCalledWith("30d");
  });
});

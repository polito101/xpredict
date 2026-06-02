/**
 * Plan 10-04 Task 1 (Wave 0) — VolumeChart tests.
 *
 * Headline assertion is the **react-is sentinel** (mirrors
 * price-history-chart.test.tsx): with >=1 daily bucket the Recharts
 * <AreaChart> must render an SVG `path` element. If `react-is` were
 * mismatched against React 19 (RESEARCH Pitfall / T-10-16), Recharts renders
 * nothing and the assertion goes red — so a green `path.recharts-area-area`
 * proves the pnpm.overrides react-is pin collapsed to the installed React.
 *
 * Recharts' <ResponsiveContainer> measures its parent via ResizeObserver,
 * which jsdom does not implement and which reports 0x0 dimensions. We stub
 * ResizeObserver and force a non-zero element box (copied VERBATIM from
 * price-history-chart.test.tsx) so the container sizes and actually paints the
 * SVG. This is a real render assertion under jsdom, not a mock of the chart.
 *
 * The <1-bucket case asserts the VolumeChartEmptyState at the same h-64 height
 * with the EXACT 10-UI-SPEC §Copywriting copy ("No activity yet" /
 * "Volume appears here as players place bets.") — no blank Recharts axis.
 */

import { describe, it, expect, vi, beforeAll } from "vitest";
import { render, screen } from "@testing-library/react";

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
    observe() {
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

import { VolumeChart } from "@/components/admin/volume-chart";
import { DauWindowToggle } from "@/components/admin/dau-window-toggle";
import type { VolumeBucket } from "@/lib/kpi-types";

const buckets: VolumeBucket[] = [
  { day: "2026-05-27T00:00:00Z", volume: "120.0000" },
  { day: "2026-05-28T00:00:00Z", volume: "340.5000" },
  { day: "2026-05-29T00:00:00Z", volume: "275.2500" },
];

describe("<VolumeChart />", () => {
  it("renders an SVG area path for >=1 bucket (react-is sentinel — chart not blank)", () => {
    const { container } = render(<VolumeChart buckets={buckets} />);
    // The volume area is an SVG <path>. If react-is were mismatched against
    // React 19, Recharts renders nothing and querySelector returns null — so a
    // non-null path proves the pnpm.overrides react-is pin is in effect.
    const path = container.querySelector("svg path");
    expect(path).not.toBeNull();
    // And it is specifically the Recharts area fill, not an incidental icon.
    expect(
      container.querySelector("path.recharts-area-area"),
    ).not.toBeNull();
  });

  it("renders the empty-state copy at h-64 for <1 bucket (no blank axis)", () => {
    const { container } = render(<VolumeChart buckets={[]} />);
    // No Recharts SVG renders — the empty state replaces the chart.
    expect(container.querySelector("svg path")).toBeNull();
    expect(screen.getByText("No activity yet")).toBeInTheDocument();
    expect(
      screen.getByText("Volume appears here as players place bets."),
    ).toBeInTheDocument();
    // The empty state occupies the SAME fixed h-64 box (no layout jump).
    expect(container.querySelector(".h-64")).not.toBeNull();
  });

  it("renders the chart title 'Bet volume — last 30 days'", () => {
    render(<VolumeChart buckets={buckets} />);
    expect(screen.getByText("Bet volume — last 30 days")).toBeInTheDocument();
  });
});

describe("<DauWindowToggle />", () => {
  it("renders 24h / 7d / 30d buttons with 24h active by default", () => {
    render(<DauWindowToggle window="24h" onChange={() => {}} />);
    expect(screen.getByRole("button", { name: "24h" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "7d" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "30d" })).toBeInTheDocument();
    // The active (default 24h) button is marked aria-pressed=true.
    expect(screen.getByRole("button", { name: "24h" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });
});

/**
 * Plan 10-04 Task 2 — KpiCard / HousePnlCard color-logic tests.
 *
 * Guards the UI-SPEC §Color contract that SC#2 requires: House P&L money
 * values are colored by SIGN read from the STRING (no float coercion):
 *   - a NEGATIVE value renders with `text-red-500`
 *   - a POSITIVE (or zero) value renders with `text-emerald-600`
 *
 * Also guards money-as-string display (UI-SPEC A-ZERO): "0.0000" renders as a
 * real "$0.0000" (NOT "N/A"/em-dash) and the displayed text derives purely
 * from the string prop (no parseFloat-for-storage round-trip — "1234.5000"
 * shows "$1234.5000", not a locale-grouped float).
 *
 * Mirrors price-history-chart.test.tsx render/assert style (RTL + jsdom).
 */

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import {
  HousePnlCard,
  KpiCard,
  formatMoney,
  isNegativeMoney,
} from "@/components/admin/kpi-card";

describe("formatMoney (display-only, string ops)", () => {
  it("pads to 4 dp and prefixes $ without parseFloat round-trip", () => {
    expect(formatMoney("0.0000")).toBe("$0.0000");
    expect(formatMoney("0")).toBe("$0.0000");
    expect(formatMoney("340")).toBe("$340.0000");
    expect(formatMoney("1234.5")).toBe("$1234.5000");
    expect(formatMoney("-12.5000")).toBe("-$12.5000");
  });
});

describe("isNegativeMoney (sign from string)", () => {
  it("only true for a leading - with non-zero magnitude", () => {
    expect(isNegativeMoney("-12.5000")).toBe(true);
    expect(isNegativeMoney("0.0000")).toBe(false);
    expect(isNegativeMoney("-0.0000")).toBe(false);
    expect(isNegativeMoney("340.0000")).toBe(false);
  });
});

describe("<HousePnlCard /> color logic", () => {
  it("colors a NEGATIVE Today value red-500", () => {
    render(<HousePnlCard today="-12.5000" cumulative="340.0000" />);
    const today = screen.getByTestId("kpi-pnl-today");
    expect(today.className).toContain("text-red-500");
    expect(today).toHaveTextContent("-$12.5000");
  });

  it("colors a POSITIVE All-time value emerald-600", () => {
    render(<HousePnlCard today="-12.5000" cumulative="340.0000" />);
    const all = screen.getByTestId("kpi-pnl-all-time");
    expect(all.className).toContain("text-emerald-600");
    expect(all).toHaveTextContent("$340.0000");
  });

  it("renders a zero P&L as $0.0000 (not N/A) in emerald-600", () => {
    render(<HousePnlCard today="0.0000" cumulative="0.0000" />);
    const today = screen.getByTestId("kpi-pnl-today");
    expect(today).toHaveTextContent("$0.0000");
    expect(today).not.toHaveTextContent("N/A");
    expect(today.className).toContain("text-emerald-600");
  });
});

describe("<KpiCard /> money display", () => {
  it("renders the money string prop verbatim (no parseFloat-for-storage)", () => {
    render(<KpiCard label="24h bet volume" value={formatMoney("1234.5")} />);
    const value = screen.getByTestId("kpi-value");
    // The exact string "$1234.5000" — not "1,234.5" or a float-grouped form.
    expect(value).toHaveTextContent("$1234.5000");
  });

  it("renders a fresh-deploy zero as a real $0.0000, never N/A", () => {
    render(<KpiCard label="24h bet volume" value={formatMoney("0")} />);
    const value = screen.getByTestId("kpi-value");
    expect(value).toHaveTextContent("$0.0000");
    expect(value).not.toHaveTextContent("N/A");
  });
});

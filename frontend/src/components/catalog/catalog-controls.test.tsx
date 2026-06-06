/**
 * Plan 17-02 — CatalogControls tests (BRW-01/02/04).
 *
 * Proves: only the provided (non-empty) categories render as chips (+ "All"),
 * clicking a chip pushes `?category` to the URL, and the search input debounces
 * to `?q`. Radix Select dropdown interaction is not exercised (jsdom/portal
 * flakiness) — the URL-driving paths that matter are the chips + debounced search.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

const replace = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
  usePathname: () => "/",
  useSearchParams: () => new URLSearchParams(),
}));

import { CatalogControls } from "@/components/catalog/catalog-controls";

beforeEach(() => {
  replace.mockClear();
});

describe("<CatalogControls />", () => {
  it("renders only the provided categories plus an 'All' chip", () => {
    render(<CatalogControls categories={["Politics", "Crypto"]} />);
    expect(screen.getByRole("button", { name: "All" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Politics" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Crypto" })).toBeInTheDocument();
    // A category that was not provided never renders (empty categories hidden).
    expect(
      screen.queryByRole("button", { name: "Sports" }),
    ).not.toBeInTheDocument();
  });

  it("renders no category row when there are no categories", () => {
    render(<CatalogControls categories={[]} />);
    expect(
      screen.queryByRole("button", { name: "All" }),
    ).not.toBeInTheDocument();
  });

  it("clicking a category chip pushes ?category to the URL", () => {
    render(<CatalogControls categories={["Politics"]} />);
    fireEvent.click(screen.getByRole("button", { name: "Politics" }));
    expect(replace).toHaveBeenCalledWith("/?category=Politics");
  });

  it("the active chip is marked aria-pressed", () => {
    render(<CatalogControls categories={["Politics"]} category="Politics" />);
    expect(screen.getByRole("button", { name: "Politics" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("debounces the search input to ?q", async () => {
    render(<CatalogControls categories={[]} />);
    fireEvent.change(screen.getByLabelText("Search markets"), {
      target: { value: "btc" },
    });
    // Debounced — not fired synchronously.
    expect(replace).not.toHaveBeenCalled();
    await waitFor(
      () => expect(replace).toHaveBeenCalledWith("/?q=btc"),
      { timeout: 1000 },
    );
  });
});

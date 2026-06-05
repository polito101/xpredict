/**
 * Plan 17-04 — ResolveEventDialog tests (EVA-03 validation).
 *
 * Proves the resolve-specific gate: "Preview impact" with no winning outcome
 * selected shows the `role="alert"` error and never calls the server action.
 * (The shared preview→execute two-step is covered by the void dialog test,
 * which avoids the Radix Select portal that jsdom handles unreliably.)
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

const resolveEvent = vi.fn();
vi.mock("@/lib/admin-events-api", () => ({
  resolveEvent: (...a: unknown[]) => resolveEvent(...a),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { ResolveEventDialog } from "@/components/admin/resolve-event-dialog";

const onResolved = vi.fn();

beforeEach(() => {
  resolveEvent.mockReset();
  onResolved.mockReset();
});

describe("<ResolveEventDialog />", () => {
  it("requires a winning outcome before previewing", () => {
    render(
      <ResolveEventDialog
        open
        onOpenChange={() => {}}
        groupId="g-1"
        outcomes={[
          { label: "Alice", yes_outcome_id: "ya" },
          { label: "Bob", yes_outcome_id: "yb" },
        ]}
        onResolved={onResolved}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Preview impact" }));
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Select the winning outcome.",
    );
    expect(resolveEvent).not.toHaveBeenCalled();
  });
});

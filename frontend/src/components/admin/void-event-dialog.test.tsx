/**
 * Plan 17-04 — VoidEventDialog tests (EVA-04: the SERVER two-step confirm).
 *
 * Proves the justification gate, then the two-step: "Preview impact" calls
 * `voidEvent({confirm:false})` and renders the projected impact, and "Confirm
 * void" calls `voidEvent({confirm:true})` and fires `onVoided`. (Resolve/reverse
 * share this exact flow; resolve adds an outcome Select tested separately.)
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

const voidEvent = vi.fn();
vi.mock("@/lib/admin-events-api", () => ({
  voidEvent: (...a: unknown[]) => voidEvent(...a),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { VoidEventDialog } from "@/components/admin/void-event-dialog";

const onVoided = vi.fn();

beforeEach(() => {
  voidEvent.mockReset();
  onVoided.mockReset();
});

function renderDialog() {
  return render(
    <VoidEventDialog
      open
      onOpenChange={() => {}}
      groupId="g-1"
      onVoided={onVoided}
    />,
  );
}

describe("<VoidEventDialog />", () => {
  it("blocks preview with an empty justification (role=alert, no call)", () => {
    renderDialog();
    fireEvent.click(screen.getByRole("button", { name: "Preview impact" }));
    expect(screen.getByRole("alert")).toHaveTextContent(
      "A justification is required.",
    );
    expect(voidEvent).not.toHaveBeenCalled();
  });

  it("previews with confirm:false then executes with confirm:true", async () => {
    renderDialog();
    fireEvent.change(screen.getByLabelText("Justification (required)"), {
      target: { value: "Event cancelled upstream" },
    });

    voidEvent.mockResolvedValueOnce({
      preview: true,
      group_id: "g-1",
      child_count: 3,
      winners: 0,
      losers: 3,
      projected_status: "void",
    });
    fireEvent.click(screen.getByRole("button", { name: "Preview impact" }));
    await waitFor(() =>
      expect(voidEvent).toHaveBeenCalledWith("g-1", {
        justification: "Event cancelled upstream",
        confirm: false,
      }),
    );
    await waitFor(() =>
      expect(screen.getByText(/All 3 outcomes settle NO/i)).toBeInTheDocument(),
    );

    voidEvent.mockResolvedValueOnce({
      preview: false,
      group_id: "g-1",
      child_count: 3,
      children_settled: 3,
      projected_status: "void",
    });
    fireEvent.click(screen.getByRole("button", { name: "Confirm void" }));
    await waitFor(() =>
      expect(voidEvent).toHaveBeenCalledWith("g-1", {
        justification: "Event cancelled upstream",
        confirm: true,
      }),
    );
    expect(onVoided).toHaveBeenCalled();
  });
});

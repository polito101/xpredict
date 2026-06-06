/**
 * Plan 17-04 — EventForm tests (EVA-01/02).
 *
 * Proves the dynamic outcomes editor (≥2, add/remove with a 2-floor), that a
 * valid create posts a CreateEventRequest with ≥2 outcomes, and that a 423 on
 * edit locks the form + shows the lock banner.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

const push = vi.fn();
const refresh = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, refresh }),
}));

const createEvent = vi.fn();
const updateEvent = vi.fn();
vi.mock("@/lib/admin-events-api", () => ({
  createEvent: (...a: unknown[]) => createEvent(...a),
  updateEvent: (...a: unknown[]) => updateEvent(...a),
}));

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { EventForm } from "@/components/admin/event-form";

beforeEach(() => {
  push.mockClear();
  refresh.mockClear();
  createEvent.mockReset();
  updateEvent.mockReset();
});

describe("<EventForm /> create", () => {
  it("renders at least 2 outcome rows by default", () => {
    render(<EventForm mode="create" />);
    expect(screen.getByLabelText("Outcome 1 label")).toBeInTheDocument();
    expect(screen.getByLabelText("Outcome 2 label")).toBeInTheDocument();
  });

  it("'Add outcome' appends a row; remove is disabled at the 2-floor", () => {
    render(<EventForm mode="create" />);
    expect(screen.getByLabelText("Remove outcome 1")).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: /add outcome/i }));
    expect(screen.getByLabelText("Outcome 3 label")).toBeInTheDocument();
    expect(screen.getByLabelText("Remove outcome 1")).not.toBeDisabled();
  });

  it("submitting valid data posts a CreateEventRequest with >=2 outcomes", async () => {
    createEvent.mockResolvedValue({ slug: "who-wins" });
    render(<EventForm mode="create" />);
    fireEvent.change(screen.getByLabelText("Title"), {
      target: { value: "Who wins?" },
    });
    fireEvent.change(screen.getByLabelText("Deadline"), {
      target: { value: "2099-01-01T12:00" },
    });
    fireEvent.change(screen.getByLabelText("Outcome 1 label"), {
      target: { value: "Alice" },
    });
    fireEvent.change(screen.getByLabelText("Outcome 1 odds"), {
      target: { value: "0.6" },
    });
    fireEvent.change(screen.getByLabelText("Outcome 2 label"), {
      target: { value: "Bob" },
    });
    fireEvent.change(screen.getByLabelText("Outcome 2 odds"), {
      target: { value: "0.4" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create event" }));
    await waitFor(() => expect(createEvent).toHaveBeenCalled());
    const body = createEvent.mock.calls[0][0] as {
      title: string;
      outcomes: { label: string; initial_odds: string }[];
    };
    expect(body.title).toBe("Who wins?");
    expect(body.outcomes).toHaveLength(2);
    expect(body.outcomes[0]).toEqual({ label: "Alice", initial_odds: "0.6" });
  });
});

describe("<EventForm /> edit — 423 edit-lock", () => {
  it("a 423 locks the form and shows the lock banner", async () => {
    updateEvent.mockRejectedValue(new Error("API error: 423"));
    render(
      <EventForm
        mode="edit"
        groupId="g-1"
        initialValues={{
          title: "Who wins?",
          category: "Politics",
          deadline: "2099-01-01T12:00",
          resolution_criteria: "",
          outcomes: [
            { label: "Alice", initial_odds: "0.6" },
            { label: "Bob", initial_odds: "0.4" },
          ],
        }}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() =>
      expect(screen.getByText(/can no longer be edited/i)).toBeInTheDocument(),
    );
    expect(screen.getByLabelText("Title")).toBeDisabled();
  });
});

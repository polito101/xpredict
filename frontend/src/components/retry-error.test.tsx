import { describe, expect, test, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const refresh = vi.hoisted(() => vi.fn());
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

import { RetryError } from "./retry-error";

describe("<RetryError />", () => {
  test("shows the title in an alert region with a retry button", () => {
    render(<RetryError title="Couldn't load your wallet" />);
    expect(screen.getByRole("alert")).toHaveTextContent("Couldn't load your wallet");
    expect(
      screen.getByRole("button", { name: /try again/i }),
    ).toBeInTheDocument();
  });

  test("refreshes the route when retry is clicked", async () => {
    refresh.mockClear();
    render(<RetryError title="Couldn't load" />);
    await userEvent.click(screen.getByRole("button", { name: /try again/i }));
    expect(refresh).toHaveBeenCalledOnce();
  });
});

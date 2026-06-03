import { describe, expect, test } from "vitest";
import { render, screen } from "@testing-library/react";

import { BetPlacedSuccess } from "./bet-placed-success";

describe("<BetPlacedSuccess />", () => {
  test("announces the success message in a status region", () => {
    render(<BetPlacedSuccess message="Bet placed — good luck!" />);
    const status = screen.getByRole("status");
    expect(status).toHaveTextContent("Bet placed — good luck!");
    expect(status).toHaveAttribute("data-testid", "bet-success");
  });
});

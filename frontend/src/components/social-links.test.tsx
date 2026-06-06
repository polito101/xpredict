import { describe, expect, test } from "vitest";
import { render, screen } from "@testing-library/react";

import { SocialLinks } from "./social-links";

describe("<SocialLinks />", () => {
  test("renders the three official XPrediction socials with correct hrefs", () => {
    render(<SocialLinks />);

    expect(screen.getByLabelText("XPrediction on LinkedIn")).toHaveAttribute(
      "href",
      "https://www.linkedin.com/company/xprediction/",
    );
    expect(screen.getByLabelText("XPrediction on Instagram")).toHaveAttribute(
      "href",
      "https://www.instagram.com/xprediction10/",
    );
    expect(screen.getByLabelText("XPrediction on YouTube")).toHaveAttribute(
      "href",
      "https://www.youtube.com/@Xprediction-v8v",
    );
  });

  test("opens each social in a new tab with a safe rel", () => {
    render(<SocialLinks />);

    for (const name of ["LinkedIn", "Instagram", "YouTube"]) {
      const link = screen.getByLabelText(`XPrediction on ${name}`);
      expect(link).toHaveAttribute("target", "_blank");
      expect(link).toHaveAttribute("rel", "noopener noreferrer");
    }
  });

  test("exposes an accessible group label and forwards className", () => {
    const { container } = render(<SocialLinks className="custom-cls" />);
    const nav = screen.getByRole("navigation", {
      name: "XPrediction on social media",
    });
    expect(nav).toBeInTheDocument();
    expect(container.querySelector("nav")).toHaveClass("custom-cls");
  });
});

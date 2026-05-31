/**
 * Plan 10-03 Task 1 (Wave 0 — RED) — BrandingForm behavior contract.
 *
 * These tests are written BEFORE the component exists (TDD RED). They pin the
 * four load-bearing behaviors from the plan's <behavior> block against the
 * EXACT 10-UI-SPEC copy:
 *
 *   1. Pre-fill: initial brand name + both hexes render; each ColorField shows
 *      a live swatch reflecting the typed/initial value.
 *   2. Invalid hex blocks submit: typing "red" and submitting shows the inline
 *      FormMessage "Enter a valid hex color, e.g. #4F46E5." and does NOT call
 *      the PUT action.
 *   3. Valid submit: calls the mocked updateTenantConfig once with the form
 *      values, then fires the success toast copy on resolve.
 *   4. Logo: a selected file shows an <img> preview; an oversize file shows
 *      "Logo must be 256 KB or smaller." and a bad-type file shows
 *      "Logo must be a PNG, JPEG, WebP, or SVG file." (client pre-check).
 *
 * The `"use server"` PUT helper is mocked so NO network call occurs. The
 * server is authoritative on validation (D-09); the client mirror is UX-only.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

// jsdom has no URL.createObjectURL — the LogoUploadField object-URL preview
// needs it. Stub a deterministic blob URL so the <img src> assertion is stable.
beforeEach(() => {
  if (!("createObjectURL" in URL)) {
    Object.defineProperty(URL, "createObjectURL", { configurable: true, value: () => {} });
  }
  vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:branding-preview");
  if (!("revokeObjectURL" in URL)) {
    Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: () => {} });
  }
  vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
});

// Mock the use-server PUT helper so the form never hits the network. Each test
// sets its resolved/rejected value.
const updateTenantConfig = vi.fn();
vi.mock("@/lib/branding-admin-api", () => ({
  updateTenantConfig: (input: unknown) => updateTenantConfig(input),
}));

// Mock sonner so success/failure toasts are deterministically assertable.
const toastSuccess = vi.fn();
const toastError = vi.fn();
vi.mock("sonner", () => ({
  toast: {
    success: (msg: string) => toastSuccess(msg),
    error: (msg: string) => toastError(msg),
  },
}));

import { BrandingForm } from "@/components/admin/branding-form";
import type { TenantConfigRead } from "@/lib/branding-types";

const INITIAL: TenantConfigRead = {
  brand_name: "XPredict",
  primary_hex: "#4f46e5",
  secondary_hex: "#0ea5e9",
  logo_url: null,
};

function renderForm(initial: TenantConfigRead = INITIAL) {
  return render(<BrandingForm initial={initial} />);
}

describe("<BrandingForm />", () => {
  beforeEach(() => {
    updateTenantConfig.mockReset();
    toastSuccess.mockReset();
    toastError.mockReset();
  });

  it("pre-fills the brand name + both hexes and shows a live swatch per color field", () => {
    renderForm();

    expect(screen.getByLabelText("Brand name")).toHaveValue("XPredict");
    expect(screen.getByLabelText("Primary color")).toHaveValue("#4f46e5");
    expect(screen.getByLabelText("Secondary color")).toHaveValue("#0ea5e9");

    // Each ColorField renders a swatch whose background reflects the value.
    const primarySwatch = screen.getByTestId("color-swatch-primary_hex");
    const secondarySwatch = screen.getByTestId("color-swatch-secondary_hex");
    expect(primarySwatch).toHaveStyle({ backgroundColor: "#4f46e5" });
    expect(secondarySwatch).toHaveStyle({ backgroundColor: "#0ea5e9" });
  });

  it("the swatch updates live as the admin types a valid hex", async () => {
    const user = userEvent.setup();
    renderForm();

    const primary = screen.getByLabelText("Primary color");
    await user.clear(primary);
    await user.type(primary, "#112233");

    expect(screen.getByTestId("color-swatch-primary_hex")).toHaveStyle({
      backgroundColor: "#112233",
    });
  });

  it("an invalid hex shows the inline FormMessage and does NOT call the PUT action", async () => {
    const user = userEvent.setup();
    updateTenantConfig.mockResolvedValue({});
    renderForm();

    const primary = screen.getByLabelText("Primary color");
    await user.clear(primary);
    await user.type(primary, "red");
    await user.click(screen.getByRole("button", { name: "Save branding" }));

    expect(
      await screen.findByText("Enter a valid hex color, e.g. #4F46E5."),
    ).toBeInTheDocument();
    expect(updateTenantConfig).not.toHaveBeenCalled();
  });

  it("a valid submit calls updateTenantConfig once and fires the success toast", async () => {
    const user = userEvent.setup();
    updateTenantConfig.mockResolvedValue({});
    renderForm();

    const name = screen.getByLabelText("Brand name");
    await user.clear(name);
    await user.type(name, "Acme Markets");
    await user.click(screen.getByRole("button", { name: "Save branding" }));

    expect(updateTenantConfig).toHaveBeenCalledTimes(1);
    expect(updateTenantConfig).toHaveBeenCalledWith(
      expect.objectContaining({
        brand_name: "Acme Markets",
        primary_hex: "#4f46e5",
        secondary_hex: "#0ea5e9",
      }),
    );
    await vi.waitFor(() =>
      expect(toastSuccess).toHaveBeenCalledWith(
        "Branding updated. Players see it on their next page load.",
      ),
    );
  });

  it("selecting a valid logo shows an <img> preview", async () => {
    const user = userEvent.setup();
    renderForm();

    const file = new File(["x"], "logo.png", { type: "image/png" });
    const input = screen.getByLabelText("Logo") as HTMLInputElement;
    await user.upload(input, file);

    const preview = within(screen.getByTestId("logo-preview")).getByRole("img");
    expect(preview).toHaveAttribute("src", "blob:branding-preview");
  });

  it("an oversize logo shows the size-cap inline copy (client pre-check) and blocks submit", async () => {
    const user = userEvent.setup();
    updateTenantConfig.mockResolvedValue({});
    renderForm();

    // 256 KB cap → 300 KB byte payload trips the client pre-check.
    const big = new File([new Uint8Array(300 * 1024)], "big.png", {
      type: "image/png",
    });
    const input = screen.getByLabelText("Logo") as HTMLInputElement;
    await user.upload(input, big);

    expect(
      await screen.findByText("Logo must be 256 KB or smaller."),
    ).toBeInTheDocument();
    expect(updateTenantConfig).not.toHaveBeenCalled();
  });

  it("a wrong-type logo shows the allowlist inline copy (client pre-check)", async () => {
    const user = userEvent.setup();
    renderForm();

    const bad = new File(["%PDF"], "doc.pdf", { type: "application/pdf" });
    const input = screen.getByLabelText("Logo") as HTMLInputElement;
    await user.upload(input, bad);

    expect(
      await screen.findByText("Logo must be a PNG, JPEG, WebP, or SVG file."),
    ).toBeInTheDocument();
  });
});

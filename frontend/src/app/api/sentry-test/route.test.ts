import { describe, it, expect } from "vitest";
import { GET } from "./route";

describe("/api/sentry-test", () => {
  it("throws an error for the synthetic Sentry trigger (D-29)", async () => {
    await expect(GET()).rejects.toThrow("sentry test from frontend");
  });
});

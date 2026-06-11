/**
 * `LIVEBETS_TABLES` catalog parsing (live multi-table). Server-only env (no
 * NEXT_PUBLIC) read at request time; malformed input must NEVER throw — it
 * degrades to an empty catalog so /live falls back to the single-default-table
 * flow.
 */
import { describe, it, expect, vi, afterEach } from "vitest";

import { getLiveCatalog, findLiveTable } from "@/lib/live-catalog";

const VALID = JSON.stringify([
  { slug: "cars", label: "Cars", tableId: "f90e010d-4540-42d2-8c7f-bade3543fe3e" },
  { slug: "birds", label: "Birds", tableId: "c4138d9f-6333-4d18-bc09-cffe08e2358a" },
]);

afterEach(() => {
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
});

describe("getLiveCatalog", () => {
  it("returns [] when LIVEBETS_TABLES is unset", () => {
    vi.stubEnv("LIVEBETS_TABLES", "");
    expect(getLiveCatalog()).toEqual([]);
  });

  it("parses a valid two-entry catalog in order", () => {
    vi.stubEnv("LIVEBETS_TABLES", VALID);
    expect(getLiveCatalog()).toEqual([
      { slug: "cars", label: "Cars", tableId: "f90e010d-4540-42d2-8c7f-bade3543fe3e" },
      { slug: "birds", label: "Birds", tableId: "c4138d9f-6333-4d18-bc09-cffe08e2358a" },
    ]);
  });

  it("returns [] (and warns) on invalid JSON — never throws", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    vi.stubEnv("LIVEBETS_TABLES", "{not json");
    expect(getLiveCatalog()).toEqual([]);
    expect(warn).toHaveBeenCalled();
  });

  it("returns [] when the JSON is not an array", () => {
    vi.spyOn(console, "warn").mockImplementation(() => {});
    vi.stubEnv("LIVEBETS_TABLES", JSON.stringify({ slug: "cars" }));
    expect(getLiveCatalog()).toEqual([]);
  });

  it("drops malformed entries (bad slug chars, empty label, missing tableId) and keeps valid ones", () => {
    vi.spyOn(console, "warn").mockImplementation(() => {});
    vi.stubEnv(
      "LIVEBETS_TABLES",
      JSON.stringify([
        { slug: "CARS!", label: "Bad slug", tableId: "x" },
        { slug: "ok", label: "  ", tableId: "x" },
        { slug: "ok2", label: "Ok", tableId: "" },
        { slug: "birds", label: "Birds", tableId: "t-1" },
      ]),
    );
    expect(getLiveCatalog()).toEqual([{ slug: "birds", label: "Birds", tableId: "t-1" }]);
  });

  it("keeps a valid optional tagline and drops malformed ones (entry survives)", () => {
    vi.spyOn(console, "warn").mockImplementation(() => {});
    vi.stubEnv(
      "LIVEBETS_TABLES",
      JSON.stringify([
        { slug: "cars", label: "Cars", tableId: "t-1", tagline: "  Count the cars.  " },
        { slug: "birds", label: "Birds", tableId: "t-2", tagline: 42 },
        { slug: "fish", label: "Fish", tableId: "t-3", tagline: "x".repeat(81) },
      ]),
    );
    expect(getLiveCatalog()).toEqual([
      { slug: "cars", label: "Cars", tableId: "t-1", tagline: "Count the cars." },
      { slug: "birds", label: "Birds", tableId: "t-2" },
      { slug: "fish", label: "Fish", tableId: "t-3" },
    ]);
  });

  it("drops duplicate slugs (first wins)", () => {
    vi.spyOn(console, "warn").mockImplementation(() => {});
    vi.stubEnv(
      "LIVEBETS_TABLES",
      JSON.stringify([
        { slug: "cars", label: "First", tableId: "t-1" },
        { slug: "cars", label: "Second", tableId: "t-2" },
      ]),
    );
    expect(getLiveCatalog()).toEqual([{ slug: "cars", label: "First", tableId: "t-1" }]);
  });
});

describe("findLiveTable", () => {
  it("finds an entry by slug", () => {
    vi.stubEnv("LIVEBETS_TABLES", VALID);
    expect(findLiveTable("birds")?.label).toBe("Birds");
  });

  it("returns undefined for an unknown slug", () => {
    vi.stubEnv("LIVEBETS_TABLES", VALID);
    expect(findLiveTable("nope")).toBeUndefined();
  });
});

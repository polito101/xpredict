import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    // Route handlers live in the Node runtime (no DOM); browser surface in
    // Phase 1 is hello-world only, no React-component tests yet.
    environment: "node",
    globals: true,
    include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
  },
});

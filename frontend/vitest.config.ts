import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "node:path";

// Multi-environment Vitest setup (Plan 02-04 Task 1):
//   - `.test.tsx` files run under `jsdom` (React component tests).
//   - `.test.ts` files run under `node` (Phase 1 API-route tests).
// The `environmentMatchGlobs` API lets a single config drive both.
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  test: {
    environmentMatchGlobs: [
      ["src/**/*.test.tsx", "jsdom"],
      ["src/**/*.test.ts", "node"],
    ],
    globals: true,
    include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
    setupFiles: ["./vitest.setup.ts"],
  },
});

// Vitest global setup (Plan 02-04 Task 1).
//
// Loaded by `vitest.config.ts > test.setupFiles`. Imports the jest-dom
// custom matchers (toBeInTheDocument, toHaveTextContent, ...) so any
// `*.test.tsx` running under the `jsdom` environment can use them.
//
// Safe to load under `node` env too — the matchers no-op when there is no
// DOM and the import does not touch `window` until a matcher is invoked.
import "@testing-library/jest-dom/vitest";

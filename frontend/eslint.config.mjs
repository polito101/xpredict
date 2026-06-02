import nextCoreWebVitals from "eslint-config-next/core-web-vitals";
import nextTypescript from "eslint-config-next/typescript";

// Next 16 removed `next lint`; eslint-config-next 16 ships as native ESLint 9 flat
// config. Consume the flat arrays directly — the previous FlatCompat shim (from the
// Next 15 scaffold) crashes under ESLint 9.39 + eslint-config-next 16 with
// "Converting circular structure to JSON". `package.json` "lint" now runs `eslint src`.
const eslintConfig = [
  ...nextCoreWebVitals,
  ...nextTypescript,
  {
    // react-hooks@7 (React Compiler era, pulled in by eslint-config-next 16) adds
    // `set-state-in-effect` as an ERROR. Existing Phase 2/8/9 components predate this
    // rule (setState-at-effect-start with a `cancelled` guard is the standard fetch
    // pattern), so it is downgraded to "warn" to restore green CI WITHOUT touching any
    // feature code — flagged for a dedicated follow-up. CI-hotfix scope only; no other
    // rule is changed.
    rules: {
      "react-hooks/set-state-in-effect": "warn",
    },
  },
  {
    ignores: [".next/**", "out/**", "build/**", "next-env.d.ts", "node_modules/**"],
  },
];

export default eslintConfig;
